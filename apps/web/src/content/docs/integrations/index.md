---
title: Integrations
description: Integrate Vishwakarma with GitHub Actions workflows and PydanticAI model providers.
---

Vishwakarma integrates with GitHub Actions CI/CD pipelines and LLM providers with PydanticAI.

## GitHub Actions Integration

### Issue Handler Workflow (`.github/workflows/vishwakarma.yml`)

The primary workflow starts when you add the `vk` label to an issue:

```yaml
name: Vishwakarma (software factory)

on:
  issues:
    types: [labeled]

permissions:
  contents: read
  issues: write

jobs:
  vk:
    if: github.event.label.name == 'vk'
    runs-on: ubuntu-latest
    timeout-minutes: 60
    steps:
      - name: Check labeler permission
        env:
          GH_TOKEN: ${{ github.token }}
          SENDER: ${{ github.event.sender.login }}
        run: |
          role=$(gh api "repos/${{ github.repository }}/collaborators/$SENDER/permission" --jq .role_name)
          case "$role" in
            admin|maintain|write|triage) ;;
            *) echo "::error::$SENDER cannot hand issues to the factory"; exit 1 ;;
          esac

      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v10.3.0
      - run: make setup-python

      - name: Run VK
        env:
          GITHUB_TOKEN: ${{ secrets.VK_GITHUB_TOKEN }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          VK_MODEL: ${{ vars.VK_MODEL || 'google:gemini-3.5-flash' }}
          VK_REPO: ${{ github.repository }}
          VK_STATE_DIR: ${{ runner.temp }}/vk-state
        run: uv run --package vk vk issue ${{ github.event.issue.number }} --unattended
```

## Model Providers (PydanticAI)

Vishwakarma uses PydanticAI as a common layer across model providers. These tables list supported providers and environment variables:

| Provider          | Model Example                    | API Key Variable                   |
| ----------------- | -------------------------------- | ---------------------------------- |
| **Anthropic**     | `anthropic:claude-3-5-sonnet`    | `ANTHROPIC_API_KEY`                |
| **Google Gemini** | `google:gemini-3.5-flash`        | `GEMINI_API_KEY`                   |
| **OpenAI**        | `openai:gpt-4o`                  | `OPENAI_API_KEY`                   |
| **Azure OpenAI**  | `azure-openai:<deployment-name>` | `AZURE_API_KEY` & `AZURE_API_BASE` |
