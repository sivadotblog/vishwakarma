# Issue #31: vk: notebook files lose trailing newlines; bad VK_MAX_OUTPUT_TOKENS crashes

- Summary: Fix whitespace stripping in `git.read_files` (`packages/vk/src/vk/git.py`) and ensure invalid `VK_MAX_OUTPUT_TOKENS` raises `ConfigError` rather than `ValueError` (`packages/vk/src/vk/config.py`).
- Verdict: proceed.


## Classification
- Type: bug
- Priority: medium
- Complexity: small
- Affected Area: packages/vk

## Research Notes
- `git.read_files` previously called `_run` without passing a option to preserve unstripped output, causing `_run` to execute `proc.stdout.strip()`. This stripped trailing newlines and leading/trailing whitespace from files read via `git show`.
- Adding `strip: bool = True` parameter to `_run` and passing `strip=False` in `git.read_files` preserves exact file contents.
- `VK_MAX_OUTPUT_TOKENS` and `VK_MAX_INPUT_TOKENS` in `config.py` were converted using raw `int()`, raising unhandled `ValueError`. Wrapping integer parsing in a `try...except ValueError` to raise `ConfigError` fixes the CLI traceback and allows `cli.main()` to catch `ConfigError` and exit with code 2.
# Issue #31: vk: notebook files lose trailing newlines; bad VK_MAX_OUTPUT_TOKENS crashes

- Summary: Fix whitespace stripping in `git.read_files` (`packages/vk/src/vk/git.py`) and ensure invalid `VK_MAX_OUTPUT_TOKENS` / `VK_MAX_INPUT_TOKENS` raise `ConfigError` rather than `ValueError` (`packages/vk/src/vk/config.py`).
- Status: Implemented & Verified

## Changes Made
- Added `strip: bool = True` parameter to `git._run`.
- Updated `git.read_files` to pass `strip=False` when reading file contents using `git show`.
- Wrapped integer parsing of `VK_MAX_OUTPUT_TOKENS` and `VK_MAX_INPUT_TOKENS` in `config.load_config` with `try...except ValueError` blocks to raise `ConfigError`.
- Updated unit tests in `test_git.py` to assert preserved trailing newlines and added test for leading/trailing whitespace preservation.
- Added tests in `test_config.py` asserting `ConfigError` is raised for non-integer token limits.

## Repo notes
- `make` is not available in test execution environments, but individual check commands work: `npm ci`, `npm run lint -w web && npm run check -w web && npm run build -w web`, `uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest`.


## Review Notes
- Verified diff against `main` on branch `vk/bug-notebook-newlines-config-error`.
- Checked all 4 acceptance criteria individually; all pass.
- Verification commands (`ruff check`, `ruff format --check`, `mypy`, `pytest`, `npm` scripts) verified and passing.
- Implementation is clean, minimal, safe, and surgical. Approved.
