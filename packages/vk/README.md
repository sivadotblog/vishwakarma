# vk

Vishwakarma (VK), the software factory: plain Python moves a GitHub issue through triage,
classifier, researcher, analyst, implementer and reviewer agents and delivers a reviewed draft
pull request. Code owns the control flow (labels, comments, revision loop, pushes, PR); the
agents only make judgments. It runs on [PydanticAI](https://ai.pydantic.dev), so any provider
PydanticAI supports works. See [SPEC.md](SPEC.md).

## Install

```bash
uv tool install ./packages/vk      # or, in this monorepo: make setup
```

Runtime dependencies are `pydantic-ai-slim`, `pydantic-ai-harness` and `requests`. `git` must be
on the PATH.

## Environment

| Variable                    | Meaning                                                    |
| --------------------------- | ---------------------------------------------------------- |
| `GITHUB_TOKEN`              | Required. Token with repo, issues and pull request access. A GitHub App installation token works. |
| `VK_MODEL`                  | Required. Native `provider:model` string, e.g. `google:gemini-3.5-flash`. LiteLLM-style `provider/model` strings are rejected (exit 2). |
| `VK_MODEL_<AGENT>`          | Optional per-agent override (`CLASSIFIER`, `RESEARCHER`, `ANALYST`, `IMPLEMENTER`, `REVIEWER`, `TRIAGE`, `PR_WRITER`, `DECIDER`, `CI_DIAGNOSER`), same format. |
| `GEMINI_API_KEY`            | Key for `google:` models. Other providers use their standard variable, e.g. `ANTHROPIC_API_KEY`. |
| `VK_REPO`                   | Optional `owner/name`; default is read from the `origin` remote. |
| `VK_SETUP_COMMAND`          | Optional command run in each fresh clone (install deps).   |
| `VK_BRANCH_PREFIX`          | Default `vk/`.                                             |
| `VK_BOT_LOGIN`              | Optional login VK acts as, e.g. `my-app[bot]`; default is `GET /user`. Required for GitHub App tokens, which cannot call `/user`. Commits are authored as this bot user (looked up via `GET /users/{login}`); if that fails, as `vk[bot]`. |
| `VK_STATE_DIR`              | Default `~/.vk` (artifacts, clones, user preferences).     |
| `VK_MAX_OUTPUT_TOKENS`      | Output token budget per agent run, default 100000.         |
| `VK_MAX_INPUT_TOKENS`       | Input token budget per agent run, default 2000000. Input is re-sent on every turn, so it grows fastest; one implementer run on #17 used about 1.05M. Exceeding either budget exits 3. |
| `VK_LOG_LEVEL`              | Log level for stderr logs (incl. token usage), default `INFO`. |

A gateway such as Kong can be added later in `build_model` (`config.py`), the one place that turns
a model string into a PydanticAI model.

## Commands

Run from inside a checkout of the target repo. Each accepts `--unattended`, which is forced
whenever stdin is not a terminal.

```bash
vk issue 42      # triage, plan, implement, review, open a draft PR (Closes #42)
vk review 57     # answer review comments on a factory PR, push fixes, log the round
vk ci-fix 57     # fix failing CI on a factory PR (at most 2 attempts)
```

The run log is committed to the PR branch as `docs/factory/issue-<N>.md`. Exit codes: 0 success,
2 configuration error, 3 token budget exceeded (input or output).

## Memory

Each agent keeps notes with the PydanticAI harness `Memory` capability, and the notes are
committed to the repo, not to a local directory, so they survive ephemeral CI runners.

- `docs/factory/memory/issue-<N>/` is the notebook for issue N: `MEMORY.md` for the work item
  and `repo-notes.md` for durable, repo-wide learnings. A run writes only its own issue's
  folder, so parallel factory PRs never conflict.
- Every run also reads the other issues' `repo-notes.md` files (newest first, bounded) as a
  read-only "factory brain" in each agent's instructions.
- The notebook is committed with the run log, so every note shows in the PR diff and a person
  reviews it at merge. Agents are told to write only what they verified themselves.
- A run that stops before a branch exists (needs-info, duplicate, blocked) persists nothing.

Per-user PR-writing preferences, if any, are read from `$VK_STATE_DIR/user-preferences/` and
applied only to attended runs.

## GitHub App identity and the review trigger

VK acts as its own GitHub App rather than a person, so it can tell its own comments from yours
and its pushes trigger CI (the built-in `GITHUB_TOKEN` does not). Create an app with Contents,
Issues and Pull requests read/write, and Checks, Actions and Metadata read; install it on the
repo; add the variable `VK_APP_ID` and the secret `VK_APP_PRIVATE_KEY`. The workflows mint a
token with `actions/create-github-app-token` and set `VK_BOT_LOGIN` to `<app-slug>[bot]`.

Two workflows are shipped in this repo:

- `.github/workflows/vishwakarma.yml`: labeling an issue `vk` runs `vk issue`.
- `.github/workflows/vishwakarma-review.yml`: submitting a review on a `vk/*` pull request runs
  `vk review`. Reviews by bots do not retrigger it, so VK's own replies cannot loop.

Both only run for people with at least triage permission.

## Trust

Issue and PR text is untrusted input. `vk` only passes on, and acts on, comments written by the
issue author, VK itself, and collaborators with triage permission or higher. `vk review` handles
review comments from those collaborators only; comments from outsiders and other bots are
ignored and never reach an agent. Repository code is read only by the clans, from their local
clone. Every tool result is capped at 30,000 characters (with a truncation note), because each one
is re-sent on every later turn. The judgment agents decide from what code hands them: `decider`, `ci_diagnoser` and
`pr_writer` have no tools, and `triage` has only the read-only issue and label tools. Every GitHub
write comes from code, through the approval policies.

## Example GitHub Actions workflow

Documentation only; copy it into your own repo's `.github/workflows/`. See
`.github/workflows/vishwakarma.yml` for the full version with the permission check.

```yaml
name: vishwakarma
on:
  issues:
    types: [labeled]
jobs:
  issue:
    if: github.event.label.name == 'vk'
    runs-on: ubuntu-latest
    timeout-minutes: 60
    permissions: { contents: read, issues: write }
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v10.3.0
      - run: uv tool install ./packages/vk
      - id: app-token
        uses: actions/create-github-app-token@v3
        with:
          app-id: ${{ vars.VK_APP_ID }}
          private-key: ${{ secrets.VK_APP_PRIVATE_KEY }}
      - run: vk issue ${{ github.event.issue.number }} --unattended
        env:
          GITHUB_TOKEN: ${{ steps.app-token.outputs.token }}
          VK_BOT_LOGIN: ${{ steps.app-token.outputs.app-slug }}[bot]
          PYDANTIC_AI_NO_BANNER: "1"
          VK_MODEL: google:gemini-3.5-flash
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
```

## Warning: no sandbox

The agents' `bash` tool runs repository code directly on the host, with no sandbox. Run the
factory only in a disposable environment such as a CI runner, especially for untrusted
repositories. The GitHub token is never written to disk or passed to agent commands.
