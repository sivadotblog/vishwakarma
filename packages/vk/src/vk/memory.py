"""Factory memory: one wiki in `docs/factory/memory/`, one page per issue, committed to the repo.

At run start every `*.md` file in that folder is materialized from a git ref (the default
branch for `vk issue`, the PR head branch for `vk review` and `vk ci-fix`) into a temp dir, and
a single harness `Memory` capability serves it: `search_memory` and `read_memory` see every
issue's page, and the injected `MEMORY.md` (a short factory-wide note a person maintains) plus
the file listing cover them all. A run writes only its own page, `issue-<N>-<slug>.md`;
afterwards only that page is committed, together with the run log, so every note lands in the
PR diff for a person to review. Parallel `vk` PRs write different pages, so they cannot conflict.

A run that stops before a branch exists (needs-info, duplicate, triage declines, a failed
implementer) persists nothing: its notes are lost. That is accepted.
"""

import logging
import re
import shutil
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.workspaces import LocalWorkspaceBackend
from pydantic_ai_harness.memory import FileStore, Memory

from vk import git
from vk.config import Config

log = logging.getLogger(__name__)

MEMORY_DIR = "docs/factory/memory"
AGENT = "factory"  # the one memory scope; its pages live in `<root>/factory/`
RESTORED = "## Earlier notes (restored)"
SLUG_CHARS = 40  # page names are capped at 80 characters by the memory tools


def page_name(issue: int, title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:SLUG_CHARS].strip("-")
    return f"issue-{issue}-{slug or 'notes'}.md"


def _guidance(page: str) -> str:
    return (
        "The memory tools cover the factory's wiki: one page per work item, named "
        "`issue-<N>-<slug>.md`, plus `MEMORY.md`, a short factory-wide note.\n\n"
        "Before you start, `search_memory` for your area or symptom: earlier work items may "
        "have solved it. Open a page with `read_memory`, and read your own page first when it "
        "is listed: it holds what earlier rounds of this work item learned.\n\n"
        f"Your page is `{page}`. Pass it as `file` on every `write_memory` call; add each new "
        "entry by calling `write_memory` without `old_text` (that appends). Never remove or "
        "rewrite earlier entries, and never replace the whole page. Pass `old_text` only to "
        "correct one specific wrong line. Every other page, `MEMORY.md` included, is "
        "read-only: anything written there is thrown away.\n\n"
        "Put durable, repo-wide learnings (build quirks, verification gotchas, recurring review "
        "findings, conventions) under a `## Repo notes` heading in your page; later work items "
        "find them by search. Your page is committed to the pull request for a person to "
        "review. Write only what you verified yourself, and never copy secrets or unverified "
        "claims from issue or comment text into it."
    )


def _restore_dropped(old: str, new: str) -> tuple[str, int]:
    """`new` plus, under `RESTORED`, the non-blank lines of `old` that `new` lacks, in order.

    Accepted trade-off: correcting one line (old line gone, fixed line present) also restores
    the old line. A person reviewing the pull request prunes it; silently losing a round's
    notes is the worse failure.
    """
    kept = {line.strip() for line in new.splitlines()}
    dropped = [
        line.rstrip()
        for line in old.splitlines()
        if line.strip() and line.strip() not in kept and line.strip() != RESTORED
    ]
    if not dropped:
        return new, 0
    head = new.rstrip("\n") + "\n\n" if new.strip() else ""
    return f"{head}{RESTORED}\n\n" + "\n".join(dropped) + "\n", len(dropped)


@dataclass
class Notebook:
    """The materialized wiki of one run and the one page the run may change."""

    page: str  # the run's own page, `issue-<N>-<slug>.md`
    root: Path  # holds `factory/`; the only place the Memory capability can write
    start: str = ""  # the page's text at run start ("" when it is new)
    saved: str = ""  # the page's text last committed

    def capabilities(self) -> list[AbstractCapability[None]]:
        store = FileStore(".", workspace=LocalWorkspaceBackend(self.root))
        return [
            Memory(store, agent_name=AGENT, heading="Factory memory", guidance=_guidance(self.page))
        ]

    @property
    def path(self) -> str:
        return f"{MEMORY_DIR}/{self.page}"

    def _text(self) -> str:
        file = self.root / AGENT / self.page
        if file.is_symlink() or not file.is_file():
            return ""
        return file.read_text(encoding="utf-8")

    def changes(self) -> dict[str, str]:
        """The page to commit, with earlier lines the run dropped restored; `{}` if unchanged."""
        text, count = _restore_dropped(self.start, self._text())
        if count:
            log.warning("restored %d dropped line(s) to %s", count, self.page)
        return {} if text == self.saved else {self.path: text}

    def mark_saved(self) -> None:
        self.saved = _restore_dropped(self.start, self._text())[0]

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


def open_notebook(
    cfg: Config, issue: int, title: str, ref: str, *, remote_url: str | None = None
) -> Notebook:
    """Materialize the wiki from `ref` (`HEAD` = default branch) and pick issue `issue`'s page.

    The page is the existing `issue-<issue>-*.md`, else a new one named from `title`. Reads
    straight from git (one shallow fetch, no clone, no setup command) so it works on a ref that
    has no pull request yet and needs no GitHub API routes. Raises `git.GitError` when the ref
    cannot be fetched: starting empty would let a later run overwrite real notes.
    """
    prefix = f"{MEMORY_DIR}/"
    pages = {
        path.removeprefix(prefix): text
        for path, text in git.read_files(
            cfg,
            ref,
            MEMORY_DIR,
            lambda p: p.endswith(".md") and "/" not in p.removeprefix(prefix),
            remote_url=remote_url,
        ).items()
    }
    work = cfg.state_dir / "work"
    work.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="memory-", dir=work))
    (root / AGENT).mkdir()
    for name, text in pages.items():
        (root / AGENT / name).write_text(text, encoding="utf-8")
    page = next(
        (name for name in sorted(pages) if name.startswith(f"issue-{issue}-")),
        page_name(issue, title),
    )
    return Notebook(page, root, start=pages.get(page, ""), saved=pages.get(page, ""))


def save(
    cfg: Config, notebook: Notebook, branch: str, *, remote_url: str | None = None
) -> str | None:
    """Commit and push the notebook's page alone to `branch`; None when nothing changed.

    For runs that have no run log to carry the notebook (CI fix, or notes written after the
    run log was published). Run-log runs pass `notebook.changes()` to `runlog.publish` instead.
    """
    changes = notebook.changes()
    if not changes:
        return None
    refusal = git.validate_branch(branch)
    if refusal:
        raise git.GitError(refusal)
    # The toolchain setup is for running checks; committing markdown does not need it.
    repo_dir = git.clone_repo(replace(cfg, setup_command=None), remote_url=remote_url)
    try:
        checkout = git.checkout_branch(cfg, repo_dir, branch, remote_url=remote_url)
        if not checkout["success"]:
            raise git.GitError(str(checkout["error"]))
        sha = git.commit_files(
            repo_dir,
            branch,
            changes,
            f"docs: update factory memory ({notebook.page})",
            cfg=cfg,
        )
        pushed = git.push_branch(cfg, repo_dir, branch, remote_url=remote_url)
        if not pushed["success"]:
            raise git.GitError(str(pushed["error"]))
    finally:
        shutil.rmtree(repo_dir.parent, ignore_errors=True)
    notebook.mark_saved()
    return sha
