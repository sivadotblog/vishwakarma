---
title: Concepts
description: Core concepts, clan architecture, status labels, run logs, and per-issue memory.
---

Vishwakarma operates as an autonomous software factory structured around Specialized AI Agent Clans working together in a pipeline.

## The Factory Pipeline

When an issue is handed to Vishwakarma, it passes through an automated issue-to-PR workflow:

1. **Triage & Classification**: Categorize issue type, priority, and affected area.
2. **Research & Planning**: Gather repository context and formulate an explicit implementation plan with acceptance criteria.
3. **Execution**: Make code changes on a feature branch (`vk/*`) and verify against `make check`.
4. **Review**: Evaluate changes against acceptance criteria and safety rules.
5. **Delivery**: Open a draft pull request with a complete run log or request human feedback when needed.

If review feedback or CI failures occur on an existing factory PR, Vishwakarma runs a review-fix or CI-fix cycle to revise code and reply.

## Agent Clans

Vishwakarma divides work among five specialized clans:

- **Classifier**: Analyzes incoming issues to determine issue type (bug, feature, chore, etc.), priority, complexity, affected paths, and actionability.
- **Researcher**: Searches the codebase and reads relevant files to gather context without making code modifications.
- **Analyst**: Synthesizes issue details and research into a step-by-step implementation plan, affected surface list, and acceptance criteria.
- **Implementer**: Creates a feature branch, executes the plan, writes minimal and surgical code changes, and verifies with repository check commands.
- **Reviewer**: Evaluates the implemented changes against acceptance criteria, verifies `make check` results, and decides whether to approve, request changes, or block.

## Status Labels

Vishwakarma updates status labels on GitHub issues to communicate current state:

| Label            | Description                                                                     |
| ---------------- | ------------------------------------------------------------------------------- |
| `vk:in-progress` | The factory is currently working on the issue.                                  |
| `vk:pr-open`     | The factory successfully completed the task and opened a draft PR.              |
| `vk:needs-info`  | The factory encountered ambiguity and posted clarifying questions on the issue. |
| `vk:blocked`     | Execution or review failed after revision limits; human intervention required.  |

## The Run Log

Every factory execution produces a durable Markdown run log saved at `docs/factory/issue-<N>.md` and committed directly to the pull request branch.

The run log details:

- Issue summary and classification metrics.
- Analyst problem statement, approach, plan, and acceptance criteria.
- Implementer change summary, verification command outputs, and any narrow deviations.
- Reviewer verdict (`approve` or `reject`) and criteria check results.

## Per-Issue Memory

To maintain state across multiple execution turns (such as review iterations):

- **`MEMORY.md`**: Maintained per issue turn to keep short durable facts, session state, and current goals.
- **`repo-notes.md`**: Stores verified repository learnings, build quirks, and conventions discovered during execution.
