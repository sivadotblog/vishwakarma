"""End-to-end CI-fix pipeline: per-agent FunctionModels + fake GitHub + local bare git remote."""

import copy
from pathlib import Path
from typing import Any

from vk.approval import Caller
from vk.ci_fix import ATTEMPT_MARKER, PAUSE_MARKER, run_ci_fix
from vk.config import Config
from vk.github import GitHub
from vk.pipeline import MAX_CI_FIX_ATTEMPTS, MAX_REVIEW_CYCLES

from .helpers import (
    BRANCH,
    IMPL,
    REVIEW,
    Call,
    FakeSession,
    PrSession,
    branch_sha,
    clan_models,
    seed_branch,
    sh,
)
from .test_pr_review import CHANGES, no_model, revisions, writes

CALLER = Caller(True, pr_number=9)
PR_COMMENTS = "/issues/9/comments"
PAGE_PATH = "docs/factory/memory/issue-7-send-reset-emails-once.md"
PAGE = "issue-7-send-reset-emails-once.md"
DIAGNOSIS = {
    "summary": "The lint check failed.",
    "likely_cause": "An unused import in a.py.",
    "fix_instructions": "Remove the unused import from a.py.",
}


def attempt_comment(user: str = "vk-bot", marker: str = ATTEMPT_MARKER) -> Any:
    return {"user": {"login": user}, "body": f"{marker}\nEarlier note."}


def routes(
    sha: str, conclusion: str = "failure", comments: list[Any] | None = None
) -> dict[tuple[str, str], Any]:
    pr = {
        "title": "Send reset emails once",
        "body": "Dedupes the send.\n\nCloses #7\n",
        "head": {"ref": BRANCH, "sha": sha},
        "base": {"ref": "main"},
    }
    run = {
        "id": 5,
        "name": "lint",
        "conclusion": conclusion,
        "html_url": "https://example.com/5",
        "output": {"summary": "1 error"},
    }
    return {
        ("GET", "/user"): {"login": "vk-bot"},
        ("GET", "/repos/o/r/pulls/9"): copy.deepcopy(pr),
        ("GET", "/repos/o/r/issues/9/comments"): comments or [],
        ("GET", "/repos/o/r/pulls/9/reviews"): [],
        ("GET", f"/repos/o/r/commits/{sha}/check-runs"): {"check_runs": [run]},
        ("GET", "/repos/o/r/check-runs/5/annotations"): [],
        ("GET", "/repos/o/r/actions/jobs/5/logs"): "ruff: F401 unused import in a.py",
    }


def go(cfg: Config, remote: Path, models: Any, session: FakeSession) -> str:
    return run_ci_fix(
        cfg,
        GitHub(cfg, session),
        9,
        CALLER,
        confirm=lambda _prompt: True,
        model=models,
        remote_url=f"file://{remote}",
    )


def test_green_checks_end_the_run_without_posting(cfg: Config, remote: Path) -> None:
    session = FakeSession(routes("a" * 40, conclusion="success"))

    summary = go(cfg, remote, no_model, session)

    assert "nothing to do" in summary
    assert not writes(session)


def test_a_failure_on_an_old_head_is_ignored(cfg: Config, remote: Path) -> None:
    old, head = "a" * 40, "b" * 40
    # The only failing runs belong to `old`; the PR has since moved to `head`, which is green.
    session = FakeSession({**routes(old), **routes(head, conclusion="success")})

    summary = go(cfg, remote, no_model, session)

    assert "nothing to do" in summary
    assert not writes(session)
    assert not any(old in path for _m, path, _b in session.calls)


def test_at_the_attempt_cap_one_pause_comment_is_posted_and_not_repeated(
    cfg: Config, remote: Path
) -> None:
    sha = "a" * 40
    earlier = [attempt_comment() for _ in range(MAX_CI_FIX_ATTEMPTS)]
    session = FakeSession(routes(sha, comments=earlier))

    summary = go(cfg, remote, no_model, session)

    (pause,) = session.posts(PR_COMMENTS)
    assert pause["body"].startswith(PAUSE_MARKER) and "pausing" in pause["body"]
    assert "paused" in summary

    paused = [*earlier, {"user": {"login": "vk-bot"}, **pause}]
    again = FakeSession(routes(sha, comments=paused))
    go(cfg, remote, no_model, again)

    assert not writes(again)


def test_an_attempt_is_announced_diagnosed_fixed_and_reported(
    cfg: Config, remote: Path, tmp_path: Path
) -> None:
    seed_branch(remote, tmp_path)
    before = branch_sha(remote)
    calls: list[Call] = []
    models = clan_models(
        calls=calls,
        ci_diagnoser=[[("submit", DIAGNOSIS)]],
        implementer=revisions(0),
        reviewer=[[("submit", REVIEW)]],
    )
    # One attempt already on record, and an attempt marker from someone else that must not count.
    earlier = [attempt_comment(), attempt_comment(user="alice")]
    session = PrSession(routes(before, comments=earlier), remote)

    summary = go(cfg, remote, models, session)

    assert [c.agent for c in calls] == ["ci_diagnoser", "implementer", "reviewer"]
    diagnoser = calls[0]
    assert diagnoser.tools == []  # the failure context is in its message
    assert "CI diagnoser" in diagnoser.instructions and "How you write" in diagnoser.instructions
    assert "ruff: F401 unused import in a.py" in diagnoser.prompt
    assert "Remove the unused import from a.py." in calls[1].prompt and BRANCH in calls[1].prompt
    assert "Remove the unused import from a.py." in calls[2].prompt

    announced, outcome = (p["body"] for p in session.posts(PR_COMMENTS))
    assert announced.startswith(ATTEMPT_MARKER)
    assert f"attempt 2 of {MAX_CI_FIX_ATTEMPTS}" in announced and "`lint`" in announced
    assert "Pushed a CI fix" in outcome and branch_sha(remote)[:7] in outcome
    assert branch_sha(remote) != before
    assert sh("git", "--git-dir", str(remote), "show", f"{BRANCH}:fix.txt") == "fixed"
    assert "Pushed a CI fix" in summary


def test_a_fix_the_reviewer_does_not_approve_is_reported_with_its_findings(
    cfg: Config, remote: Path, tmp_path: Path
) -> None:
    seed_branch(remote, tmp_path)
    models = clan_models(
        ci_diagnoser=[[("submit", DIAGNOSIS)]],
        implementer=revisions(MAX_REVIEW_CYCLES),
        reviewer=[[("submit", CHANGES)]] * (MAX_REVIEW_CYCLES + 1),
    )
    session = PrSession(routes(branch_sha(remote)), remote)

    summary = go(cfg, remote, models, session)

    outcome = session.posts(PR_COMMENTS)[-1]["body"]
    assert "reviewer still has findings" in outcome and "fix.txt: the guard is missing" in outcome
    assert "still has findings" in summary


def test_a_stage_failing_posts_an_error_after_the_attempt_comment(
    cfg: Config, remote: Path, tmp_path: Path
) -> None:
    seed_branch(remote, tmp_path)
    models = clan_models(
        ci_diagnoser=[[("submit", DIAGNOSIS)]],
        implementer=revisions(0, {**IMPL, "pushed": False, "known_limitations": ["push rejected"]}),
    )
    session = PrSession(routes(branch_sha(remote)), remote)

    summary = go(cfg, remote, models, session)

    announced, error = (p["body"] for p in session.posts(PR_COMMENTS))
    assert announced.startswith(ATTEMPT_MARKER)
    assert "implementer" in error and "push rejected" in error and "not fixed" in error
    assert "implementer" in summary


def test_notes_from_a_fix_attempt_are_committed_to_the_branch_after_the_fix(
    cfg: Config, remote: Path, tmp_path: Path
) -> None:
    seed_branch(remote, tmp_path)
    before = branch_sha(remote)
    models = clan_models(
        ci_diagnoser=[
            [("write_memory", {"content": "- lint runs on the whole tree", "file": PAGE})],
            [("submit", DIAGNOSIS)],
        ],
        implementer=revisions(0),
        reviewer=[[("submit", REVIEW)]],
    )
    session = PrSession(routes(before), remote)

    go(cfg, remote, models, session)

    git = ["git", "--git-dir", str(remote)]
    assert sh(*git, "show", "--name-only", "--format=", BRANCH).split() == [PAGE_PATH]
    assert "lint runs on the whole tree" in sh(*git, "show", f"{BRANCH}:{PAGE_PATH}")
    outcome = session.posts(PR_COMMENTS)[-1]["body"]
    assert branch_sha(remote)[:7] in outcome  # the reported head includes the notes commit
