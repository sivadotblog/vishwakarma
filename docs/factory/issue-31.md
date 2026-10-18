# Factory run log: issue #31

## Summary

Fix trailing newline stripping in git.read_files and raise ConfigError for invalid VK_MAX_OUTPUT_TOKENS values in packages/vk.

Reviewer verdict: approve.

## Classification

- type: bug
- priority: medium
- complexity: small
- affected_area: packages/vk

## Analysis

### Problem

`git.read_files` strips trailing newlines and whitespace from files fetched via git because helper `_run` calls `proc.stdout.strip()`, causing notebooks and other files read from git to lose trailing newlines. Additionally, non-integer values for environment variables like `VK_MAX_OUTPUT_TOKENS` raise an unhandled `ValueError` in `load_config()` rather than raising `ConfigError`, causing CLI executions to crash with a traceback instead of exiting cleanly with status code 2.

### Approach

Add a `strip: bool = True` parameter to `git._run`, and pass `strip=False` in `git.read_files` so file contents read from git preserve trailing newlines and whitespace. Wrap integer conversion of `VK_MAX_OUTPUT_TOKENS` and `VK_MAX_INPUT_TOKENS` in `load_config` within `try...except ValueError` blocks that raise `ConfigError`. Alternative rejected: Changing `_run` to never strip stdout by default was rejected because other git helpers (such as `rev-parse`) rely on stripping trailing newlines from command output (e.g. SHAs).

### Plan

1. In `packages/vk/src/vk/git.py`, update `_run` to accept an optional `strip: bool = True` keyword argument and return `proc.stdout.strip() if strip else proc.stdout`.
2. In `packages/vk/src/vk/git.py`, update `read_files` to call `_run` with `strip=False` when reading file contents via `git show`.
3. In `packages/vk/src/vk/config.py`, wrap parsing of `VK_MAX_OUTPUT_TOKENS` and `VK_MAX_INPUT_TOKENS` in `try...except ValueError` blocks to raise `ConfigError` with descriptive error messages when non-integer strings are provided.
4. In `packages/vk/tests/test_git.py`, update assertions in `test_read_files_filters_and_reads_a_branch_or_the_default` and `test_read_files_accepts_head_and_plain_branch_names` to expect preserved trailing newlines (`"A\\n"`), and add a unit test verifying trailing newline and whitespace preservation.
5. In `packages/vk/tests/test_config.py`, add a test verifying that invalid non-integer values for `VK_MAX_OUTPUT_TOKENS` and `VK_MAX_INPUT_TOKENS` raise `ConfigError`.
6. Run `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`, and `uv run pytest` to verify all quality checks pass cleanly.

### Acceptance criteria

- [x] git.read_files preserves trailing newlines and leading/trailing whitespace of files read from git refs.
- [x] Setting VK_MAX_OUTPUT_TOKENS or VK_MAX_INPUT_TOKENS to a non-integer value raises ConfigError during load_config().
- [x] Executing the CLI with invalid VK_MAX_OUTPUT_TOKENS outputs 'Configuration error: ...' to stderr and exits with status code 2.
- [x] uv run ruff check, uv run ruff format --check, uv run mypy, and uv run pytest pass cleanly.

## Implementation

Branch `vk/bug-notebook-newlines-config-error` (base `main`).

### Change summary

- `packages/vk/src/vk/git.py`: Added optional strip parameter to git._run and set strip=False in git.read_files to preserve trailing newlines and whitespace.
- `packages/vk/src/vk/config.py`: Wrapped VK_MAX_OUTPUT_TOKENS and VK_MAX_INPUT_TOKENS parsing in try...except ValueError blocks to raise ConfigError.
- `packages/vk/tests/test_git.py`: Updated assertions to expect preserved trailing newlines ("A\n") and added test_read_files_preserves_whitespace_and_newlines.
- `packages/vk/tests/test_config.py`: Added test_output_token_budget_comes_from_the_environment and test_invalid_token_limits_raise_config_error.

### Verification

- `uv run ruff check`: pass: All checks passed!
- `uv run ruff format --check`: pass: 105 files already formatted
- `uv run mypy --strict packages/vk apps/api`: pass: Success: no issues found in 43 source files
- `uv run pytest`: pass: 269 passed in 63.85s
- `npm run lint -w web && npm run check -w web && npm run build -w web`: pass: Astro lint, check, and build completed with 0 errors

### Deviations

- None

## Review

Verdict: **approve**

The implementation correctly addresses both issues with minimal, targeted changes. `git.read_files` now passes `strip=False` to preserve raw file content with trailing newlines and whitespace, while `config.load_config` handles invalid integer token overrides by raising a `ConfigError`, allowing `cli.main()` to output clean configuration errors and exit with status code 2. All acceptance criteria and verification checks pass.

### Criteria results

- pass: git.read_files preserves trailing newlines and leading/trailing whitespace of files read from git refs. (packages/vk/src/vk/git.py adds strip: bool = True to _run and passes strip=False in read_files. In packages/vk/tests/test_git.py, existing tests were updated to expect unstripped trailing newlines ("A\n") and test_read_files_preserves_whitespace_and_newlines was added and passes.)
- pass: Setting VK_MAX_OUTPUT_TOKENS or VK_MAX_INPUT_TOKENS to a non-integer value raises ConfigError during load_config(). (packages/vk/src/vk/config.py wraps integer parsing for both VK_MAX_OUTPUT_TOKENS and VK_MAX_INPUT_TOKENS in try...except ValueError blocks that raise ConfigError. Unit test test_invalid_token_limits_raise_config_error in packages/vk/tests/test_config.py verifies this for "abc", "12.3", and "".)
- pass: Executing the CLI with invalid VK_MAX_OUTPUT_TOKENS outputs 'Configuration error: ...' to stderr and exits with status code 2. (cli.main() catches ConfigError and exits with code 2. CLI execution verified via CLI invocation (GITHUB_TOKEN=test VK_MODEL=test:m VK_REPO=o/r VK_MAX_OUTPUT_TOKENS=abc uv run vk issue 123), which output "Configuration error: VK_MAX_OUTPUT_TOKENS='abc' must be an integer." to stderr and returned status code 2.)
- pass: uv run ruff check, uv run ruff format --check, uv run mypy, and uv run pytest pass cleanly. (Verified locally: ruff check passed, ruff format check passed, mypy --strict passed with zero errors, and all 268 pytest tests in packages/vk passed.)
