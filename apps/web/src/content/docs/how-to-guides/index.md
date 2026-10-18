---
title: How-to Guides
description: Task-focused guides for Vishwakarma.
---

This section provides step-by-step guides for common tasks when you operate Vishwakarma.

## How to Hand an Issue to VK

To hand an issue to Vishwakarma:

1. Open a GitHub issue that describes the bug, feature, or maintenance task.
2. Add the label `vk` to the issue.
3. The `.github/workflows/vishwakarma.yml` workflow starts automatically.
4. **Permission check**: Vishwakarma verifies that the labeler holds at least `triage`, `write`, `maintain`, or `admin` repository permission. If an unauthorized user labels an issue, execution stops to prevent unauthorized resource usage.

## How to Respond to a VK Pull Request

When Vishwakarma opens a draft pull request:

1. Review the changes and the run log in `docs/factory/issue-<N>.md`.
2. If you request changes, write review comments on the pull request.
3. Submit the review. The `.github/workflows/vishwakarma-review.yml` workflow starts the review cycle.
4. To start the review cycle locally, run `vk review <PR_NUMBER>`.
5. Vishwakarma checks out the PR branch, reads the review comments, and answers each comment.
6. Vishwakarma updates `docs/factory/issue-<N>.md` with review rounds and pushes updated commits.

## How to Change the LLM Model Used by VK

Vishwakarma uses PydanticAI to integrate with model providers such as Anthropic, OpenAI, and Gemini.

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

You can assign specific models to individual clans with per-clan environment variables:

- `VK_MODEL_CLASSIFIER`
- `VK_MODEL_RESEARCHER`
- `VK_MODEL_ANALYST`
- `VK_MODEL_IMPLEMENTER`
- `VK_MODEL_REVIEWER`
- `VK_MODEL_TRIAGER`
- `VK_MODEL_PR_WRITER`
- `VK_MODEL_CI_DIAGNOSER`

This example sets a small model for classification and a large model for implementation:

```bash
export VK_MODEL_CLASSIFIER="google:gemini-2.5-flash"
export VK_MODEL_IMPLEMENTER="anthropic:claude-3-5-sonnet"
```
