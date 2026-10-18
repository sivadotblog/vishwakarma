# VK Prefect Stage-Task Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run VK inside the Prefect flow process and show each VK stage (clan or judgment agent) as its own Prefect task.

**Architecture:** `src/vk` gains a Prefect-free seam: an optional `StageWrapper` on `Stages`, passed in through a `stage_wrapper` keyword on the three pipelines. `prefect_flows/stage_tasks.py` supplies a wrapper that runs each stage as a no-cache, no-persist Prefect task. `prefect_flows/flows.py` stops running the `vk` CLI as a subprocess and calls `run_issue` / `run_review` directly with that wrapper; `prefect.yaml` installs VK into the image's Python so the flow can import it.

**Tech Stack:** Python 3.12, Prefect 3.8.8, Pydantic AI 2.57, uv, pytest, mypy `--strict`, ruff.

**Spec:** `docs/superpowers/specs/2026-10-18-vk-prefect-task-visibility-design.md`

## Global Constraints

- `src/vk` never imports `prefect`; `prefect` stays in the `vk` dev dependency group.
- With no wrapper, VK behaves exactly as today (`vk issue N` on a laptop is unchanged; `cli.py` is not edited).
- Prefect task retries are 0; VK's `_attempt` retry-once stays the only retry. Stage tasks use `persist_result=False` and `cache_policy=NO_CACHE`, and take no parameters.
- A handled `StageFailed` leaves the flow **Completed** with VK's "Stopped: ..." summary; only an exception that escapes VK fails the flow.
- No secret (GitHub token, Gemini key, PEM) in a task name, task parameter, log line or exception message.
- Tests never contact Prefect Cloud, even when `PREFECT_API_URL` / `PREFECT_API_KEY` are set in the shell: any test that runs a Prefect flow or task uses `prefect.testing.utilities.prefect_test_harness`.
- uv only, never pip (`uv pip install --system` is uv). Never hand-edit `uv.lock`.
- `make check` from the repo root passes at the end. Line length and style follow the existing code (ruff config in root `pyproject.toml`).
- Commit only the files your task lists, with `git add <paths>`; never `git add -A` (the user's `.claude/settings.json` change must stay uncommitted). If `git commit` fails on `index.lock`, wait a few seconds and retry. End each commit message with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Review Focus

1. A stage whose first attempt fails and second succeeds: the wrapper is called **once** for that stage (both attempts inside one task) → test in Task 1.
2. The implementer/reviewer revision loop calls the same stage name twice: two separate task runs, no cache hit returning the first result → test in Task 2.
3. A stage that fails twice inside a flow that catches the error: task run Failed, flow run Completed → test in Task 2.
4. VK returns a "Stopped: ..." summary: the flow returns it and posts **no** extra failure comment → test in Task 3.
5. An exception escapes VK after the token exists (`UsageLimitExceeded`, `ConfigError`, a crash): comment posted, original exception re-raised, token not in logs → tests in Task 3.

---

### Task 1: Stage wrapper seam in `src/vk`

**Files:**

- Modify: `packages/vk/src/vk/pipeline.py` (`Stages` at line 71, `run_issue` at line 415 and its `Stages(...)` at line 445)
- Modify: `packages/vk/src/vk/pr_review.py` (`run_review` at line 198, `Stages(...)` at line 240)
- Modify: `packages/vk/src/vk/ci_fix.py` (`run_ci_fix` at line 36, `Stages(...)` at line 85)
- Create: `packages/vk/tests/test_stage_wrapper.py`

**Interfaces:**

- Consumes: nothing new.
- Produces (in `vk.pipeline`):

  ```python
  class StageWrapper(Protocol):
      def __call__[T](self, stage: str, call: Callable[[], T], /) -> T: ...
  ```

  `Stages` gains a last field `wrap: StageWrapper | None = None`. `run_issue`, `run_review`, `run_ci_fix` each gain keyword-only `stage_wrapper: StageWrapper | None = None` and build `Stages(cfg, model, remote_url, notebook, stage_wrapper)`.

- [ ] **Step 1: Write the failing tests** in `packages/vk/tests/test_stage_wrapper.py`. Patch `vk.pipeline.run_clan` and `vk.pipeline.agents.run_typed` with fakes (use `monkeypatch.setattr`); build `Stages(cfg)` with a minimal `Config` (copy how `tests/test_issue_pipeline.py` builds one). Tests:
  - `test_clan_without_wrapper_unchanged`: `Stages(cfg).clan("analyst", "m", Analysis)` returns the fake's result.
  - `test_clan_goes_through_wrapper`: a recording wrapper `def wrap(stage, call): seen.append(stage); return call()`; `Stages(cfg, wrap=wrap).clan("analyst", ...)` returns the fake's result and `seen == ["analyst"]`.
  - `test_agent_goes_through_wrapper`: same for `Stages(...).agent("triage", Triage, "i", "m", [])`, `seen == ["triage"]`.
  - `test_retry_happens_inside_one_wrapper_call`: the fake `run_clan` raises `RuntimeError` on the first call and returns on the second; `seen == ["analyst"]` (one wrapper call) and the fake was called twice.
  - `test_stage_failed_passes_through_wrapper`: the fake always raises; `pytest.raises(StageFailed)` and `seen == ["analyst"]`.
  - `test_pipelines_pass_stage_wrapper`: for each of `run_issue`, `run_review`, `run_ci_fix`, assert `inspect.signature(fn).parameters["stage_wrapper"].default is None` and `.kind is KEYWORD_ONLY`.
  - `test_run_issue_uses_stage_wrapper`: reuse the end-to-end setup of one passing test in `tests/test_issue_pipeline.py` (its fakes from `tests/helpers.py`), pass a recording `stage_wrapper`, and assert the recorded stages start with `["triage", "classifier"]` and include `"analyst"`, `"implementer"`, `"reviewer"`, `"pr_writer"`.

- [ ] **Step 2: Run them and see them fail**

  Run: `uv run pytest packages/vk/tests/test_stage_wrapper.py -q`
  Expected: FAIL (`Stages` has no `wrap`, pipelines have no `stage_wrapper`).

- [ ] **Step 3: Implement.** Add `StageWrapper` (import `Protocol` from `typing`) and the `wrap` field next to `Stages`. In `clan` and `agent`, build the existing `_attempt(name, ...)` call as a zero-argument callable and run it as `self.wrap(name, run) if self.wrap else run()`; a small private method `_run[T](self, name: str, call: Callable[[], T]) -> T` is fine. Keep the `isinstance` check in `clan` outside the wrapper. Add the `stage_wrapper` keyword to the three pipelines' signatures and docstrings ("`stage_wrapper` runs each stage, for example as a Prefect task") and pass it to `Stages`. Do not touch `cli.py`.

- [ ] **Step 4: Run the new and existing VK tests**

  Run: `uv run pytest packages/vk/tests -q -k "not prefect" && uv run mypy && uv run ruff check packages/vk && uv run ruff format --check packages/vk`
  Expected: all pass.

- [ ] **Step 5: Commit**

  ```bash
  git add packages/vk/src/vk/pipeline.py packages/vk/src/vk/pr_review.py packages/vk/src/vk/ci_fix.py packages/vk/tests/test_stage_wrapper.py
  git commit -m "feat(vk): optional stage wrapper on Stages and the pipelines"
  ```

---

### Task 2: Prefect stage tasks

**Files:**

- Create: `packages/vk/prefect_flows/stage_tasks.py`
- Create: `packages/vk/tests/test_prefect_stage_tasks.py`

**Interfaces:**

- Consumes: nothing from `vk` (the wrapper matches `vk.pipeline.StageWrapper` structurally; do not import `vk` here).
- Produces:
  - `stage_task[T](stage: str, call: Callable[[], T]) -> Task[[], T]`: a Prefect task named `stage`, `persist_result=False`, `cache_policy=NO_CACHE` (from `prefect.cache_policies`), `retries=0`, wrapping a zero-parameter function that returns `call()`.
  - `prefect_stage[T](stage: str, call: Callable[[], T]) -> T`: runs `stage_task(stage, call)()` and returns its result; exceptions propagate unchanged.

- [ ] **Step 1: Write the failing tests** in `packages/vk/tests/test_prefect_stage_tasks.py`. Import with `from prefect_flows.stage_tasks import prefect_stage, stage_task` (pytest's `pythonpath` covers `packages/vk`). Add a module-scoped autouse fixture that enters `prefect_test_harness()`. Tests:
  - `test_stage_task_options`: `t = stage_task("analyst", lambda: 1)`; assert `t.name == "analyst"`, `t.persist_result is False`, `t.cache_policy is NO_CACHE`, `t.retries == 0`, and `inspect.signature(t.fn).parameters == {}`.
  - `test_prefect_stage_returns_result`: inside a `@flow`, `prefect_stage("analyst", lambda: 41) + 1` returns `42`.
  - `test_repeated_stage_runs_twice`: a flow calls `prefect_stage("implementer", next_value)` twice where `next_value` returns 1 then 2; the flow returns `[1, 2]`; reading task runs for that flow run (`get_client(sync_client=True).read_task_runs(flow_run_filter=FlowRunFilter(id=FlowRunFilterId(any_=[state.state_details.flow_run_id])))`, with the flow called as `f(return_state=True)`) gives two runs whose names start with `"implementer"`.
  - `test_failed_stage_fails_task_not_flow`: a flow wraps `prefect_stage("analyst", boom)` (where `boom` raises `RuntimeError("x")`) in `try/except RuntimeError` and returns `"Stopped"`; the flow state `is_completed()`, its result is `"Stopped"`, and its single task run's state `is_failed()`.

- [ ] **Step 2: Run them and see them fail**

  Run: `uv run pytest packages/vk/tests/test_prefect_stage_tasks.py -q`
  Expected: FAIL with `ModuleNotFoundError: prefect_flows.stage_tasks`.

- [ ] **Step 3: Implement `packages/vk/prefect_flows/stage_tasks.py`** with a module docstring saying it runs each VK stage as a Prefect task for visibility only (no result storage, no caching, no retries: VK retries a stage itself). The zero-parameter inner function keeps prompts, config and secrets out of task inputs; say so in one comment.

- [ ] **Step 4: Run the tests**

  Run: `uv run pytest packages/vk/tests/test_prefect_stage_tasks.py -q && uv run mypy && uv run ruff check packages/vk && uv run ruff format --check packages/vk`
  Expected: all pass. The harness start takes some seconds; that is normal.

- [ ] **Step 5: Commit**

  ```bash
  git add packages/vk/prefect_flows/stage_tasks.py packages/vk/tests/test_prefect_stage_tasks.py
  git commit -m "feat(prefect): run each VK stage as a Prefect task"
  ```

---

### Task 3: Run VK in the flow process

Starts after Tasks 1 and 2 are committed.

**Files:**

- Modify: `packages/vk/prefect_flows/flows.py`
- Modify: `packages/vk/prefect_flows/prefect.yaml`
- Modify: `packages/vk/tests/test_prefect_flows.py`
- Modify: `packages/vk/README.md` ("Run on Prefect" section, lines 87–119)

**Interfaces:**

- Consumes: `vk.pipeline.run_issue(..., stage_wrapper=...)`, `vk.pr_review.run_review(..., stage_wrapper=...)` (Task 1); `prefect_stage` from `.stage_tasks` (Task 2, relative import like `.github_app`).
- Produces: `run_vk(kind: Kind, number: int, logger: Log, run_url: str | None) -> str` (same signature as today) and the unchanged flows `vk_issue(issue_number)`, `vk_review(pr_number)`. Removed: `vk_command`, the subprocess code.

- [ ] **Step 1: Rewrite the tests in `packages/vk/tests/test_prefect_flows.py`.** Delete `test_vk_command`, `use_script` and the subprocess-based tests. Keep `test_vk_env`, `test_failure_body`, `test_post_comment_request`, `test_flows_loads_as_prefect_script`, `test_run_vk_settings_failure_skips_comment`. Extend the `comments` fixture so it also (a) calls `monkeypatch.setenv(key, os.environ.get(key, ""))` for every key `vk_env` sets, so `run_vk`'s changes to `os.environ` are undone after the test, and (b) patches `flows.GitHub` to a stub class and `flows.with_bot_identity` to `lambda cfg, gh: cfg`. Add a helper that patches `flows.run_issue` / `flows.run_review` with a recorder that returns a given value or raises a given exception. New tests:
  - `test_run_vk_issue_calls_pipeline`: `run_vk("issue", 5, LOGGER, "u")` returns the stub's `"PR opened"`; the stub got `number == 5`, a `Caller` with `unattended is True` and `issue_number == 5`, a `Config` with `repo == "sivadotblog/vishwakarma"`, `github_token == "ghs_secret"`, `model == "google:m"`, `bot_login == "vk-factory[bot]"`, and `stage_wrapper is prefect_stage`; `comments.calls == []`.
  - `test_run_vk_review_calls_pipeline`: same for `"review"` → `run_review`, `Caller.pr_number == 7`.
  - `test_run_vk_sets_process_env`: after a run, `os.environ["GEMINI_API_KEY"] == "gk"` and `os.environ["PATH"]` starts with `~/.local/bin` (VK's `build_model` and the git/make/uv subprocesses read the process env).
  - `test_run_vk_stopped_summary_completes`: stub returns `"Stopped: the analyst step failed (x)."`; `run_vk` returns it and `comments.calls == []`.
  - `test_run_vk_escaped_error_comments_and_reraises`: stub raises `UsageLimitExceeded("budget")`; `pytest.raises(UsageLimitExceeded)`; `comments.calls == [("ghs_secret", 5, "The software factory run failed. Log: u")]`.
  - `test_run_vk_config_error_comments_and_reraises`: same with `ConfigError("bad")`.
  - `test_run_vk_comment_failure_still_raises_original`: `post_comment` raises `httpx.ConnectError`; the stub's `RuntimeError("boom")` is what propagates.
  - `test_run_vk_does_not_log_token`: stub raises `RuntimeError("boom")`; with `caplog` at DEBUG, `"ghs_secret"`, `"gk"` and `"pem"` are not in `caplog.text`.

- [ ] **Step 2: Run them and see them fail**

  Run: `uv run pytest packages/vk/tests/test_prefect_flows.py -q`
  Expected: FAIL (`flows` has no `run_issue` / `GitHub`).

- [ ] **Step 3: Implement in `flows.py`.**
  - Module docstring: the pull steps install VK into the image's Python; each run mints a token and calls VK's pipeline in-process, with each stage as a Prefect task; secrets are never logged. Remove the "never import `vk`" sentence.
  - Imports: `Caller` (`vk.approval`), `ConfigError`, `load_config` (`vk.config`), `GitHub`, `with_bot_identity` (`vk.github`), `run_issue` (`vk.pipeline`), `run_review` (`vk.pr_review`), `UsageLimitExceeded` (`pydantic_ai.exceptions`), and `from .stage_tasks import prefect_stage`.
  - `run_vk`: load settings and mint the token (unchanged, outside the `try`). Build `env = vk_env(os.environ, token, settings, state_dir)`, then `os.environ.update(env)` and `logging.getLogger("vk").setLevel(logging.INFO)`. Inside one `try`: `cfg = load_config(env)`, `gh = GitHub(cfg)`, `cfg = with_bot_identity(cfg, gh)`, then call `run_issue(cfg, gh, number, Caller(True, issue_number=number), stage_wrapper=prefect_stage)` or `run_review(cfg, gh, number, Caller(True, pr_number=number), stage_wrapper=prefect_stage)` and return its summary. `except ConfigError` → `logger.error("Configuration error: %s", exc)`; `except UsageLimitExceeded` → `logger.error("Token budget exceeded: %s", exc)`; then for any exception: post the best-effort failure comment exactly as today (log only `type(error).__name__` if the comment fails) and `raise` the original exception.
  - Delete `vk_command`, the `subprocess` import and any other import the change leaves unused. `vk_env` and `REPO_ROOT` stay (the loader test uses `REPO_ROOT`).

- [ ] **Step 4: Update `prefect.yaml`.**
  - Pin `image: prefecthq/prefect:3.8.8-python3.12` (matches the `prefect` version in `uv.lock`, so the locked VK dependencies fit the image's Prefect).
  - Add `PREFECT_LOGGING_EXTRA_LOGGERS: vk` to `job_variables.env`.
  - Append to the shell script, after `uv sync --locked`:
    ```
    PATH="$HOME/.local/bin:$PATH" uv export --frozen --package vk --no-dev --no-emit-workspace --no-hashes | PATH="$HOME/.local/bin:$PATH" uv pip install --system -r -
    PATH="$HOME/.local/bin:$PATH" uv pip install --system --no-deps packages/vk
    PATH="$HOME/.local/bin:$PATH" uv pip check --system
    ```
  - Update the comment above `pull:` to say the step also installs VK into the image's Python so the flow imports it.
  - Check locally that the export resolves: `uv export --frozen --package vk --no-dev --no-emit-workspace --no-hashes | head -5` prints requirement lines and no `vk` / `prefect` line.

- [ ] **Step 5: Update the README "Run on Prefect" section.** Say the pull steps also install VK into the image's Python; each flow run shows one task per VK stage (`triage`, `classifier`, `analyst`, `implementer`, `reviewer`, `pr_writer`, ...), with VK's log lines inside each task; a stage that failed twice shows as a Failed task while the flow still ends Completed with VK's "Stopped: ..." summary (VK's failure, not Prefect's); only an error that escapes VK fails the flow. Keep it short and in the README's existing style.

- [ ] **Step 6: Run the checks**

  Run: `uv run pytest packages/vk/tests/test_prefect_flows.py -q` then `make check` from the repo root.
  Expected: both pass.

- [ ] **Step 7: Commit**

  ```bash
  git add packages/vk/prefect_flows/flows.py packages/vk/prefect_flows/prefect.yaml packages/vk/tests/test_prefect_flows.py packages/vk/README.md
  git commit -m "feat(prefect): run VK in-process with a task per stage"
  ```

---

### Task 4: Whole-branch review and a real run (coordinator)

- [ ] **Step 1:** Review the full branch diff against the spec and this plan's Global Constraints and Review Focus. Run `make check` once.
- [ ] **Step 2:** Push the branch, open the PR (dependency note: none added), and deploy the branch with `VK_BRANCH=<branch> VK_DEPLOYMENT=<slug> uv run prefect --no-prompt deploy --all --prefect-file packages/vk/prefect_flows/prefect.yaml` (or `gh workflow run prefect-deploy.yml --ref <branch>`).
- [ ] **Step 3:** With the user's go-ahead, run `vk-issue/<slug>` on a small test issue. Check in the Prefect UI: one task per stage, VK log lines inside the tasks, the flow result is VK's summary, and a draft PR exists.

## Amendment (after the first real run)

The managed pool rejected `prefecthq/prefect:3.8.8-python3.12`: managed pools accept only Prefect's listed tags (`3-python3.12`, `3.7-python3.12`, ...), and there is no 3.8 tag. Task 3 Step 4 changes to: keep `image: prefecthq/prefect:3-python3.12`, and drop `--no-dev` from the `uv export` so the install also pins the locked `prefect==3.8.8` (the vk dev group adds only `prefect` and `types-requests`). The image's Prefect then matches `uv.lock` even when the floating tag moves; `uv pip check --system` still guards the result.

The system install then crashed the run during the pull step. Final shape, as the user asked: no `image` job variable (the pool's default latest image), the pull step only runs `uv sync --locked --python "$(command -v python)"` after the existing toolchain line, and `flows.py` activates that `.venv` in-process with `site.addsitedir` before it imports VK (appended, so the worker's Prefect still wins).
