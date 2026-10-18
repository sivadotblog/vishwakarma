---
title: Contribute
description: Monorepo layout, tool guidelines, definition of done, and pull request expectations.
---

Thank you for your contributions to Vishwakarma! This guide covers monorepo layout, strict tool rules, and pull request standards.

## Monorepo Layout

The repository contains distinct workspaces:

| Path           | Description                                            | Tools                                                 |
| -------------- | ------------------------------------------------------ | ----------------------------------------------------- |
| `packages/vk`  | Vishwakarma agent orchestrator, clans, tools, and CLI. | `uv` workspace, `ruff`, `mypy --strict`, `pytest`     |
| `apps/web`     | Frontend documentation site with Astro Starlight.      | `npm` workspace (`-w web`), `prettier`, `astro check` |
| `apps/api`     | Python backend service.                                | `uv` workspace, `ruff`, `mypy --strict`, `pytest`     |
| `docs/factory` | Execution run logs from factory runs.                  | Markdown files                                        |

## Strict Tool Rules

To maintain monorepo stability across automated and human contributions, follow these package rules:

- **Python Package Manager**: Use **uv** exclusively. Never use `pip`, `poetry`, or `conda`.
- **Node Package Manager**: Use **npm** exclusively. Never use `pnpm`, `yarn`, or `bun`.
- **Lockfile Integrity**: Never hand-edit `uv.lock` or `package-lock.json`. Manage dependencies with `uv` or `npm` commands.

## Development Workflow Commands

Run all workspace commands from the root of the repository:

- `make setup`: Installs all dependencies across Python (`uv sync --locked`) and JS (`npm ci`).
- `make format`: Auto-fixes Python format and lint issues with `ruff`.
- `make check`: Runs full lint, typecheck, test, and build suite.

## Definition of Done

The definition of done for any issue or pull request is simple:

:::note[Definition of Done]
`make check` must pass cleanly with 0 errors and 0 warnings before you submit a pull request or complete a task.
:::

The `make check` command runs these checks:

1. Python lint and format checks (`ruff`).
2. Strict type check (`mypy --strict`).
3. Python tests (`pytest`).
4. Web workspace format check (`prettier`).
5. Astro content diagnostic check (`astro check`).
6. Astro static site build (`astro build`).

## Pull Request Guidelines

1. **Surgical Changes**: Touch only necessary lines. Do not refactor adjacent code or modify format style outside your change scope.
2. **Dependency Justification**: Any new dependency requires a one-line justification in the PR description.
3. **Green CI**: All GitHub Actions CI checks must pass before you merge code. Never push directly to `main`.
