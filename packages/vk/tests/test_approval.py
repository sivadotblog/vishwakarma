"""Truth table for approval policies per caller class."""

from typing import Any

import pytest

from vk import github
from vk.approval import Caller, Decision, policy_for

UNATTENDED = Caller(unattended=True, issue_number=42, pr_number=57)
ATTENDED = Caller(unattended=False)

# (tool, args, unattended decision, attended decision)
CASES: list[tuple[str, dict[str, Any], Decision, Decision]] = [
    ("getFileContent", {"path": "a"}, "run", "run"),
    ("listReviewComments", {"pull_number": 1}, "run", "run"),
    ("getCollaboratorPermission", {"username": "alice"}, "run", "run"),
    ("addLabels", {"issue_number": 9, "labels": ["x"]}, "run", "run"),
    ("removeLabel", {"issue_number": 9, "name": "x"}, "run", "run"),
    ("ensureLabel", {"name": "vk:pr-open"}, "run", "run"),
    ("closeIssue", {"issue_number": 9}, "run", "run"),
    ("updateIssue", {"issue_number": 9, "state": "closed"}, "run", "run"),
    ("updateIssue", {"issue_number": 9, "state": "open", "state_reason": "reopened"}, "run", "run"),
    ("updateIssue", {"issue_number": 9, "title": "t"}, "deny", "run"),
    ("updateIssue", {"issue_number": 9, "state": "closed", "body": "sneaky"}, "deny", "run"),
    ("createIssue", {"title": "t"}, "deny", "run"),
    ("addAssignees", {"issue_number": 42, "assignees": ["a"]}, "deny", "run"),
    ("removeAssignees", {"issue_number": 42, "assignees": ["a"]}, "deny", "run"),
    ("requestReviewers", {"pull_number": 57, "reviewers": ["a"]}, "deny", "run"),
    ("addIssueComment", {"issue_number": 42, "body": "b"}, "run", "run"),
    ("addIssueComment", {"issue_number": 43, "body": "b"}, "deny", "run"),
    ("addIssueComment", {"body": "b"}, "deny", "run"),
    ("addPullRequestComment", {"pull_number": 57, "body": "b"}, "run", "run"),
    ("addPullRequestComment", {"pull_number": 58, "body": "b"}, "deny", "run"),
    ("replyToReviewComment", {"pull_number": 57, "comment_id": 1, "body": "b"}, "run", "run"),
    ("replyToReviewComment", {"pull_number": 58, "comment_id": 1, "body": "b"}, "deny", "run"),
    ("createPullRequest", {"title": "t", "head": "h", "draft": True}, "run", "run"),
    ("createPullRequest", {"title": "t", "head": "h", "draft": False}, "deny", "ask"),
    ("createPullRequest", {"title": "t", "head": "h"}, "deny", "ask"),
    ("createPullRequest", {"title": "t", "head": "h", "draft": "true"}, "deny", "ask"),
    ("updatePullRequest", {"pull_number": 57, "draft": False}, "deny", "ask"),
    ("updatePullRequest", {"pull_number": 57, "title": "t"}, "deny", "ask"),
    ("someFutureTool", {}, "deny", "ask"),
]


@pytest.mark.parametrize(("tool", "args", "unattended", "attended"), CASES)
def test_truth_table(
    tool: str, args: dict[str, Any], unattended: Decision, attended: Decision
) -> None:
    assert policy_for(tool, args, UNATTENDED) == unattended
    assert policy_for(f"github__{tool}", args, ATTENDED) == attended


def test_unattended_without_stamps_cannot_comment() -> None:
    bare = Caller(unattended=True, issue_number=None, pr_number=None)
    assert policy_for("addIssueComment", {"issue_number": 1}, bare) == "deny"
    assert policy_for("addPullRequestComment", {"pull_number": 1}, bare) == "deny"


def test_no_merge_or_push_surface() -> None:
    names = {t.name for t in github.github_tools(github.GitHub.__new__(github.GitHub), ATTENDED)}
    assert not {n for n in names if "merge" in n.lower() or "push" in n.lower()}
    assert "github__createPullRequest" in names
