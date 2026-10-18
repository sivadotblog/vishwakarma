# Factory run log: issue #36

## Summary

Rewrite root README.md with project overview, repository layout, quick start instructions, workflow overview, contributor rules, and license.

Reviewer verdict: approve.

## Classification

- type: chore
- priority: medium
- complexity: small
- affected_area: documentation

## Analysis

### Problem

The root README.md currently has only two lines and provides no information about project structure, setup commands, execution workflow, contributor rules, or license.

### Approach

Replace the 2-line placeholder root README.md with a structured 6-section README (~45 lines) based strictly on AGENTS.md, Makefile, packages/vk/README.md, and LICENSE. Alternative rejected: Adding badges, images, or speculative configuration instructions not verified in the codebase.

### Plan

1. Rewrite README.md to include all six required sections: project overview description, repository layout table, quick start prerequisites and make commands, workflow description linking to Prefect docs, contributor rules, and license pointer.
2. Verify all referenced repo paths (apps/web, apps/api, packages/vk, LICENSE) and section anchors (#run-on-prefect) exist.
3. Verify README.md line count is within 40 to 80 lines, with no badges or images.
4. Run make check from repo root to verify lint, typecheck, pytest, and web build pass.
5. Verify git diff to confirm only README.md was modified.

### Acceptance criteria

- [x] README.md contains the opening sentence: 'ai-engineering-pod demonstrates the possibility of a fully autonomous development lifecycle: issue → triage → PR → review → fix → merge, with agents doing each step.'
- [x] README.md contains a Markdown table listing apps/web, apps/api, and packages/vk with their descriptions and tooling.
- [x] README.md lists prerequisites (uv, Node 22) and commands (make setup, make check, make format).
- [x] README.md contains a paragraph explaining VK running on Prefect with a relative link to packages/vk/README.md#run-on-prefect.
- [x] README.md lists the three contributor rules regarding package managers (uv and npm), main branch protection, and secret management.
- [x] README.md includes a one-line License section referencing LICENSE.
- [x] README.md is plain Markdown between 40 and 80 lines long with no badges or images.
- [x] No repository source files other than README.md are modified.
- [x] make check completes with 0 exit code.

## Implementation

Branch `vk/chore-root-readme` (base `main`).

### Change summary

- `README.md`: Replaced 2-line placeholder with a structured root README.md covering project overview, repository layout, quick start commands, workflow description, contributor rules, and license pointer.

### Verification

- `make setup`: pass: Installed Python workspace dependencies via uv sync --locked and npm workspace dependencies via npm ci.
- `make check`: pass: Executed ruff check, ruff format --check, mypy --strict, pytest (245 tests passed), prettier linting on web workspace, astro check, and astro build without errors.
- `wc -l README.md`: pass: Verified README.md line count is 40 lines (within 40-80 line requirement).
- `git status`: pass: Verified only README.md was changed.

### Deviations

- None

## Review

Verdict: **approve**

The PR replaces the 2-line placeholder root README.md with a clear, accurate, 40-line documentation file covering project overview, repository layout, quick start instructions, workflow overview, contributor rules, and license pointer. All 9 acceptance criteria pass and `make check` completes with exit code 0.

### Criteria results

- pass: README.md contains the opening sentence: 'ai-engineering-pod demonstrates the possibility of a fully autonomous development lifecycle: issue → triage → PR → review → fix → merge, with agents doing each step.' (README.md line 3 contains the exact opening sentence verbatim.)
- pass: README.md contains a Markdown table listing apps/web, apps/api, and packages/vk with their descriptions and tooling. (README.md contains the Markdown table under '## Repository Layout' with apps/web, apps/api, and packages/vk along with descriptions and tooling.)
- pass: README.md lists prerequisites (uv, Node 22) and commands (make setup, make check, make format). (README.md lists uv and Node.js 22 under Prerequisites, and make setup, make check, make format under Commands.)
- pass: README.md contains a paragraph explaining VK running on Prefect with a relative link to packages/vk/README.md#run-on-prefect. (README.md section '## How Work Gets Done Here' includes the paragraph and link [Run on Prefect](packages/vk/README.md#run-on-prefect).)
- pass: README.md lists the three contributor rules regarding package managers (uv and npm), main branch protection, and secret management. (README.md section '## Rules for Contributors' lists all 3 bullet points from AGENTS.md.)
- pass: README.md includes a one-line License section referencing LICENSE. (README.md section '## License' contains 'This project is licensed under the [MIT License](LICENSE).' referencing LICENSE.)
- pass: README.md is plain Markdown between 40 and 80 lines long with no badges or images. (wc -l README.md returns 40 lines. The file contains plain markdown with no badges or images.)
- pass: No repository source files other than README.md are modified. (git status and git diff main...HEAD --name-status confirm only README.md was modified.)
- pass: make check completes with 0 exit code. (make check executed cleanly with 0 exit code (linting, typechecking, 245 pytest tests, astro check, and astro build all passed).)
