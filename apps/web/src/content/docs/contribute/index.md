---
title: Contributing
description: Monorepo layout, tooling guidelines, definition of done, and pull request expectations.
---

Thank you for contributing to Vishwakarma! This guide covers monorepo layout, strict tooling rules, and pull request standards.

## Monorepo Layout

The repository is organized into distinct workspaces:

| Path           | Description                                             | Tooling                                               |
| -------------- | ------------------------------------------------------- | ----------------------------------------------------- |
| `packages/vk`  | Vishwakarma agent orchestrator, clans, tools, and CLI.  | `uv` workspace, `ruff`, `mypy --strict`, `pytest`     |
| `apps/web`     | Frontend documentation site built with Astro Starlight. | `npm` workspace (`-w web`), `prettier`, `astro check` |
| `apps/api`     | Python backend service.                                 | `uv` workspace, `ruff`, `mypy --strict`, `pytest`     |
| `docs/factory` | Execution run logs generated during factory runs.       | Markdown files                                        |

## Strict Tooling Rules

To maintain monorepo stability across automated and human contributions, strictly adhere to these package management rules:

- **Python Package Manager**: Use **uv** exclusively. Never use `pip`, `poetry`, or `conda`.
- **Node Package Manager**: Use **npm** exclusively. Never use `pnpm`, `yarn`, or `bun`.
- **Lockfile Integrity**: Never hand-edit `uv.lock` or `package-lock.json`. Dependencies must be managed through `uv` or `npm` commands.

## Development Workflow Commands

Run all workspace commands from the root of the repository:

- `make setup`: Installs all dependencies across Python (`uv sync --locked`) and JS (`npm ci`).
- `make format`: Auto-fixes Python formatting and linting issues using `ruff`.
- `make check`: Runs full lint, typecheck, test, and build suite.

## Definition of Done

The definition of done for any issue or pull request is simple:

:::note[Definition of Done]
`make check` must pass cleanly with 0 errors and 0 warnings before submitting a pull request or completing a task.
:::

`make check` runs:

1. Python linting and formatting verification (`ruff`).
2. Strict typechecking (`mypy --strict`).
3. Python tests (`pytest`).
4. Web workspace formatting check (`prettier`).
5. Astro content diagnostic check (`astro check`).
6. Astro static site build (`astro build`).

## Pull Request Guidelines

1. **Surgical Changes**: Touch only necessary lines. Do not refactor adjacent code or modify formatting outside your change scope.
2. **Dependency Justification**: Any new dependency requires a one-line justification in the PR description.
3. **Green CI**: All GitHub Actions CI checks must pass before merging. Never push directly to `main`.
