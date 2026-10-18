"""Code-driven CI-fix pipeline: count attempts, diagnose, fix as a revision, report."""

import json
import logging
import re
import time
from typing import Any

from vk import git, memory
from vk.approval import Caller, Confirm
from vk.config import Config
from vk.github import GitHub
from vk.models import CiDiagnosis
from vk.pipeline import (
    MAX_CI_FIX_ATTEMPTS,
    LoopResult,
    ModelFactory,
    PrOps,
    StageFailed,
    Stages,
    agent_instructions,
    dump,
    implement_and_review,
    load_notebook,
    review_findings,
    section,
)

log = logging.getLogger(__name__)

ATTEMPT_MARKER = "<!-- vk:ci-fix-attempt -->"
PAUSE_MARKER = "<!-- vk:ci-fix-paused -->"
_CLOSES = re.compile(r"\bcloses\s+#(\d+)", re.IGNORECASE)


def run_ci_fix(
    cfg: Config,
    gh: GitHub,
    pr_number: int,
    caller: Caller,
    *,
    confirm: Confirm | None = None,
    model: ModelFactory | None = None,
    remote_url: str | None = None,
) -> str:
    """Try to fix failing CI on factory PR `pr_number`; returns a summary.

    Green checks, or a failure that is not on the current head, end the run without a post.
    `model` and `remote_url` are test seams.
    """
    ops = PrOps(gh, caller, confirm, pr_number)
    ctx = ops.context()
    pr = ctx["pull_request"]
    sha = pr["head"]["sha"]
    failure = ops.call("getCiFailureContext", pull_number=pr_number)
    failed = failure["failed_check_runs"]
    if not failed or failure["head_sha"] != sha:
        return f"No failing checks on the current head of PR #{pr_number}; nothing to do."

    mine = ops.my_comments(ctx)
    attempts = sum(ATTEMPT_MARKER in body for body in mine)
    if attempts >= MAX_CI_FIX_ATTEMPTS:
        if any(PAUSE_MARKER in body for body in mine):
            return f"Automated CI fixes on PR #{pr_number} are already paused."
        ops.comment(
            f"{PAUSE_MARKER}\nI'm pausing my automated CI fixes on this pull request to avoid "
            f"looping. {attempts} attempts have not turned the checks green, so the rest needs "
            "a person."
        )
        return f"PR #{pr_number} hit the cap of {MAX_CI_FIX_ATTEMPTS} CI fix attempts; paused."

    names = ", ".join(f"`{run['name']}`" for run in failed)
    ops.comment(
        f"{ATTEMPT_MARKER}\nCI failed on `{sha[:7]}` ({names}). Starting fix attempt "
        f"{attempts + 1} of {MAX_CI_FIX_ATTEMPTS}."
    )
    head, base = pr["head"]["ref"], pr["base"]["ref"]
    started = time.monotonic()
    log.info("ci-fix PR #%d attempt %d", pr_number, attempts + 1)
    try:
        closes = _CLOSES.search(pr.get("body") or "")
        # Memory is per issue, so a PR that names none runs without it.
        notebook = load_notebook(cfg, int(closes.group(1)), head, remote_url) if closes else None
        try:
            stages = Stages(cfg, model, remote_url, notebook)
            summary = _attempt(cfg, ops, stages, pr, failure, head, base)
        finally:
            if notebook:
                notebook.close()
    except StageFailed as exc:
        ops.comment(
            f"I hit an error in the {exc.stage} step and stopped, so the CI failure is not "
            f"fixed.\n\nError: {exc.__cause__}"
        )
        summary = f"Stopped: the {exc.stage} step failed ({exc.__cause__})."
    log.info("ci-fix PR #%d finished in %.1fs", pr_number, time.monotonic() - started)
    return summary


def _attempt(
    cfg: Config,
    ops: PrOps,
    stages: Stages,
    pr: dict[str, Any],
    failure: dict[str, Any],
    head: str,
    base: str,
) -> str:
    context = [
        f"# Pull request #{ops.number}: {pr.get('title', '')}",
        f"Head branch `{head}`, base `{base}`.",
        pr.get("body") or "(no description)",
    ]
    diagnosis = stages.agent(
        "ci_diagnoser",
        CiDiagnosis,
        agent_instructions(cfg, "ci_diagnoser"),
        "\n\n".join([*context, section("Failed checks", json.dumps(failure, indent=2))]),
        ops.read_tools(),
    )
    findings = section("CI diagnosis", dump(diagnosis))
    task = "\n\n".join(
        [
            f"Fix the failing CI on pull request #{ops.number}.",
            *context,
            findings,
            section(
                "Revision requested",
                f"The work is already on branch `{head}`. Fetch it with checkout_branch, make "
                "the checks pass, run the repository's own checks to confirm, and push to the "
                "same branch. Do not open a new pull request.",
            ),
        ]
    )
    brief = "\n\n".join(
        [
            f"Review a fix for failing CI on pull request #{ops.number}: judge whether the "
            "change fixes the diagnosed failure without breaking anything else.",
            *context,
            findings,
        ]
    )
    loop = implement_and_review(stages, task, brief, branch=head)
    if stages.notebook:  # no run log here to carry the notes, so commit them alone
        try:
            memory.save(cfg, stages.notebook, head, remote_url=stages.remote_url)
        except git.GitError as exc:
            raise StageFailed("memory", exc) from exc
    sha = ops.context()["pull_request"]["head"]["sha"]
    ops.comment(_outcome(loop, diagnosis, head, sha))
    if loop.approved:
        return f"Pushed a CI fix to `{head}` ({sha[:7]}) for PR #{ops.number}; checks will re-run."
    return (
        f"Pushed a CI fix to `{head}` ({sha[:7]}) for PR #{ops.number}, but the reviewer still "
        "has findings; posted them."
    )


def _outcome(loop: LoopResult, diagnosis: CiDiagnosis, head: str, sha: str) -> str:
    changes = "\n".join(f"- `{c.path}`: {c.change}" for c in loop.implementation.change_summary)
    if loop.approved:
        return (
            f"Pushed a CI fix to `{head}` (`{sha[:7]}`); the checks will run again.\n\n"
            f"{diagnosis.summary}\n\nCause: {diagnosis.likely_cause}\n\nWhat changed:\n{changes}"
        )
    return (
        f"I pushed a CI fix to `{head}` (`{sha[:7]}`), but the factory's reviewer still has "
        f"findings on it after {loop.revisions} revision(s) (verdict: {loop.review.verdict}). "
        f"The checks will run again, and a person should look at this.\n\n"
        f"{diagnosis.summary}\n\n{loop.review.summary}\n\nUnresolved findings:\n\n"
        f"{review_findings(loop.review)}"
    )
