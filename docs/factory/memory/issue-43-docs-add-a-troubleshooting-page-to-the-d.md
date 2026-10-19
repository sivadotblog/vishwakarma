# Issue #43 Notebook: docs: add a Troubleshooting page to the docs site

- Summary: Add a Troubleshooting page at `apps/web/src/content/docs/how-to-guides/troubleshooting.md`.
- Status: Triaged.

## Strategy & Requirements
- New page at `apps/web/src/content/docs/how-to-guides/troubleshooting.md`.
- Content sections:
  1. Exit Code 2 (Configuration Error): GITHUB_TOKEN missing, bad vk.toml (unknown key/clan, provider:model format, non-positive integer budget), bad VK_CONFIG path, missing origin remote. Link to `/api-reference/#exit-codes`.
  2. Exit Code 3 (Token Budget Exceeded): budget keys `[defaults]` / `[clans.<name>]`, reading `agent ... total_tokens=` log lines. Link to `/api-reference/#exit-codes`.
  3. Status Labels: `vk:needs-info` and `vk:blocked` definitions and user next steps. Link to `/api-reference/status-labels/`.
  4. Prefect Run Failures: failure comment links to Prefect flow UI, stage retries once before blocking.
- Style: ASD-STE100 Simplified Technical English.
- Verification: `npm run lint -w web && npm run check -w web && npm run build -w web` and python checks.


## Execution & Verification
- Created `apps/web/src/content/docs/how-to-guides/troubleshooting.md` with ASD-STE100 technical writing guidelines.
- Added cross-link in `apps/web/src/content/docs/how-to-guides/index.md`.
- Formatted markdown using `prettier --write`.
- Verified static route generation `/how-to-guides/troubleshooting/index.html` with Astro (`npm run check -w web`, `npm run build -w web`).
- Verified code quality and test suites with Python checks (`ruff`, `mypy`, `pytest`).

## Repo notes
- When creating markdown files in `apps/web/src/content/docs`, running `prettier --write` ensures formatting compliance before running `npm run lint -w web`.
- Astro Starlight automatically includes markdown files added to `apps/web/src/content/docs/how-to-guides/` in the sidebar and site navigation.

## Review
- Checked git diff against main: 2 files changed (`troubleshooting.md` created, `index.md` cross-linked).
- Verified all acceptance criteria pass.
- Verified web workspace lint, typecheck, build, and python test suite.
- Verdict: approve.

## Final PR Creation
- Drafted pull request for Issue #43.
