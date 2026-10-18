"""End-to-end issue pipeline: per-agent FunctionModels + fake GitHub + local bare git remote."""

import getpass
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel

from vk.approval import Caller
from vk.config import Config
from vk.github import GitHub
from vk.pipeline import MAX_REVIEW_CYCLES, STATUS_LABELS, run_issue
from vk.tools import preference_tools

from .helpers import (
    ANALYSIS,
    BRANCH,
    CLS,
    IMPL,
    REVIEW,
    Call,
    FakeSession,
    clan_models,
    implementer_turns,
    sh,
)

ISSUE_BODY = "Users get two reset emails per request."
ISSUE = {
    "number": 7,
    "title": "Reset emails sent twice",
    "body": ISSUE_BODY,
    "user": {"login": "alice"},
    "labels": [],
}
TRIAGE = {
    "proceed": True,
    "duplicate_of": None,
    "labels": ["bug"],
    "reason": "A fresh bug report.",
    "needs_research": False,
    "research_question": "",
}
PR_BODY = {"title": "Send reset emails once", "body": "Dedupes the reset email send."}
PR_URL = "https://github.com/o/r/pull/12"
CHANGES = {
    **REVIEW,
    "verdict": "request_changes",
    "criteria_results": [{"criterion": "Only one email", "pass": False, "evidence": "still two"}],
    "blocking_findings": ["fix.txt: the guard is missing"],
    "summary": "Needs another pass.",
}
ROUTES: dict[tuple[str, str], Any] = {
    ("GET", "/repos/o/r/issues/7"): ISSUE,
    ("GET", "/repos/o/r/issues/7/comments"): [],
    ("GET", "/repos/o/r/labels"): [{"name": "bug"}, {"name": "enhancement"}],
    ("POST", "/repos/o/r/pulls"): {"number": 12, "html_url": PR_URL},
}
UNATTENDED = Caller(True, issue_number=7)
Models = Callable[[str], Model]


def implementer_runs(revisions: int = 0) -> list[Any]:
    """Turns for the first implementer run plus `revisions` revision runs."""
    turns = implementer_turns(prefix=f"git checkout -qb {BRANCH} && ")
    for _ in range(revisions):
        turns += implementer_turns(("checkout_branch", {"branch": BRANCH}))
    return turns


def happy_models(calls: list[Call], **overrides: list[Any]) -> Models:
    roles: dict[str, list[Any]] = {
        "triage": [[("submit", TRIAGE)]],
        "classifier": [[("submit", CLS)]],
        "analyst": [[("submit", ANALYSIS)]],
        "implementer": implementer_runs(),
        "reviewer": [[("submit", REVIEW)]],
        "pr_writer": [[("submit", PR_BODY)]],
    }
    return clan_models(calls=calls, **{**roles, **overrides})


def start(
    cfg: Config,
    remote: Path,
    models: Models,
    *,
    routes: dict[tuple[str, str], Any] | None = None,
    caller: Caller = UNATTENDED,
) -> tuple[str, FakeSession]:
    session = FakeSession({**ROUTES, **(routes or {})})
    reply = run_issue(
        cfg,
        GitHub(cfg, session),
        7,
        caller,
        confirm=lambda _prompt: True,
        model=models,
        remote_url=f"file://{remote}",
    )
    return reply, session


def label_events(session: FakeSession) -> list[Any]:
    """Status and triage label changes on the issue, in order; removals are `-name`."""
    events: list[Any] = []
    for method, path, body in session.calls:
        if path == "/repos/o/r/issues/7/labels" and method == "POST":
            events.append(body["labels"])
        elif method == "DELETE" and "/issues/7/labels/" in path:
            events.append("-" + path.rsplit("/", 1)[1].replace("%3A", ":"))
    return events


def comment_bodies(session: FakeSession) -> list[str]:
    return [b["body"] for b in session.posts("/issues/7/comments")]


def test_happy_path(cfg: Config, remote: Path) -> None:
    calls: list[Call] = []
    base = happy_models(calls)
    run_log_at_pr_writer: list[str] = []

    def models(name: str) -> Model:
        if name != "pr_writer":
            return base(name)

        def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            git = ["git", "--git-dir", str(remote)]
            run_log_at_pr_writer.append(sh(*git, "show", f"{BRANCH}:docs/factory/issue-7.md"))
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, PR_BODY)])

        return FunctionModel(fn)

    reply, session = start(cfg, remote, models)

    assert PR_URL in reply and "approve" in reply
    assert [c.agent for c in calls] == [
        "triage",
        "classifier",
        "analyst",
        "implementer",
        "reviewer",
    ]
    assert label_events(session) == [
        ["vk:in-progress"],
        ["bug"],
        "-vk:in-progress",
        ["vk:pr-open"],
    ]
    ensured = [b["name"] for m, p, b in session.calls if m == "POST" and p == "/repos/o/r/labels"]
    assert ensured == list(STATUS_LABELS)
    # The run log is on the branch before the pr_writer runs, so before the PR is opened.
    assert (
        "issue #7" in run_log_at_pr_writer[0] and "- [x] Only one email" in run_log_at_pr_writer[0]
    )
    pr = session.posts("/pulls")[0]
    assert pr["draft"] is True and pr["head"] == BRANCH and pr["base"] == "main"
    assert pr["title"] == PR_BODY["title"]
    assert pr["body"].endswith("Closes #7\n") and PR_BODY["body"] in pr["body"]
    assert len(comment_bodies(session)) == 2  # classification note, plan note


def test_agents_get_self_contained_messages_and_the_right_tools(cfg: Config, remote: Path) -> None:
    calls: list[Call] = []
    analysis = {**ANALYSIS, "artifact_id": "art-1"}
    models = happy_models(calls, analyst=[[("submit", analysis)]])

    start(cfg, remote, models)

    by_agent = {c.agent: c for c in calls}
    triage = by_agent["triage"]
    assert triage.tools and all(t.startswith("github__") for t in triage.tools)
    reads = {"github__getIssueContext", "github__searchIssues", "github__listLabels"}
    writes = {"github__addIssueComment", "github__addLabels", "github__createPullRequest"}
    assert reads <= set(triage.tools) and not writes & set(triage.tools)
    assert "Triaging Issues" in triage.instructions and "How you write" in triage.instructions
    assert "enhancement" in triage.prompt  # the repo's label vocabulary
    assert by_agent["pr_writer"].tools == []
    assert "How you write" in by_agent["pr_writer"].instructions
    assert "Writing Quality" in by_agent["pr_writer"].instructions
    for name in ("classifier", "analyst", "implementer", "reviewer", "pr_writer"):
        assert ISSUE_BODY in by_agent[name].prompt, name
    assert '"problem_statement": "Duplicate sends."' in by_agent["implementer"].prompt
    assert "Analysis artifact id: art-1" in by_agent["implementer"].prompt
    assert "Analysis artifact id: art-1" in by_agent["reviewer"].prompt
    assert f"`{BRANCH}`" in by_agent["reviewer"].prompt


def test_research_runs_only_when_triage_asks(cfg: Config, remote: Path) -> None:
    calls: list[Call] = []
    ask = {**TRIAGE, "needs_research": True, "research_question": "Does lib 2.0 fix the bug?"}
    research = {
        "summary": "It does.",
        "findings": [
            {
                "claim": "2.0 fixes it",
                "sources": [{"url": "https://example.com/changelog", "title": "Changelog"}],
                "confidence": "high",
                "notes": "",
            }
        ],
        "gaps": [],
        "artifact_id": "res-1",
    }
    models = happy_models(calls, triage=[[("submit", ask)]], researcher=[[("submit", research)]])

    start(cfg, remote, models)

    by_agent = {c.agent: c for c in calls}
    assert [c.agent for c in calls][2] == "researcher"
    assert "Does lib 2.0 fix the bug?" in by_agent["researcher"].prompt
    assert "2.0 fixes it" in by_agent["analyst"].prompt
    assert "Research artifact id: res-1" in by_agent["analyst"].prompt


def test_clarification_stops_after_the_classifier(cfg: Config, remote: Path) -> None:
    calls: list[Call] = []
    unclear = {**CLS, "needs_clarification": True, "questions": ["Which email template?"]}
    models = clan_models(
        calls=calls, triage=[[("submit", TRIAGE)]], classifier=[[("submit", unclear)]]
    )

    reply, session = start(cfg, remote, models)

    assert [c.agent for c in calls] == ["triage", "classifier"]
    assert label_events(session) == [
        ["vk:in-progress"],
        ["bug"],
        "-vk:in-progress",
        ["vk:needs-info"],
    ]
    assert "- Which email template?" in comment_bodies(session)[0]
    assert not session.posts("/pulls")
    assert "clarification" in reply


def test_review_failing_after_max_revisions_blocks_without_a_pr(cfg: Config, remote: Path) -> None:
    calls: list[Call] = []
    analysis = {**ANALYSIS, "artifact_id": "art-1"}
    models = happy_models(
        calls,
        analyst=[[("submit", analysis)]],
        implementer=implementer_runs(revisions=MAX_REVIEW_CYCLES),
        reviewer=[[("submit", CHANGES)]] * (MAX_REVIEW_CYCLES + 1),
    )

    reply, session = start(cfg, remote, models)

    agents = [c.agent for c in calls]
    assert agents.count("implementer") == MAX_REVIEW_CYCLES + 1
    assert agents.count("reviewer") == MAX_REVIEW_CYCLES + 1
    assert "pr_writer" not in agents and not session.posts("/pulls")
    assert label_events(session)[-2:] == ["-vk:in-progress", ["vk:blocked"]]
    final = comment_bodies(session)[-1]
    assert "fix.txt: the guard is missing" in final and "Only one email" in final
    assert BRANCH in final and "did not open a pull request" in final
    revision = [c for c in calls if c.agent == "implementer"][1].prompt
    assert BRANCH in revision and "fix.txt: the guard is missing" in revision
    assert '"change": "fix"' in revision  # the previous implementation summary
    assert "Analysis artifact id: art-1" in revision
    assert ISSUE_BODY in revision
    assert "no pull request" in reply


def test_an_unpushed_implementation_blocks_without_reaching_the_reviewer(
    cfg: Config, remote: Path
) -> None:
    calls: list[Call] = []
    unpushed = {**IMPL, "pushed": False, "known_limitations": ["push was rejected"]}
    models = happy_models(calls, implementer=[[("submit", unpushed)]])

    reply, session = start(cfg, remote, models)

    agents = [c.agent for c in calls]
    assert agents.count("implementer") == 1 and "reviewer" not in agents
    assert not session.posts("/pulls")
    assert label_events(session)[-2:] == ["-vk:in-progress", ["vk:blocked"]]
    assert "did not push" in comment_bodies(session)[-1] and "push was rejected" in reply


def test_one_revision_then_approval_opens_the_pr(cfg: Config, remote: Path) -> None:
    calls: list[Call] = []
    models = happy_models(
        calls,
        implementer=implementer_runs(revisions=1),
        reviewer=[[("submit", CHANGES)], [("submit", REVIEW)]],
    )

    reply, session = start(cfg, remote, models)

    assert PR_URL in reply and "1 revision(s)" in reply
    assert session.posts("/pulls")
    assert any("Revising" in b for b in comment_bodies(session))


def test_reject_verdict_stops_without_revising(cfg: Config, remote: Path) -> None:
    calls: list[Call] = []
    rejected = {**CHANGES, "verdict": "reject"}
    models = happy_models(calls, reviewer=[[("submit", rejected)]])

    _, session = start(cfg, remote, models)

    assert [c.agent for c in calls].count("implementer") == 1
    assert label_events(session)[-1] == ["vk:blocked"]
    assert not session.posts("/pulls")


def test_duplicate_stops_with_a_link(cfg: Config, remote: Path) -> None:
    calls: list[Call] = []
    dup = {**TRIAGE, "proceed": False, "duplicate_of": 5, "labels": ["bug"], "reason": "Same bug."}
    routes = {
        ("GET", "/repos/o/r/issues/5"): {**ISSUE, "number": 5},
        ("GET", "/repos/o/r/issues/5/comments"): [],
    }
    models = clan_models(calls=calls, triage=[[("submit", dup)]])

    reply, session = start(cfg, remote, models, routes=routes)

    assert [c.agent for c in calls] == ["triage"]
    assert "duplicate of #5" in comment_bodies(session)[0]
    assert label_events(session)[-1] == ["vk:needs-info"]
    assert not session.posts("/pulls")
    assert "#5" in reply


def test_unknown_duplicate_number_is_not_trusted(cfg: Config, remote: Path) -> None:
    calls: list[Call] = []
    invented = {**TRIAGE, "duplicate_of": 99}

    _, session = start(cfg, remote, happy_models(calls, triage=[[("submit", invented)]]))

    assert "pr_writer" in [c.agent for c in calls]  # GET issue 99 is a 404: carried on
    assert session.posts("/pulls")


def test_only_existing_non_status_labels_are_applied(cfg: Config, remote: Path) -> None:
    calls: list[Call] = []
    greedy = {**TRIAGE, "labels": ["bug", "invented", "vk:blocked", "bug"]}
    unclear = {**CLS, "needs_clarification": True, "questions": ["Why?"]}
    models = clan_models(
        calls=calls, triage=[[("submit", greedy)]], classifier=[[("submit", unclear)]]
    )

    _, session = start(cfg, remote, models)

    applied = [e for e in label_events(session) if isinstance(e, list)]
    assert applied == [["vk:in-progress"], ["bug"], ["vk:needs-info"]]


def test_stale_status_label_from_an_earlier_run_is_removed(cfg: Config, remote: Path) -> None:
    calls: list[Call] = []
    stale = {**ISSUE, "labels": [{"name": "vk:needs-info"}]}

    _, session = start(
        cfg, remote, happy_models(calls), routes={("GET", "/repos/o/r/issues/7"): stale}
    )

    assert label_events(session)[:2] == ["-vk:needs-info", ["vk:in-progress"]]


def flaky(base: Models, agent: str, failures: int) -> Models:
    """Wrap `base` so the first `failures` runs of `agent` raise."""
    left = [failures]

    def factory(name: str) -> Model:
        if name == agent and left[0] > 0:
            left[0] -= 1

            def boom(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
                raise RuntimeError("model fell over")

            return FunctionModel(boom)
        return base(name)

    return factory


def test_a_failing_clan_is_retried_once(cfg: Config, remote: Path) -> None:
    calls: list[Call] = []

    reply, session = start(cfg, remote, flaky(happy_models(calls), "classifier", 1))

    assert PR_URL in reply and session.posts("/pulls")
    assert [c.agent for c in calls].count("classifier") == 1  # the failed run never got scripted


def test_a_clan_failing_twice_blocks_the_run(cfg: Config, remote: Path) -> None:
    calls: list[Call] = []

    reply, session = start(cfg, remote, flaky(happy_models(calls), "analyst", 2))

    assert [c.agent for c in calls] == ["triage", "classifier"]
    assert label_events(session)[-2:] == ["-vk:in-progress", ["vk:blocked"]]
    assert "analyst" in comment_bodies(session)[-1] and "model fell over" in reply
    assert not session.posts("/pulls")


def test_exhausted_token_budget_is_not_retried(cfg: Config, remote: Path) -> None:
    calls: list[Call] = []
    attempts: list[int] = []

    def models(name: str) -> Model:
        if name != "classifier":
            return happy_models(calls)(name)

        def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            attempts.append(1)
            raise UsageLimitExceeded("out of tokens")

        return FunctionModel(fn)

    with pytest.raises(UsageLimitExceeded):
        start(cfg, remote, models)

    assert attempts == [1]


def test_preferences_reach_the_pr_writer_only_when_attended(cfg: Config, remote: Path) -> None:
    save = preference_tools(cfg, getpass.getuser())[1]
    save.fn({"preferences": "Keep PR bodies under 100 words."})

    attended: list[Call] = []
    start(cfg, remote, happy_models(attended), caller=Caller(False))
    unattended: list[Call] = []
    sh("git", "--git-dir", str(remote), "branch", "-D", BRANCH)
    start(cfg, remote, happy_models(unattended))

    assert "Keep PR bodies under 100 words." in attended[-1].instructions
    assert "Keep PR bodies" not in unattended[-1].instructions
