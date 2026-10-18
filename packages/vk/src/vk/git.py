"""Git operations for clans: clone, checkout, push, all against the literal GitHub URL.

The GitHub token is only ever passed per command via `git -c http.<url>.extraHeader=...`.
It is never written to `.git/config`, and every command targets the literal repo URL,
never `origin`.
"""

import base64
import logging
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path

from vk.config import Config
from vk.tooling import Tool, ToolError

log = logging.getLogger(__name__)

PROTECTED_BRANCHES = {"main", "master"}
BRANCH_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._/-]*[A-Za-z0-9])?$")
BOT_NAME = "vk[bot]"
BOT_EMAIL = "vk[bot]@users.noreply.github.com"
MAX_DETAIL = 2000

_CREDENTIAL_PATTERNS = [
    re.compile(r"\bgh[a-z]_[A-Za-z0-9_]{8,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{8,}\b"),
    re.compile(r"x-access-token:[^@\s\"']+", re.IGNORECASE),
    re.compile(r"\b(?:proxy-)?authorization\b\s*[:=][^\r\n]*", re.IGNORECASE),
    re.compile(r"\bbasic\s+[A-Za-z0-9+/=]{8,}", re.IGNORECASE),
    re.compile(r"\bbearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE),
]


class GitError(RuntimeError):
    """A git command failed; the message is already sanitized."""


def remote_url_for(cfg: Config) -> str:
    return f"https://github.com/{cfg.repo}.git"


def validate_branch(branch: str) -> str | None:
    """Refusal reason, or None when the branch may reach a git command line."""
    if not BRANCH_PATTERN.fullmatch(branch) or ".." in branch or "//" in branch:
        return f'"{branch}" is not a valid branch name.'
    if branch.startswith("refs/") or branch == "HEAD":
        return (
            f'"{branch}" is not a plain branch name. Pass the branch name without a refs/ prefix.'
        )
    if branch in PROTECTED_BRANCHES:
        return (
            f"Direct pushes to {branch} are not allowed. "
            "Push a feature branch and open a pull request."
        )
    return None


def sanitize(text: str, token: str | None = None) -> str:
    """Strip the token (raw and base64) and anything credential-shaped from `text`."""
    if token:
        b64 = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        text = text.replace(token, "[redacted]").replace(b64, "[redacted]")
    for pattern in _CREDENTIAL_PATTERNS:
        text = pattern.sub("[redacted]", text)
    return text


def _auth_args(cfg: Config, remote_url: str | None) -> list[str]:
    """`-c` args carrying the token, scoped to github.com. Empty for injected remotes."""
    if remote_url is not None:
        return []
    basic = base64.b64encode(f"x-access-token:{cfg.github_token}".encode()).decode()
    return ["-c", f"http.https://github.com/.extraHeader=Authorization: Basic {basic}"]


def _run(
    cfg: Config, args: list[str], cwd: Path | None, *, remote_url: str | None = None, auth: bool
) -> str:
    cmd = ["git", *(_auth_args(cfg, remote_url) if auth else []), *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            env=_git_env(),
            timeout=600,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git {args[0]} timed out after {exc.timeout:.0f}s.") from None
    if proc.returncode != 0:
        detail = sanitize((proc.stderr or proc.stdout).strip(), cfg.github_token)[:MAX_DETAIL]
        raise GitError(f"git {args[0]} exited {proc.returncode}: {detail}")
    return proc.stdout.strip()


def _git_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in {"GITHUB_TOKEN", "GH_TOKEN"}}
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def clone_repo(cfg: Config, dest: Path | None = None, *, remote_url: str | None = None) -> Path:
    """Fresh shallow clone into a new temp dir under `dest` (default `<state_dir>/work`).

    Sets a repo-local bot identity (`cfg.bot_name`/`bot_email`, else `BOT_NAME`/`BOT_EMAIL`)
    and runs `cfg.setup_command` inside the checkout.
    """
    parent = dest if dest is not None else cfg.state_dir / "work"
    parent.mkdir(parents=True, exist_ok=True)
    repo_dir = Path(tempfile.mkdtemp(prefix="repo-", dir=parent)) / "repo"
    url = remote_url or remote_url_for(cfg)
    log.info("git clone repo=%s dest=%s", cfg.repo, repo_dir)
    _run(
        cfg, ["clone", "--depth", "50", url, str(repo_dir)], None, remote_url=remote_url, auth=True
    )
    _run(cfg, ["config", "user.name", cfg.bot_name or BOT_NAME], repo_dir, auth=False)
    _run(cfg, ["config", "user.email", cfg.bot_email or BOT_EMAIL], repo_dir, auth=False)
    if cfg.setup_command:
        proc = subprocess.run(
            cfg.setup_command,
            shell=True,
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=False,
            env=_git_env(),
        )
        if proc.returncode != 0:
            detail = sanitize((proc.stderr or proc.stdout).strip(), cfg.github_token)[:MAX_DETAIL]
            raise GitError(f"Setup command failed (exit {proc.returncode}): {detail}")
    return repo_dir


def _head(cfg: Config, repo_dir: Path, ref: str = "HEAD") -> str:
    return _run(cfg, ["rev-parse", ref], repo_dir, auth=False)


def checkout_branch(
    cfg: Config, repo_dir: Path, branch: str, *, remote_url: str | None = None
) -> dict[str, object]:
    """Fetch an existing branch from the literal remote URL and check it out."""
    refusal = validate_branch(branch)
    if refusal:
        return {"error": refusal, "success": False}
    url = remote_url or remote_url_for(cfg)
    log.info("git checkout branch=%s", branch)
    try:
        _run(cfg, ["fetch", url, branch], repo_dir, remote_url=remote_url, auth=True)
        _run(cfg, ["checkout", "-B", branch, "FETCH_HEAD"], repo_dir, auth=False)
        return {"branch": branch, "sha": _head(cfg, repo_dir), "success": True}
    except GitError as exc:
        return {"error": str(exc), "success": False}


def push_branch(
    cfg: Config, repo_dir: Path, branch: str, *, remote_url: str | None = None
) -> dict[str, object]:
    """Push a committed local feature branch to the literal remote URL."""
    refusal = validate_branch(branch)
    if refusal:
        return {"error": refusal, "success": False}
    url = remote_url or remote_url_for(cfg)
    log.info("git push branch=%s", branch)
    try:
        _run(
            cfg,
            ["push", url, f"refs/heads/{branch}:refs/heads/{branch}"],
            repo_dir,
            remote_url=remote_url,
            auth=True,
        )
        return {"branch": branch, "sha": _head(cfg, repo_dir, branch), "success": True}
    except GitError as exc:
        return {"error": str(exc), "success": False}


def commit_files(
    repo_dir: Path,
    branch: str,
    files: Mapping[str, str | None],
    message: str,
    *,
    cfg: Config | None = None,
) -> str:
    """Write (or, for `None`, delete) `files` (repo-relative paths) on local `branch` in one commit.

    Returns the sha. Does not push. Raises `GitError` on failure or an unsafe path/branch.
    """
    refusal = validate_branch(branch)
    if refusal:
        raise GitError(refusal)
    root = repo_dir.resolve()
    targets: dict[Path, str | None] = {}
    for path, content in files.items():
        target = (root / path).resolve()
        if not target.is_relative_to(root) or ".git" in target.relative_to(root).parts:
            raise GitError(f'"{path}" is outside the repository.')
        targets[target] = content
    token = cfg.github_token if cfg else None
    log.info("git commit_files branch=%s paths=%s", branch, ",".join(files))

    def git(*args: str) -> str:
        proc = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=False, env=_git_env()
        )
        if proc.returncode != 0:
            detail = sanitize((proc.stderr or proc.stdout).strip(), token)[:MAX_DETAIL]
            raise GitError(f"git {args[0]} exited {proc.returncode}: {detail}")
        return proc.stdout.strip()

    if git("rev-parse", "--abbrev-ref", "HEAD") != branch:
        git("checkout", branch)
    for target, content in targets.items():
        if content is None:
            target.unlink(missing_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        git("add", "-A", "--", str(target.relative_to(root)))
    git("commit", "-m", message)
    return git("rev-parse", "HEAD")


def commit_file(
    repo_dir: Path, branch: str, path: str, content: str, message: str, *, cfg: Config | None = None
) -> str:
    """Write `path` (relative to the repo) on local `branch`, commit it, return the sha."""
    return commit_files(repo_dir, branch, {path: content}, message, cfg=cfg)


def read_files(
    cfg: Config,
    ref: str,
    prefix: str,
    wanted: Callable[[str], bool],
    *,
    remote_url: str | None = None,
) -> dict[str, str]:
    """Text of the files under `prefix` at `ref` on the remote that `wanted(path)` accepts.

    Fetches only that one commit (no checkout, no setup command), so it is cheap enough to
    run at the start of every run. `ref` may be a branch name or `HEAD` (the default branch).
    """
    if ref != "HEAD" and (
        not BRANCH_PATTERN.fullmatch(ref) or ".." in ref or "//" in ref or ref.startswith("refs/")
    ):
        # A read, so unlike `validate_branch` it allows main; the ref is PR-author controlled.
        raise GitError(f'"{ref}" is not a valid ref to read.')
    parent = cfg.state_dir / "work"
    parent.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="snapshot-", dir=parent))
    try:
        _run(cfg, ["init", "-q"], scratch, auth=False)
        url = remote_url or remote_url_for(cfg)
        _run(
            cfg,
            ["fetch", "-q", "--depth", "1", url, ref],
            scratch,
            remote_url=remote_url,
            auth=True,
        )
        listing = _run(
            cfg,
            ["ls-tree", "-r", "-z", "--name-only", "FETCH_HEAD", "--", prefix],
            scratch,
            auth=False,
        )
        return {
            path: _run(cfg, ["show", f"FETCH_HEAD:{path}"], scratch, auth=False)
            for path in listing.split("\0")
            if path and wanted(path)
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def git_tools(
    cfg: Config, repo_dir: Path, allow_push: bool, *, remote_url: str | None = None
) -> list[Tool]:
    """`checkout_branch` and, when `allow_push`, `push_branch` as clan tools."""
    branch_schema = {
        "type": "object",
        "properties": {"branch": {"type": "string", "minLength": 1}},
        "required": ["branch"],
        "additionalProperties": False,
    }

    def _branch(args: dict[str, object]) -> str:
        branch = args.get("branch")
        if not isinstance(branch, str) or not branch:
            raise ToolError("branch is required.")
        return branch

    tools = [
        Tool(
            name="checkout_branch",
            description=(
                "Fetch an existing branch of the factory repository and check it out in the "
                "working checkout. Use this on a revision run or when reviewing, when the "
                "message names a branch that already exists; fresh work starts from the "
                "default branch with plain git instead."
            ),
            parameters=branch_schema,
            fn=lambda a: checkout_branch(cfg, repo_dir, _branch(a), remote_url=remote_url),
        )
    ]
    if allow_push:
        tools.append(
            Tool(
                name="push_branch",
                description=(
                    "Push a local branch of the checkout to the factory repository. The branch "
                    "must already exist locally with the work committed and the checks run; "
                    "main and master are refused. After a successful push, report the branch "
                    "name in your structured output so the factory can open the pull "
                    "request."
                ),
                parameters=branch_schema,
                fn=lambda a: push_branch(cfg, repo_dir, _branch(a), remote_url=remote_url),
            )
        )
    return tools
