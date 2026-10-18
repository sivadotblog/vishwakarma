"""Code-driven review pipeline: decide per comment, fix in one batch, reply to every one."""

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Literal

from vk import runlog
from vk.approval import Caller, Confirm
from vk.config import Config
from vk.github import GitHub, GitHubError
from vk.models import CommentDecision, Implementation
from vk.pipeline import (
    LoopResult,
    ModelFactory,
    PrOps,
    StageFailed,
    Stages,
    agent_instructions,
    implement_and_review,
    review_findings,
    section,
)
from vk.tooling import ToolError

log = logging.getLogger(__name__)

REPLY_MARKER = "<!-- vk:review-reply:{} -->"
_REPLY_ID = re.compile(r"<!-- vk:review-reply:(\d+) -->")
_CLOSES = re.compile(r"\bcloses\s+#(\d+)", re.IGNORECASE)
UNSETTLED = "I couldn't settle on a response to this one, so a person should look at it."


@dataclass(frozen=True)
class Item:
    """One unanswered inline comment or review body."""

    id: int
    kind: Literal["inline", "review"]
    author: str
    body: str
    path: str | None = None
    line: int | None = None
    thread: str = ""

    def label(self) -> str:
        if self.kind == "review":
            return f"Review {self.id} by @{self.author}"
        where = f" on {self.path}:{self.line}" if self.path and self.line else ""
        return f"Comment {self.id}{where} by @{self.author}"


def _unanswered(ops: PrOps, ctx: dict[str, Any]) -> list[Item]:
    """Inline comments with no VK reply, then review bodies VK has not answered."""
    raw = ops.call("listReviewComments", pull_number=ops.number)
    threads: dict[int, list[dict[str, Any]]] = {}
    for c in raw:
        threads.setdefault(int(c.get("in_reply_to_id") or c["id"]), []).append(c)
    items = []
    for c in raw:
        if c["answered"]:
            continue
        root = int(c.get("in_reply_to_id") or c["id"])
        earlier = [f"@{t['user']}: {t['body']}" for t in threads[root] if t["id"] != c["id"]]
        items.append(
            Item(
                c["id"],
                "inline",
                c["user"],
                c["body"],
                c.get("path"),
                c.get("line"),
                "\n\n".join(earlier),
            )
        )

    me = ops.gh.me()
    answered = {int(i) for body in ops.my_comments(ctx) for i in _REPLY_ID.findall(body)}
    for r in ctx["reviews"]:
        user = r.get("user") or {}
        body = (r.get("body") or "").strip()
        if (
            not body
            or r.get("state") == "APPROVED"
            or user.get("type") == "Bot"
            or user.get("login") == me
            or r["id"] in answered
        ):
            continue
        items.append(Item(r["id"], "review", user.get("login", "unknown"), body))
    return items


def _render_item(item: Item) -> str:
    kind = "inline comment" if item.kind == "inline" else "review body"
    lines = [f"### Item {item.id}: {kind} by @{item.author}"]
    if item.path:
        lines.append(f"File: {item.path}" + (f", line {item.line}" if item.line else ""))
    lines += ["", item.body]
    if item.thread:
        lines += ["", "Rest of the thread:", "", item.thread]
    return "\n".join(lines)


def _files_text(files: list[dict[str, Any]]) -> str:
    return (
        "\n".join(
            f"- {f['filename']} ({f.get('status', 'modified')}, "
            f"+{f.get('additions', 0)} -{f.get('deletions', 0)})"
            for f in files
        )
        or "(none)"
    )


def _settle(items: list[Item], decisions: list[CommentDecision]) -> dict[int, CommentDecision]:
    """Exactly one decision per item: unknown ids and repeats dropped, gaps filled."""
    known = {i.id for i in items}
    settled: dict[int, CommentDecision] = {}
    for d in decisions:
        if d.comment_id in known:
            settled.setdefault(d.comment_id, d)
    for i in items:
        settled.setdefault(
            i.id,
            CommentDecision(
                comment_id=i.id, decision="wontfix", reason=UNSETTLED, fix_instructions=""
            ),
        )
    return settled


def _changes(impl: Implementation, path: str | None) -> str:
    entries = [c for c in impl.change_summary if c.path == path] or impl.change_summary
    return "\n".join(f"- `{c.path}`: {c.change}" for c in entries) or "- (no per-file summary)"


def _reply_text(item: Item, d: CommentDecision, loop: LoopResult | None, sha: str) -> str:
    if d.decision == "wontfix" or loop is None:
        return d.reason
    if loop.approved:
        changes = _changes(loop.implementation, item.path)
        return f"Fixed in `{sha[:7]}`. {d.reason}\n\nWhat changed:\n{changes}"
    return (
        f"A fix for this is on the branch (`{sha[:7]}`), but the factory's reviewer still has "
        "findings on it, so a person should check it. I listed them in a comment on the pull "
        "request."
    )


def _post_reply(ops: PrOps, item: Item, text: str) -> bool:
    try:
        if item.kind == "inline":
            ops.call("replyToReviewComment", pull_number=ops.number, comment_id=item.id, body=text)
        else:
            ops.comment(
                f"{REPLY_MARKER.format(item.id)}\nIn reply to @{item.author}'s review:\n\n{text}"
            )
    except ToolError as exc:
        log.warning("could not reply to %s: %s", item.label(), exc)
        return False
    return True


def run_review(
    cfg: Config,
    gh: GitHub,
    pr_number: int,
    caller: Caller,
    *,
    confirm: Confirm | None = None,
    model: ModelFactory | None = None,
    remote_url: str | None = None,
) -> str:
    """Answer every unanswered review comment on factory PR `pr_number`; returns a summary.

    A run with nothing unanswered makes no model call and posts nothing. `model` and
    `remote_url` are test seams.
    """
    ops = PrOps(gh, caller, confirm, pr_number)
    ctx = ops.context()
    items = _unanswered(ops, ctx)
    if not items:
        return f"No unanswered review comments on PR #{pr_number}; nothing to do."
    pr = ctx["pull_request"]
    match = _CLOSES.search(pr.get("body") or "")
    if not match:
        return (
            f"PR #{pr_number} has no 'Closes #N' in its description, so I can't find its run "
            "log and did nothing."
        )
    issue = int(match.group(1))
    head, base = pr["head"]["ref"], pr["base"]["ref"]
    try:
        log_file = ops.call("getFileContent", path=runlog.log_path(issue), ref=head)
    except GitHubError as exc:
        if exc.status != 404:
            raise
        return f"The run log {runlog.log_path(issue)} is not on branch `{head}`; I did nothing."

    started = time.monotonic()
    stages = Stages(cfg, model, remote_url)
    log.info("review PR #%d starting items=%d", pr_number, len(items))
    try:
        summary = _handle(cfg, ops, stages, pr, issue, items, log_file["content"], head, base)
    except StageFailed as exc:
        ops.comment(
            f"I hit an error in the {exc.stage} step and stopped, so the review comments above "
            f"are still open.\n\nError: {exc.__cause__}\n\nRequest a review again to retry."
        )
        summary = f"Stopped: the {exc.stage} step failed ({exc.__cause__})."
    log.info("review PR #%d finished in %.1fs", pr_number, time.monotonic() - started)
    return summary


def _handle(
    cfg: Config,
    ops: PrOps,
    stages: Stages,
    pr: dict[str, Any],
    issue: int,
    items: list[Item],
    run_log: str,
    head: str,
    base: str,
) -> str:
    files = ops.call("listPullRequestFiles", pull_number=ops.number, per_page=100)
    context = [
        f"# Pull request #{ops.number}: {pr.get('title', '')}",
        f"Head branch `{head}` at `{pr['head']['sha']}`, base `{base}`.",
        section("Run log", run_log),
    ]
    decisions = stages.agent(
        "decider",
        list[CommentDecision],
        agent_instructions(stages.cfg, "decider"),
        "\n\n".join(
            [
                *context,
                section("Changed files", _files_text(files)),
                section("Unanswered items", "\n\n".join(_render_item(i) for i in items)),
            ]
        ),
        ops.read_tools(),
    )
    decided = _settle(items, decisions)
    fixes = [i for i in items if decided[i.id].decision == "fix"]

    loop: LoopResult | None = None
    if fixes:
        wanted = section(
            "Review comments to fix",
            "\n\n".join(
                f"{_render_item(i)}\n\nWhat to change: {decided[i.id].fix_instructions}"
                for i in fixes
            ),
        )
        task = "\n\n".join(
            [
                f"Revise pull request #{ops.number}: address each review comment below.",
                *context,
                wanted,
                section(
                    "Revision requested",
                    f"The work is already on branch `{head}`. Fetch it with checkout_branch, "
                    "fix every comment above (or record in `deviations` why one should stand), "
                    "and push to the same branch.",
                ),
            ]
        )
        brief = "\n\n".join(
            [
                f"Review the changes made for pull request #{ops.number} in response to "
                "review comments. Treat each comment below as a criterion: judge whether it "
                "is addressed correctly and nothing else broke.",
                *context,
                wanted,
            ]
        )
        loop = implement_and_review(stages, task, brief, branch=head)
    sha = ops.context()["pull_request"]["head"]["sha"]

    failed = 0
    for item in items:
        if not _post_reply(ops, item, _reply_text(item, decided[item.id], loop, sha)):
            failed += 1
    if loop and not loop.approved:
        ops.comment(
            f"The reviewer still has findings on the fix for the review comments, after "
            f"{loop.revisions} revision(s) (verdict: {loop.review.verdict}). The work is on "
            f"branch `{head}`.\n\n{loop.review.summary}\n\nUnresolved findings:\n\n"
            f"{review_findings(loop.review)}"
        )

    notes = "\n".join(
        f"- {i.label()}: {decided[i.id].decision}. {' '.join(decided[i.id].reason.split())}"
        for i in items
    )
    args: dict[str, Any] = {"issue_number": issue, "branch": head, "mode": "append", "notes": notes}
    if loop:
        args["implementation"] = loop.implementation.model_dump(mode="json", by_alias=True)
        args["review"] = loop.review.model_dump(mode="json", by_alias=True)
    try:
        runlog.publish(cfg, args, remote_url=stages.remote_url)
    except ToolError as exc:
        raise StageFailed("run log", exc) from exc

    fixed = len(fixes) if loop and loop.approved else 0
    summary = (
        f"Answered {len(items) - failed} of {len(items)} item(s) on PR #{ops.number}: "
        f"{fixed} fixed, {len(items) - len(fixes)} explained"
    )
    if loop and not loop.approved:
        summary += f", {len(fixes)} fix(es) pushed but the reviewer still has findings"
    if failed:
        summary += f"; {failed} reply(ies) failed to post and stay unanswered"
    return summary + "."
