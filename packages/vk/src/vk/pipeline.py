"""Code-driven issue pipeline: Python owns the control flow, agents only make judgments."""

import getpass
import json
import logging
import re
import time
from collections.abc import Callable, Collection
from dataclasses import dataclass, replace
from typing import Any

from pydantic import BaseModel
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.models import Model

from vk import agents, git, memory, runlog
from vk.approval import PREFIX, READS, Caller, Confirm
from vk.clans import load_prompt, run_clan
from vk.config import Config
from vk.github import GitHub, GitHubError, github_tools
from vk.memory import Notebook
from vk.models import (
    Analysis,
    Classification,
    Implementation,
    PrBody,
    Research,
    Review,
    Triage,
)
from vk.tooling import Tool, ToolError
from vk.tools import load_skill, preference_tools

log = logging.getLogger(__name__)

MAX_REVIEW_CYCLES = 2
MAX_CI_FIX_ATTEMPTS = 2
STATUS_LABELS = ("vk:in-progress", "vk:pr-open", "vk:needs-info", "vk:blocked")
IN_PROGRESS, PR_OPEN, NEEDS_INFO, BLOCKED = STATUS_LABELS
TRUSTED_ROLES = {"admin", "maintain", "write", "triage"}  # same bar as the workflow's check

# Triage only reads issues and labels: repository code is for the clans, from their own clone.
TRIAGE_TOOLS = frozenset(
    {"searchIssues", "listIssues", "getIssueContext", "listIssueComments", "listLabels"}
)

ModelFactory = Callable[[str], Model]


class StageFailed(Exception):
    """A stage raised twice; the run ends blocked."""

    def __init__(self, stage: str, cause: Exception) -> None:
        super().__init__(f"{stage} failed: {cause}")
        self.stage = stage


def _attempt[T](stage: str, call: Callable[[], T]) -> T:
    """Run `call`, retrying once on any failure except a spent token budget."""
    try:
        return call()
    except UsageLimitExceeded:
        raise
    except Exception as first:
        log.warning("stage %s failed, retrying once: %s", stage, first)
    try:
        return call()
    except UsageLimitExceeded:
        raise
    except Exception as exc:
        log.error("stage %s failed again: %s", stage, exc)
        raise StageFailed(stage, exc) from exc


@dataclass(frozen=True)
class Stages:
    """Runs clans and judgment agents with the shared retry rule and test seams."""

    cfg: Config
    model: ModelFactory | None = None
    remote_url: str | None = None
    notebook: Notebook | None = None  # the run's memory, attached to every agent

    def clan[T: BaseModel](self, name: str, message: str, out: type[T]) -> T:
        nb = self.notebook
        result = _attempt(
            name,
            lambda: run_clan(
                name,
                message,
                self.cfg,
                model=self.model,
                remote_url=self.remote_url,
                capabilities=nb.capabilities() if nb else (),
            ),
        )
        if not isinstance(result, out):
            raise TypeError(f"clan {name} returned {type(result).__name__}, not {out.__name__}")
        return result

    def agent[T](
        self, name: str, out: type[T], instructions: str, message: str, tools: list[Tool]
    ) -> T:
        nb = self.notebook
        return _attempt(
            name,
            lambda: agents.run_typed(
                name,
                out,
                instructions,
                message,
                tools,
                self.cfg,
                capabilities=nb.capabilities() if nb else (),
                model=self.model(name) if self.model else None,
            ),
        )

    def notebook_changes(self) -> dict[str, str]:
        """The notebook page to commit with the run log (none without a notebook)."""
        return self.notebook.changes() if self.notebook else {}


class Ops:
    """A run's GitHub reads and writes, all through the guarded `github__*` tools."""

    def __init__(self, gh: GitHub, caller: Caller, confirm: Confirm | None) -> None:
        self.gh = gh
        self._tools = {t.name: t for t in github_tools(gh, caller, confirm)}
        self._roles: dict[str, bool] = {}

    def call(self, tool: str, /, **args: Any) -> Any:
        return self._tools[PREFIX + tool].fn(args)

    def read_tools(self, only: Collection[str] | None = None) -> list[Tool]:
        """The read-only GitHub tools, or just those named in `only`."""
        return [
            t
            for t in self._tools.values()
            if (name := t.name.removeprefix(PREFIX)) in READS and (only is None or name in only)
        ]

    def trusted(self, login: str) -> bool:
        """Whether a login holds a role that may hand work to the factory; cached per run."""
        if login not in self._roles:
            role = self.call("getCollaboratorPermission", username=login)["role_name"]
            self._roles[login] = role in TRUSTED_ROLES
        return self._roles[login]


class IssueOps(Ops):
    """The intake issue's status labels and comments."""

    def __init__(self, gh: GitHub, caller: Caller, confirm: Confirm | None, number: int) -> None:
        super().__init__(gh, caller, confirm)
        self.number = number
        self.status: str | None = None

    def visible_comments(
        self, ctx: dict[str, Any], comments: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], int]:
        """The comments an agent may read, and how many were left out.

        Labeling the issue `vk` vouches for its author, not for strangers who comment later.
        So only VK's own comments, the author's, and those of trusted collaborators pass;
        other bots and everyone else are omitted.
        """
        author = (ctx["issue"].get("user") or {}).get("login")
        kept = []
        for c in comments:
            user = c.get("user") or {}
            login = user.get("login", "")
            if login == self.gh.me():
                kept.append(c)
            elif user.get("type") == "Bot":
                continue
            elif login == author or (login and self.trusted(login)):
                kept.append(c)
        return kept, len(comments) - len(kept)

    def read_tools(self, only: Collection[str] | None = None) -> list[Tool]:
        """Read tools, with this issue's comments screened wherever an agent could fetch them."""
        screened = {"getIssueContext", "listIssueComments"}
        return [
            replace(t, fn=self._screen(t)) if t.name.removeprefix(PREFIX) in screened else t
            for t in super().read_tools(only)
        ]

    def _screen(self, tool: Tool) -> Callable[[dict[str, Any]], Any]:
        def fn(args: dict[str, Any]) -> Any:
            result = tool.fn(args)
            if args.get("issue_number") != self.number:
                return result
            ctx = (
                result
                if isinstance(result, dict)
                else self.call("getIssueContext", issue_number=self.number)
            )
            comments = ctx["comments"] if isinstance(result, dict) else result
            kept, omitted = self.visible_comments(ctx, comments)
            if isinstance(result, dict):
                return {**result, "comments": kept, "omitted_comments": omitted}
            return kept

        return fn

    def comment(self, body: str) -> None:
        self.call("addIssueComment", issue_number=self.number, body=body)

    def remove_label(self, name: str) -> None:
        try:
            self.call("removeLabel", issue_number=self.number, name=name)
        except GitHubError as exc:
            if exc.status != 404:  # already gone: someone removed it by hand
                raise

    def set_status(self, label: str) -> None:
        if self.status:
            self.remove_label(self.status)
        self.call("addLabels", issue_number=self.number, labels=[label])
        self.status = label

    def issue_exists(self, number: int) -> bool:
        try:
            self.call("getIssueContext", issue_number=number)
        except GitHubError as exc:
            if exc.status != 404:
                raise
            return False
        return True


class PrOps(Ops):
    """The pull request's context and comments (review and CI-fix runs)."""

    def __init__(self, gh: GitHub, caller: Caller, confirm: Confirm | None, number: int) -> None:
        super().__init__(gh, caller, confirm)
        self.number = number

    def context(self) -> dict[str, Any]:
        """The pull request with its issue comments and reviews, read fresh."""
        ctx: dict[str, Any] = self.call("getPullRequestContext", pull_number=self.number)
        return ctx

    def comment(self, body: str) -> None:
        self.call("addPullRequestComment", pull_number=self.number, body=body)

    def my_comments(self, ctx: dict[str, Any]) -> list[str]:
        """Bodies of the PR comments in `ctx` that VK itself posted."""
        me = self.gh.me()
        return [
            c.get("body") or "" for c in ctx["comments"] if (c.get("user") or {}).get("login") == me
        ]


def dump(model: BaseModel) -> str:
    return json.dumps(model.model_dump(mode="json", by_alias=True), indent=2)


def _issue_text(number: int, ctx: dict[str, Any], ops: IssueOps) -> str:
    """The issue verbatim: title, body, and the comments `ops.visible_comments` lets through."""
    issue = ctx["issue"]
    author = (issue.get("user") or {}).get("login", "unknown")
    parts = [f"# Issue #{number}: {issue.get('title', '')}", f"Opened by @{author}.", ""]
    parts.append(issue.get("body") or "(no description)")
    comments, omitted = ops.visible_comments(ctx, ctx.get("comments") or [])
    if comments:
        parts += ["", "## Comments"]
        for c in comments:
            parts += ["", f"@{(c.get('user') or {}).get('login', 'unknown')}:", c.get("body", "")]
    if omitted:
        parts += [
            "",
            f"({omitted} comment(s) omitted: not from the issue author, VK, or a collaborator "
            "with write access.)",
        ]
    return "\n".join(parts)


def _artifact_line(kind: str, artifact_id: str | None) -> str:
    if not artifact_id:
        return ""
    return f"\n\n{kind} artifact id: {artifact_id} (open it with read_artifact before you start)."


def section(title: str, body: str) -> str:
    return f"## {title}\n\n{body}"


def agent_instructions(cfg: Config, name: str, *extra: str) -> str:
    """Agent prompt, then any extra text, then the shared writing style."""
    parts = [load_prompt(name, repo=cfg.repo), *extra, load_prompt("style")]
    return "\n\n".join(p.strip() for p in parts) + "\n"


def revision_section(branch: str) -> str:
    return section("Revision requested", load_prompt("revision", branch=branch))


def review_findings(review: Review) -> str:
    lines = [f"- {f}" for f in review.blocking_findings]
    lines += [
        f"- Failed criterion: {c.criterion} ({c.evidence})"
        for c in review.criteria_results
        if not c.passed
    ]
    lines += [f"- Advisory: {s}" for s in review.suggestions]
    return "\n".join(lines) or "- (the reviewer gave no itemized findings; see its summary)"


@dataclass(frozen=True)
class LoopResult:
    implementation: Implementation
    review: Review
    approved: bool
    revisions: int


def _require_pushed(impl: Implementation, branch: str | None) -> None:
    """Fail the run when the implementer's work is not on the branch the caller expects."""
    problem = None
    if not impl.pushed:
        why = "; ".join(impl.known_limitations) or "no reason given"
        problem = f"the implementer did not push branch `{impl.branch}`: {why}"
    elif branch is not None and impl.branch != branch:
        problem = f"the implementer pushed `{impl.branch}`, not the branch `{branch}`"
    if problem:
        cause = RuntimeError(problem)
        raise StageFailed("implementer", cause) from cause


def implement_and_review(
    stages: Stages,
    task: str,
    brief: str,
    *,
    progress: Callable[[str], None] | None = None,
    branch: str | None = None,
) -> LoopResult:
    """Implementer then reviewer, with up to MAX_REVIEW_CYCLES revisions on `request_changes`.

    `task` is the implementer's self-contained first message and `brief` the context the
    reviewer needs (work item, criteria, artifact ids); the implementation report is appended
    for it. A `reject` verdict stops at once: iteration will not fix a wrong approach. An
    implementation that is not pushed (or, with `branch`, not on that branch) fails the stage
    instead of reaching the reviewer.
    """

    def implement(message: str) -> Implementation:
        impl = stages.clan("implementer", message, Implementation)
        _require_pushed(impl, branch)
        return impl

    impl = implement(task)
    revisions = 0
    while True:
        review_message = "\n\n".join(
            [
                brief,
                section("Implementer report", dump(impl)),
                f"Review the branch `{impl.branch}` (base `{impl.base}`).",
            ]
        )
        review = stages.clan("reviewer", review_message, Review)
        log.info(
            "reviewer verdict=%s blocking_findings=%d cycle=%d",
            review.verdict,
            len(review.blocking_findings),
            revisions + 1,
        )
        if review.verdict != "request_changes" or revisions == MAX_REVIEW_CYCLES:
            return LoopResult(impl, review, review.verdict == "approve", revisions)
        revisions += 1
        if progress:
            progress(
                f"The reviewer asked for changes ({revisions} of {MAX_REVIEW_CYCLES}). Revising."
            )
        revision = "\n\n".join(
            [
                task,
                revision_section(impl.branch),
                section("Your previous implementation report", dump(impl)),
                section("Reviewer findings", review_findings(review)),
            ]
        )
        impl = implement(revision)


def load_notebook(
    cfg: Config, issue: int, title: str, ref: str, remote_url: str | None
) -> Notebook:
    """Materialize the run's memory from `ref`; a git failure ends the run as a stage failure."""
    try:
        return memory.open_notebook(cfg, issue, title, ref, remote_url=remote_url)
    except git.GitError as exc:
        raise StageFailed("memory", exc) from exc


def _preferences(cfg: Config, caller: Caller) -> str:
    """The signed-in user's saved preferences; unattended runs have none."""
    if caller.unattended:
        return ""
    get = next(
        t for t in preference_tools(cfg, getpass.getuser()) if t.name == "get_user_preferences"
    )
    found = get.fn({})
    prefs = str(found.get("preferences", "")).strip()
    return load_prompt("preferences", preferences=prefs) if prefs else ""


def _with_closes(body: str, number: int) -> str:
    if re.search(rf"\bcloses\s+#{number}\b", body, re.IGNORECASE):
        return body
    return f"{body.rstrip()}\n\nCloses #{number}\n"


def run_issue(
    cfg: Config,
    gh: GitHub,
    number: int,
    caller: Caller,
    *,
    confirm: Confirm | None = None,
    model: ModelFactory | None = None,
    remote_url: str | None = None,
) -> str:
    """Take issue `number` from triage to a draft pull request; returns the closing summary.

    `model` (agent name -> PydanticAI model) and `remote_url` are test seams.
    """
    ops = IssueOps(gh, caller, confirm, number)
    started = time.monotonic()

    ctx = ops.call("getIssueContext", issue_number=number)
    on_issue = {label["name"] for label in ctx.get("labels", [])}
    for label in STATUS_LABELS:
        ops.call("ensureLabel", name=label)
    for stale in on_issue & set(STATUS_LABELS):  # left by an earlier run
        ops.remove_label(stale)
    ops.set_status(IN_PROGRESS)
    issue = _issue_text(number, ctx, ops)
    log.info("issue #%d starting repo=%s", number, cfg.repo)

    try:
        notebook = load_notebook(cfg, number, ctx["issue"].get("title", ""), "HEAD", remote_url)
        try:
            stages = Stages(cfg, model, remote_url, notebook)
            summary = _run(cfg, ops, stages, caller, number, issue, on_issue)
        finally:
            notebook.close()
    except StageFailed as exc:
        ops.comment(
            f"I hit an error in the {exc.stage} step and stopped, so no pull request was "
            f"opened.\n\nError: {exc.__cause__}\n\nLabel the issue `vk` again to retry."
        )
        ops.set_status(BLOCKED)
        summary = f"Stopped: the {exc.stage} step failed twice ({exc.__cause__})."
    log.info("issue #%d finished in %.1fs", number, time.monotonic() - started)
    return summary


def _run(
    cfg: Config,
    ops: IssueOps,
    stages: Stages,
    caller: Caller,
    number: int,
    issue: str,
    on_issue: set[str],
) -> str:
    # 1. Triage: duplicates, labels, whether research is needed.
    repo_labels = [label["name"] for label in ops.call("listLabels", per_page=100)]
    triage = stages.agent(
        "triage",
        Triage,
        agent_instructions(cfg, "triage", load_skill("triaging-issues")),
        f"{issue}\n\n## Existing labels\n\n" + ("\n".join(repo_labels) or "(none)"),
        ops.read_tools(TRIAGE_TOOLS),
    )
    log.info("triage proceed=%s duplicate_of=%s", triage.proceed, triage.duplicate_of)
    # Code decides which labels apply: only ones the repo already has, never a status label.
    wanted = [
        label
        for label in dict.fromkeys(triage.labels)
        if label in repo_labels and label not in STATUS_LABELS and label not in on_issue
    ]
    if wanted:
        ops.call("addLabels", issue_number=number, labels=wanted)

    dup = triage.duplicate_of
    if dup is not None and dup != number and ops.issue_exists(dup):
        ops.comment(
            f"This looks like a duplicate of #{dup}. {triage.reason}\n\n"
            "I'm not running the factory on it. If that's wrong, say so here and label the "
            "issue `vk` again."
        )
        ops.set_status(NEEDS_INFO)
        return f"Issue #{number} looks like a duplicate of #{dup}; I commented and stopped."
    if not triage.proceed:
        ops.comment(f"I'm not going to work on this one. {triage.reason}")
        ops.set_status(BLOCKED)
        return f"Triage decided not to proceed on #{number}: {triage.reason}"

    # 2. Classify; stop for clarification.
    classification = stages.clan("classifier", issue, Classification)
    log.info(
        "classification type=%s priority=%s complexity=%s needs_clarification=%s",
        classification.type,
        classification.priority,
        classification.complexity,
        classification.needs_clarification,
    )
    if classification.needs_clarification:
        questions = "\n".join(f"- {q}" for q in classification.questions)
        ops.comment(
            "Thanks for the report. Before I start, I need a few answers:\n\n"
            f"{questions}\n\nReply here, then label the issue `vk` again and I'll pick it up."
        )
        ops.set_status(NEEDS_INFO)
        return f"Issue #{number} needs clarification; I posted my questions."
    c = classification
    ops.comment(
        f"Classified as {c.type} ({c.priority} priority, {c.complexity}) in {c.affected_area}. "
        + ("Researching first, then planning." if triage.needs_research else "Planning next.")
    )
    context = [issue, section("Classification", dump(classification))]

    # 3. Research (only when triage asks), then analysis.
    research: Research | None = None
    if triage.needs_research:
        question = triage.research_question or "Verify the facts this issue depends on."
        research = stages.clan(
            "researcher", "\n\n".join([*context, section("Research question", question)]), Research
        )
        context.append(section("Research", dump(research)))
    analysis_message = "\n\n".join(context)
    if research:
        analysis_message += _artifact_line("Research", research.artifact_id)
    analysis = stages.clan("analyst", analysis_message, Analysis)
    ops.comment(
        f"The plan is ready: {len(analysis.plan)} step(s), {len(analysis.acceptance_criteria)} "
        "acceptance criteria. Implementing now."
    )

    # 4. Implement and review.
    plan = [*context, section("Analysis", dump(analysis))]
    artifact = _artifact_line("Analysis", analysis.artifact_id)
    task = "\n\n".join(["Implement this work item.", *plan]) + artifact
    brief = "\n\n".join(["Review this work item.", *plan]) + artifact
    result = implement_and_review(stages, task, brief, progress=ops.comment)
    impl, review = result.implementation, result.review
    if not result.approved:
        ops.comment(
            f"The reviewer still has unresolved findings after {result.revisions} "
            f"revision(s) (verdict: {review.verdict}), so I did not open a pull request. "
            f"The work is on branch `{impl.branch}`.\n\n{review.summary}\n\n"
            f"Unresolved findings:\n\n{review_findings(review)}"
        )
        ops.set_status(BLOCKED)
        return (
            f"Review did not pass for #{number} ({review.verdict}); "
            "findings posted, no pull request."
        )

    # 5. Publish the run log before the PR, then write and open the draft PR.
    try:
        runlog.publish(
            cfg,
            {
                "issue_number": number,
                "branch": impl.branch,
                "mode": "write",
                "classification": classification.model_dump(mode="json", by_alias=True),
                "analysis": analysis.model_dump(mode="json", by_alias=True),
                "implementation": impl.model_dump(mode="json", by_alias=True),
                "review": review.model_dump(mode="json", by_alias=True),
            },
            remote_url=stages.remote_url,
            files=stages.notebook_changes(),
        )
    except ToolError as exc:
        raise StageFailed("run log", exc) from exc
    if stages.notebook:
        stages.notebook.mark_saved()
    pr_message = "\n\n".join(
        [
            *plan,
            section("Implementer report", dump(impl)),
            section("Reviewer verdict", dump(review)),
            f"The run log is `{runlog.log_path(number)}` on branch `{impl.branch}`.",
        ]
    )
    pr = stages.agent(
        "pr_writer",
        PrBody,
        agent_instructions(
            cfg, "pr_writer", load_skill("writing-quality"), _preferences(cfg, caller)
        ),
        pr_message,
        [],
    )
    if stages.notebook:  # the pr_writer has the notebook too, so keep what it wrote
        try:
            memory.save(cfg, stages.notebook, impl.branch, remote_url=stages.remote_url)
        except git.GitError as exc:
            raise StageFailed("memory", exc) from exc
    created = ops.call(
        "createPullRequest",
        title=pr.title,
        head=impl.branch,
        base=impl.base,
        body=_with_closes(pr.body, number),
        draft=True,
    )
    ops.set_status(PR_OPEN)
    url = created.get("html_url") or f"(pull request #{created.get('number', '?')})"
    return (
        f"Opened draft pull request {url} for #{number}. Reviewer verdict: approve after "
        f"{result.revisions} revision(s). {review.summary}"
    )
