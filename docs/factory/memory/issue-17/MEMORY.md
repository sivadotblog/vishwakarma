# Issue #17 Notebook

- Summary: Restructure docs site (`apps/web`, Astro Starlight) into nine standard sections.
- Priority: Medium
- Complexity: Large
- Affected Area: `apps/web`
- Plan: Move existing pages, create section index files under 9 directories, update astro.config.mjs sidebar and index.mdx links, verify with `make check`.
- Artifact Saved: `analysis-analysis-restructure-docs-site-into-nine-standar-ce726c`
# Issue #17 Notebook

- Summary: Restructure docs site (`apps/web`, Astro Starlight) into nine standard sections.
- Priority: Medium
- Complexity: Large
- Affected Area: `apps/web`
- Status: Completed and verified with `make check`.
- Changes Made:
  - Moved `guides/getting-started.md` to `getting-started/index.md`.
  - Moved `reference/status-labels.md` to `api-reference/status-labels.md`.
  - Created section index pages for `concepts`, `how-to-guides`, `advanced`, `examples`, `integrations`, `api-reference`, `contribute`, and `release-notes`.
  - Configured 9 sidebar groups in `apps/web/astro.config.mjs` in required exact order.
  - Updated action link in `apps/web/src/content/docs/index.mdx`.
- Verification: `make check` passed cleanly (ruff, mypy, pytest, prettier, astro check, astro build).
