"""Shared fakes and payloads for the end-to-end pipeline tests."""

import json
import subprocess
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, NamedTuple

import requests
from pydantic_ai import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextContent,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel

from vk.config import Config, read_settings

SETTINGS = read_settings()  # the shipped vk.toml


def with_settings(cfg: Config, **sections: dict[str, Any]) -> Config:
    """`cfg` with keys replaced in named settings sections, e.g. `git={"setup_command": "x"}`."""
    updates = {
        name: getattr(cfg.settings, name).model_copy(update=values)
        for name, values in sections.items()
    }
    return replace(cfg, settings=cfg.settings.model_copy(update=updates))


BRANCH = "vk/bug-dedupe"
CLS = {
    "type": "bug",
    "priority": "high",
    "complexity": "small",
    "affected_area": "api",
    "summary": "Reset emails are sent twice.",
}
ANALYSIS = {
    "problem_statement": "Duplicate sends.",
    "approach": "Dedupe.",
    "plan": ["Guard"],
    "affected_surface": ["a.py"],
    "risks": [],
    "acceptance_criteria": ["Only one email"],
    "test_strategy": "pytest",
    "assumptions": [],
    "open_questions": [],
    "artifact_id": None,
}
IMPL = {
    "branch": BRANCH,
    "base": "main",
    "pushed": True,
    "change_summary": [{"path": "fix.txt", "change": "fix"}],
    "verification": [{"command": "true", "result": "ok"}],
    "deviations": [],
    "known_limitations": [],
}
REVIEW = {
    "verdict": "approve",
    "criteria_results": [{"criterion": "Only one email", "pass": True, "evidence": "diff"}],
    "blocking_findings": [],
    "suggestions": [],
    "summary": "Fine.",
}


def sh(*args: str, cwd: Path | None = None) -> str:
    out = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True)
    return out.stdout.strip()


class Call(NamedTuple):
    """What one agent run was given: recorded on its first model request."""

    agent: str
    instructions: str
    prompt: str
    tools: list[str]  # the agent's own tools, without the memory tools
    memory_tools: tuple[str, ...] = ()
    memory: str = ""  # the notebook block the memory capability injected beside the prompt


MEMORY_TOOLS = {"write_memory", "read_memory", "delete_memory", "search_memory"}


def clan_models(*, calls: list[Call] | None = None, **roles: list[Any]) -> Callable[[str], Model]:
    """Scripted agent models: one queue of turns per agent; `submit` calls the output tool.

    With `calls`, the first request of every run is recorded.
    """

    def factory(name: str) -> Model:
        turns = roles[name]

        def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            if calls is not None and len(messages) == 1:
                first = messages[0]
                assert isinstance(first, ModelRequest)
                prompt = next(p.content for p in first.parts if isinstance(p, UserPromptPart))
                names = [t.name for t in info.function_tools]
                injected = "\n".join(
                    item.content
                    for p in first.parts
                    if isinstance(p, UserPromptPart) and not isinstance(p.content, str)
                    for item in p.content
                    if isinstance(item, TextContent)
                )
                calls.append(
                    Call(
                        name,
                        first.instructions or "",
                        str(prompt),
                        [n for n in names if n not in MEMORY_TOOLS],
                        tuple(n for n in names if n in MEMORY_TOOLS),
                        injected,
                    )
                )
            parts = [
                ToolCallPart(info.output_tools[0].name if tool == "submit" else tool, args)
                for tool, args in turns.pop(0)
            ]
            return ModelResponse(parts=parts)

        return FunctionModel(fn)

    return factory


class Resp:
    def __init__(self, status: int, data: Any) -> None:
        self.status_code, self._data = status, data
        self.text, self.content = json.dumps(data), b"x"

    def json(self) -> Any:
        return self._data


class FakeSession(requests.Session):
    def __init__(self, routes: dict[tuple[str, str], Any]) -> None:
        super().__init__()
        self.routes = routes
        self.calls: list[tuple[str, str, Any]] = []

    def request(self, method: str, url: str, **kw: Any) -> Any:  # type: ignore[override]
        path = url.removeprefix("https://api.github.com")
        self.calls.append((method, path, kw.get("json")))
        if (method, path) in self.routes:
            return Resp(200, self.routes[(method, path)])
        return Resp(201, {"id": 1}) if method == "POST" else Resp(404, {"message": "Not Found"})

    def posts(self, suffix: str) -> list[Any]:
        return [body for m, p, body in self.calls if m == "POST" and p.endswith(suffix)]


def implementer_turns(*first: tuple[str, dict[str, Any]], prefix: str = "") -> list[Any]:
    commit = (
        prefix
        + "echo fixed >> fix.txt && git add -A && git commit -qm fix; git branch --show-current"
    )
    return [
        [*first, ("bash", {"command": commit})],
        [("push_branch", {"branch": BRANCH})],
        [("submit", IMPL)],
    ]


def seed_branch(remote: Path, tmp_path: Path) -> None:
    """Push `BRANCH` carrying a run log for issue 7, as the issue pipeline leaves it."""
    work = tmp_path / "work"
    sh("git", "clone", str(remote), str(work))
    sh("git", "checkout", "-qb", BRANCH, cwd=work)
    (work / "docs/factory").mkdir(parents=True)
    (work / "docs/factory/issue-7.md").write_text("# Factory run log: issue #7\n")
    sh("git", "add", ".", cwd=work)
    sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "log", cwd=work)
    sh("git", "push", "origin", BRANCH, cwd=work)


def branch_sha(remote: Path) -> str:
    return sh("git", "--git-dir", str(remote), "rev-parse", f"refs/heads/{BRANCH}")


class PrSession(FakeSession):
    """FakeSession whose PR 9 head sha follows `BRANCH` on the bare remote, so pushes move it."""

    def __init__(self, routes: dict[tuple[str, str], Any], remote: Path) -> None:
        super().__init__(routes)
        self.remote = remote

    def request(self, method: str, url: str, **kw: Any) -> Any:  # type: ignore[override]
        key = ("GET", "/repos/o/r/pulls/9")
        if key in self.routes:
            self.routes[key]["head"]["sha"] = branch_sha(self.remote)
        return super().request(method, url, **kw)
