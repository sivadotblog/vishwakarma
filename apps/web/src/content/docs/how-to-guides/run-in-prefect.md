---
title: Run VK in Prefect
description: How to run Vishwakarma as a Prefect flow.
---

Vishwakarma runs on demand as two Prefect flows: `vk-issue` and `vk-review`. Nothing triggers these flows automatically. You must start a run yourself.

- The `vk-issue` flow receives the `issue_number` parameter.
- The `vk-review` flow receives the `pr_number` parameter.

Both flows run on the `vk-agents` managed work pool.

## Set up the Workspace

Before you start your first run, you must add these secrets and variables to your Prefect workspace:

1. Create a Secret block named `vk-app-private-key`. Put the GitHub App private key (PEM format) in it.
2. Create a Secret block named `vk-gemini-api-key`. Put your Gemini API key in it.
3. Create a Variable named `vk_app_id`. Put the GitHub App ID in it.

## Understand Deployments

The `packages/vk/prefect_flows/prefect.yaml` file defines the deployments. The `.github/workflows/prefect-deploy.yml` workflow registers the deployments with Prefect.

When you push a commit to the `main` branch, the workflow deploys `vk-issue/main` and `vk-review/main`.

To test a different branch, run the workflow manually on that branch. The workflow names the deployment after your branch slug.

To deploy manually from your machine, run this command:

```bash
VK_BRANCH=<branch> VK_DEPLOYMENT=<slug> uv run prefect --no-prompt deploy --all --prefect-file packages/vk/prefect_flows/prefect.yaml
```

## Start a Run

You can start a run with the Prefect CLI or the Prefect UI.

To start a run for an issue with the CLI, run this command:

```bash
prefect deployment run 'vk-issue/main' -p issue_number=<n>
```

To start a run for a pull request with the CLI, run this command:

```bash
prefect deployment run 'vk-review/main' -p pr_number=<n>
```

To start a run in the Prefect UI, go to the **Deployments** page. Select the deployment and click **Run**. Provide the issue number or PR number when the UI prompts you.

## What a Run Does

When a flow runs, it does these steps:

1. **Pull steps:** The flow clones the specified branch, installs `uv`, installs Node 22 with `uv tool install "nodejs-wheel>=22,<23"`, and runs `uv sync --locked`.
2. **Setup:** The flow activates the virtual environment in its own process. It mints a GitHub App installation token to authenticate.
3. **Execution:** The flow runs the Vishwakarma pipeline. It shows each stage (such as `triage`, `classifier`, `analyst`) as a Prefect task.
4. **Failure comment:** If an error escapes Vishwakarma, the flow posts a failure comment with a link to the Prefect run log on the GitHub issue or pull request.

## Configure Settings

Vishwakarma reads the models, token budgets, and flow timeout (`flow_timeout_s`) from `packages/vk/src/vk/vk.toml`. It does not read these settings from Prefect variables. See the [Change the LLM Model Used by VK](./index.md#how-to-change-the-llm-model-used-by-vk) guide for more data on configuration.
