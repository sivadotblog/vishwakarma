---
title: Getting Started
description: Setup, prerequisites, and handing your first issue to Vishwakarma.
---

Vishwakarma (VK) is an autonomous software factory that turns GitHub issues into reviewed draft pull requests.

## What This Repo Is

This monorepo contains the Vishwakarma engine along with an API backend and documentation site:

- **Software Factory (`packages/vk`)**: Python package implementing the issue-to-PR agentic workflow.
- **Backend API (`apps/api`)**: Python backend service.
- **Frontend Docs (`apps/web`)**: Astro Starlight documentation site.

## Prerequisites

Before running Vishwakarma or developing locally, ensure you have installed:

- **Git**: Required for repository cloning, branch management, and commits.
- **Python 3.12+**: Required for `packages/vk` and `apps/api`.
- **Node.js 18+ & npm**: Required for building and running `apps/web`.
- **uv**: Fast Python package installer and workspace manager.

## Installation & Setup

Install all workspace dependencies across Python packages and Node workspaces using the root Makefile:

```bash
make setup
```

Under the hood, `make setup` executes:

- `uv sync --locked` for Python dependencies.
- `npm ci` for Node.js dependencies.

## Verification

Run the full project verification suite before submitting changes:

```bash
make check
```

`make check` executes:

1. Python linting and formatting via `ruff`.
2. Strict typechecking via `mypy --strict`.
3. Test suite via `pytest`.
4. Web workspace formatting via Prettier.
5. Astro site diagnostic check (`astro check`).
6. Astro static site build (`astro build`).

## Handing Your First Issue to VK

Handing an issue to the factory requires minimal action:

1. Open a GitHub issue in a repository where Vishwakarma workflows are enabled.
2. Label the issue with `vk`.
3. Vishwakarma automatically triggers via GitHub Actions, classifies the task, creates an implementation plan, makes surgical code changes, runs `make check`, and opens a draft Pull Request linked to the issue (e.g., `Closes #12`).
