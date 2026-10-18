# VK on Prefect Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run VK's issue and review pipelines as on-demand Prefect flows on the managed `vk-agents` pool, replacing the two GitHub Actions workflows.

**Architecture:** A `packages/vk/prefect_flows/` directory sits next to `src/`, inside the same uv project. The flow module imports only stdlib, Prefect, `httpx` and `cryptography`, because it runs in the Prefect image's Python. At run time it bootstraps a toolchain (uv, make, Node 22), runs `uv sync --locked`, mints a GitHub App installation token, and runs `uv run --package vk vk issue|review <n> --unattended` as a subprocess. A local `deploy.py` registers both deployments with `flow.from_source(...)`.

**Tech Stack:** Python 3.12, Prefect 3 (3.8.x), httpx, cryptography, uv 0.12.1, pytest, mypy `--strict`, ruff.

**Spec:** `docs/superpowers/specs/2026-10-18-vk-prefect-flows-design.md`

## Global Constraints

- One uv project: there is no new workspace member or lockfile. Add deps only with `uv add`; never hand-edit `uv.lock`.
- Never use pip anywhere, including Prefect's `pip_packages`.
- The flow module (`flows.py`, `github_app.py`) may import only the stdlib, `prefect`, `httpx`, and `cryptography`. It must **never** import `vk`.
- Repo: `sivadotblog/vishwakarma`, URL `https://github.com/sivadotblog/vishwakarma`.
- Work pool: `vk-agents`. Image: `prefecthq/prefect:3-python3.12`. No schedule.
- Flow names are `vk-issue` and `vk-review`, each with `timeout_seconds=3600`.
- Prefect Secret blocks are `vk-app-private-key` and `vk-gemini-api-key`. Prefect Variables are `vk_app_id` and `vk_model`; `vk_model` defaults to `google:gemini-3.5-flash`.
- VK env: `GITHUB_TOKEN`, `VK_BOT_LOGIN=<slug>[bot]`, `GEMINI_API_KEY`, `VK_MODEL`, `VK_REPO=sivadotblog/vishwakarma`, `VK_STATE_DIR=<fresh temp dir>`, `PYDANTIC_AI_NO_BANNER=1`.
- The failure comment reads exactly `The software factory run failed. Log: <flow run UI URL>`.
- Style: ruff line length 100, mypy strict, and module docstrings like `packages/vk/src/vk/*.py`.
- `make check` must pass.

## Review Focus

- **A VK run that exits nonzero** must post the failure comment and also fail the Prefect run. The comment alone is not enough. Covered by Task 3's `test_run_vk_failure_comments_and_raises`.
- **A failure before a token exists** (bootstrap or token minting fails) must not attempt a comment and must not mask the original error. Covered by Task 3's `test_run_vk_bootstrap_failure_skips_comment`.
- **Secrets must not leak into logs.** Never log the env dict, the token, or the private key. Covered by Task 3's `test_run_vk_does_not_log_token`.
- **A branch name with `/` or uppercase letters** (`vk/Foo_bar`) still has to produce a valid deployment name. Covered by Task 4's `test_deployment_name_slugifies`.
- **A failure-comment POST that itself fails** must not hide VK's original failure. The run still raises the VK error. Covered by Task 3's `test_run_vk_comment_failure_still_raises_vk_error`.

---

### Task 1: Scaffolding and dependency (do first, alone)

**Files:**

- Modify: `packages/vk/pyproject.toml` (the `dev` group gains `prefect`, via `uv add`)
- Modify: `pyproject.toml` (root): mypy `files` and pytest `pythonpath`
- Create: `packages/vk/prefect_flows/__init__.py`

This is a deliberate deviation from the spec's "`prefect` dependency group". `prefect` goes into the existing `dev` group of `packages/vk`, next to `types-requests`, so `make setup` installs it with no default-groups config.

- [ ] **Step 1:** Run `uv add --package vk --dev "prefect>=3.8.8"`. Expected: `uv.lock` updated and `uv run python -c "import prefect, httpx, cryptography"` exits 0.
- [ ] **Step 2:** Create `packages/vk/prefect_flows/__init__.py` with the docstring `"""Prefect flows that run VK on the managed vk-agents pool."""`.
- [ ] **Step 3:** In the root `pyproject.toml`, append `"packages/vk/prefect_flows"` to `[tool.mypy] files` and add `pythonpath = ["packages/vk"]` to `[tool.pytest.ini_options]`.
- [ ] **Step 4:** Run `make check-python`. Expected: PASS.
- [ ] **Step 5:** Commit with `chore(prefect): add prefect dev dependency and prefect_flows package`.

### Task 2: GitHub App token minting

**Files:**

- Create: `packages/vk/prefect_flows/github_app.py`
- Test: `packages/vk/tests/test_prefect_github_app.py`

**Interfaces:**

- Produces:
  - `API = "https://api.github.com"`
  - `@dataclass(frozen=True) class AppToken: token: str; bot_login: str`, where `bot_login` is `"<slug>[bot]"`
  - `def app_jwt(app_id: str, private_key_pem: str, now: float | None = None) -> str`
  - `def installation_token(app_id: str, private_key_pem: str, repo: str, client: httpx.Client | None = None) -> AppToken`

- [ ] **Step 1: Write the failing tests.** Generate an RSA key in a fixture with `rsa.generate_private_key(public_exponent=65537, key_size=2048)` and serialize it to PKCS8 PEM.
  - `test_app_jwt_claims_and_signature`: `app_jwt("123", pem, now=1_000_000)` splits into 3 base64url parts. The header is `{"alg": "RS256", "typ": "JWT"}` and the payload is `{"iat": 999_940, "exp": 1_000_540, "iss": "123"}`. The signature verifies with `public_key.verify(sig, f"{h}.{p}".encode(), padding.PKCS1v15(), hashes.SHA256())`.
  - `test_installation_token_calls_github`: pass `httpx.Client(transport=httpx.MockTransport(handler))`. The handler answers three requests:
    - `GET /app` → `{"slug": "vk-factory"}`
    - `GET /repos/sivadotblog/vishwakarma/installation` → `{"id": 7}`
    - `POST /app/installations/7/access_tokens` → `{"token": "ghs_x"}`

    Assert the result is `AppToken(token="ghs_x", bot_login="vk-factory[bot]")`. Also assert every request carried `Authorization: Bearer <jwt>`, `Accept: application/vnd.github+json` and `X-GitHub-Api-Version: 2022-11-28`.

  - `test_installation_token_raises_on_http_error`: the handler returns 404 for `/installation`, and `installation_token` raises `httpx.HTTPStatusError`.
- [ ] **Step 2:** Run `uv run pytest packages/vk/tests/test_prefect_github_app.py -v`. Expected: FAIL (ImportError).
- [ ] **Step 3:** Implement `github_app.py`. Build the JWT by hand: base64url without padding, compact JSON (`separators=(",", ":")`), signed with `cryptography` PKCS1v15 + SHA256, `iat = int(now) - 60`, `exp = int(now) + 540`. Call `raise_for_status()` on every response. When `client` is None, create and close one.
- [ ] **Step 4:** Rerun the tests. Expected: PASS. Then run `uv run mypy` and `uv run ruff check`. Expected: clean.
- [ ] **Step 5:** Commit with `feat(prefect): mint GitHub App installation tokens`.

### Task 3: The flows

**Files:**

- Create: `packages/vk/prefect_flows/flows.py`
- Create: `packages/vk/prefect_flows/bootstrap.sh` (executable)
- Test: `packages/vk/tests/test_prefect_flows.py`

**Interfaces:**

- Consumes: `AppToken` and `installation_token(app_id, private_key_pem, repo)` from Task 2. Import them as `from prefect_flows.github_app import AppToken, installation_token`.
- Produces:
  - `REPO = "sivadotblog/vishwakarma"`, `DEFAULT_MODEL = "google:gemini-3.5-flash"`, `REPO_ROOT = Path(__file__).resolve().parents[3]`
  - `Kind = Literal["issue", "review"]`
  - `@dataclass(frozen=True) class Settings: app_id: str; private_key: str; gemini_api_key: str; model: str`
  - `def load_settings() -> Settings`: reads `Secret.load("vk-app-private-key").get()`, `Secret.load("vk-gemini-api-key").get()`, `Variable.get("vk_app_id")` and `Variable.get("vk_model", default=DEFAULT_MODEL)`. Raise `RuntimeError("Prefect variable vk_app_id is not set")` if it is missing.
  - `def bootstrap() -> None`: runs `bootstrap.sh` with `cwd=REPO_ROOT` and `check=True`, and logs its output.
  - `def vk_command(kind: Kind, number: int) -> list[str]`: returns `["uv", "run", "--package", "vk", "vk", kind, str(number), "--unattended"]`
  - `def vk_env(base: Mapping[str, str], token: AppToken, settings: Settings, state_dir: Path) -> dict[str, str]`: `base` plus the seven VK vars from Global Constraints, with `~/.local/bin` prepended to `PATH`.
  - `def failure_body(run_url: str | None) -> str`
  - `def post_comment(token: str, number: int, body: str, client: httpx.Client | None = None) -> None`: `POST /repos/{REPO}/issues/{number}/comments`. This endpoint serves PRs too.
  - `def run_vk(kind: Kind, number: int, logger: logging.Logger | logging.LoggerAdapter[logging.Logger], run_url: str | None) -> str`: returns VK's stdout.
  - `@flow(name="vk-issue", timeout_seconds=3600) def vk_issue(issue_number: int) -> str` and `@flow(name="vk-review", timeout_seconds=3600) def vk_review(pr_number: int) -> str`. Each calls `run_vk` with `get_run_logger()` and `prefect.runtime.flow_run.ui_url`.

**`run_vk` order:**

1. `bootstrap()`
2. `load_settings()`
3. `installation_token(...)`
4. Run `vk_command` with `vk_env` (cwd `REPO_ROOT`, `state_dir` from `tempfile.mkdtemp(prefix="vk-state-")`). Forward stderr to `logger.info` line by line as it arrives; send stdout to a temp file so the pipe can't deadlock.
5. On a nonzero exit, try `post_comment(token, number, failure_body(run_url))`. Log, don't raise, if the comment fails. Then raise `RuntimeError(f"vk {kind} {number} exited {code}")`.
6. Exceptions from steps 1-3 propagate unchanged, with no comment.

`bootstrap.sh` (bash, `set -euo pipefail`):

- Use `sudo` only when `id -u` is not 0 and `sudo` exists.
- When `make` or `node` is missing, run `apt-get update` and install `make curl ca-certificates`, then Node 22 from NodeSource (`curl -fsSL https://deb.nodesource.com/setup_22.x | bash -` then `apt-get install -y nodejs`).
- When `uv` is missing, install uv with `curl -LsSf https://astral.sh/uv/0.12.1/install.sh | sh` and `export PATH="$HOME/.local/bin:$PATH"`.
- Finally run `uv sync --locked`.

- [ ] **Step 1: Write the failing tests.** Monkeypatch these module attributes: `flows.bootstrap`, `flows.load_settings` (returns `Settings("1", "pem", "gk", "google:m")`), `flows.installation_token` (returns `AppToken("ghs_secret", "vk-factory[bot]")`), `flows.post_comment` (a recorder), and `flows.vk_command`, which returns `[sys.executable, "-c", <script>]` so a real subprocess runs.
  - `test_vk_command`: `vk_command("review", 9) == ["uv", "run", "--package", "vk", "vk", "review", "9", "--unattended"]`.
  - `test_vk_env`: the result contains `GITHUB_TOKEN="ghs_secret"`, `VK_BOT_LOGIN="vk-factory[bot]"`, `GEMINI_API_KEY="gk"`, `VK_MODEL="google:m"`, `VK_REPO="sivadotblog/vishwakarma"`, `PYDANTIC_AI_NO_BANNER="1"`, and `VK_STATE_DIR=str(tmp_path)`. `PATH` starts with `str(Path.home() / ".local/bin")`. A key from `base` is preserved.
  - `test_failure_body`: `failure_body("https://app.prefect.cloud/x") == "The software factory run failed. Log: https://app.prefect.cloud/x"`.
  - `test_run_vk_success_returns_stdout`: the script prints `done` to stdout and `step 1` to stderr. Assert `run_vk("issue", 5, logger, "u") == "done"`, that `step 1` was logged (pytest `caplog`), and that no comment was posted.
  - `test_run_vk_failure_comments_and_raises`: the script runs `sys.exit(3)`. `pytest.raises(RuntimeError, match="vk issue 5 exited 3")` passes, and the recorder got exactly `("ghs_secret", 5, "The software factory run failed. Log: u")`.
  - `test_run_vk_bootstrap_failure_skips_comment`: `bootstrap` raises `subprocess.CalledProcessError(1, "bootstrap.sh")`. That same error propagates, and no comment is posted.
  - `test_run_vk_comment_failure_still_raises_vk_error`: the script exits 2 and `post_comment` raises `httpx.ConnectError("x")`. `RuntimeError` matching `exited 2` is raised.
  - `test_run_vk_does_not_log_token`: after a failing run, `"ghs_secret"` and `"pem"` appear nowhere in `caplog.text`.
  - `test_post_comment_request`: a MockTransport client records `POST https://api.github.com/repos/sivadotblog/vishwakarma/issues/5/comments` with JSON `{"body": "b"}` and `Authorization: Bearer ghs_x`.
- [ ] **Step 2:** Run `uv run pytest packages/vk/tests/test_prefect_flows.py -v`. Expected: FAIL (ImportError).
- [ ] **Step 3:** Implement `flows.py` and `bootstrap.sh` to the interfaces above, then `chmod +x bootstrap.sh`.
- [ ] **Step 4:** Rerun the tests. Expected: PASS. Then run `bash -n packages/vk/prefect_flows/bootstrap.sh`, `uv run mypy` and `uv run ruff check`. Expected: clean.
- [ ] **Step 5:** Commit with `feat(prefect): vk-issue and vk-review flows`.

### Task 4: Deployment script

**Files:**

- Create: `packages/vk/prefect_flows/deploy.py`
- Test: `packages/vk/tests/test_prefect_deploy.py`

**Interfaces:**

- Produces:
  - `REPO_URL = "https://github.com/sivadotblog/vishwakarma"`, `WORK_POOL = "vk-agents"`, `IMAGE = "prefecthq/prefect:3-python3.12"`
  - `ENTRYPOINTS = {"vk-issue": "packages/vk/prefect_flows/flows.py:vk_issue", "vk-review": "packages/vk/prefect_flows/flows.py:vk_review"}`
  - `def deployment_name(branch: str) -> str`: lowercase, each run of characters outside `[a-z0-9]` becomes `-`, and leading and trailing `-` are stripped.
  - `def main(argv: Sequence[str] | None = None) -> int`: argparse `--branch` (default `main`). For each entrypoint, call `flow.from_source(source=GitRepository(url=REPO_URL, branch=branch), entrypoint=...).deploy(name=deployment_name(branch), work_pool_name=WORK_POOL, job_variables={"image": IMAGE})`. Print `prefect deployment run '<flow>/<name>'` for each. Return 0.
  - At the bottom: `if __name__ == "__main__": raise SystemExit(main())`.

deploy.py must not import `prefect_flows.flows`, because `from_source` loads the flow from git. The flow names in `ENTRYPOINTS` must match Task 3's `@flow(name=...)`.

- [ ] **Step 1: Write the failing tests.**
  - `test_deployment_name_slugifies`: `deployment_name("main") == "main"`, `deployment_name("vk/Foo_bar") == "vk-foo-bar"` and `deployment_name("--x--") == "x"`.
  - `test_main_deploys_both_flows`: monkeypatch `deploy.flow.from_source` with a fake whose `.deploy(**kw)` records its kwargs. After `main(["--branch", "feat/x"])`, there are two records, both with `name="feat-x"`, `work_pool_name="vk-agents"` and `job_variables={"image": "prefecthq/prefect:3-python3.12"}`. The `from_source` entrypoints equal the two `ENTRYPOINTS` values, and each source is a `GitRepository` with `branch == "feat/x"`.
- [ ] **Step 2:** Run `uv run pytest packages/vk/tests/test_prefect_deploy.py -v`. Expected: FAIL (ImportError).
- [ ] **Step 3:** Implement `deploy.py`. Import with `from prefect import flow` and `from prefect.runner.storage import GitRepository`.
- [ ] **Step 4:** Rerun the tests. Expected: PASS. Then run `uv run mypy` and `uv run ruff check`. Expected: clean.
- [ ] **Step 5:** Commit with `feat(prefect): deploy script for the vk-agents pool`.

### Task 5: Docs

**Files:**

- Modify: `packages/vk/README.md`. Edit the "GitHub App identity and the review trigger" section (about lines 67-79) and add a new `## Run on Prefect` section right after it.
- Modify: `AGENTS.md` line 13. `CLAUDE.md` is a symlink to it, so don't edit `CLAUDE.md` separately.

- [ ] **Step 1:** Add `## Run on Prefect` to `packages/vk/README.md` with:
  - the four Prefect objects to create (the Secret blocks and Variables from Global Constraints, each with what it holds)
  - how to deploy: `uv run --package vk python packages/vk/prefect_flows/deploy.py [--branch <b>]`, with `PREFECT_API_URL` and `PREFECT_API_KEY` set
  - how to run: `prefect deployment run 'vk-issue/main' -p issue_number=<n>` and `prefect deployment run 'vk-review/main' -p pr_number=<n>`
  - that managed runs pull from GitHub, so changes must be pushed first
  - that the pool runs one flow at a time
- [ ] **Step 2:** In the existing section, add one sentence saying the two workflows are turned off (`gh workflow disable`) in favour of the Prefect flows and will be deleted later. Leave the rest of that section and the example workflow alone.
- [ ] **Step 3:** Change `AGENTS.md` line 13 to say that VK runs on demand as Prefect flows on the `vk-agents` pool (see `packages/vk/README.md`), and that the `vk` label no longer triggers anything. Change "Hand it to VK" to mean starting the `vk-issue` deployment for the issue.
- [ ] **Step 4:** Run `npx prettier --check AGENTS.md packages/vk/README.md` if prettier covers them, then `make check`. Expected: PASS.
- [ ] **Step 5:** Commit with `docs(vk): document running VK on Prefect`.

### Task 6: Live verification (owner-gated, not for implementer subagents)

- [ ] Push the branch and open the PR. The description justifies the new dependency in one line: "prefect: deploy, typecheck and test the Prefect flows; the managed image ships it at run time".
- [ ] Once the owner confirms the blocks and variables exist, run `deploy.py --branch <branch>` and start `vk-issue/<slug>` on a throwaway issue. Success means VK opens a draft PR.
- [ ] After the owner merges: run `deploy.py` (main), then `gh workflow disable vishwakarma.yml` and `gh workflow disable vishwakarma-review.yml`.

## Parallelism

Task 1 runs first, alone, because it touches `uv.lock` and the shared config. Tasks 2-5 then touch disjoint files and can run in parallel. Task 3 depends on Task 2 only through the interface block above, and its tests monkeypatch `installation_token`. Task 6 is done by the session lead with the owner.

## Amendment (2026-10-18, owner direction)

- Deployment moved from `deploy.py` to Prefect's CI/CD pattern. `packages/vk/prefect_flows/prefect.yaml`
  defines both deployments, and `.github/workflows/prefect-deploy.yml` runs the marketplace
  action `PrefectHQ/actions-prefect-deploy@v4`. Pushes to `main` deploy `<flow>/main`, and a
  manual dispatch on a branch deploys `<flow>/<branch-slug>`. The branch reaches the run through
  `VK_BRANCH`, which is baked into the job env and resolved by the `git_clone` pull step at run
  time. `deploy.py` and its tests are removed.
- `bootstrap.sh` is removed. The toolchain install (make, Node 22, uv) and `uv sync --locked`
  are now a `run_shell_script` pull step in `prefect.yaml`. This still uses no pip: the owner
  suggested a pip install step, but the repo's hard rules forbid pip, and pip could not install
  make or Node in any case.
- New repo secret: `PREFECT_API_KEY`. The workspace API URL is set in the workflow; it is not a
  secret.
