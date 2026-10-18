# AGENTS.md

## Project

Monorepo demonstrating a fully autonomous development lifecycle: issue → triage → PR → review → fix → merge, with agents doing each step. Code written here is read and changed by agents, so keep it conventional and the checks strict.

| Path                | What                                                     | Tooling                                     |
| ------------------- | -------------------------------------------------------- | ------------------------------------------- |
| `apps/web`          | Frontend, Astro Starlight                                | npm workspaces (`-w web`), `astro check`    |
| `apps/api`          | Python backend (`src/` layout, package `api`)            | uv workspace, ruff, mypy `--strict`, pytest |
| `packages/vk` | Vishwakarma (VK), the software factory (issue → PR → review-fix), PydanticAI + requests | uv workspace, ruff, mypy `--strict`, pytest |

**Vishwakarma**, or **VK**, is this repo's software factory. VK runs on demand as Prefect flows (`vk-issue`, `vk-review`) on the `vk-agents` pool; see `packages/vk/README.md`. Running `vk-issue` on an issue opens a draft PR from a `vk/*` branch. The `vk` label no longer triggers anything. "Hand it to VK" means start the `vk-issue` deployment for the issue.

### Commands (run from repo root)

- `make setup` — install everything (`uv sync --locked` + `npm ci`)
- `make check` — lint + typecheck + test + build. **Definition of done: must pass before you say a task is complete.** CI runs exactly this.
- `make format` — auto-fix Python lint and formatting

### Hard rules

- Package managers: **uv** for Python, **npm** for JS. Never use pip, poetry, pnpm, or yarn. Never hand-edit `uv.lock` or `package-lock.json`.
- Never push to `main`; all changes land through a PR with green CI.
- New dependencies need a one-line justification in the PR description.
- Secrets live in GitHub Actions secrets or a local untracked `.env`, never in code.

Skills: `uv` (Python deps/running), `starlight` (frontend/docs content), `verify` (run and fix `make check`).

---

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
