import ast
from pathlib import Path
from typing import Any

from pydantic_ai import ModelMessage, ModelRequest, ModelResponse, ToolCallPart
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel

from vk import clans
from vk.clans import CLANS, load_prompt, run_clan
from vk.config import Config
from vk.models import Classification

from .helpers import SETTINGS

MAX_LITERAL = 300  # characters
MAX_REPO_INSTRUCTIONS = SETTINGS.prompts.max_repo_instruction_chars
CFG = Config(repo="o/r", github_token="t", state_dir=Path("/x"))


def test_repo_instruction_files_are_injected(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("Use uv, never pip.")
    (tmp_path / "CLAUDE.md").write_text("Run make check before done.")

    prompt = CLANS["implementer"].prompt(CFG, tmp_path)

    assert "Use uv, never pip." in prompt
    assert "Run make check before done." in prompt
    assert prompt.index("AGENTS.md") < prompt.index("CLAUDE.md")


def test_no_section_without_instruction_files(tmp_path: Path) -> None:
    assert "Repository instructions" not in CLANS["analyst"].prompt(CFG, tmp_path)


def test_clans_without_a_repo_get_no_section() -> None:
    assert "Repository instructions" not in CLANS["classifier"].prompt(CFG, None)


def test_long_instruction_files_are_truncated(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("x" * (MAX_REPO_INSTRUCTIONS + 500))

    prompt = CLANS["reviewer"].prompt(CFG, tmp_path)

    assert "x" * MAX_REPO_INSTRUCTIONS in prompt
    assert "x" * (MAX_REPO_INSTRUCTIONS + 1) not in prompt
    assert "[truncated]" in prompt


def test_analyst_is_told_to_read_nested_instruction_files() -> None:
    assert "AGENTS.md" in CLANS["analyst"].prompt(CFG, Path("/nowhere"))


def test_run_clan_returns_the_clan_output_model() -> None:
    payload = {
        "type": "bug",
        "priority": "high",
        "complexity": "small",
        "affected_area": "api",
        "summary": "Reset emails are sent twice.",
    }
    seen: list[str] = []

    def factory(name: str) -> Model:
        seen.append(name)

        def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, payload)])

        return FunctionModel(fn)

    result = run_clan("classifier", "go", CFG, model=factory)

    assert result == Classification.model_validate(payload)
    assert seen == ["classifier"]


def _instructions(name: str, payload: dict[str, Any]) -> str:
    """Run one clan with a fake model and return the instructions the model saw."""
    seen: list[str] = []

    def factory(_name: str) -> Model:
        def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            first = messages[0]
            assert isinstance(first, ModelRequest)
            seen.append(first.instructions or "")
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, payload)])

        return FunctionModel(fn)

    run_clan(name, "go", CFG, model=factory)
    return seen[0]


def test_clans_with_tools_are_told_to_batch_tool_calls() -> None:
    research: dict[str, Any] = {"summary": "s", "findings": [], "gaps": [], "artifact_id": None}

    assert "## Tool calls" in _instructions("researcher", research)


def test_clans_without_tools_get_no_tool_call_section() -> None:
    classification = {
        "type": "bug",
        "priority": "low",
        "complexity": "small",
        "affected_area": "api",
        "summary": "s",
    }

    assert "## Tool calls" not in _instructions("classifier", classification)


def test_no_module_carries_long_model_text() -> None:
    """Wording a model reads lives in `prompts/*.md`; code only fills placeholders."""
    long = []
    for source in sorted(Path(clans.__file__).parent.glob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
        }
        long += [
            f"{source.name}:{node.lineno} ({len(node.value)} chars)"
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
            and len(node.value) > MAX_LITERAL
        ]
    assert not long, f"move this text into src/vk/prompts/*.md: {long}"


def test_load_prompt_fills_only_the_named_placeholders() -> None:
    assert "`issue-7-x.md`" in load_prompt("memory", page="issue-7-x.md")
    assert "{page}" in load_prompt("memory")
