---
title: Troubleshooting
description: Solutions for common exit codes, status labels, and Prefect execution failures.
---

This guide explains how to diagnose and resolve errors when a Vishwakarma run stops or fails.

## Exit Code 2 (Configuration Error)

Exit code `2` indicates a configuration error. Vishwakarma stops before execution when configuration parameters are missing or invalid.

### Causes and Solutions

- **Missing `GITHUB_TOKEN`**: The `GITHUB_TOKEN` environment variable is not set. Set `GITHUB_TOKEN` to a valid GitHub access token with repository, issue, and pull request write access.
- **Invalid `vk.toml` configuration**:
  - **Unknown key or clan**: `vk.toml` contains an unknown key or clan name. Remove unknown keys and use only valid clan names (`classifier`, `researcher`, `analyst`, `implementer`, `reviewer`, `triager`, `pr_writer`, `ci_diagnoser`).
  - **Model format is not `provider:model`**: A model string does not use the `provider:model` format (for example, `provider/model` is rejected). Set model values using `provider:model` syntax (for example, `anthropic:claude-sonnet-5-5` or `google:gemini-2.5-flash`).
  - **Non-integer or non-positive budget**: A token or request limit parameter is not a positive integer. Set budget parameters (`max_input_tokens`, `max_output_tokens`, `max_total_tokens`, `max_requests`) to positive integers.
- **Bad `VK_CONFIG` file path**: The `VK_CONFIG` environment variable points to a file that does not exist or cannot be read. Correct the file path or unset `VK_CONFIG` to use the default `packages/vk/src/vk/vk.toml` configuration.
- **Missing `github.com` `origin` remote**: `VK_REPO` is not set and the local git `origin` remote is missing or is not a `github.com` URL. Set the `VK_REPO` environment variable (for example, `owner/repo`) or configure a valid `github.com` remote named `origin`.

For the complete list of exit codes, see the [Exit Codes reference](/api-reference/#exit-codes).

## Exit Code 3 (Token Budget Exceeded)

Exit code `3` indicates that an agent execution exceeded a token budget or request budget limit.

### Configuration Keys

You set token and request budgets in `vk.toml` under the `[defaults]` table or per clan under `[clans.<name>]`. The budget keys are:

- `max_input_tokens`: Maximum input tokens allowed per run.
- `max_output_tokens`: Maximum output tokens allowed per run.
- `max_total_tokens`: Maximum total tokens allowed per run.
- `max_requests`: Maximum LLM API requests allowed per run.

### Read Stderr Logs to Adjust Budgets

When an agent run exceeds a budget, inspect the stderr logs to check usage details. Look for these log lines:

- `llm <clan> model=... turn=<M> prompt_tokens=<P> completion_tokens=<C> total_tokens=<N>`
- `agent <name> done status=... total_tokens=<N>`

To resolve the error:

1. Identify the `total_tokens` consumed in the stderr log lines.
2. Increase `max_total_tokens`, `max_input_tokens`, or `max_output_tokens` in `vk.toml` to a value higher than the reported usage.

For the complete list of exit codes, see the [Exit Codes reference](/api-reference/#exit-codes).

## Status Labels

Vishwakarma sets status labels on GitHub issues to communicate workflow state.

### `vk:needs-info`

- **Meaning**: Vishwakarma found ambiguous requirements or missing details and posted clarifying questions on the issue. Execution stopped.
- **Next Action**: Read the questions on the issue, reply with clarifications, and re-apply the `vk` label to restart execution.

### `vk:blocked`

- **Meaning**: Execution stopped because a pipeline stage failed after retries, a review loop reached maximum attempt limits, or an off-topic request was declined.
- **Next Action**: Read the issue comments or run log to identify the error. Resolve the underlying problem (such as fixing configuration or dependencies), and re-apply the `vk` label to retry.

For the full list of status labels, see the [Status Labels reference](/api-reference/status-labels/).

## Prefect Flow Failures

When Vishwakarma runs as a Prefect flow (`vk-issue` or `vk-review`), execution details are logged in the Prefect UI.

### Failure Comments and Run Logs

If an unhandled error escapes execution during a flow run, Vishwakarma posts a comment on the GitHub issue or pull request:

```text
The software factory run failed. Log: <url>
```

Follow the link in the comment to view the Prefect flow run UI, inspect stage logs, and trace failure exceptions.

### Stage Retry Behavior

Vishwakarma retries each workflow stage once automatically when a failure occurs. If a stage fails on the second attempt, execution stops and Vishwakarma sets the issue status to `vk:blocked`.
