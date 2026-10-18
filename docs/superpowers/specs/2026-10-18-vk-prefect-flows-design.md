# Run VK from Prefect instead of GitHub Actions

## Intent

Today VK runs on GitHub Actions runners: labeling an issue `vk` triggers
`.github/workflows/vishwakarma.yml`, and submitting a review on a `vk/*` PR triggers
`.github/workflows/vishwakarma-review.yml`. The owner wants VK to run on Prefect instead. Both
workflows become Prefect flows that run on the existing Prefect Cloud work pool `vk-agents`.
This is for testing, so runs are started by hand. Scheduling may come later.

## Goals

- Two Prefect flows that do the same work as the two workflows:
  - **`vk-issue`** takes `issue_number: int` and runs `vk issue <n> --unattended`.
  - **`vk-review`** takes `pr_number: int` and runs `vk review <n> --unattended`.
- Both are deployed to the `vk-agents` pool with no schedule. They start on demand from the
  Prefect UI or with `prefect deployment run 'vk-issue/vk-issue' -p issue_number=42`.
- A failed run comments on the issue or PR with a link to the Prefect flow run. This replaces
  the old link to the Actions run.
- Turn off both GitHub VK workflows. Do not delete them yet; that happens in a later change.

## Non-goals

- Schedules, GitHub webhooks, or Prefect automations that trigger runs from GitHub events.
- Porting `ci.yml` or `pages.yml`. They stay on GitHub Actions.
- A `vk ci-fix` flow. No workflow exists for it today.
- Changes to VK's own pipeline code (`packages/vk/src/vk/`).

## Anti-goals

- A second Python project or lockfile. The owner was explicit: **one uv project.** The flows
  live under `packages/vk` and share `packages/vk/pyproject.toml` and the root `uv.lock`.
- Secrets in code, in the repo, or in deployment parameters.
- Using pip anywhere, including Prefect's `pip_packages` job variable. Python deps come from
  `uv sync --locked`.

## Known environment (verified 2026-10-18)

- Prefect Cloud account `e861a32c-182b-46fd-9e1c-d8ad40b9f903`, workspace
  `2fd4b32d-fb16-4dcf-afa7-139fb725d830`. API URL:
  `https://api.prefect.cloud/api/accounts/e861a32c-182b-46fd-9e1c-d8ad40b9f903/workspaces/2fd4b32d-fb16-4dcf-afa7-139fb725d830`.
  The API key is `PREFECT_API_KEY`, exported from the owner's `~/.zshrc`.
- Work pool `vk-agents` is type **`prefect:managed`** (serverless), status READY, with
  **pool concurrency limit 1**. Managed pools only run the `prefecthq/prefect[-client]` images
  in the pool's enum. No custom images.
- The repo is public at `https://github.com/sivadotblog/vishwakarma`, so the managed pool can
  pull code without credentials.
- VK reads its config from env (`packages/vk/src/vk/config.py`): `GITHUB_TOKEN`, `VK_MODEL`,
  `VK_REPO`, `VK_STATE_DIR`, `VK_BOT_LOGIN`, `GEMINI_API_KEY`, and `PYDANTIC_AI_NO_BANNER`.
  VK clones the target repo itself into `VK_STATE_DIR/work`. Its agents have a bash tool and
  may run `make check`, which needs `uv`, `make`, and Node (`.nvmrc` = 22).

## Decided by the owner

- **Serverless:** stay on the managed `vk-agents` pool.
- **Secrets:** stored as Prefect blocks. The owner creates and loads them.
- **One uv project:** `packages/vk/pyproject.toml` serves both `src/vk` and the flows.
- **Concurrency:** the pool's limit of 1 is the concurrency control. Drop the workflows'
  per-issue and per-PR concurrency groups.
- **Old workflows:** turn their triggers off now and delete them later.

## Design

### Layout

```
packages/vk/
  pyproject.toml          # gains a `prefect` dependency group
  src/vk/                 # unchanged
  prefect_flows/
    __init__.py
    flows.py              # vk_issue and vk_review flows plus shared helpers
    github_app.py         # mints a GitHub App installation token
    deploy.py             # registers both deployments (run locally)
  tests/test_prefect_flows.py
```

`prefect_flows` sits next to `src/`, not inside the `vk` package. It is never part of the
`vk` wheel. Add it to mypy's `files` in the root `pyproject.toml` and make it importable from
tests. The builder picks the mechanism (pytest `pythonpath` or similar).

### Dependencies

- Add **`prefect`** (3.x) to a `prefect` dependency group in `packages/vk/pyproject.toml`,
  using `uv add --package vk --group prefect prefect`. Justification for the PR: it is needed
  locally to deploy, typecheck, and test the flows. The managed image already ships Prefect at
  run time. Add the group to the default groups if needed so `make setup` and `make check`
  install it.
- No other new deps. `github_app.py` signs the JWT with `cryptography`, which is already in
  `uv.lock` and which Prefect depends on. HTTP calls use `httpx` (a Prefect dependency) or
  `requests` (a VK dependency), matching whatever the flow environment has.

### Two environments in one run

The managed pool runs the flow module with the image's own Python, which has Prefect but no
VK. So the flow module may import only the stdlib, Prefect, and Prefect's own dependencies
(`httpx`, `cryptography`). VK itself always runs as a subprocess inside the uv env:
`uv run --package vk vk ...`. It is never imported by the flow.

### Flow steps (same for both flows)

1. **Bootstrap the toolchain.** Install uv with its official installer, pinned to a version,
   then `make` and Node 22. Run `uv sync --locked` in the pulled checkout. This is a Prefect
   task with logged output. It replaces `actions/checkout`, `setup-uv`, and
   `make setup-python`; the checkout itself comes from the deployment's `from_source` pull.
2. **Load secrets** from the Prefect blocks and variables listed below.
3. **Mint a GitHub App installation token.** This replaces `actions/create-github-app-token`:
   - Create an RS256 JWT with `iss` = app id, `iat` = now − 60s, and `exp` = now + 9 min.
   - `GET /app` gives the app slug, so `VK_BOT_LOGIN` = `<slug>[bot]`.
   - `GET /repos/{owner}/{repo}/installation` gives the installation id.
   - `POST /app/installations/{id}/access_tokens` gives the token.
   - The token is valid for one hour, which covers the 60-minute run timeout.
4. **Run VK**: `uv run --package vk vk issue|review <n> --unattended`. Pass the env from the
   workflows: `GITHUB_TOKEN`, `VK_BOT_LOGIN`, `GEMINI_API_KEY`, `VK_MODEL`,
   `VK_REPO=sivadotblog/vishwakarma`, `VK_STATE_DIR` set to a fresh temp dir, and
   `PYDANTIC_AI_NO_BANNER=1`. Stream VK's stderr into the Prefect run logger and log its stdout
   (the final reply).
5. **On a nonzero exit**, comment on the issue or PR using the installation token:
   `The software factory run failed. Log: <flow run UI URL>`. Use
   `prefect.runtime.flow_run.ui_url` for the URL. Then fail the flow run. If the failure
   happens before a token exists, skip the comment and just fail. Note that the comment now
   comes from the VK app; the old workflows commented as `github-actions`.

Flow timeout is 3600s, matching `timeout-minutes: 60`. Flow names are `vk-issue` and
`vk-review`.

**Dropped from the workflows:** the labeler and reviewer permission checks (only the owner
starts runs now), the `vk/` branch check on reviews, the bot-reviewer check, and the
concurrency groups.

### Secrets and config (the owner creates these)

| Prefect object | Name                 | Holds                                           |
| -------------- | -------------------- | ----------------------------------------------- |
| Secret block   | `vk-app-private-key` | GitHub App private key (PEM)                    |
| Secret block   | `vk-gemini-api-key`  | `GEMINI_API_KEY`                                |
| Variable       | `vk_app_id`          | GitHub App id (`vars.VK_APP_ID`)                |
| Variable       | `vk_model`           | Optional. Defaults to `google:gemini-3.5-flash` |

The builder documents these names in the README so the owner can create them.

### Deployment

`packages/vk/prefect_flows/deploy.py` is run locally with
`uv run --package vk python packages/vk/prefect_flows/deploy.py`, with `PREFECT_API_URL` and
`PREFECT_API_KEY` in the env. It calls
`flow.from_source("https://github.com/sivadotblog/vishwakarma", entrypoint=...).deploy(...)`
for both flows with these settings:

- `work_pool_name="vk-agents"`
- image `prefecthq/prefect:3-python3.12`
- no schedule
- the git branch is a CLI option, default `main`, so an unmerged branch can be tested.
  *(Spec author's call)* The deployment name is the branch slug: `vk-issue/main` from `main`,
  `vk-issue/<branch-slug>` from a feature branch. That way a branch deploy never replaces the
  `main` one.

Managed runs pull code from GitHub, so flow changes must be pushed before they can run.

### Turning off the old workflows

Run `gh workflow disable vishwakarma.yml` and `gh workflow disable vishwakarma-review.yml`.
This leaves the files untouched, so deleting them later is a clean change. Do it once the
Prefect flows have completed one successful run.

### Docs

- `packages/vk/README.md`: add a "Run on Prefect" section covering prerequisites (blocks and
  variables), how to deploy, and how to start a run.
- `packages/vk/README.md` lines ~72-79 describe the two Actions workflows and how they mint a
  token. Mark them as turned off and point to the Prefect section.
- `CLAUDE.md` / `AGENTS.md` (`CLAUDE.md` is a symlink): the line saying the `vk` label
  triggers the workflow becomes wrong. Update it to say VK runs on demand through Prefect.
- *(Spec author's call)* `packages/vk/SPEC.md` and the Starlight site under
  `apps/web/src/content/docs/` also describe the label trigger. Leave them alone in this
  change, and update them in the later change that deletes the workflows. That keeps this PR
  Python-only.

### Tests

These go in `packages/vk/tests/test_prefect_flows.py`, with no network access and no Prefect
server:

- the JWT has the right claims and verifies against the matching public key
- the token-minting calls hit the right endpoints, with HTTP mocked
- the VK command and env are built correctly for `issue` and `review`
- a failing VK subprocess posts the failure comment and fails the run

`make check` must pass.

### Verification beyond `make check`

Order *(spec author's call)*:

1. Open the PR.
2. Deploy from the feature branch and run `vk-issue/<branch-slug>` on a throwaway issue.
   Success means VK finishes and opens a draft PR. A failure comment proves only the failure
   path.
3. Once the owner merges, deploy from `main`.
4. Run `gh workflow disable` on both workflows.

## Left to the builder

- How to install `make` and Node 22 in the container (apt, NodeSource, or a tarball), and how
  to handle the case where the container is not root.
- How `prefect_flows` becomes importable for pytest and mypy.
- How the two flows share code internally.
