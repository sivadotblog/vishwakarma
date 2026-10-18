---
title: API Reference
description: Command-line reference, exit codes, and environment variable specifications for `vk`.
---

This section documents the `vk` command-line interface, exit codes, and environment variables.

## CLI Commands

The `vk` CLI must be executed inside a local checkout of the target repository.

### `vk issue <N>`

Processes an unhandled GitHub issue end-to-end (triage, planning, implementation, verification, review) and opens a draft pull request.

```bash
vk issue <ISSUE_NUMBER> [--unattended]
```

- **`<ISSUE_NUMBER>`**: Integer GitHub issue number (e.g. `42`).
- **`--unattended`**: Non-interactive flag. Automatically enabled when standard input is not a terminal.

### `vk review <PR>`

Processes review comments posted on an existing factory pull request, applies necessary fixes, updates the run log, and pushes commits.

```bash
vk review <PR_NUMBER> [--unattended]
```

### `vk ci-fix <PR>`

Attempts to automatically resolve failing CI checks on a factory pull request (maximum 2 attempts).

```bash
vk ci-fix <PR_NUMBER> [--unattended]
```

## Exit Codes

| Code | Name                  | Description                                                                                                |
| ---- | --------------------- | ---------------------------------------------------------------------------------------------------------- |
| `0`  | Success               | Operation completed successfully, PR opened or revised.                                                    |
| `2`  | Configuration Error   | Missing required environment variables (`GITHUB_TOKEN`, `VK_MODEL`), missing `git`, or invalid repository. |
| `3`  | Token Budget Exceeded | Execution aborted because cumulative LLM token output exceeded `VK_MAX_OUTPUT_TOKENS`.                     |

## Environment Variables Reference

| Variable               | Required | Default      | Description                                                                                                                             |
| ---------------------- | -------- | ------------ | --------------------------------------------------------------------------------------------------------------------------------------- |
| `GITHUB_TOKEN`         | Yes      | —            | Authentication token with repository, issue, and PR write access.                                                                       |
| `VK_MODEL`             | Yes      | —            | Default model identifier in PydanticAI `provider:model` syntax (e.g. `google:gemini-3.5-flash` or `anthropic:claude-3-5-sonnet`).       |
| `VK_MODEL_<CLAN>`      | No       | `VK_MODEL`   | Per-clan override (`CLASSIFIER`, `RESEARCHER`, `ANALYST`, `IMPLEMENTER`, `REVIEWER`, `TRIAGE`, `PR_WRITER`, `DECIDER`, `CI_DIAGNOSER`). |
| `VK_BOT_LOGIN`         | No       | `None`       | GitHub login for the bot user.                                                                                                          |
| `VK_REPO`              | No       | Git `origin` | Target repository specified as `owner/repo`.                                                                                            |
| `VK_SETUP_COMMAND`     | No       | None         | Setup shell command executed in fresh repository clones.                                                                                |
| `VK_BRANCH_PREFIX`     | No       | `vk/`        | Branch prefix used for generated feature branches.                                                                                      |
| `VK_STATE_DIR`         | No       | `~/.vk`      | Storage location for clones, agent state, and working memory.                                                                           |
| `VK_MAX_OUTPUT_TOKENS` | No       | `100000`     | Maximum token limit per agent execution.                                                                                                |
| `VK_LOG_LEVEL`         | No       | `INFO`       | Stderr log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`).                                                                                 |

## Additional Reference Pages

- [Status Labels](/api-reference/status-labels/): Reference for status labels set by Vishwakarma on GitHub issues.
