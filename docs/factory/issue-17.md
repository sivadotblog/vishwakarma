# Factory run log: issue #17

## Summary

Restructure the Astro Starlight documentation site in `apps/web` into nine standard sections with updated sidebar configuration and content.

Reviewer verdict: approve.

## Classification

- type: feature
- priority: medium
- complexity: large
- affected_area: apps/web

## Analysis

### Problem

The Astro Starlight documentation site in `apps/web` currently has only two sidebar groups (Guides, Reference) and template placeholder pages. It needs to be restructured into nine standard sections (Getting Started, Concepts, How-to Guides, Advanced, Examples, Integrations, API Reference, Contribute, Release Notes) with updated sidebar configuration, moved existing pages without broken links, and real technical content drawn from the repository.

### Approach

Reorganize the Astro Starlight content directory (`apps/web/src/content/docs/`) into nine dedicated section directories. Use `git mv` to move existing pages (`guides/getting-started.md` -> `getting-started/index.md` and `reference/status-labels.md` -> `api-reference/status-labels.md`). Populate index pages for all nine sections using technical facts drawn directly from repository sources (`packages/vk/README.md`, `packages/vk/SPEC.md`, `AGENTS.md`, and `.github/workflows/vishwakarma.yml`). Update `apps/web/astro.config.mjs` sidebar configuration to list all nine groups in exact order, and update action links in `apps/web/src/content/docs/index.mdx`. The alternative of keeping flat files without section subfolders was rejected because folder-based autogeneration provides cleaner navigation and maintainability.

### Plan

1. 1. Move `apps/web/src/content/docs/guides/getting-started.md` to `apps/web/src/content/docs/getting-started/index.md` and `apps/web/src/content/docs/reference/status-labels.md` to `apps/web/src/content/docs/api-reference/status-labels.md` using `git mv`.
2. 2. Remove empty legacy directories `apps/web/src/content/docs/guides` and `apps/web/src/content/docs/reference`.
3. 3. Update `apps/web/src/content/docs/getting-started/index.md` with complete repo overview, prerequisites, `make setup`, `make check`, and first issue handoff instructions.
4. 4. Create `apps/web/src/content/docs/concepts/index.md` covering Vishwakarma architecture, issue-to-PR loop, the five clans, status labels, run log structure, and per-issue memory.
5. 5. Create `apps/web/src/content/docs/how-to-guides/index.md` covering task-based guides (handing an issue to VK, replying with PR review comments, changing model configurations).
6. 6. Create `apps/web/src/content/docs/advanced/index.md` covering environment configuration variables, GitHub App identity, comment trust rules, execution safety/sandbox warning, and local VK runs.
7. 7. Create `apps/web/src/content/docs/examples/index.md` covering a worked example walkthrough built from a real factory run log (`docs/factory/issue-12.md`).
8. 8. Create `apps/web/src/content/docs/integrations/index.md` covering GitHub Actions workflows (`vishwakarma.yml` and review workflows) and LiteLLM model provider options.
9. 9. Create `apps/web/src/content/docs/api-reference/index.md` covering `vk` CLI subcommands (`issue`, `review`, `ci-fix`), exit codes (0, 2, 3), and environment variable specifications.
10. 10. Create `apps/web/src/content/docs/contribute/index.md` covering repo layout, tooling rules (uv for Python, npm for JS), `make check` DoD, and PR guidelines.
11. 11. Create `apps/web/src/content/docs/release-notes/index.md` describing current state of the project.
12. 12. Update `apps/web/astro.config.mjs` sidebar array to list all nine groups in exact order: Getting Started, Concepts, How-to Guides, Advanced, Examples, Integrations, API Reference, Contribute, Release Notes.
13. 13. Update action link in `apps/web/src/content/docs/index.mdx` from `guides/getting-started/` to `getting-started/`.
14. 14. Run `make check` to verify linting, typechecking, astro check, and astro build complete without errors or warnings.

### Acceptance criteria

- [ ] The sidebar in `apps/web/astro.config.mjs` shows exactly these nine groups in this order: Getting Started, Concepts, How-to Guides, Advanced, Examples, Integrations, API Reference, Contribute, Release Notes.
- [x] Each section has at least an index page with real content drawn from the repo (`packages/vk/README.md`, `packages/vk/SPEC.md`, `AGENTS.md`, the workflows). No placeholder or lorem text.
- [x] Existing pages are moved, not duplicated, and no internal link is broken.
- [x] Facts match the code: commands, env var names and file paths must exist in the repo.
- [x] `make check` passes (it includes the Astro build).

## Implementation

Branch `vk/feature-restructure-docs` (base `main`).

### Change summary

- `apps/web/astro.config.mjs`: Updated sidebar configuration to list all nine standard groups in required order using Starlight items autogenerate syntax.
- `apps/web/src/content/docs/index.mdx`: Updated hero action button link from guides/getting-started/ to getting-started/.
- `apps/web/src/content/docs/getting-started/index.md`: Moved from guides/getting-started.md and expanded with repo overview, prerequisites, setup, check, and issue handoff instructions.
- `apps/web/src/content/docs/concepts/index.md`: Created section index page documenting Vishwakarma architecture, pipeline, clans, status labels, run logs, and issue memory.
- `apps/web/src/content/docs/how-to-guides/index.md`: Created section index page documenting task-focused guides for issue handoff, PR review comment handling, and LLM model selection.
- `apps/web/src/content/docs/advanced/index.md`: Created section index page documenting configuration variables, GitHub App identity, trust rules, host execution safety, and local execution.
- `apps/web/src/content/docs/examples/index.md`: Created section index page documenting a step-by-step worked example based on the factory run log for issue #12.
- `apps/web/src/content/docs/integrations/index.md`: Created section index page documenting GitHub Actions workflows (vishwakarma.yml) and LiteLLM model provider options.
- `apps/web/src/content/docs/api-reference/index.md`: Created section index page documenting vk CLI subcommands, exit codes, and environment variables.
- `apps/web/src/content/docs/api-reference/status-labels.md`: Moved from reference/status-labels.md to api-reference/status-labels.md without content loss.
- `apps/web/src/content/docs/contribute/index.md`: Created section index page documenting repository layout, tooling rules, Definition of Done, and PR guidelines.
- `apps/web/src/content/docs/release-notes/index.md`: Created section index page documenting current project state and capabilities.

### Verification

- `make check`: pass: ruff linting, ruff formatting check, mypy strict typechecking, 115 pytest tests, web workspace prettier linting, astro check (0 errors, 0 warnings, 0 hints), and astro static build all passed cleanly. Generates 12 static HTML routes including all 9 section index pages.

### Deviations

- None

## Review

Verdict: **approve**

The implementation successfully restructures the Astro Starlight documentation site in `apps/web` into nine standard sections in the exact requested order. Each section contains detailed, accurate technical documentation derived directly from repository source files without placeholder text. Existing pages were moved without duplication, internal links were updated, and `make check` passed cleanly across all Python and Web workspace checks.

### Criteria results

- pass: The sidebar in `apps/web/astro.config.mjs` shows exactly these nine groups in this order. (`apps/web/astro.config.mjs` defines the `sidebar` array with all nine groups in the verbatim required order: Getting Started, Concepts, How-to Guides, Advanced, Examples, Integrations, API Reference, Contribute, Release Notes.)
- pass: Each section has at least an index page with real content drawn from the repo (`packages/vk/README.md`, `packages/vk/SPEC.md`, `AGENTS.md`, the workflows). No placeholder or lorem text. (Every section directory under `apps/web/src/content/docs/` contains an `index.md` file populated with real technical content drawn from repo sources (`packages/vk/README.md`, `packages/vk/SPEC.md`, `AGENTS.md`, `docs/factory/issue-12.md`, `.github/workflows/vishwakarma.yml`). No placeholder or lorem text was found.)
- pass: Existing pages are moved, not duplicated, and no internal link is broken. (`guides/getting-started.md` was relocated to `getting-started/index.md` (and expanded with real content), `reference/status-labels.md` was moved via git rename to `api-reference/status-labels.md`, and the hero link in `index.mdx` was updated to `getting-started/`. `astro build` generated 12 static HTML routes cleanly with no missing pages or broken internal links.)
- pass: Facts match the code: commands, env var names and file paths must exist in the repo. (All commands (`make setup`, `make check`, `uv sync --locked`, `npm ci`, `ruff check`, `mypy --strict`, `pytest`, `astro check`, `astro build`, `vk issue`, `vk review`, `vk ci-fix`), environment variables (`GITHUB_TOKEN`, `VK_MODEL`, `VK_MODEL_<CLAN>`, `VK_REPO`, `VK_SETUP_COMMAND`, `VK_BRANCH_PREFIX`, `VK_STATE_DIR`, `VK_MAX_OUTPUT_TOKENS`, `VK_LOG_LEVEL`), and paths (`apps/web`, `apps/api`, `packages/vk`, `docs/factory/issue-12.md`) exist and match repository files.)
- pass: `make check` passes (it includes the Astro build). (Executed `make check` from root after running `make setup`. All checks passed: ruff linting, ruff formatting check, mypy strict typechecking, 115 pytest tests, web workspace prettier linting, astro check (0 errors, 0 warnings, 0 hints), and astro static build (12 HTML pages generated).)
