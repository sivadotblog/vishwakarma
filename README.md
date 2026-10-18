# ai-engineering-pod

ai-engineering-pod demonstrates the possibility of a fully autonomous development lifecycle: issue → triage → PR → review → fix → merge, with agents doing each step.

## Repository Layout

| Path | Description | Tooling |
| --- | --- | --- |
| `apps/web` | Frontend and docs site, Astro Starlight | npm workspace (`web`) |
| `apps/api` | Python backend (`src/` layout, package `api`) | uv workspace |
| `packages/vk` | [Vishwakarma (VK)](packages/vk/README.md), the software factory (issue → PR → review-fix), built on PydanticAI | uv workspace |

## Quick Start

### Prerequisites

- [uv](https://github.com/astral-sh/uv)
- Node.js 22

### Commands

Run these commands from the repository root:

- `make setup` — install everything (`uv sync --locked` + `npm ci`)
- `make check` — lint, typecheck, test, and build. This is the definition of done, and CI runs exactly this.
- `make format` — auto-fix Python lint and formatting

## How Work Gets Done Here

VK runs on demand as Prefect flows (`vk-issue`, `vk-review`) on the `vk-agents` pool. Starting `vk-issue` for an issue opens a draft PR from a `vk/*` branch. See the [Run on Prefect](packages/vk/README.md#run-on-prefect) section of `packages/vk/README.md` for details.

## Rules for Contributors

- Package managers: **uv** for Python and **npm** for JS (never pip, poetry, pnpm, or yarn).
- Never push to `main`; every change lands through a PR with green CI.
- Secrets live in GitHub Actions secrets or a local untracked `.env`, never in code.

## License

This project is licensed under the [MIT License](LICENSE).
