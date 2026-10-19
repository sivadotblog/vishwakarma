---
title: How-to Guides
description: Task-focused guides for Vishwakarma.
---

This section provides step-by-step guides for common tasks when you operate Vishwakarma.

## How to Hand an Issue to VK

To hand an issue to Vishwakarma:

1. Open a GitHub issue that describes the bug, feature, or maintenance task.
2. Add the label `vk` to the issue.
3. The `.github/workflows/vishwakarma.yml` workflow starts automatically.
4. **Permission check**: Vishwakarma verifies that the labeler holds at least `triage`, `write`, `maintain`, or `admin` repository permission. If an unauthorized user labels an issue, execution stops to prevent unauthorized resource usage.

## How to Respond to a VK Pull Request

When Vishwakarma opens a draft pull request:

1. Review the changes and the run log in `docs/factory/issue-<N>.md`.
2. If you request changes, write review comments on the pull request.
3. Submit the review. The `.github/workflows/vishwakarma-review.yml` workflow starts the review cycle.
4. To start the review cycle locally, run `vk review <PR_NUMBER>`.
5. Vishwakarma checks out the PR branch, reads the review comments, and answers each comment.
6. Vishwakarma updates `docs/factory/issue-<N>.md` with review rounds and pushes updated commits.

## How to Change the LLM Model Used by VK

Vishwakarma uses PydanticAI to integrate with model providers such as Anthropic, OpenAI, and Gemini.

### Default Model Configuration

Set `model` in the `[defaults]` table of `packages/vk/src/vk/vk.toml` to specify the default model for all clans:

```toml
[defaults]
model = "anthropic:claude-sonnet-5-5"
```

### Per-Clan Models and Token Budgets

Each clan has a table in the same file: `[clans.classifier]`, `[clans.researcher]`, `[clans.analyst]`, `[clans.implementer]`, `[clans.reviewer]`, `[clans.triager]`, `[clans.pr_writer]`, and `[clans.ci_diagnoser]`. A key in a clan table overrides the `[defaults]` value for that clan. The keys are `model`, `max_input_tokens`, `max_output_tokens`, `max_total_tokens`, `max_requests`, and `output_retries`.

This example sets a small model for classification and a large model with a bigger budget for implementation:

```toml
[clans.classifier]
model = "google:gemini-2.5-flash"

[clans.implementer]
model = "anthropic:claude-sonnet-5-5"
max_output_tokens = 200_000
```

To use a different file without editing the shipped one, set `VK_CONFIG` to its path.

## How to Troubleshoot Failures

When a Vishwakarma run stops or fails, see the [Troubleshooting guide](/how-to-guides/troubleshooting/) for solutions to exit codes, status labels, and Prefect execution failures.
