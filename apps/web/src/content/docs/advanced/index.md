---
title: Advanced
description: Detailed configuration, security model, trust rules, and local CLI execution.
---

This guide details advanced execution options, environment variables, security considerations, and local usage for Vishwakarma.

## Environment Configuration Matrix

Models, per-clan token budgets, loop caps, tool limits, timeouts, and the clone setup command live in one file, `packages/vk/src/vk/vk.toml`. See [Change the LLM model](../how-to-guides/#how-to-change-the-llm-model-used-by-vk). The environment holds only secrets and per-run values:

| Variable       | Required | Description                                                                     | Default                                   |
| -------------- | -------- | ------------------------------------------------------------------------------- | ----------------------------------------- |
| `GITHUB_TOKEN` | Yes      | Token with access to read/write repository contents, issues, and pull requests. | —                                         |
| `VK_CONFIG`    | No       | Path to a settings file to use instead of the shipped `vk.toml`.                | `packages/vk/src/vk/vk.toml`              |
| `VK_BOT_LOGIN` | No       | GitHub login for the bot user.                                                  | `None`                                    |
| `VK_REPO`      | No       | Target repository formatted as `owner/repo`.                                    | Inferred from `git remote get-url origin` |
| `VK_STATE_DIR` | No       | Directory for execution state, clones, and logs.                                | `~/.vk`                                   |
| `VK_LOG_LEVEL` | No       | Stderr log verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`).                     | `INFO`                                    |

## GitHub Identity and Authentication

In GitHub Actions workflows, Vishwakarma uses tokens for repository operations:

- **`VK_GITHUB_TOKEN`**: Dedicated Personal Access Token or GitHub App Installation Token in a secret (`secrets.VK_GITHUB_TOKEN`).
- **`github.token`**: Default repository token for read actions and failure comments.

A GitHub App token or PAT allows workflows from PR creation to run downstream CI actions that a standard `GITHUB_TOKEN` can suppress.

## Trust Rules and Permissions

Vishwakarma enforces role-based authorization before it executes commands:

- **Issue Handover**: When an issue receives the `vk` label, the workflow checks the sender role at `repos/{owner}/{repo}/collaborators/{username}/permission`.
- **Allowed Roles**: `admin`, `maintain`, `write`, and `triage`.
- **Unauthorized User**: If a user without permissions adds the label, the workflow stops with an error comment.

## Security and Execution Safety

:::caution[No Sandbox Notice]
The Implementer and Reviewer clans execute shell commands with a `bash` tool directly on the host system without container isolation or sandbox protection.
:::

Security requirements:

- **Disposable Environments**: Run Vishwakarma strictly inside isolated, ephemeral environments like GitHub Actions runners or disposable VMs.
- **Token Isolation**: The system provides the GitHub authentication token with `git -c http.extraHeader` or an environment variable. The system never writes the token to disk or passes it to agent prompt contexts.

## Run VK Locally

To execute Vishwakarma on a local clone for test or debug tasks:

```bash
export GITHUB_TOKEN="your-github-token"
export ANTHROPIC_API_KEY="your-api-key"

# Process issue #42 locally
uv run --package vk vk issue 42
```

Add `--unattended` when you run in non-interactive environments:

```bash
uv run --package vk vk issue 42 --unattended
```
