# Factory run log: issue #43

## Summary

Add a Troubleshooting page to the docs site covering exit codes, status labels, and Prefect failures.

Reviewer verdict: approve.

## Classification

- type: feature
- priority: medium
- complexity: small
- affected_area: docs

## Analysis

### Problem

The documentation site lacks a central Troubleshooting page explaining how to diagnose and resolve Vishwakarma execution failures, exit codes (code 2 for configuration errors and code 3 for token budget limits), status labels (`vk:needs-info` and `vk:blocked`), and Prefect flow failures.

### Approach

Create `apps/web/src/content/docs/how-to-guides/troubleshooting.md` containing task-focused troubleshooting guidance using ASD-STE100 Simplified Technical English. Ground all details strictly in existing code (`packages/vk/src/vk/config.py`, `packages/vk/src/vk/pipeline.py`, `packages/vk/prefect_flows/flows.py`) and documentation. Link directly to `/api-reference/#exit-codes` and `/api-reference/status-labels/` rather than duplicating reference tables. The alternative of copying reference tables into the troubleshooting guide was rejected to maintain a single source of truth and comply with issue constraints.

### Plan

1. Create `apps/web/src/content/docs/how-to-guides/troubleshooting.md` with frontmatter: `title: Troubleshooting` and `description: Solutions for common exit codes, status labels, and Prefect execution failures.`.
2. Add a section for **Exit Code 2 (Configuration Error)** covering missing `GITHUB_TOKEN`, invalid `vk.toml` settings (unknown key or clan, model format not `provider:model`, non-integer or non-positive budget values), invalid `VK_CONFIG` file path, and missing `github.com` `origin` remote. Add a Markdown link to `/api-reference/#exit-codes`.
3. Add a section for **Exit Code 3 (Token Budget Exceeded)** covering token budget settings in `[defaults]` and `[clans.<name>]` (`max_input_tokens`, `max_output_tokens`, `max_total_tokens`, `max_requests`), and explain how to read `agent ... total_tokens=` log lines from stderr to determine required budget increases. Add a Markdown link to `/api-reference/#exit-codes`.
4. Add a section for **Status Labels** detailing `vk:needs-info` (meaning: VK posted clarifying questions; action: user replies on the issue and re-applies `vk` label) and `vk:blocked` (meaning: stage failed after retries or request was declined; action: user reviews run log / comments, resolves error, and re-applies `vk` label). Add a Markdown link to `/api-reference/status-labels/`.
5. Add a section for **Prefect Flow Failures** detailing that unhandled flow errors post an issue/PR comment linking to the Prefect flow run UI (`Log: <url>`), and note that VK retries each stage once before setting status `vk:blocked`.
6. Verify formatting and static site compilation with `npm run lint -w web`, `npm run check -w web`, and `npm run build -w web`. Run Python checks (`uv run ruff check`, `uv run mypy`, `uv run pytest`).

### Acceptance criteria

- [x] File `apps/web/src/content/docs/how-to-guides/troubleshooting.md` exists with frontmatter (`title` and `description`).
- [x] The Troubleshooting page includes an Exit Code 2 section covering missing `GITHUB_TOKEN`, invalid `vk.toml` (unknown key or clan, model not matching `provider:model`, non-integer or non-positive budget), bad `VK_CONFIG` path, and missing `github.com` `origin` remote.
- [x] The Exit Code 2 section links to the existing Exit Codes reference (`/api-reference/#exit-codes`) and does not duplicate the exit code table.
- [x] The Troubleshooting page includes an Exit Code 3 section describing `[defaults]` and `[clans.<name>]` budget keys (`max_input_tokens`, `max_output_tokens`, `max_total_tokens`, `max_requests`) and how to inspect `agent ... total_tokens=` stderr log lines.
- [x] The Exit Code 3 section links to the existing Exit Codes reference (`/api-reference/#exit-codes`) and does not duplicate the exit code table.
- [x] The Troubleshooting page covers `vk:needs-info` and `vk:blocked` status labels, explaining their meaning and what a user must do next for each.
- [x] The Status Labels section links to the existing Status Labels reference (`/api-reference/status-labels/`) and does not duplicate the status label table.
- [x] The Troubleshooting page covers Prefect run failures, specifying that the failure comment links to the Prefect flow run UI (`Log: <url>`) and that each stage is retried once before the run is marked blocked.
- [x] The page text follows Simplified Technical English (ASD-STE100) guidelines with active voice and concise instructions.
- [x] `npm run lint -w web`, `npm run check -w web`, `npm run build -w web`, and Python check commands (`ruff`, `mypy`, `pytest`) pass cleanly.

## Implementation

Branch `vk/feature-docs-troubleshooting` (base `main`).

### Change summary

- `apps/web/src/content/docs/how-to-guides/troubleshooting.md`: Add Troubleshooting guide covering exit code 2 configuration errors, exit code 3 token budgets, status labels (vk:needs-info and vk:blocked), and Prefect flow failures using ASD-STE100 Simplified Technical English guidelines.
- `apps/web/src/content/docs/how-to-guides/index.md`: Add section and cross-link to the new Troubleshooting guide under How-to Guides index page.

### Verification

- `npm run lint -w web && npm run check -w web && npm run build -w web`: Passed cleanly. Astro checked static types and compiled 13 HTML routes including /how-to-guides/troubleshooting/index.html with 0 errors or warnings.
- `uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest`: Passed cleanly. Python ruff linting, formatting check, mypy strict type checking, and 270 pytest tests passed.

### Deviations

- None

## Review

Verdict: **approve**

The implementation successfully adds the requested Troubleshooting page at `apps/web/src/content/docs/how-to-guides/troubleshooting.md` along with a cross-link in `index.md`. All required topics (exit codes 2 and 3, status labels, and Prefect execution/retry behavior) are accurately covered without duplicating reference tables, using Simplified Technical English (ASD-STE100). All web workspace formatting/typecheck/build commands and Python check/test suites pass cleanly.

### Criteria results

- pass: File `apps/web/src/content/docs/how-to-guides/troubleshooting.md` exists with frontmatter (`title` and `description`). (The file `apps/web/src/content/docs/how-to-guides/troubleshooting.md` was created with YAML frontmatter containing `title: Troubleshooting` and `description: Solutions for common exit codes, status labels, and Prefect execution failures.`.)
- pass: The Troubleshooting page includes an Exit Code 2 section covering missing `GITHUB_TOKEN`, invalid `vk.toml` (unknown key or clan, model not matching `provider:model`, non-integer or non-positive budget), bad `VK_CONFIG` path, and missing `github.com` `origin` remote. (The `## Exit Code 2 (Configuration Error)` section covers missing GITHUB_TOKEN, unknown keys/clans, non-`provider:model` syntax, non-integer or non-positive token budgets, invalid VK_CONFIG path, and missing github.com origin remote.)
- pass: The Exit Code 2 section links to the existing Exit Codes reference (`/api-reference/#exit-codes`) and does not duplicate the exit code table. (The Exit Code 2 section includes the link `[Exit Codes reference](/api-reference/#exit-codes)` and lists actionable cause/solution pairs without duplicating the exit code table.)
- pass: The Troubleshooting page includes an Exit Code 3 section describing `[defaults]` and `[clans.<name>]` budget keys (`max_input_tokens`, `max_output_tokens`, `max_total_tokens`, `max_requests`) and how to inspect `agent ... total_tokens=` stderr log lines. (The `## Exit Code 3 (Token Budget Exceeded)` section explains setting limits under `[defaults]` or `[clans.<name>]` for all four keys and explains how to inspect stderr log lines (`llm ... total_tokens=<N>` and `agent ... total_tokens=<N>`) to adjust limits.)
- pass: The Exit Code 3 section links to the existing Exit Codes reference (`/api-reference/#exit-codes`) and does not duplicate the exit code table. (The Exit Code 3 section includes the link `[Exit Codes reference](/api-reference/#exit-codes)` without duplicating the exit code reference table.)
- pass: The Troubleshooting page covers `vk:needs-info` and `vk:blocked` status labels, explaining their meaning and what a user must do next for each. (The `## Status Labels` section details `vk:needs-info` and `vk:blocked`, explaining what each label means and what specific action a user must take next.)
- pass: The Status Labels section links to the existing Status Labels reference (`/api-reference/status-labels/`) and does not duplicate the status label table. (The Status Labels section includes the link `[Status Labels reference](/api-reference/status-labels/)` without recreating the status label reference table.)
- pass: The Troubleshooting page covers Prefect run failures, specifying that the failure comment links to the Prefect flow run UI (`Log: <url>`) and that each stage is retried once before the run is marked blocked. (The `## Prefect Flow Failures` section documents the exact comment format (`The software factory run failed. Log: <url>`) linking to the Prefect flow run UI, and explains that each stage is retried once before transition to `vk:blocked`.)
- pass: The page text follows Simplified Technical English (ASD-STE100) guidelines with active voice and concise instructions. (The document uses short, direct sentences, direct instructions, and active voice throughout.)
- pass: `npm run lint -w web`, `npm run check -w web`, `npm run build -w web`, and Python check commands (`ruff`, `mypy`, `pytest`) pass cleanly. (Re-ran `npm run lint -w web && npm run check -w web && npm run build -w web` (compiled 13 HTML routes with 0 errors/warnings) and `uv run ruff check && uv run ruff format --check && uv run mypy packages/vk apps/api && uv run pytest` (270 passed).)
