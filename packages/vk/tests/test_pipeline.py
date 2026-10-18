"""End-to-end: scripted LLM + fake GitHub + local bare git remote."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from vk.approval import Caller
from vk.cli import issue_task, review_task
from vk.config import Config
from vk.github import GitHub
from vk.orchestrator import run_vk

from .helpers import (
    ANALYSIS,
    BRANCH,
    CLS,
    IMPL,
    REVIEW,
    FakeSession,
    clan_models,
    implementer_turns,
    sh,
)


class Script:
    """Scripted orchestrator `complete`: a queue of turns for the VK agent."""

    def __init__(self, vk: list[Any]) -> None:
        self.turns = vk
        self.n = 0

    def __call__(self, **kw: Any) -> Any:
        turn = self.turns.pop(0)
        self.n += 1
        calls = None
        if isinstance(turn, list):
            calls = [
                SimpleNamespace(
                    id=f"c{self.n}-{i}",
                    function=SimpleNamespace(name=name, arguments=json.dumps(args)),
                )
                for i, (name, args) in enumerate(turn)
            ]
        msg = SimpleNamespace(content=None if calls else turn, tool_calls=calls)
        usage = SimpleNamespace(completion_tokens=1)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=usage)


def run_clan_call(name: str, message: str = "go") -> tuple[str, dict[str, Any]]:
    return (f"run_{name}", {"message": message})


def test_issue_pipeline(cfg: Config, remote: Path) -> None:
    impl = implementer_turns(prefix=f"git checkout -qb {BRANCH} && ")
    log_args = {
        "issue_number": 7,
        "branch": BRANCH,
        "mode": "write",
        "classification": CLS,
        "analysis": ANALYSIS,
        "implementation": IMPL,
        "review": REVIEW,
    }
    script = Script(
        vk=[
            [("github__ensureLabel", {"name": "vk:in-progress"})],
            [("github__addLabels", {"issue_number": 7, "labels": ["vk:in-progress", "bug"]})],
            [run_clan_call("classifier")],
            [run_clan_call("analyst")],
            [run_clan_call("implementer")],
            [run_clan_call("reviewer")],
            [("publish_run_log", log_args)],
            [
                (
                    "github__createPullRequest",
                    {
                        "title": "Fix",
                        "head": BRANCH,
                        "base": "main",
                        "draft": True,
                        "body": "Closes #7",
                    },
                )
            ],
            [("github__addLabels", {"issue_number": 7, "labels": ["vk:pr-open"]})],
            "Opened a draft PR.",
        ]
    )
    models = clan_models(
        classifier=[[("submit", CLS)]],
        analyst=[[("submit", ANALYSIS)]],
        implementer=impl,
        reviewer=[[("checkout_branch", {"branch": BRANCH})], [("submit", REVIEW)]],
    )
    session = FakeSession({})
    reply = run_vk(
        cfg,
        issue_task(7, True),
        Caller(True, issue_number=7),
        gh=GitHub(cfg, session),
        complete=script,
        clan_model=models,
        remote_url=f"file://{remote}",
    )

    assert reply == "Opened a draft PR."
    git = ["git", "--git-dir", str(remote)]
    assert sh(*git, "rev-parse", "--verify", f"refs/heads/{BRANCH}")
    log = sh(*git, "show", f"{BRANCH}:docs/factory/issue-7.md")
    assert "issue #7" in log and "- [x] Only one email" in log
    assert sh(*git, "show", f"{BRANCH}:fix.txt") == "fixed"
    pr = session.posts("/pulls")[0]
    assert pr["draft"] is True and "Closes #7" in pr["body"]
    labels = [b["labels"] for b in session.posts("/issues/7/labels")]
    assert ["vk:pr-open"] in labels and "vk:in-progress" in labels[0]


def seed_branch(remote: Path, tmp_path: Path) -> None:
    work = tmp_path / "work"
    sh("git", "clone", str(remote), str(work))
    sh("git", "checkout", "-qb", BRANCH, cwd=work)
    (work / "docs/factory").mkdir(parents=True)
    (work / "docs/factory/issue-7.md").write_text("# Factory run log: issue #7\n")
    sh("git", "add", ".", cwd=work)
    sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "log", cwd=work)
    sh("git", "push", "origin", BRANCH, cwd=work)


def test_review_pipeline(cfg: Config, remote: Path, tmp_path: Path) -> None:
    seed_branch(remote, tmp_path)
    comments = [
        {"id": 101, "user": {"login": "alice"}, "body": "Please add a guard", "path": "a.py"},
        {"id": 102, "user": {"login": "alice"}, "body": "Rename everything?", "path": "a.py"},
    ]
    session = FakeSession(
        {
            ("GET", "/user"): {"login": "bot"},
            ("GET", "/repos/o/r/pulls/9/comments"): comments,
        }
    )
    script = Script(
        vk=[
            [("github__listReviewComments", {"pull_number": 9})],
            [run_clan_call("implementer", f"fix comment 101 on {BRANCH}")],
            [run_clan_call("reviewer")],
            [
                (
                    "github__replyToReviewComment",
                    {"pull_number": 9, "comment_id": 101, "body": "Fixed in the new commit."},
                ),
                (
                    "github__replyToReviewComment",
                    {"pull_number": 9, "comment_id": 102, "body": "Won't change: out of scope."},
                ),
            ],
            [
                (
                    "publish_run_log",
                    {
                        "issue_number": 7,
                        "branch": BRANCH,
                        "mode": "append",
                        "implementation": IMPL,
                        "review": REVIEW,
                        "notes": "101 fixed, 102 explained.",
                    },
                )
            ],
            "Fixed one comment, explained one.",
        ]
    )
    models = clan_models(
        implementer=implementer_turns(("checkout_branch", {"branch": BRANCH})),
        reviewer=[[("checkout_branch", {"branch": BRANCH})], [("submit", REVIEW)]],
    )
    reply = run_vk(
        cfg,
        review_task(9, True),
        Caller(True, pr_number=9),
        gh=GitHub(cfg, session),
        complete=script,
        clan_model=models,
        remote_url=f"file://{remote}",
    )

    assert reply.startswith("Fixed one")
    git = ["git", "--git-dir", str(remote)]
    assert sh(*git, "show", f"{BRANCH}:fix.txt") == "fixed"
    log = sh(*git, "show", f"{BRANCH}:docs/factory/issue-7.md")
    assert "## Review round 1" in log and "101 fixed, 102 explained." in log
    replies = {p: b["body"] for m, p, b in session.calls if m == "POST" and p.endswith("/replies")}
    assert replies == {
        "/repos/o/r/pulls/9/comments/101/replies": "Fixed in the new commit.",
        "/repos/o/r/pulls/9/comments/102/replies": "Won't change: out of scope.",
    }
