# Factory run log: issue #46

## Summary

Add a 'Run VK in Prefect' how-to guide to the documentation site covering flow definitions, workspace setup, deployments, execution, and configuration.

Reviewer verdict: approve.

## Classification

- type: feature
- priority: medium
- complexity: small
- affected_area: apps/web

## Analysis

### Problem

The documentation site does not explain how to run Vishwakarma as Prefect flows, causing the relevant instructions to be hidden in the backend package's README and flow code. A new How-to page is needed on the web documentation site, written in ASD-STE100 Simplified Technical English, containing the execution, deployment, workspace setup, and configuration steps.

### Approach

Create a new how-to guide matching the Astro Starlight documentation structure. Apply ASD-STE100 Simplified Technical English by using direct commands, active voice, and short sentences. Source the technical constraints verbatim from the README, workflow configurations, and `flows.py`. Rely on Astro's sidebar autogeneration to automatically index the new file.

### Plan

1. Create `apps/web/src/content/docs/how-to-guides/run-in-prefect.md`.
2. Add standard Astro Starlight frontmatter (`title: Run VK in Prefect`, `description: How to run Vishwakarma as a Prefect flow.`).
3. Insert the content drafted in the artifact, which describes the flow parameters, the required Secrets/Variables, deployment mechanics, CLI/UI start commands, execution steps, and configuration behavior.
4. Use a relative anchor link `[Change the LLM Model Used by VK](./index.md#how-to-change-the-llm-model-used-by-vk)` to avoid duplicating settings documentation.
5. Run `make check` from the repository root to verify that the Astro site builds without linting or checking errors.

### Acceptance criteria

- [x] The file `apps/web/src/content/docs/how-to-guides/run-in-prefect.md` exists.
- [x] The document explicitly names the `vk-issue` and `vk-review` flows, their parameters, and the `vk-agents` work pool, clarifying that no automatic triggers exist.
- [x] The workspace setup section correctly lists the `vk-app-private-key` and `vk-gemini-api-key` Secret blocks, and the `vk_app_id` Variable.
- [x] The deployments section covers `prefect.yaml`, the `prefect-deploy.yml` workflow, branch behavior, and the `uv run prefect` manual deployment command.
- [x] The document provides exact CLI commands to start a run and mentions the Prefect UI method.
- [x] The execution section lists the clone and `uv sync` pull steps, the token minting, Prefect tasks representation of stages, and the failure comment behavior.
- [x] The settings section clarifies that timeouts, budgets, and models originate from `packages/vk/src/vk/vk.toml`, linking to existing docs where applicable.
- [x] The content follows ASD-STE100 principles (short, active, direct sentences).
- [x] `make check` runs successfully.

## Implementation

Branch `vk/feature-run-in-prefect` (base `main`).

### Change summary

- `apps/web/src/content/docs/how-to-guides/run-in-prefect.md`: Added a how-to guide covering execution, deployment, workspace setup, and configuration steps for Vishwakarma using Prefect flows.

### Verification

- `npm run format -w web`: Formatted the newly added markdown file successfully using Prettier.
- `npm run lint -w web && npm run check -w web && npm run build -w web`: All matched files used Prettier formatting, Astro checks passed with 0 errors/warnings, and the static files built successfully.
- `uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest`: Linting, type checking, and all 276 tests passed successfully.

### Deviations

- None

## Review

Verdict: **approve**

The implementation completely and accurately adds the 'Run VK in Prefect' how-to guide to `apps/web/src/content/docs/how-to-guides/run-in-prefect.md`. The documentation matches the technical details from the codebase (`prefect.yaml`, `prefect-deploy.yml`, `flows.py`, and `vk.toml`), adheres to ASD-STE100 Simplified Technical English, cleanly links to existing guide anchors, and passes all repository formatting, type checking, testing, and documentation build verification checks.

### Criteria results

- pass: The file `apps/web/src/content/docs/how-to-guides/run-in-prefect.md` exists. (The file was created on branch `vk/feature-run-in-prefect` at `apps/web/src/content/docs/how-to-guides/run-in-prefect.md`.)
- pass: The document explicitly names the `vk-issue` and `vk-review` flows, their parameters, and the `vk-agents` work pool, clarifying that no automatic triggers exist. (The introductory section explicitly lists `vk-issue` (parameter `issue_number`), `vk-review` (parameter `pr_number`), the `vk-agents` managed work pool, and states that nothing triggers them automatically.)
- pass: The workspace setup section correctly lists the `vk-app-private-key` and `vk-gemini-api-key` Secret blocks, and the `vk_app_id` Variable. (The 'Set up the Workspace' section lists `vk-app-private-key` (Secret block), `vk-gemini-api-key` (Secret block), and `vk_app_id` (Variable).)
- pass: The deployments section covers `prefect.yaml`, the `prefect-deploy.yml` workflow, branch behavior, and the `uv run prefect` manual deployment command. (The 'Understand Deployments' section covers `packages/vk/prefect_flows/prefect.yaml`, `.github/workflows/prefect-deploy.yml`, branch deployments, and includes the manual command `VK_BRANCH=<branch> VK_DEPLOYMENT=<slug> uv run prefect --no-prompt deploy --all --prefect-file packages/vk/prefect_flows/prefect.yaml`.)
- pass: The document provides exact CLI commands to start a run and mentions the Prefect UI method. (The 'Start a Run' section includes `prefect deployment run 'vk-issue/main' -p issue_number=<n>` and `prefect deployment run 'vk-review/main' -p pr_number=<n>`, along with step-by-step instructions for running via the Prefect UI.)
- pass: The execution section lists the clone and `uv sync` pull steps, the token minting, Prefect tasks representation of stages, and the failure comment behavior. (The 'What a Run Does' section specifies the pull steps (git clone, uv installation, nodejs-wheel installation, `uv sync --locked`), virtualenv setup and GitHub App token minting, Prefect tasks per pipeline stage, and the failure comment behavior if an unhandled error occurs.)
- pass: The settings section clarifies that timeouts, budgets, and models originate from `packages/vk/src/vk/vk.toml`, linking to existing docs where applicable. (The 'Configure Settings' section notes that models, token budgets, and `flow_timeout_s` originate from `packages/vk/src/vk/vk.toml` rather than Prefect variables, and links to `./index.md#how-to-change-the-llm-model-used-by-vk`.)
- pass: The content follows ASD-STE100 principles (short, active, direct sentences). (The document uses direct, active-voice, short sentences matching Simplified Technical English and the existing documentation conventions.)
- pass: `make check` runs successfully. (Ran Prettier formatting check, Astro diagnostics (`astro check`), and Astro build (`astro build`), resulting in 0 errors and generating 13 pages (including `/how-to-guides/run-in-prefect/index.html`). Ran Python ruff check/format, mypy typecheck, and pytest (276 passed).)
