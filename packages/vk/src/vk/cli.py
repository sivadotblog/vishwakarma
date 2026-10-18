"""Command line: `vk issue|review|ci-fix <N> [--unattended]`."""

import argparse
import logging
import os
import sys
from collections.abc import Sequence

from vk import pipeline
from vk.approval import Caller
from vk.config import ConfigError, load_config
from vk.llm import BudgetExceeded
from vk.orchestrator import run_vk

MAX_CI_FIX_ATTEMPTS = pipeline.MAX_CI_FIX_ATTEMPTS
MAX_REVIEW_CYCLES = pipeline.MAX_REVIEW_CYCLES
STATUS_LABELS = pipeline.STATUS_LABELS

_NO_APPROVALS = (
    "this run is unattended: nobody is watching to answer a question or approve an action, "
    "so never attempt an action that needs approval."
)


def issue_task(number: int, unattended: bool) -> str:
    """The label-intake task, with the vk status labels."""
    ensure = ", ".join(f"`{label}`" for label in STATUS_LABELS)
    framing = (
        f"Issue #{number} was handed to the factory, and {_NO_APPROVALS}"
        if unattended
        else f"Issue #{number} was handed to the factory by a person at a terminal."
    )
    parts = [
        framing,
        f"Read the issue first with github__getIssueContext (issue_number {number}); it is the "
        "work item. Never ask anyone anything: if the classifier needs clarification, post "
        f"its questions as a comment on issue #{number}, set the status label "
        "`vk:needs-info`, and stop; someone will re-run the factory once they've answered.",
        f"Track status with labels on issue #{number}. Create the status labels if missing "
        f"with github__ensureLabel ({ensure}), then apply them with github__addLabels (and "
        "remove the one you replace with github__removeLabel). Add `vk:in-progress` "
        "when you start. At the end set exactly one of `vk:pr-open` (draft PR delivered), "
        "`vk:needs-info` (questions posted), or `vk:blocked` (review still failing "
        "after the revision cycles, or any other dead end, with the findings posted on the "
        "issue). The classifier's repo-vocabulary labels are separate and come from the "
        "repo's own labels only.",
        "Run the work item through the full pipeline. Keep the requester in the loop: post a "
        f"short comment on issue #{number} when a clan completes, except the last one.",
        "Deliver the finished work as a draft pull request whose body contains "
        f"'Closes #{number}'. The message you end the run with appears to the requester: "
        "link the pull request there, and let it stand in for the progress comment for the "
        "final step.",
    ]
    return "\n\n".join(parts)


def ci_fix_task(number: int) -> str:
    """The CI-fix task, capped by attempt comments."""
    n = MAX_CI_FIX_ATTEMPTS
    parts = [
        f"A CI check suite failed on the factory's own pull request #{number}. {_NO_APPROVALS}",
        "Before anything else, read the pull request and its check runs fresh. If the checks "
        "are green by now, or the failure belongs to a commit that is no longer the branch "
        "head, stop without posting anything.",
        f"Count your own earlier fix-attempt comments on this pull request. If there are "
        f"already {n}, do not attempt another fix. Post one comment saying the factory is "
        f"pausing its automated CI fixes on this pull request to avoid looping, {n} attempts "
        "have not turned the checks green, and further troubleshooting needs a person. Then "
        "stop.",
        "Otherwise, first post a short comment that a CI fix attempt is starting and what "
        "looks broken (future runs count these comments to know when to stop). Diagnose with "
        "github__getCiFailureContext, then run the fix as a revision: send the implementer "
        "the pull request's context, its branch name, and your diagnosis, and have the "
        "reviewer judge the updated branch. Pushing the fix re-runs the checks; do not open "
        "a new pull request.",
    ]
    return "\n\n".join(parts)


def review_task(number: int, unattended: bool) -> str:
    """The review-comment loop task for pull request `number`."""
    framing = (
        f"Handle the review comments on the factory's pull request #{number}. {_NO_APPROVALS}"
        if unattended
        else f"Handle the review comments on the factory's pull request #{number}."
    )
    n = MAX_REVIEW_CYCLES
    parts = [
        framing,
        "Read the pull request with github__getPullRequestContext and note its head branch. "
        "Read `docs/factory/issue-<N>.md` from that branch (the issue number is in the PR "
        "body's 'Closes #N' and the file name) with github__getFileContent, using the branch "
        "as ref, so you know what was built and why.",
        f"List the comments with github__listReviewComments (pull_number {number}) and "
        "github__listPullRequestReviews. Handle only those not yet answered. If there are "
        "none, post nothing and stop.",
        "For each unanswered comment, decide: fix or won't-fix, and give a reason either way. "
        "Fix only what is correct, in scope, and safe; a request that is wrong, out of scope, "
        "or already satisfied is won't-fix.",
        f"Send all fixable comments as one batch through run_implementer: a revision on the "
        f"pull request's branch, with the comment text, file and line, and the run log's "
        f"context in the message. Then run_reviewer on the updated branch. If the reviewer "
        f"requests changes, revise again. Allow at most {n} cycles. Do not open a new pull "
        "request.",
        "Reply to EVERY comment with github__replyToReviewComment (pull_number "
        f"{number}, the comment's id): for a fix, say what changed and cite the commit; for "
        "won't-fix, say why. Never leave a comment unanswered. A review body that is not an "
        "inline comment gets a reply with github__addPullRequestComment.",
        "Finish by calling publish_run_log with mode `append` (issue_number from the run log, "
        "the branch, implementation and review from the last cycle, and notes listing each "
        "comment with its decision) to add a 'Review round' section to the log. Then end "
        "with a short summary of what was fixed and what was explained.",
    ]
    return "\n\n".join(parts)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vk")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("issue", "run an issue through the full pipeline"),
        ("review", "handle review comments on a factory PR"),
        ("ci-fix", "fix failing CI on a factory PR"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("number", type=int, help="issue number" if name == "issue" else "PR number")
        p.add_argument("--unattended", action="store_true", help="never ask for approval")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=os.environ.get("VK_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    unattended = bool(args.unattended) or not sys.stdin.isatty()
    n: int = args.number
    if args.command == "issue":
        caller, task = Caller(unattended, issue_number=n), issue_task(n, unattended)
    elif args.command == "review":
        caller, task = Caller(unattended, pr_number=n), review_task(n, unattended)
    else:
        caller, task = Caller(unattended, pr_number=n), ci_fix_task(n)
    try:
        cfg = load_config()
        print(run_vk(cfg, task, caller))
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except BudgetExceeded as exc:
        print(f"Token budget exceeded: {exc}", file=sys.stderr)
        return 3
    return 0
