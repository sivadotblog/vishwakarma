"""Code-driven review pipeline: decide per comment, fix in one batch, reply to every one."""

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Literal

from vk import runlog
from vk.approval import Caller, Confirm
from vk.clans import load_prompt
from vk.config import Config
from vk.github import GitHub, GitHubError
from vk.models import Analysis, Implementation, ItemTriage
from vk.pipeline import (
    LoopResult,
    ModelFactory,
    PrOps,
    StageFailed,
    Stages,
    agent_instructions,
    artifact_line,
    dump,
    implement_and_review,
    load_notebook,
    review_findings,
    revision_section,
    section,
)
from vk.tooling import ToolError

log = logging.getLogger(__name__)

REPLY_MARKER = "<!-- vk:review-reply:{} -->"
_REPLY_ID = re.compile(r"<!-- vk:review-reply:(\d+) -->")
_CLOSES = re.compile(r"\bcloses\s+#(\d+)", re.IGNORECASE)
UNSETTLED = "I couldn't settle on a response to this one, so a person should look at it."
FIXES = ("fix_direct", "analyze")


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
    diff_hunk: str = ""

    @property
    def ref(self) -> tuple[str, int]:
        """Unique across kinds: GitHub's inline comment ids and review ids are separate spaces."""
        return (self.kind, self.id)

    @property
    def key(self) -> int:
        """The id the triager sees and answers with: reviews are negated so they never collide."""
        return self.id if self.kind == "inline" else -self.id

    @property
    def name(self) -> str:
        return f"{'review' if self.kind == 'review' else 'comment'} {self.id}"

    def label(self) -> str:
        if self.kind == "review":
            return f"Review {self.id} by @{self.author}"
        where = f" on {self.path}:{self.line}" if self.path and self.line else ""
        return f"Comment {self.id}{where} by @{self.author}"


@dataclass(frozen=True)
class Repeat:
    """An item that repeats an earlier one word for word; code answers it, no model call."""

    item: Item
    of: Item


def _unanswered(ops: PrOps, ctx: dict[str, Any]) -> tuple[list[Item], list[Repeat], int]:
    """Unanswered inline comments, then unanswered review bodies, from trusted people only.

    Anyone can comment on a public repo's PR, so words from other authors never reach an
    agent. Returns the items for the triager, the repeats of an earlier item (answered by code,
    see `_split_repeats`), and how many comments were skipped as untrusted.
    """
    me = ops.gh.me()
    trusted = ops.trusted
    skipped = 0

    def allowed(login: str, user_type: str | None, what: str) -> bool:
        nonlocal skipped
        if user_type == "Bot" or login == me:
            return False
        if trusted(login):
            return True
        log.info("ignoring %s: @%s is not a trusted collaborator", what, login)
        skipped += 1
        return False

    raw = ops.call("listReviewComments", pull_number=ops.number)
    threads: dict[int, list[dict[str, Any]]] = {}
    for c in raw:
        threads.setdefault(int(c.get("in_reply_to_id") or c["id"]), []).append(c)
    items = []
    for c in raw:
        if c["answered"]:
            continue
        if not allowed(c["user"], c.get("user_type"), f"comment {c['id']}"):
            continue
        root = int(c.get("in_reply_to_id") or c["id"])
        earlier = [  # the thread is context for the agents too, so it gets the same filter
            f"@{t['user']}: {t['body']}"
            for t in threads[root]
            if t["id"] != c["id"]
            and (t["user"] == me or (t.get("user_type") != "Bot" and trusted(t["user"])))
        ]
        items.append(
            Item(
                c["id"],
                "inline",
                c["user"],
                c["body"],
                c.get("path"),
                c.get("line"),
                "\n\n".join(earlier),
                c.get("diff_hunk") or "",
            )
        )

    answered = {int(i) for body in ops.my_comments(ctx) for i in _REPLY_ID.findall(body)}
    for r in ctx["reviews"]:
        user = r.get("user") or {}
        body = (r.get("body") or "").strip()
        if not body or r.get("state") == "APPROVED" or r["id"] in answered:
            continue
        if allowed(user.get("login", "unknown"), user.get("type"), f"review {r['id']}"):
            items.append(Item(r["id"], "review", user["login"], body))
    items, repeats = _split_repeats(items)
    return items, repeats, skipped


def _split_repeats(items: list[Item]) -> tuple[list[Item], list[Repeat]]:
    """Keep the earliest of identical items; later copies become repeats of it.

    Items are identical when the same author sent the same text (whitespace aside) as a review
    body, or as an inline comment on the same path and line.
    """
    first: dict[tuple[object, ...], Item] = {}
    keep, repeats = [], []
    for item in items:  # GitHub lists comments and reviews oldest first
        text = " ".join(item.body.split())
        where = (item.path, item.line) if item.kind == "inline" else ()
        original = first.setdefault((item.kind, item.author, *where, text), item)
        if original is item:
            keep.append(item)
        else:
            repeats.append(Repeat(item, original))
    return keep, repeats


def _render_item(item: Item) -> str:
    kind = "inline comment" if item.kind == "inline" else "review body"
    lines = [f"### Item {item.key}: {kind} by @{item.author}"]
    if item.path:
        lines.append(f"File: {item.path}" + (f", line {item.line}" if item.line else ""))
    if item.diff_hunk:
        lines += ["", "Code the comment is on (diff hunk):", "", "```diff", item.diff_hunk, "```"]
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


def _settle(items: list[Item], verdicts: list[ItemTriage]) -> dict[tuple[str, int], ItemTriage]:
    """Exactly one verdict per item: unknown ids and repeats dropped, gaps filled."""
    by_key = {i.key: i for i in items}
    settled: dict[tuple[str, int], ItemTriage] = {}
    for v in verdicts:
        if v.item_id in by_key:
            settled.setdefault(by_key[v.item_id].ref, v)
    for i in items:
        settled.setdefault(
            i.ref, ItemTriage(item_id=i.key, verdict="skip", reason=UNSETTLED, instructions="")
        )
    return settled


def _changes(impl: Implementation, path: str | None) -> str:
    entries = [c for c in impl.change_summary if c.path == path] or impl.change_summary
    return "\n".join(f"- `{c.path}`: {c.change}" for c in entries) or "- (no per-file summary)"


def _reply_text(item: Item, d: ItemTriage, loop: LoopResult | None, sha: str) -> str:
    if d.verdict not in FIXES or loop is None:
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
    items, repeats, skipped = _unanswered(ops, ctx)
    ignored = f" Ignored {skipped} from untrusted authors." if skipped else ""
    if not items:
        return f"No unanswered review comments on PR #{pr_number}; nothing to do.{ignored}"
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
    log.info("review PR #%d starting items=%d", pr_number, len(items))
    try:
        notebook = load_notebook(cfg, issue, pr.get("title", ""), head, remote_url)
        try:
            stages = Stages(cfg, model, remote_url, notebook)
            summary = _handle(
                cfg, ops, stages, pr, issue, items, repeats, log_file["content"], head, base
            )
        finally:
            notebook.close()
        summary += ignored
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
    repeats: list[Repeat],
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
    verdicts = stages.agent(
        "triager",
        list[ItemTriage],
        agent_instructions(stages.cfg, "triager", load_prompt("triager_review")),
        "\n\n".join(
            [
                *context,
                section("Changed files", _files_text(files)),
                section("Unanswered items", "\n\n".join(_render_item(i) for i in items)),
            ]
        ),
    )
    decided = _settle(items, verdicts)
    fixes = [i for i in items if decided[i.ref].verdict in FIXES]
    investigate = any(decided[i.ref].verdict == "analyze" for i in fixes)
    log.info(
        "triager fix=%d (analyze=%s) other=%d", len(fixes), investigate, len(items) - len(fixes)
    )

    loop: LoopResult | None = None
    if fixes:
        wanted = section(
            "Review comments to fix",
            "\n\n".join(
                f"{_render_item(i)}\n\n"
                + (
                    "What to change: "
                    if decided[i.ref].verdict == "fix_direct"
                    else "Investigate: "
                )
                + decided[i.ref].instructions
                for i in fixes
            ),
        )
        plan = []
        if investigate:  # the analyst reads the PR branch and plans every fix item together
            analysis = stages.clan(
                "analyst",
                "\n\n".join(
                    [
                        f"Plan the fixes for the review comments on pull request #{ops.number}.",
                        *context,
                        wanted,
                    ]
                ),
                Analysis,
                branch=head,
            )
            plan = [
                section("Analysis", dump(analysis))
                + artifact_line("Analysis", analysis.artifact_id)
            ]
        task = "\n\n".join(
            [
                f"Revise pull request #{ops.number}: address each review comment below.",
                *context,
                wanted,
                *plan,
                revision_section(head),
            ]
        )
        brief = "\n\n".join(
            [load_prompt("review_brief", number=str(ops.number)), *context, wanted, *plan]
        )
        loop = implement_and_review(stages, task, brief, branch=head)
    sha = ops.context()["pull_request"]["head"]["sha"]

    failed = 0
    posted = set()
    for item in items:
        if _post_reply(ops, item, _reply_text(item, decided[item.ref], loop, sha)):
            posted.add(item.ref)
        else:
            failed += 1
    for repeat in repeats:  # only once the item they point to has its answer
        text = f"This repeats {repeat.of.name}, answered there."
        if repeat.of.ref in posted and _post_reply(ops, repeat.item, text):
            continue
        failed += 1
    if loop and not loop.approved:
        ops.comment(
            f"The reviewer still has findings on the fix for the review comments, after "
            f"{loop.revisions} revision(s) (verdict: {loop.review.verdict}). The work is on "
            f"branch `{head}`.\n\n{loop.review.summary}\n\nUnresolved findings:\n\n"
            f"{review_findings(loop.review)}"
        )

    notes = "\n".join(
        f"- {i.label()}: {decided[i.ref].verdict}. {' '.join(decided[i.ref].reason.split())}"
        for i in items
    ) + "".join(f"\n- {r.item.label()}: repeats {r.of.name}; answered there." for r in repeats)
    args: dict[str, Any] = {"issue_number": issue, "branch": head, "mode": "append", "notes": notes}
    if loop:
        args["implementation"] = loop.implementation.model_dump(mode="json", by_alias=True)
        args["review"] = loop.review.model_dump(mode="json", by_alias=True)
    try:
        runlog.publish(cfg, args, remote_url=stages.remote_url, files=stages.notebook_changes())
    except ToolError as exc:
        raise StageFailed("run log", exc) from exc

    fixed = len(fixes) if loop and loop.approved else 0
    total = len(items) + len(repeats)
    summary = (
        f"Answered {total - failed} of {total} item(s) on PR #{ops.number}: "
        f"{fixed} fixed, {total - len(fixes)} explained"
    )
    if loop and not loop.approved:
        summary += f", {len(fixes)} fix(es) pushed but the reviewer still has findings"
    if failed:
        summary += f"; {failed} reply(ies) failed to post and stay unanswered"
    return summary + "."
