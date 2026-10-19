# Issue #46: docs: add a 'Run VK in Prefect' page to the docs site

- Summary: Add a How-to guide `apps/web/src/content/docs/how-to-guides/run-in-prefect.md` explaining how to run VK as Prefect flows.
- Verdict: proceed.

## Triage Notes
- The request is clear and specifies the file path, required topics, and source files in the repo.
- Content must follow ASD-STE100 Simplified Technical English and link to existing docs where appropriate.

## Classification
- Type: feature
- Priority: medium
- Complexity: small
- Affected Area: apps/web
- Summary: Add a 'Run VK in Prefect' how-to guide to the documentation site covering flow definitions, workspace setup, deployments, execution, and configuration.
- Summary: Add a How-to guide `apps/web/src/content/docs/how-to-guides/run-in-prefect.md` explaining how to run VK as Prefect flows.
- Verified facts: `packages/vk/prefect_flows/prefect.yaml` and `.github/workflows/prefect-deploy.yml` define and deploy the flows. Secrets `vk-app-private-key`, `vk-gemini-api-key` and variable `vk_app_id` are required.
- The page must be written in ASD-STE100 Simplified Technical English.
- Drafted the content in artifact `analysis-draft-documentation-for-run-vk-in-prefect-5197e7`.

## Repo notes
- When adding new documentation pages to Astro Starlight, use the frontmatter format `title:` and `description:`.
- Ensure the newly created file is formatted properly (e.g. running `npm run format -w web`) to pass `npm run lint -w web`.
- Internal links should use `#slugified-heading-name` format when linking to specific headings within other markdown files.

## Review Notes
- Verified branch `vk/feature-run-in-prefect` against `main`.
- `apps/web/src/content/docs/how-to-guides/run-in-prefect.md` accurately documents the flows, parameters, workspace secrets and variables, deployments, CLI/UI execution, run lifecycle, and configuration from `vk.toml`.
- Verification passed: `npm run lint -w web`, `npm run check -w web`, `npm run build -w web`, and all python checks (`ruff`, `mypy`, `pytest` 276 tests).
- Verdict: approve.
