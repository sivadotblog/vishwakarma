---
title: Advanced
description: Detailed configuration, security model, trust rules, and local CLI execution.
---

This guide details advanced execution options, environment variables, security considerations, and local usage for Vishwakarma.

## Environment Configuration Matrix

Vishwakarma is configured via environment variables:

| Variable               | Required | Description                                                                                                  | Default                                   |
| ---------------------- | -------- | ------------------------------------------------------------------------------------------------------------ | ----------------------------------------- |
| `GITHUB_TOKEN`         | Yes      | Token with access to read/write repository contents, issues, and pull requests.                              | —                                         |
| `VK_MODEL`             | Yes      | Primary model identifier passed to LiteLLM (e.g. `anthropic/claude-3-5-sonnet`).                             | —                                         |
| `VK_MODEL_<CLAN>`      | No       | Per-clan model overrides (`ORCHESTRATOR`, `CLASSIFIER`, `RESEARCHER`, `ANALYST`, `IMPLEMENTER`, `REVIEWER`). | `VK_MODEL`                                |
| `VK_REPO`              | No       | Target repository formatted as `owner/repo`.                                                                 | Inferred from `git remote get-url origin` |
| `VK_SETUP_COMMAND`     | No       | Command executed in fresh repository clones before processing.                                               | None                                      |
| `VK_BRANCH_PREFIX`     | No       | Prefix for factory feature branches.                                                                         | `vk/`                                     |
| `VK_STATE_DIR`         | No       | Directory for execution state, clones, and logs.                                                             | `~/.vk`                                   |
| `VK_MAX_OUTPUT_TOKENS` | No       | Maximum token budget allowed per agent execution.                                                            | `100000`                                  |
| `VK_LOG_LEVEL`         | No       | Stderr logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`).                                              | `INFO`                                    |

## GitHub Identity & Authentication

In GitHub Actions workflows, Vishwakarma utilizes tokens for repository interaction:

- **`VK_GITHUB_TOKEN`**: A Dedicated Personal Access Token or GitHub App Installation Token provided as a secret (`secrets.VK_GITHUB_TOKEN`).
- **`github.token`**: Default repository token, used for read actions and reporting failure comments.

Using a GitHub App token or PAT allows workflows triggered by PR creation to run downstream CI actions that standard `GITHUB_TOKEN` creation might otherwise suppress.

## Trust Rules & Permissions

Vishwakarma enforces role-based authorization before executing commands:

- **Issue Hand-off**: When an issue receives the `vk` label, the workflow checks the sender's permission role against `repos/{owner}/{repo}/collaborators/{username}/permission`.
- **Allowed Roles**: `admin`, `maintain`, `write`, and `triage`.
- **Unauthorized Labeling**: If attached by a user without required permissions, the workflow aborts with an error comment.

## Security & Execution Safety

:::caution[No Sandbox Notice]
The Implementer and Reviewer clans execute shell commands via a `bash` tool directly on the host operating system without container isolation or sandboxing.
:::

Security requirements:

- **Disposable Environments**: Run Vishwakarma strictly inside isolated, ephemeral environments like GitHub Actions runners or disposable VMs.
- **Token Isolation**: The GitHub authentication token is supplied via `git -c http.extraHeader` or environment variable and is never written to disk or passed to agent prompt contexts.

## Running VK Locally

To execute Vishwakarma on a local clone for testing or debugging:

```bash
export GITHUB_TOKEN="your-github-token"
export VK_MODEL="anthropic/claude-3-5-sonnet"
export ANTHROPIC_API_KEY="your-api-key"

# Process issue #42 locally
uv run --package vk vk issue 42
```

Add `--unattended` when running in non-interactive environments:

```bash
uv run --package vk vk issue 42 --unattended
```
