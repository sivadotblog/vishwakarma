"""End-to-end: scripted LLM + fake GitHub + local bare git remote."""

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import requests
from pydantic_ai import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel

from vk.approval import Caller
from vk.cli import issue_task, review_task
from vk.config import Config
from vk.github import GitHub
from vk.orchestrator import run_vk

BRANCH = "vk/bug-dedupe"
CLS = {
    "type": "bug",
    "priority": "high",
    "complexity": "small",
    "affected_area": "api",
    "actionable": True,
    "needs_clarification": False,
    "questions": [],
    "summary": "Reset emails are sent twice.",
}
ANALYSIS = {
    "problem_statement": "Duplicate sends.",
    "approach": "Dedupe.",
    "plan": ["Guard"],
    "affected_surface": ["a.py"],
    "risks": [],
    "acceptance_criteria": ["Only one email"],
    "test_strategy": "pytest",
    "assumptions": [],
    "open_questions": [],
    "artifact_id": None,
}
IMPL = {
    "branch": BRANCH,
    "base": "main",
    "pushed": True,
    "change_summary": [{"path": "fix.txt", "change": "fix"}],
    "verification": [{"command": "true", "result": "ok"}],
    "deviations": [],
    "known_limitations": [],
}
REVIEW = {
    "verdict": "approve",
    "criteria_results": [{"criterion": "Only one email", "pass": True, "evidence": "diff"}],
    "blocking_findings": [],
    "suggestions": [],
    "summary": "Fine.",
}


def sh(*args: str, cwd: Path | None = None) -> str:
    out = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True)
    return out.stdout.strip()


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


def clan_models(**roles: list[Any]) -> Callable[[str], Model]:
    """Scripted clan models: one queue of turns per clan; `submit` calls the output tool."""

    def factory(name: str) -> Model:
        turns = roles[name]

        def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            calls = turns.pop(0)
            parts = [
                ToolCallPart(info.output_tools[0].name if tool == "submit" else tool, args)
                for tool, args in calls
            ]
            return ModelResponse(parts=parts)

        return FunctionModel(fn)

    return factory


class Resp:
    def __init__(self, status: int, data: Any) -> None:
        self.status_code, self._data = status, data
        self.text, self.content = json.dumps(data), b"x"

    def json(self) -> Any:
        return self._data


class FakeSession(requests.Session):
    def __init__(self, routes: dict[tuple[str, str], Any]) -> None:
        super().__init__()
        self.routes = routes
        self.calls: list[tuple[str, str, Any]] = []

    def request(self, method: str, url: str, **kw: Any) -> Any:  # type: ignore[override]
        path = url.removeprefix("https://api.github.com")
        self.calls.append((method, path, kw.get("json")))
        if (method, path) in self.routes:
            return Resp(200, self.routes[(method, path)])
        return Resp(201, {"id": 1}) if method == "POST" else Resp(404, {"message": "Not Found"})

    def posts(self, suffix: str) -> list[Any]:
        return [body for m, p, body in self.calls if m == "POST" and p.endswith(suffix)]


@pytest.fixture
def remote(tmp_path: Path) -> Path:
    bare = tmp_path / "remote.git"
    sh("git", "init", "--bare", "-b", "main", str(bare))
    seed = tmp_path / "seed"
    sh("git", "clone", str(bare), str(seed))
    (seed / "README.md").write_text("hi\n")
    sh("git", "add", ".", cwd=seed)
    sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "init", cwd=seed)
    sh("git", "push", "origin", "HEAD:main", cwd=seed)
    return bare


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    return Config(
        repo="o/r", github_token="tok", model="m", clan_models={}, state_dir=tmp_path / "state"
    )


def run_clan_call(name: str, message: str = "go") -> tuple[str, dict[str, Any]]:
    return (f"run_{name}", {"message": message})


def implementer_turns(*first: tuple[str, dict[str, Any]], prefix: str = "") -> list[Any]:
    commit = (
        prefix
        + "echo fixed >> fix.txt && git add -A && git commit -qm fix; git branch --show-current"
    )
    return [
        [*first, ("bash", {"command": commit})],
        [("push_branch", {"branch": BRANCH})],
        [("submit", IMPL)],
    ]


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
