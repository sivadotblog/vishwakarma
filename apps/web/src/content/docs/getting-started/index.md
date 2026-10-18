---
title: Get Started
description: Setup, prerequisites, and how to transfer your first issue to Vishwakarma.
---

Vishwakarma (VK) is an autonomous software factory that converts GitHub issues into reviewed draft pull requests.

## What This Repository Is

This monorepo contains the Vishwakarma engine, an API backend, and a documentation site:

- **Software Factory (`packages/vk`)**: Python package that executes the issue-to-PR workflow.
- **Backend API (`apps/api`)**: Python backend service.
- **Frontend Docs (`apps/web`)**: Astro Starlight documentation site.

## Prerequisites

Before you run Vishwakarma or develop code locally, install these tools:

- **Git**: Required to clone repositories, manage branches, and commit code.
- **Python 3.12+**: Required for `packages/vk` and `apps/api`.
- **Node.js 18+ & npm**: Required to build and run `apps/web`.
- **uv**: Fast Python package installer and workspace manager.

## Installation and Setup

Install all workspace dependencies across Python packages and Node workspaces with the root Makefile:

```bash
make setup
```

The `make setup` command executes these commands:

- `uv sync --locked` for Python dependencies.
- `npm ci` for Node.js dependencies.

## Verification

Run the full project verification suite before you submit changes:

```bash
make check
```

The `make check` command executes these checks:

1. Python lint and format checks with `ruff`.
2. Strict type check with `mypy --strict`.
3. Test suite with `pytest`.
4. Web workspace format check with Prettier.
5. Astro site diagnostic check (`astro check`).
6. Astro static site build (`astro build`).

## Transfer Your First Issue to VK

Transfer an issue to the factory with these steps:

1. Open a GitHub issue in a repository where Vishwakarma workflows run.
2. Label the issue with `vk`.
3. GitHub Actions automatically starts Vishwakarma.
4. Vishwakarma classifies the task and creates an implementation plan.
5. Vishwakarma changes the code and runs `make check`.
6. Vishwakarma opens a draft Pull Request linked to the issue (e.g., `Closes #12`).
