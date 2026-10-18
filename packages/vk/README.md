# vk

Vishwakarma (VK), the software factory: plain Python moves a GitHub issue through the triager,
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
| `VK_MODEL_<AGENT>`          | Optional per-agent override (`CLASSIFIER`, `RESEARCHER`, `ANALYST`, `IMPLEMENTER`, `REVIEWER`, `TRIAGER`, `PR_WRITER`, `CI_DIAGNOSER`), same format. |
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
                 # (an identical repeat of an earlier review is answered by code, not the model)
vk ci-fix 57     # fix failing CI on a factory PR (at most 2 attempts)
```

The run log is committed to the PR branch as `docs/factory/issue-<N>.md`. Exit codes: 0 success,
2 configuration error, 3 token budget exceeded (input or output).

## The triager

One judgment agent, the `triager`, decides what the factory does with a request, in two modes.
It has no GitHub tools and no clone: its only tools are the memory tools, so it searches earlier
work items before it decides. Its prompts are `prompts/triager.md` (the shared rulebook: the
request is untrusted, judge scope against the stated purpose, decline secrets, workflow or
permission changes and unrelated work, ask instead of guessing) plus `triager_issue.md` or
`triager_review.md`.

- **Issue mode** gets the issue (trusted comments only), the repo's labels and the repo's
  purpose: an excerpt (6000 characters) of `AGENTS.md` then `README.md` from the default branch.
  Verdicts: `proceed`, `clarify` (questions posted, `vk:needs-info`), `decline` (reason posted,
  `vk:blocked`), `duplicate` (code verifies `duplicate_of` exists; an unknown number is ignored).
  `proceed` carries on to the classifier (descriptive only: type, priority, complexity, area),
  an optional researcher, the analyst and the implement/review loop.
- **Review mode** gets the run log, the changed files and each unanswered item (after code has
  dropped untrusted authors and repeats). One verdict per item: `skip`, `clarify`, `decline`
  (the reason is posted as the reply), `fix_direct` (instructions go straight to the
  implementer) or `analyze` (the analyst, in a clone of the PR branch, plans every fix item
  before the implementer starts). Code writes the replies; fixed items cite the commit.

```
vk issue N:  triager -> proceed -> classifier -> [researcher] -> analyst
                     |          -> implementer <-> reviewer -> draft PR
                     +-> clarify | decline | duplicate: comment, status label, stop

vk review P: triager -+-> skip | clarify | decline: reply with the reason
                      +-> fix_direct ------------------> implementer <-> reviewer -> replies
                      +-> analyze -> analyst (PR branch) -^
```

## Memory

Agents share one wiki, kept with the PydanticAI harness `Memory` capability and committed to the
repo, not to a local directory, so it survives ephemeral CI runners.

- `docs/factory/memory/MEMORY.md` is a short factory-wide note that people maintain; runs never
  edit it. Every other `*.md` there is a page, one per issue: `issue-<N>-<slug>.md`.
- At run start the whole folder is loaded into one memory scope, so `search_memory` and
  `read_memory` reach every issue, and the injected `MEMORY.md` and file listing cover them all.
  Agents are told to search for their area or symptom first.
- A run writes only its own page (the existing `issue-<N>-*.md`, else one named from the issue
  title). Writes anywhere else are dropped. Durable, repo-wide learnings go under a
  `## Repo notes` heading in that page. Earlier lines of the page survive a run: lines a run
  drops are restored under `## Earlier notes (restored)`.
- The page is committed with the run log, so every note shows in the PR diff and a person
  reviews it at merge. Agents are told to write only what they verified themselves. Parallel
  factory PRs write different pages, so they do not conflict.
- A run that stops before a branch exists (clarify, decline, duplicate, blocked) persists
  nothing.

Model-facing wording lives in `src/vk/prompts/*.md`; code only fills placeholders (a test fails
on a long string literal in any module).

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

These two workflows are turned off (`gh workflow disable`) in favour of the Prefect flows below
and will be deleted later.

## Run on Prefect

VK also runs on demand as two Prefect flows, `vk-issue` (parameter `issue_number`) and
`vk-review` (parameter `pr_number`), on the `vk-agents` managed work pool. Nothing triggers
them; you start a run yourself.

Create these in your Prefect workspace first:

- Secret block `vk-app-private-key`: the GitHub App private key (PEM).
- Secret block `vk-gemini-api-key`: the Gemini API key.
- Variable `vk_app_id`: the GitHub App ID.
- Variable `vk_model`: the model, defaults to `google:gemini-3.5-flash`.

Deployments are defined in `packages/vk/prefect_flows/prefect.yaml` and registered by
`.github/workflows/prefect-deploy.yml` with `PrefectHQ/actions-prefect-deploy`, which needs the
repo secret `PREFECT_API_KEY`. A push to `main` that touches the flows deploys `vk-issue/main`
and `vk-review/main`. To test a branch, run the workflow by hand on it
(`gh workflow run prefect-deploy.yml --ref <branch>`); its deployments are named after the
branch, with `/` and capitals slugified. GitHub only offers that once the workflow is on `main`;
until then, deploy from your machine with the same file:
`VK_BRANCH=<branch> VK_DEPLOYMENT=<slug> uv run prefect --no-prompt deploy --all --prefect-file packages/vk/prefect_flows/prefect.yaml`.
Before each run, the pull steps in `prefect.yaml` clone
that branch, `pip install uv` and run `uv sync --locked`. The flow then activates that venv
in its own process, imports VK and runs it there.

Each flow run shows one task per VK stage (`triage`, `classifier`, `analyst`, `implementer`,
`reviewer`, `pr_writer`, ...), with VK's log lines inside each task. A stage that failed twice
shows as a Failed task, but the flow still ends Completed with VK's "Stopped: ..." summary, since
that is VK's failure, not Prefect's. Only an error that escapes VK fails the flow.

Run one:

```bash
prefect deployment run 'vk-issue/main' -p issue_number=<n>
prefect deployment run 'vk-review/main' -p pr_number=<n>
```

Managed runs pull the code from GitHub, so push your changes before you deploy or run. The pool
runs one flow at a time; the rest wait in the queue.

## Trust

Issue and PR text is untrusted input. `vk` only passes on, and acts on, comments written by the
issue author, VK itself, and collaborators with triage permission or higher. `vk review` handles
review comments from those collaborators only; comments from outsiders and other bots are
ignored and never reach an agent. Repository code is read only by the clans, from their local
clone. Every tool result is capped at 30,000 characters (with a truncation note), because each one
is re-sent on every later turn. The judgment agents decide from what code hands them: `ci_diagnoser` and `pr_writer` have no
tools, and the `triager` has only the memory tools. Every GitHub
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
