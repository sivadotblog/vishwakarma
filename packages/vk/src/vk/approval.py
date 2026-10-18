"""Approval policies: which GitHub tool calls run, ask, or are denied.

Pure functions. `policy_for` decides whether a GitHub tool call runs, needs a
human `y/N`, or is denied outright. Reads always run; merge tools do not exist.
"""

import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

Decision = Literal["run", "ask", "deny"]
Confirm = Callable[[str], bool]

PREFIX = "github__"

# Writes an unattended run may always perform (reversible triage).
_LABEL_WRITES = {"addLabels", "removeLabel", "ensureLabel"}
# Reversible writes that attended callers run without a prompt.
_BASELINE_WRITES = {
    "createIssue",
    "updateIssue",
    "addIssueComment",
    "addAssignees",
    "removeAssignees",
    "addPullRequestComment",
    "requestReviewers",
    "replyToReviewComment",
}
_ALWAYS_RUN = _LABEL_WRITES | {"closeIssue"}
_STATE_ONLY_KEYS = {"issue_number", "state", "state_reason"}


@dataclass(frozen=True)
class Caller:
    unattended: bool
    issue_number: int | None = None  # the intake issue of an unattended run
    pr_number: int | None = None  # the PR an unattended run owns (review / ci-fix)


def _is_int(value: object, expected: int | None) -> bool:
    return expected is not None and type(value) is int and value == expected


def _ship(caller: Caller) -> Decision:
    """Shipping parks for a person; unattended runs stop at a draft PR."""
    return "deny" if caller.unattended else "ask"


def policy_for(tool_name: str, args: dict[str, Any], caller: Caller) -> Decision:
    name = tool_name.removeprefix(PREFIX)
    if name in _ALWAYS_RUN:
        return "run"
    if name == "createPullRequest":
        return "run" if args.get("draft") is True else _ship(caller)
    if name == "updatePullRequest":
        return _ship(caller)
    if name in _BASELINE_WRITES:
        if not caller.unattended:
            return "run"
        return _unattended_write(name, args, caller)
    if _is_known_read(name):
        return "run"
    # Unknown tool: fail closed.
    return "deny" if caller.unattended else "ask"


def _unattended_write(name: str, args: dict[str, Any], caller: Caller) -> Decision:
    if name == "addIssueComment":
        return "run" if _is_int(args.get("issue_number"), caller.issue_number) else "deny"
    if name in {"addPullRequestComment", "replyToReviewComment"}:
        return "run" if _is_int(args.get("pull_number"), caller.pr_number) else "deny"
    # Close/reopen is triage; a state change must not smuggle in other edits.
    if name == "updateIssue" and "state" in args and set(args) <= _STATE_ONLY_KEYS:
        return "run"
    return "deny"


READS = {
    "getRepository",
    "getRepositoryTree",
    "getFileContent",
    "searchCode",
    "listBranches",
    "listCommits",
    "getCommit",
    "compareCommits",
    "searchIssues",
    "listIssues",
    "getIssueContext",
    "listIssueComments",
    "listLabels",
    "listPullRequests",
    "getPullRequestContext",
    "listPullRequestFiles",
    "listPullRequestReviews",
    "listCheckRuns",
    "getCiFailureContext",
    "listReviewComments",
    "getCollaboratorPermission",
}


def _is_known_read(name: str) -> bool:
    return name in READS


def default_confirm(prompt: str) -> bool:
    """`y/N` on the terminal when stdin is a TTY, otherwise refuse."""
    if not sys.stdin.isatty():
        return False
    return input(f"{prompt} [y/N] ").strip().lower() in {"y", "yes"}
