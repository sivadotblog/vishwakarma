"""Run log committed to the PR branch: `docs/factory/issue-<N>.md`."""

import re
import shutil
from collections.abc import Mapping
from typing import Any

from vk import git
from vk.config import Config
from vk.tooling import ToolError

Data = dict[str, Any]
ROUND_HEADING = "## Review round"


def log_path(issue_number: int) -> str:
    return f"docs/factory/issue-{issue_number}.md"


def _bullets(items: list[str] | None) -> list[str]:
    return [f"- {i}" for i in items or []] or ["- None"]


def _numbered(items: list[str] | None) -> list[str]:
    return [f"{n}. {i}" for n, i in enumerate(items or [], 1)] or ["- None"]


def _implementation(impl: Data) -> list[str]:
    lines = [f"Branch `{impl.get('branch', '')}` (base `{impl.get('base', '')}`).", ""]
    lines += ["### Change summary", ""]
    lines += [f"- `{c['path']}`: {c['change']}" for c in impl.get("change_summary", [])] or [
        "- None"
    ]
    lines += ["", "### Verification", ""]
    lines += [f"- `{v['command']}`: {v['result']}" for v in impl.get("verification", [])] or [
        "- None"
    ]
    lines += ["", "### Deviations", "", *_bullets(impl.get("deviations"))]
    return lines


def _review(review: Data) -> list[str]:
    lines = [f"Verdict: **{review.get('verdict', '')}**", "", str(review.get("summary", ""))]
    lines += ["", "### Criteria results", ""]
    for c in review.get("criteria_results", []):
        mark = "pass" if c["pass"] else "fail"
        lines.append(f"- {mark}: {c['criterion']} ({c['evidence']})")
    if not review.get("criteria_results"):
        lines.append("- None")
    if review.get("blocking_findings"):
        lines += ["", "### Blocking findings", "", *_bullets(review["blocking_findings"])]
    if review.get("suggestions"):
        lines += ["", "### Suggestions", "", *_bullets(review["suggestions"])]
    return lines


def render_run_log(issue_number: int, data: Data) -> str:
    """Markdown for the first pass: summary, classification, analysis, implementation, review."""
    cls: Data = data.get("classification") or {}
    analysis: Data = data.get("analysis") or {}
    impl: Data = data.get("implementation") or {}
    review: Data = data.get("review") or {}
    passed = {c["criterion"]: c["pass"] for c in review.get("criteria_results", [])}

    out = [f"# Factory run log: issue #{issue_number}", "", "## Summary", ""]
    out += [str(cls.get("summary", "")), ""]
    if review:
        out += [f"Reviewer verdict: {review.get('verdict', '')}.", ""]
    out += ["## Classification", ""]
    out += [
        f"- {k}: {cls[k]}" for k in ("type", "priority", "complexity", "affected_area") if k in cls
    ]
    out += ["", "## Analysis", ""]
    out += ["### Problem", "", str(analysis.get("problem_statement", "")), ""]
    out += ["### Approach", "", str(analysis.get("approach", "")), ""]
    out += ["### Plan", "", *_numbered(analysis.get("plan")), ""]
    out += ["### Acceptance criteria", ""]
    criteria = analysis.get("acceptance_criteria") or []
    out += [f"- [{'x' if passed.get(c) else ' '}] {c}" for c in criteria] or ["- None"]
    out += ["", "## Implementation", "", *_implementation(impl), ""]
    out += ["## Review", "", *_review(review), ""]
    return "\n".join(out)


def render_review_round(round_no: int, data: Data) -> str:
    """One appended section: what the comment-handling round decided and re-verified."""
    impl: Data = data.get("implementation") or {}
    review: Data = data.get("review") or {}
    out = ["", f"{ROUND_HEADING} {round_no}", ""]
    if data.get("notes"):
        out += [str(data["notes"]), ""]
    if impl:
        out += ["### Changes", "", *_implementation(impl), ""]
    if review:
        out += ["### Review", "", *_review(review), ""]
    return "\n".join(out)


def _next_round(existing: str) -> int:
    return len(re.findall(rf"^{ROUND_HEADING} \d+", existing, re.MULTILINE)) + 1


def publish(
    cfg: Config,
    args: Data,
    *,
    remote_url: str | None = None,
    files: Mapping[str, str | None] | None = None,
) -> Data:
    """Commit the run log; `files` (repo path -> text, `None` deletes) ride in the same commit."""
    issue = args.get("issue_number")
    branch = args.get("branch")
    mode = args.get("mode", "write")
    if not isinstance(issue, int) or isinstance(issue, bool) or not isinstance(branch, str):
        raise ToolError("issue_number (integer) and branch (string) are required.")
    if mode not in ("write", "append"):
        raise ToolError('mode must be "write" or "append".')
    if mode == "write" and not all(
        args.get(k) for k in ("classification", "analysis", "implementation", "review")
    ):
        raise ToolError("write mode needs classification, analysis, implementation and review.")
    refusal = git.validate_branch(branch)
    if refusal:
        raise ToolError(refusal)

    repo_dir = git.clone_repo(cfg, remote_url=remote_url)
    try:
        checkout = git.checkout_branch(cfg, repo_dir, branch, remote_url=remote_url)
        if not checkout["success"]:
            raise ToolError(str(checkout["error"]))
        path = log_path(issue)
        if mode == "write":
            content = render_run_log(issue, args)
            message = f"docs: add factory run log for #{issue}"
        else:
            file = repo_dir / path
            if not file.is_file():
                raise ToolError(f"{path} does not exist on {branch}; use mode write first.")
            existing = file.read_text(encoding="utf-8")
            round_no = args.get("round") or _next_round(existing)
            content = existing.rstrip("\n") + "\n" + render_review_round(int(round_no), args)
            message = f"docs: append review round {round_no} to factory run log for #{issue}"
        try:
            sha = git.commit_files(
                repo_dir, branch, {path: content, **(files or {})}, message, cfg=cfg
            )
        except git.GitError as exc:
            raise ToolError(str(exc)) from None
        pushed = git.push_branch(cfg, repo_dir, branch, remote_url=remote_url)
        if not pushed["success"]:
            raise ToolError(str(pushed["error"]))
        return {"path": path, "sha": sha, "branch": branch}
    finally:
        shutil.rmtree(repo_dir.parent, ignore_errors=True)
