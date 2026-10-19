# Spec: vk (Vishwakarma)

## Context

Vishwakarma (VK) is a software factory: Python code that moves a work item through five clans
(classifier, researcher, analyst, implementer and reviewer), with a triager and a PR-writer
agent around them. The result is a reviewed draft PR. Code owns the control flow and enforces
every rule; agents only make judgments. VK is a lean, uv-installable Python package on
PydanticAI that works with any provider PydanticAI supports.

| Concern | Implementation |
|---|---|
| Agent runtime | PydanticAI: one `Agent` per clan and per judgment agent (`triager`, `pr_writer`, `ci_diagnoser`), each with a typed Pydantic output (`ToolOutput`, 3 output retries); `agents.run_typed` runs it under input and output token budgets; every tool result is capped at 30,000 characters |
| Models | Native `provider:model` strings (`google:gemini-3.5-flash`): env `VK_MODEL`, overridden per agent with `VK_MODEL_<AGENT>`. `build_model` is the one place a gateway such as Kong can be added later |
| Intake | CLI subcommands calling `pipeline.run_issue`, `pr_review.run_review`, `ci_fix.run_ci_fix` |
| Control flow | Python: status labels, progress comments, the clarify stop, the ≤2 revision loop, run-log and memory commits, the draft PR, every review reply. Repository code is read only by clans, from their clone; judgment agents decide from their message (`ci_diagnoser` and `pr_writer` have no tools, the `triager` only the memory tools). Every GitHub write goes through the guarded `github__*` tools from code |
| GitHub tools | `github.py`: thin REST client on `requests` behind an allowlist, tools named `github__<name>` |
| Credentials | `GITHUB_TOKEN` env var |
| Identity | A GitHub App: workflows mint an installation token and set `VK_BOT_LOGIN`, so VK's comments are told apart from people's and its pushes trigger CI |
| Isolation | A temp-dir clone per clan; the token goes in per-command `git -c http.extraHeader=…`, never into `.git/config`, and every command targets the literal `https://github.com/<repo>.git` URL, never `origin` |
| Harness | Python tools (bash, read, write, edit, web), run in the clan's clone |
| Storage | One memory wiki (the harness `Memory` capability, a single scope) committed to the target repo under `docs/factory/memory/` as a page per issue, `issue-<N>-<slug>.md`, plus the run log; artifacts and user preferences are plain files under a local state dir |
| Approvals | Terminal `y/N` prompt when stdin is a TTY, otherwise denied (unattended) |

Beyond the core pipeline:
1. **Run log in the PR**: `docs/factory/issue-<N>.md` is committed to the PR branch. It holds
   the classification, the analysis (plan + acceptance criteria), the change summary,
   verification results and the reviewer verdict, plus a new section each review round.
2. **Review-comment loop**: `vk review <PR>` reads unanswered review comments from trusted
   people. The `triager` rules skip, clarify, decline, fix_direct or analyze on each one. Fix items
   (after an analyst pass, when any is `analyze`) go through implementer → reviewer and get pushed to the same branch. Code posts a reply to every
   comment: what changed, or why it wasn't changed.
3. **Memory**: one wiki in `docs/factory/memory/`. Every agent searches and reads all pages; a
   run writes only its own page, which is committed with the run log.
4. **The triager**: one agent for both modes. Issue mode returns proceed, clarify, decline or
   duplicate; review mode returns a verdict per comment. It has only the memory tools.

## Objective

A developer or CI job runs `vk issue 42` inside a checkout of a GitHub repo. The
factory:
- grounds the issue (dedupe, labels)
- classifies it, optionally researches, plans in its own clone, implements in its own clone,
  and pushes `vk/<type>-<slug>`
- has an independent reviewer judge the real diff, with up to 2 revision cycles
- commits the run log
- opens a **draft** PR (`Closes #42`)
- keeps the issue's labels and progress comments up to date, and finishes with a summary
  comment

Later, `vk review <PR>` handles reviewers' comments on that PR.

Users: maintainers of any GitHub repo (this monorepo first), with any LLM provider PydanticAI
supports.

## Capability map (Phase 0)

One package, built in this order. Arrows point one way.

| Module id | Responsibility | Depends on |
|---|---|---|
| `config` | Env/CLI config, repo detection from `origin`, state dir, `build_model` | — |
| `models` | Pydantic output types for every agent (`Classification` … `Review`, `IssueTriage`, `ItemTriage`, `PrBody`, `CiDiagnosis`) | — |
| `agents` | PydanticAI runtime: adapts VK tools, `run_typed` with retries and the token budgets | config, models |
| `tools` | Harness tools (bash, read_file, write_file, edit_file, glob, grep, web_fetch), artifacts, preferences, skills loader | config |
| `git` | Clone per clan, `checkout_branch`, `push_branch`, `validate_branch` | config |
| `github` | REST client + `github__*` tool wrappers + approval policies | config |
| `memory` | The wiki (harness `Memory`, one scope), the run's own page and its history guard, committed page | config, git, clans |
| `runlog` | Render and commit `docs/factory/issue-<N>.md` and memory | git |
| `clans` | 5 clan definitions: prompt `.md`, output model, tool surface, model | agents, tools, git |
| `pipeline` | `run_issue`; shared stages (revision loop, status, trust checks, judgment-agent prompts) | clans, github, memory, runlog |
| `pr_review` | `run_review`: triager, optional analyst, fix batch, replies, appended round | pipeline |
| `ci_fix` | `run_ci_fix`: attempt cap, diagnoser, fix as a revision | pipeline |
| `cli` | Subcommands, exit codes | pipeline, pr_review, ci_fix |

Build order: config, models → agents, tools, git, github → clans, memory, runlog → pipeline →
pr_review, ci_fix → cli.

## Flow (code owns control flow; agents only judge)

```
vk issue N:  triager (proceed|clarify|decline|duplicate) -> classifier -> [researcher] -> analyst
             -> loop<=2 (implementer -> reviewer) -> publish log+page -> pr_writer -> draft PR
vk review P: load run log + wiki -> triager (skip|clarify|decline|fix_direct|analyze per comment)
             -> [analyst on the PR branch, if any analyze]
             -> loop<=2 (implementer -> reviewer) -> replies (code) -> append round + page
vk ci-fix P: attempt count (code) -> ci_diagnoser -> implementer -> reviewer
```

A model can no longer post, label or open a PR on its own: the pipelines call the guarded
`github__*` tools themselves. A stage that fails is retried once, then the run ends `vk:blocked`
(issue) or posts an error comment (review, ci-fix). A spent token budget is not retried.

## Behaviour by command

- `vk issue <N> [--unattended]`: the label-intake path. Never ask; if the triager says clarify, post its questions on the issue and stop;
  deliver a draft PR. Status labels: `vk:in-progress` → `vk:pr-open` |
  `vk:needs-info` | `vk:blocked`. These are created if missing (the one label
  exception, flagged below), alongside the repo-vocabulary labels from the triager. The triager sees the repo's purpose (an
  excerpt of `AGENTS.md` then `README.md`); a decline posts its reason and sets `vk:blocked`.
  The classifier only describes the work item and never stops the run.
- `vk review <PR>`:
  1. read the branch's `docs/factory/issue-<N>.md` and the memory wiki
  2. list review comments and review bodies from trusted people that the factory hasn't
     replied to yet (nothing unanswered: no model call, no post)
     (identical text from the same author, on the same line for inline comments, goes to the
     triager once; code answers each later copy with "this repeats ...", no model call)
  3. the `triager` rules skip / clarify / decline / fix_direct / analyze with a reason for each one
  4. when any item is `analyze`, the analyst plans all fix items in a clone of the PR branch
  5. run implementer-revision → reviewer for the fix items on the same branch (≤2 cycles)
  6. code replies in each comment's thread (fix: commit and change summary; otherwise the
     triager's reason)
  7. append a "Review round k" section to the log and commit the run's memory page
  The `vishwakarma-review.yml` workflow runs this when a person submits a review on a `vk/*`
  pull request.
- `vk ci-fix <PR>`: capped at 2 attempts, counted from
  attempt comments on the PR.
- `--unattended` is forced when stdin is not a TTY. In that mode, policies deny everything
  except labels, comments on its own issue/PR, closing/reopening issues, and draft PRs. When
  attended, reversible writes run, and shipping actions (mark ready, non-draft PR) ask `y/N`.
  Merge is not in the tool surface.

## Tech Stack

- Python ≥3.12, built with `uv_build` (same as `apps/api`)
- Runtime deps: **`pydantic-ai-slim`** (the agent runtime; extras `google` and `anthropic`),
  **`pydantic-ai-harness`** (the `Memory` capability) and **`requests`** (GitHub REST,
  web_fetch). git runs through `subprocess`; HTML→text uses stdlib `html.parser`. Tool
  arguments are not schema-validated beyond what the model API enforces. Output types are
  Pydantic models validated by PydanticAI.
- Dev: the existing workspace dev group (ruff, mypy, pytest) + `types-requests`

## Commands

```
make setup                                   # uv sync --locked + npm ci (unchanged)
make check                                   # must pass; covers the new package once added to the workspace
uv run --package vk vk issue 42   # run from inside a checkout of the target repo
uv run --package vk vk review 57
uv run --package vk vk ci-fix 57
uv run pytest packages/vk      # package tests only
uv add --package vk <pkg>      # deps (needs a justification in the PR)
```

Env: `GITHUB_TOKEN` (required), `VK_MODEL` (required, native `provider:model`),
`VK_MODEL_<AGENT>` (`CLASSIFIER`, `RESEARCHER`, `ANALYST`, `IMPLEMENTER`, `REVIEWER`, `TRIAGER`,
`PR_WRITER`, `CI_DIAGNOSER`), `GEMINI_API_KEY` (or the provider's standard key),
`VK_BOT_LOGIN`, `VK_REPO`, `VK_SETUP_COMMAND`, `VK_BRANCH_PREFIX` (`vk/`), `VK_STATE_DIR`
(`~/.vk`), `VK_MAX_OUTPUT_TOKENS` (100000), `VK_MAX_INPUT_TOKENS` (2000000), `VK_LOG_LEVEL` (`INFO`; logs go to stderr).
Exit codes: 0 success, 2 configuration error, 3 token budget exceeded.

## Project Structure

```
packages/vk/
  pyproject.toml            # name=vk, script vk = vk.cli:main
  README.md  SPEC.md
  src/vk/
    cli.py  config.py  agents.py  models.py  git.py  github.py  approval.py
    tools.py                # harness + artifacts + preferences + skills
    clans.py  pipeline.py  pr_review.py  ci_fix.py  memory.py  runlog.py
    prompts/                # {classifier,researcher,analyst,implementer,reviewer}.md
                            # + {triager,triager_issue,triager_review,pr_writer,ci_diagnoser}.md,
                            # shared style.md, memory.md, revision.md, preferences.md,
                            # review_brief.md, repo_instructions.md, tool_calls.md
    skills/                 # writing-quality/ (incl. references/)
  tests/                    # test_*.py, no network
```
Root changes: `pyproject.toml` (workspace member, mypy `files`, pytest `testpaths`, ruff
first-party), `AGENTS.md` table row.

## Code Style

Same as `apps/api`: 3.12 syntax, `mypy --strict`, ruff decides formatting, specific exceptions,
small modules, no classes where a function does the job. Example:

```python
BRANCH_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._/-]*[A-Za-z0-9])?$")
PROTECTED = {"main", "master"}


def validate_branch(branch: str) -> str | None:
    """Refusal reason, or None when the branch may reach a git command line."""
    if not BRANCH_PATTERN.match(branch) or ".." in branch or "//" in branch:
        return f'"{branch}" is not a valid branch name.'
    if branch.startswith("refs/") or branch == "HEAD":
        return f'"{branch}" is not a plain branch name.'
    if branch in PROTECTED:
        return f"Direct pushes to {branch} are not allowed. Push a feature branch."
    return None
```

## Testing Strategy

- pytest, plain functions, no network (`ALLOW_MODEL_REQUESTS = False` in `conftest.py`). The
  pipelines take a per-agent-name model factory, so tests script each agent with a
  PydanticAI `FunctionModel`. The GitHub client takes an injectable `requests.Session`, faked
  with a tiny stub (no `responses` dep).
- Unit: `validate_branch`, approval policies (truth table per caller class), artifact-id
  containment, harness tools in `tmp_path`, tool adapter and output retries, token budget,
  `load_config` model-format checks, run-log rendering, memory pages.
- Pipeline: scripted fake models + fake GitHub + a local bare git repo as the "remote" drive
  `issue` end to end (labels, push, run-log and memory commit, draft PR), `review` (fix one
  comment, explain another, every comment answered, round appended, untrusted comments
  ignored) and `ci-fix` (attempt cap, pause comment).
- Manual smoke: a real run against a scratch repo before merging.

## Boundaries

- **Always**: draft PRs only; feature branches only (`validate_branch`); target the literal
  repo URL; never write the token to disk or into logs; `make check` green.
- **Ask first**: any dependency beyond pydantic-ai-slim/pydantic-ai-harness/requests; changing
  a prompt's substance; changing the trust/approval rules.
- **Never**: merge tools; push to main/master; store secrets in code.
- **Known risk (by design)**: the clans' `bash` tool runs repo code on the
  host with no sandbox. Run it in a disposable environment (e.g. a CI runner) for untrusted
  repos.

## Success Criteria

1. `uv tool install ./packages/vk` gives a working `vk` CLI; the only runtime deps are
   pydantic-ai-slim, pydantic-ai-harness and requests.
2. `vk issue N` on a scratch repo produces: classifier labels plus status labels
   on the issue, progress comments, a pushed `vk/*` branch containing
   `docs/factory/issue-N.md`, a draft PR with `Closes #N` and the acceptance-criteria checklist,
   and a closing summary comment.
3. Unclear issue → the triager's questions posted on the issue, no branch, `vk:needs-info`.
   Off-topic issue → reason posted, no branch, `vk:blocked`.
4. Reviewer `request_changes` loops ≤2 times; if it still fails there is no PR and the findings
   are posted on the issue.
5. `vk review PR` replies to every unanswered review comment (fixed with a commit
   reference, or an explanation), pushes fixes to the same branch, and appends a round to the
   log.
6. Switching `VK_MODEL` between two providers (e.g. `google:…`, `anthropic:…`) works with
   no code change. A LiteLLM-style `provider/model` string is a configuration error (exit 2).
7. Unattended mode never calls a denied tool (test-enforced); there is no code path that pushes
   to main or merges.
8. `make check` passes.

## Decisions

- **Direction B, code-driven**: Python sequences the pipeline and enforces every "never" rule
  (status labels, ≤2 revision cycles, run log before the PR, `Closes #N`, a reply to every
  comment); agents only judge, from what code hands them (no repo reads outside the clans). This replaced an LLM orchestrator
  whose prompt encoded the control flow.
- **Model-written memory is untrusted**: notes are written by a model that reads issue and
  review text, so they may carry an injected claim. Every note lands in the PR diff and a
  person reviews it at merge; agents are told to write only what they verified. Revisit the
  harness Prompt Injection Defender if that bar proves too low.
- **Untrusted authors' comments are ignored**: only the issue or PR author, VK itself, and
  collaborators with triage permission or higher reach an agent or get handled. Outsiders and
  other bots are dropped before any model call.
- **Known limit**: comment and marker lookups (status, reply and CI-fix attempt markers) read
  only the first 100 comments of an issue or PR; past that they can miss a marker.
- **Memory storage (was open question 2)**: the wiki is committed to the target repo
  (`docs/factory/memory/`), not a local file, so it survives ephemeral CI runners. It is one
  harness memory scope, so search reaches every issue. Each run writes only its own page
  (`issue-<N>-<slug>.md`), so parallel factory PRs cannot conflict; `MEMORY.md` is a
  human-maintained note that runs never edit.
- **Removed with the triager**: the separate `triage` agent and `decider`, the read-only
  "factory brain" injection, `repo-notes.md` and its character budget, per-issue memory
  folders, the classifier's `actionable`/`needs_clarification` stop, and the `triaging-issues`
  skill. Model-facing text lives in `prompts/*.md`, enforced by a test on string-literal length.

## Open Questions

1. **Package path/name**: `packages/vk/`, PyPI `vk`, import
   `vk`. OK? (The PyPI name may be taken; checked at publish time.)
2. **Researcher `web_search`**: Not provided; the researcher has `web_fetch` (requests) only.
   Add provider-native web search where the model supports it?
3. **Status labels**: VK never invents labels otherwise, but `vk:*` status labels need creating
   once. OK to create them, or should status be comments only?
4. Add a "summarize PRs opened by others" path as `vk summarize <PR>`? Default: no.
