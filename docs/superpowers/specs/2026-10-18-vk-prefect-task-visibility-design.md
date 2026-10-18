# VK on Prefect: stage-level task visibility

Status: draft for review. Follows `2026-10-18-vk-prefect-flows-design.md` (shipped in PR #32).

## Intent

Today a `vk-issue` or `vk-review` flow run in Prefect Cloud is one opaque box. The flow starts the
`vk` CLI as a subprocess and streams its stderr into the flow log. The Prefect UI cannot show which
VK stage is running, how long each stage took, which stage failed, or that a stage was retried.

The goal is **visibility**: open a flow run in Prefect and see VK's pipeline as a list of tasks,
one per clan or judgment agent, each with its own state, duration and logs.

This is not a durability project. Nothing is stored, cached or replayed.

## Goals

1. **Groundwork: run VK in the flow process.** The flow imports `vk` and calls the pipeline
   functions directly, the same way `vk.cli.main` does, instead of running `uv run vk ...` as a
   subprocess. Without this, Prefect cannot see inside VK.
2. **Level 1: one Prefect task per VK stage.** Every call to `Stages.clan(...)` and
   `Stages.agent(...)` runs as a Prefect task named after the stage: `triage`, `classifier`,
   `researcher`, `analyst`, `implementer`, `reviewer`, `pr_writer` for an issue; `decider` (plus
   the clans it starts) for a review; `ci_diagnoser` for a CI fix. A typical issue run shows about
   6–10 task runs. Implementer/reviewer revision cycles show as repeated task runs of the same name.
3. **VK's log lines land on the task that produced them.** A line that `vk.clans` logs while the
   analyst runs shows in the analyst task's log, not only in the flow log.
4. **A stage that fails shows as a Failed task**, so the failed stage is visible at a glance.

## Non-goals

- **No result storage, caching or replay.** Tasks run with `persist_result=False` and no cache
  policy. A rerun of a flow starts from the beginning, as today.
- **No per-model-request or per-tool-call tasks.** That is "Level 2" (Pydantic AI's
  `PrefectDurability` capability, which wraps each model request, tool call and MCP call as a task).
  It is deferred. VK's tools mutate a throwaway clone and the managed pool has no shared volume,
  so per-tool replay is not safe; per-request visibility alone is better served by Logfire if it is
  ever wanted.
- **The memory notebook stays as it is.** Its storage problem on an ephemeral container is parked
  for a later spec.
- **No change to how VK behaves outside Prefect.** `vk issue N` on a laptop runs exactly as today.
- **No change to the CLI, the GitHub workflows, `SPEC.md` or the Starlight site.**
- **VK's handled failures do not fail the flow.** Decided by the user: Prefect's job is to run the
  agent. If VK runs and then stops on its own (a stage failed twice, a 403, memory, run log, an
  implementer that did not push), VK posts its comment and returns its "Stopped: ..." summary,
  and the flow ends **Completed** with that summary as its result. The failure belongs to VK, not
  to Prefect.

## Anti-goals (would count as a failure even if it works)

- Prefect leaks into `src/vk`. VK must not import `prefect`; `prefect` stays a dev dependency.
- Two retry layers. VK's own retry-once rule (`_attempt` in `pipeline.py`) stays the only retry.
  Prefect task retries stay at 0. (The Pydantic AI docs warn that retries multiply across layers.)
- A secret (GitHub token, Gemini key, App private key) appears in a task name, task parameter,
  artifact or log line.
- Task parameters that Prefect cannot serialize produce warnings on every task (prompts and
  `Config` objects as task inputs). Prefect hashes task inputs for cache keys by default; the
  docs note that agent and model objects cannot be serialized.

## Constraints

- Prefect 3.8.8, Prefect Cloud managed pool `vk-agents` (`prefect:managed`), image
  `prefecthq/prefect:3-python3.12`, concurrency 1. Deploys still go through
  `.github/workflows/prefect-deploy.yml` (`PrefectHQ/actions-prefect-deploy@v4`).
- uv only, never pip. "Install into the image's Python" means `uv pip install --system`, not pip.
- One uv project: `packages/vk/pyproject.toml` serves both `src/vk` and `prefect_flows`.
- Secrets come from the Prefect Secret blocks `vk-app-private-key`, `vk-gemini-api-key` and the
  Variables `vk_app_id`, `vk_model`, as today.
- `make check` passes (ruff, mypy `--strict` including `packages/vk/prefect_flows`, pytest).
- The flow still loads as a Prefect script with a relative import (`test_flows_loads_as_prefect_script`
  must keep passing).
- Small, focused diff in `src/vk`: only what Level 1 needs.

## Decided design

### Groundwork: VK in-process

**Install VK into the image's Python.** The flow runs in the Prefect image's interpreter, not in
the clone's `.venv`, so `import vk` needs VK and its locked dependencies there. The `prefect.yaml`
`run_shell_script` pull step gains an install of VK's locked runtime dependencies plus the `vk`
package itself into the system Python with uv (for example
`uv export --frozen --package vk --no-dev --no-emit-workspace | uv pip install --system -r -`
then `uv pip install --system --no-deps packages/vk`). The existing toolchain steps (make, node,
uv, `uv sync --locked`) stay, because VK's implementer and reviewer clans run `make` in their own
clones.

**Call VK directly.** `flows.py` replaces the subprocess in `run_vk` with the body of
`vk.cli.main`:

1. Load settings and mint the installation token (unchanged).
2. Build VK's config with `load_config(env)`, passing an explicit env dict with the same keys
   `vk_env` builds today (`GITHUB_TOKEN`, `VK_BOT_LOGIN`, `VK_MODEL`, `VK_REPO`, `VK_STATE_DIR`).
3. Make the Gemini key visible to `vk.config.build_model`, which reads `GEMINI_API_KEY` from
   `os.environ`. Setting it in the flow process's environment is acceptable: the container is
   single-use.
4. `gh = GitHub(cfg)`, `cfg = with_bot_identity(cfg, gh)`, then
   `run_issue(cfg, gh, n, Caller(True, issue_number=n), stage_wrapper=...)` or
   `run_review(cfg, gh, n, Caller(True, pr_number=n), stage_wrapper=...)`.
5. Return VK's summary string as the flow result (as today with stdout).

`ConfigError` and `UsageLimitExceeded` fail the flow with a clear message, as the CLI's exit codes
2 and 3 did. Any exception that escapes VK still posts the best-effort failure comment with the
flow run URL, then re-raises. Failures before a token exists still skip the comment.

**Logging.** The deployment's job variables set `PREFECT_LOGGING_EXTRA_LOGGERS=vk`, so every
`vk.*` logger is forwarded to the Prefect run logger of the current flow or task run. VK's log
level stays INFO.

**Module docstring and the "never import vk" rule.** The rule in `flows.py`'s docstring goes away.
The relative import of `github_app` stays.

### Level 1: stage tasks

**A seam in `Stages`, not a Prefect dependency.** `Stages` (frozen dataclass, `pipeline.py:71`)
gains one optional field: a stage wrapper. Its type is a plain callable alias defined in
`pipeline.py`, roughly `StageWrapper = Callable[[str, Callable[[], T]], T]`: given the stage name
and the zero-argument call that runs the whole stage (both attempts), it returns the result.
`Stages.clan` and `Stages.agent` pass their existing `_attempt(name, ...)` call through the wrapper
when one is set. With no wrapper, behavior is byte-for-byte unchanged.

**The three pipelines accept it.** `run_issue`, `run_review` and `run_ci_fix` each gain a
keyword-only `stage_wrapper: StageWrapper | None = None` and pass it to the `Stages(...)` they
build (`pipeline.py:445`, `pr_review.py:240`, `ci_fix.py:85`). `cli.py` does not change.

**The Prefect wrapper lives in `prefect_flows`.** It runs the call inside a Prefect task:

- task name = the stage name; task run names may get Prefect's automatic suffixes for repeats
- `persist_result=False`, `cache_policy=NO_CACHE`, `retries=0`
- the task takes no parameters that carry prompts, config or secrets; the stage name is the only
  identifying input (the call is closed over, not passed as a task argument)
- the wrapped call is the whole stage, so VK's retry-once happens inside one task run and shows
  as a warning line in that task's log

**Flow and task states.**

- When a stage fails twice, `StageFailed` passes through the stage's task, so that task run is
  Failed. VK then catches it, comments and returns its "Stopped: ..." summary, so the flow ends
  Completed (see Non-goals). Failures that VK raises outside a wrapped stage (memory, run log, an
  implementer that did not push) produce no Failed task; the flow log shows them.
- Only an exception that escapes VK fails the flow, as a nonzero CLI exit does today:
  `ConfigError`, `UsageLimitExceeded`, a crash, or a failure before VK starts (settings, token).
  Those keep the best-effort failure comment from today's `run_vk`.

## Calls made while writing (check these)

- A failed stage's task shows Failed even though the flow ends Completed. That is the point of
  the visibility work and does not make Prefect report VK's failure as its own.
- An exception that escapes VK still fails the flow and posts the failure comment, as today.
- `run_ci_fix` gets the `stage_wrapper` keyword only for symmetry; no `vk-ci-fix` flow is added.
- The `vk` loggers are set to INFO in the flow without `logging.basicConfig`.
- The processes VK starts (git, `make`, `uv`) must still find `uv`: the flow keeps `~/.local/bin`
  first on `PATH` and runs from the clone directory, as `vk_env` and `cwd=REPO_ROOT` do today.

## Left to the builder

- The exact uv commands for the system install, and how to keep the image's Prefect and VK's
  locked dependencies compatible (pinning the image tag to the locked Prefect version is one
  option). The check is: the flow imports `vk` on the managed worker and `uv pip check` is clean.
- The exact type of `StageWrapper` that satisfies mypy `--strict` with the generic `clan`/`agent`.
- Test shape. Expected at minimum: `Stages` routes `clan` and `agent` through a wrapper and is
  unchanged without one; each pipeline passes its `stage_wrapper` to `Stages`; the flow calls
  `run_issue`/`run_review` with the right arguments (stub them); the Prefect wrapper produces a
  task per stage with `persist_result=False` (use `prefect_test_harness` or inspect the task
  object); a stopped run leaves the flow Completed with VK's summary; an exception that escapes
  VK fails the flow and posts the comment; the token never appears in logs.
- README update for the new run view, and removal of now-dead helpers (`vk_command`, the
  subprocess code, `vk_env` if it no longer has a caller).

## References

- Pydantic AI, durable execution with Prefect:
  https://pydantic.dev/docs/ai/capabilities/durable_execution/prefect/ (`PrefectDurability`;
  `PrefectAgent` is deprecated). Source of the Level 2 option, the multiplied-retries warning and
  the serializable-inputs rule.
- Prefect, AI data analyst with pydantic-ai:
  https://docs.prefect.io/v3/examples/ai-data-analyst-with-pydantic-ai (agent run inside a
  `@flow`, no artifacts, no caching settings).

## Done means

- `make check` passes.
- A real `vk-issue` run on the managed pool shows one task per stage in the Prefect UI, with VK's
  log lines inside the right task.
- A run whose stage fails twice shows that task Failed, the flow Completed with VK's "Stopped"
  summary, and VK's error comment on the issue.
- `vk issue N` from a laptop behaves exactly as before.
