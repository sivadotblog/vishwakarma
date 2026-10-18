# Issue #17 Notebook

- Summary: Restructure docs site (`apps/web`, Astro Starlight) into nine standard sections.
- Priority: Medium
- Complexity: Large
- Affected Area: `apps/web`
- Status: Completed initial implementation; processing PR #18 review comments.
- Review comment decisions:
  - Item -5561096099: fix (update environment variables and model format to PydanticAI runtime, remove nonexistent vishwakarma-review section).
  - Item -5561098414: fix (duplicate review body, same fix instructions as -5561096099).
  - Item -5561109392: fix (duplicate review body, same fix instructions as -5561096099).
- Addressed review comments:
  - Updated model documentation across `advanced/index.md`, `api-reference/index.md`, `how-to-guides/index.md`, `integrations/index.md`, and `release-notes/index.md` to reflect PydanticAI `provider:model` syntax.
  - Updated per-clan model list to match all agent clans (`CLASSIFIER`, `RESEARCHER`, `ANALYST`, `IMPLEMENTER`, `REVIEWER`, `TRIAGE`, `PR_WRITER`, `DECIDER`, `CI_DIAGNOSER`).
  - Added `VK_BOT_LOGIN` environment variable row to configuration matrices.
  - Removed obsolete `vishwakarma-review.yml` section from `integrations/index.md`.
  - Ran `make check` (ruff, mypy, pytest, prettier, astro check, astro build) - all passed.
