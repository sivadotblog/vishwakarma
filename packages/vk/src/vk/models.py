# ruff: noqa: E501
"""Typed structured outputs for every agent; the Pydantic mirror of `schemas.py`."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Classification(_Model):
    type: Literal["bug", "feature", "refactor", "question", "chore", "security"]
    priority: Literal["critical", "high", "medium", "low"]
    complexity: Literal["trivial", "small", "medium", "large"]
    affected_area: str = Field(
        description="Best guess at the component, service, or layer involved (e.g. 'frontend/auth', 'API', 'CI pipeline', 'unknown')."
    )
    actionable: bool = Field(
        description="Whether the request contains enough information to act on."
    )
    needs_clarification: bool = Field(
        description="True when the request is ambiguous, contradictory, or missing essential details; the questions to ask go in `questions`."
    )
    questions: list[str] = Field(
        description="The specific clarifying questions to ask; empty unless needs_clarification is true."
    )
    summary: str = Field(description="One-sentence restatement of the work item.")


class Source(_Model):
    url: str = Field(description="The source URL, as visited.")
    title: str = Field(description="The source's title or publication name.")


class Finding(_Model):
    claim: str = Field(description="A single, specific factual claim the caller can rely on.")
    sources: list[Source] = Field(
        min_length=1,
        description="The real, fetched sources backing the claim; never empty, never invented.",
    )
    confidence: Literal["high", "medium", "low"] = Field(
        description="'high' = multiple strong independent sources; 'low' = single or weaker source."
    )
    notes: str = Field(
        description="Caveats: date-sensitivity, scope limits, or where sources disagree."
    )


class Research(_Model):
    summary: str = Field(
        description="A 1-3 sentence synthesis of what the research establishes, for the root to scan first."
    )
    findings: list[Finding] = Field(
        description="One entry per verified factual claim; every entry carries at least one real source."
    )
    gaps: list[str] = Field(
        description="What could not be found or verified; surfaced to the caller rather than guessed at."
    )
    artifact_id: str | None = Field(
        description="Id of the saved research-notes artifact holding the full memo, or null when none was saved."
    )


class Analysis(_Model):
    problem_statement: str = Field(
        description="What is actually wrong or wanted, restated as a precise engineering problem."
    )
    approach: str = Field(
        description="The chosen solution strategy, and briefly the main alternative rejected and why."
    )
    plan: list[str] = Field(
        min_length=1,
        description="Ordered, concrete steps; each independently verifiable. The smallest change that fully solves the problem.",
    )
    affected_surface: list[str] = Field(
        description="Files, modules, interfaces, or systems the change will touch; anything with a public contract called out."
    )
    risks: list[str] = Field(
        description="What could break, edge cases, migration or compatibility concerns, and how the plan mitigates each."
    )
    acceptance_criteria: list[str] = Field(
        min_length=1,
        description="Objective, testable criteria the reviewer will check one by one, verbatim.",
    )
    test_strategy: str = Field(
        description="What should be tested and how (unit, integration, manual), grounded in the repository's own test setup."
    )
    assumptions: list[str] = Field(
        description="Assumptions the plan rests on, stated so the implementer and reviewer can see them."
    )
    open_questions: list[str] = Field(
        description="External facts the plan could not resolve from the repository; surfaced instead of guessed."
    )
    artifact_id: str | None = Field(
        description="Id of the saved analysis artifact holding the full supporting detail, or null when none was saved."
    )


class FileChange(_Model):
    path: str = Field(description="The file path.")
    change: str = Field(description="What changed in this file and why.")


class Verification(_Model):
    command: str = Field(description="The command as run.")
    result: str = Field(description="What it produced: pass/fail and the relevant output.")


class Implementation(_Model):
    branch: str = Field(description="The feature branch the work was committed and pushed to.")
    base: str = Field(
        description="The branch the work is based on, normally the repository's default branch."
    )
    pushed: bool = Field(
        description="Whether push_branch succeeded; when false, the failure reason is in known_limitations."
    )
    change_summary: list[FileChange] = Field(description="What changed and why, per file.")
    verification: list[Verification] = Field(
        description="Commands run and what they produced, exactly."
    )
    deviations: list[str] = Field(
        description="Departures from the plan, each with its reason; empty when the plan held."
    )
    known_limitations: list[str] = Field(description="Anything the reviewer should scrutinize.")


class CriterionResult(_Model):
    # `pass` is a Python keyword, so the attribute is `passed` and the JSON name is the alias.
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    criterion: str = Field(description="The acceptance criterion, verbatim.")
    passed: bool = Field(alias="pass")
    evidence: str = Field(
        description="What in the diff or verification output shows it passing or failing."
    )


class Review(_Model):
    verdict: Literal["approve", "request_changes", "reject"]
    criteria_results: list[CriterionResult] = Field(
        description="One entry per acceptance criterion from the analysis, judged individually."
    )
    blocking_findings: list[str] = Field(
        description="Problems that block shipping: each names where it is, what is wrong, and why it matters."
    )
    suggestions: list[str] = Field(description="Advisory notes that do not block shipping.")
    summary: str = Field(description="One paragraph: the verdict and what drove it.")


class Triage(_Model):
    proceed: bool = Field(description="Whether VK should work on this issue at all.")
    duplicate_of: int | None = Field(
        description="Number of the existing issue this duplicates, or null when it is not a duplicate."
    )
    labels: list[str] = Field(description="Labels to apply to the issue.")
    reason: str = Field(description="Why this decision was made, in one or two sentences.")
    needs_research: bool = Field(
        description="True when the work turns on a fact the repository and its issues do not hold."
    )
    research_question: str = Field(
        default="",
        description="The specific question for the researcher; empty unless needs_research is true.",
    )


class CommentDecision(_Model):
    comment_id: int = Field(description="Id of the review comment this decision answers.")
    decision: Literal["fix", "wontfix"]
    reason: str = Field(description="Why the comment is being fixed or declined.")
    fix_instructions: str = Field(
        description="What the implementer must change; empty when the decision is wontfix."
    )


class PrBody(_Model):
    title: str = Field(description="The pull request title.")
    body: str = Field(description="The pull request description in Markdown.")


class CiDiagnosis(_Model):
    summary: str = Field(description="What failed in CI, in one or two sentences.")
    likely_cause: str = Field(description="The most likely root cause of the failure.")
    fix_instructions: str = Field(description="What the implementer must change to make CI pass.")
