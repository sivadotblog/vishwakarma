---
title: API Reference
description: Command-line reference, exit codes, and environment variable specifications for `vk`.
---

This section documents the `vk` command-line interface, exit codes, and environment variables.

## CLI Commands

Execute the `vk` CLI inside a local checkout of the target repository.

### `vk issue <N>`

Processes an unhandled GitHub issue end-to-end (triage, plan, implementation, verification, review) and opens a draft pull request.

```bash
vk issue <ISSUE_NUMBER> [--unattended]
```

- **`<ISSUE_NUMBER>`**: Integer GitHub issue number (e.g. `42`).
- **`--unattended`**: Non-interactive flag. The CLI enables this mode automatically when standard input is not a terminal.

### `vk review <PR>`

Processes review comments on an open factory pull request, applies fixes, updates the run log, and pushes commits.

```bash
vk review <PR_NUMBER> [--unattended]
```

### `vk ci-fix <PR>`

Attempts to resolve failed CI checks on a factory pull request (maximum 2 attempts).

```bash
vk ci-fix <PR_NUMBER> [--unattended]
```

## Exit Codes

| Code | Name                  | Description                                                                                                     |
| ---- | --------------------- | --------------------------------------------------------------------------------------------------------------- |
| `0`  | Success               | The operation completes, and the factory opens or updates a PR.                                                 |
| `2`  | Configuration Error   | A required environment variable (`GITHUB_TOKEN`, `VK_MODEL`) or `git` is missing, or the repository is invalid. |
| `3`  | Token Budget Exceeded | Execution stops because total LLM token output exceeds `VK_MAX_OUTPUT_TOKENS`.                                  |

## Environment Variables Reference

| Variable               | Required | Default      | Description                                                                                                                       |
| ---------------------- | -------- | ------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| `GITHUB_TOKEN`         | Yes      | —            | Authentication token with repository, issue, and PR write access.                                                                 |
| `VK_MODEL`             | Yes      | —            | Default model identifier in PydanticAI `provider:model` syntax (e.g. `google:gemini-3.5-flash` or `anthropic:claude-3-5-sonnet`). |
| `VK_MODEL_<CLAN>`      | No       | `VK_MODEL`   | Per-clan override (`CLASSIFIER`, `RESEARCHER`, `ANALYST`, `IMPLEMENTER`, `REVIEWER`, `TRIAGER`, `PR_WRITER`, `CI_DIAGNOSER`).     |
| `VK_BOT_LOGIN`         | No       | `None`       | GitHub login for the bot user.                                                                                                    |
| `VK_REPO`              | No       | Git `origin` | Target repository specified as `owner/repo`.                                                                                      |
| `VK_SETUP_COMMAND`     | No       | None         | Setup shell command that runs in fresh repository clones.                                                                         |
| `VK_BRANCH_PREFIX`     | No       | `vk/`        | Branch prefix for feature branches.                                                                                               |
| `VK_STATE_DIR`         | No       | `~/.vk`      | Storage location for clones, agent state, and memory.                                                                             |
| `VK_MAX_OUTPUT_TOKENS` | No       | `100000`     | Maximum token limit per agent execution.                                                                                          |
| `VK_LOG_LEVEL`         | No       | `INFO`       | Stderr log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`).                                                                           |

## Additional Reference Pages

- [Status Labels](/api-reference/status-labels/): Reference for status labels that Vishwakarma sets on GitHub issues.
