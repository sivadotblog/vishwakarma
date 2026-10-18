---
title: How-to Guides
description: Task-focused operational guides for working with Vishwakarma.
---

This section provides step-by-step guides for common tasks when operating Vishwakarma.

## How to Hand an Issue to VK

To hand an issue to Vishwakarma for processing:

1. Open a GitHub issue describing the bug, feature, or maintenance task.
2. Add the label `vk` to the issue.
3. The `.github/workflows/vishwakarma.yml` workflow triggers automatically.
4. **Permission check**: Vishwakarma verifies that the user who attached the label holds at least `triage`, `write`, `maintain`, or `admin` repository permission. If an unauthorized user labels an issue, execution stops to prevent unauthorized resource usage.

## How to Respond to a VK Pull Request

When Vishwakarma opens a draft pull request:

1. Review the changes and the run log committed at `docs/factory/issue-<N>.md`.
2. If changes are requested, leave review comments directly on the pull request.
3. Trigger the review cycle by running `vk review <PR_NUMBER>` (or through configured workflow triggers).
4. Vishwakarma checks out the existing PR branch, reads review comments, addresses each finding, updates `docs/factory/issue-<N>.md` with review rounds, and pushes updated commits.

## How to Change the LLM Model Used by VK

Vishwakarma uses PydanticAI, allowing integration with model providers like Anthropic, OpenAI, and Gemini.

### Default Model Configuration

Set the `VK_MODEL` environment variable (or GitHub Actions variable/secret) to specify the default model for all clans:

```bash
export VK_MODEL="anthropic:claude-3-5-sonnet"
```

In GitHub Actions (`.github/workflows/vishwakarma.yml`):

```yaml
env:
  VK_MODEL: ${{ vars.VK_MODEL || 'google:gemini-3.5-flash' }}
```

### Per-Clan Model Overrides

You can assign specific models to individual clans using per-clan environment variables:

- `VK_MODEL_CLASSIFIER`
- `VK_MODEL_RESEARCHER`
- `VK_MODEL_ANALYST`
- `VK_MODEL_IMPLEMENTER`
- `VK_MODEL_REVIEWER`
- `VK_MODEL_TRIAGER`
- `VK_MODEL_PR_WRITER`
- `VK_MODEL_CI_DIAGNOSER`

Example using a lighter model for classification and a larger model for implementation:

```bash
export VK_MODEL_CLASSIFIER="google:gemini-2.5-flash"
export VK_MODEL_IMPLEMENTER="anthropic:claude-3-5-sonnet"
```
