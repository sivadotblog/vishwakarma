# vk

Vishwakarma (VK), the software factory: an orchestrator agent moves a GitHub
issue through classifier, researcher, analyst, implementer and reviewer clans and delivers a
reviewed draft pull request. Any LLM supported by LiteLLM works. See [SPEC.md](SPEC.md).

## Install

```bash
pip install ./packages/vk      # or, in this monorepo: make setup
```

Runtime dependencies are `litellm` and `requests` only. `git` must be on the PATH.

## Environment

| Variable                    | Meaning                                                    |
| --------------------------- | ---------------------------------------------------------- |
| `GITHUB_TOKEN`              | Required. Token with repo, issues and pull request access. |
| `VK_MODEL`             | Required. Any LiteLLM model string, e.g. `anthropic/...`.  |
| `VK_MODEL_<CLAN>`   | Optional per-clan override (`ORCHESTRATOR`, `CLASSIFIER`, `RESEARCHER`, `ANALYST`, `IMPLEMENTER`, `REVIEWER`). |
| provider API key            | The provider's standard LiteLLM variable, e.g. `ANTHROPIC_API_KEY`. |
| `VK_REPO`              | Optional `owner/name`; default is read from the `origin` remote. |
| `VK_SETUP_COMMAND`     | Optional command run in each fresh clone (install deps).   |
| `VK_BRANCH_PREFIX`     | Default `vk/`.                                        |
| `VK_BOT_LOGIN`         | Optional login VK acts as, e.g. `my-app[bot]`; default is `GET /user`. Required for GitHub App tokens. |
| `VK_STATE_DIR`         | Default `~/.vk` (brain, artifacts, clones).  |
| `VK_MAX_OUTPUT_TOKENS` | Output token budget per agent run, default 100000.         |
| `VK_LOG_LEVEL`         | Log level for stderr logs (incl. token usage), default `INFO`. |

## Commands

Run from inside a checkout of the target repo. Each accepts `--unattended`, which is forced
whenever stdin is not a terminal.

```bash
vk issue 42      # triage, plan, implement, review, open a draft PR (Closes #42)
vk review 57     # answer review comments on a factory PR, push fixes, log the round
vk ci-fix 57     # fix failing CI on a factory PR (at most 2 attempts)
```

The run log is committed to the PR branch as `docs/factory/issue-<N>.md`. Exit codes: 0 success,
2 configuration error, 3 token budget exceeded.

## Example GitHub Actions workflow

Documentation only; copy it into your own repo's `.github/workflows/`.

```yaml
name: vishwakarma
on:
  issues:
    types: [labeled]
jobs:
  issue:
    if: github.event.label.name == 'vk'
    runs-on: ubuntu-latest
    permissions: { contents: write, issues: write, pull-requests: write }
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv tool install ./packages/vk
      - run: vk issue ${{ github.event.issue.number }} --unattended
        env:
          GITHUB_TOKEN: ${{ secrets.VK_GITHUB_TOKEN }}
          VK_MODEL: anthropic/claude-sonnet-4-5
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

## Warning: no sandbox

The clans' `bash` tool runs repository code directly on the host, with no sandbox. Run the
factory only in a disposable environment such as a CI runner, especially for untrusted
repositories. The GitHub token is never written to disk or passed to clan commands.
