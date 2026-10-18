---
title: Concepts
description: Core concepts, clan architecture, status labels, run logs, and per-issue memory.
---

Vishwakarma operates as an autonomous software factory. It uses specialized AI agent clans that work together in a pipeline.

## The Factory Pipeline

When you transfer an issue to Vishwakarma, the issue passes through an automated issue-to-PR workflow:

1. **Triage and Classification**: Categorize the issue type, priority, and affected area.
2. **Research and Plan**: Gather repository context and formulate an explicit implementation plan with acceptance criteria.
3. **Execution**: Make code changes on a feature branch (`vk/*`) and verify with `make check`.
4. **Review**: Evaluate changes against acceptance criteria and safety rules.
5. **Delivery**: Open a draft pull request with a complete run log or request human feedback when needed.

If review feedback or CI failures occur on an open factory PR, Vishwakarma runs a review-fix or CI-fix cycle to revise code and reply.

## Agent Clans

Vishwakarma divides work among five specialized clans:

- **Classifier**: Analyzes new issues to determine issue type (bug, feature, chore, etc.), priority, complexity, affected paths, and actionability.
- **Researcher**: Searches the codebase and reads relevant files to gather context without code modifications.
- **Analyst**: Synthesizes issue details and research into a step-by-step implementation plan, affected surface list, and acceptance criteria.
- **Implementer**: Creates a feature branch, executes the plan, writes minimal and surgical code changes, and verifies with repository check commands.
- **Reviewer**: Evaluates the implemented changes against acceptance criteria, verifies `make check` results, and decides whether to approve, request changes, or block.

## Status Labels

Vishwakarma updates status labels on GitHub issues to communicate current state:

| Label            | Description                                                                        |
| ---------------- | ---------------------------------------------------------------------------------- |
| `vk:in-progress` | The factory processes the issue.                                                   |
| `vk:pr-open`     | The factory completed the task and opened a draft PR.                              |
| `vk:needs-info`  | The factory encountered ambiguity and posted questions on the issue.               |
| `vk:blocked`     | Execution or review failed after revision limits; human intervention is necessary. |

## The Run Log

Every factory execution produces a durable Markdown run log. The factory saves the log at `docs/factory/issue-<N>.md` and commits it to the pull request branch.

The run log details:

- Issue summary and classification metrics.
- Analyst problem statement, approach, plan, and acceptance criteria.
- Implementer change summary, verification command outputs, and any narrow deviations.
- Reviewer verdict (`approve` or `reject`) and criteria check results.

## Per-Issue Memory

To maintain state across multiple execution turns (such as review iterations):

- **`MEMORY.md`**: Stores short durable facts, session state, and current goals for each issue turn.
- **`repo-notes.md`**: Stores verified repository facts, build quirks, and conventions.
