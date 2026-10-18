"""The five clans as data: prompt, output model, model and tool surface."""

import logging
import shutil
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.models import Model

from vk import agents, git
from vk.config import Config
from vk.models import Analysis, Classification, Implementation, Research, Review
from vk.tooling import Tool
from vk.tools import artifact_tools, harness_tools

log = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
# Agent instruction files a target repo may carry at its root, in injection order.
REPO_INSTRUCTION_FILES = ("AGENTS.md", "CLAUDE.md")
MAX_REPO_INSTRUCTIONS = 20_000  # characters per file

ToolBuilder = Callable[[Config, Path, str | None], list[Tool]]


def _classifier(_cfg: Config, _repo: Path, _remote: str | None) -> list[Tool]:
    return []


def _researcher(cfg: Config, repo: Path, _remote: str | None) -> list[Tool]:
    web = [t for t in harness_tools(repo, read_only=True, web=True) if t.name == "web_fetch"]
    return [*web, *artifact_tools(cfg, can_save=True)]


def _analyst(cfg: Config, repo: Path, _remote: str | None) -> list[Tool]:
    return [*harness_tools(repo, read_only=True, web=False), *artifact_tools(cfg, can_save=True)]


def _implementer(cfg: Config, repo: Path, remote: str | None) -> list[Tool]:
    return [
        *harness_tools(repo, read_only=False, web=False),
        *git.git_tools(cfg, repo, allow_push=True, remote_url=remote),
        *artifact_tools(cfg, can_save=False),
    ]


def _reviewer(cfg: Config, repo: Path, remote: str | None) -> list[Tool]:
    return [
        *harness_tools(repo, read_only=True, web=False),
        *git.git_tools(cfg, repo, allow_push=False, remote_url=remote),
        *artifact_tools(cfg, can_save=False),
    ]


@dataclass(frozen=True)
class Clan:
    name: str
    output: type[BaseModel]
    needs_repo: bool
    tools: ToolBuilder

    def prompt(self, cfg: Config, repo_dir: Path | None) -> str:
        text = (PROMPTS_DIR / f"{self.name}.md").read_text(encoding="utf-8")
        text = text.replace("{repo}", cfg.repo)
        text = text.replace("{repo_dir}", str(repo_dir) if repo_dir else "")
        return text + repo_instructions(repo_dir) if repo_dir else text


def repo_instructions(repo_dir: Path) -> str:
    """The target repo's own agent instructions, so clans follow its toolchain and rules."""
    sections = []
    for name in REPO_INSTRUCTION_FILES:
        path = repo_dir / name
        if not path.is_file():
            continue
        body = path.read_text(encoding="utf-8", errors="replace")
        if len(body) > MAX_REPO_INSTRUCTIONS:
            body = body[:MAX_REPO_INSTRUCTIONS] + "\n[truncated]"
        sections.append(f"### {name}\n\n{body.strip()}")
    if not sections:
        return ""
    header = (
        "\n\n## Repository instructions\n\n"
        "The target repository ships these instructions for agents working in it. Follow them:"
        " they decide the package manager, the check commands, and the hard rules, and they"
        " override your own habits.\n\n"
    )
    return header + "\n\n".join(sections) + "\n"


CLANS: dict[str, Clan] = {
    "classifier": Clan("classifier", Classification, False, _classifier),
    "researcher": Clan("researcher", Research, False, _researcher),
    "analyst": Clan("analyst", Analysis, True, _analyst),
    "implementer": Clan("implementer", Implementation, True, _implementer),
    "reviewer": Clan("reviewer", Review, True, _reviewer),
}


def run_clan(
    name: str,
    message: str,
    cfg: Config,
    *,
    model: Callable[[str], Model] | None = None,
    remote_url: str | None = None,
    capabilities: Sequence[AbstractCapability[None]] = (),
) -> BaseModel:
    """Run one clan to its typed output, in a fresh clone when it needs a repo.

    `model` (clan name -> PydanticAI model) and `remote_url` are test seams (fake model,
    git remote override). Without `model`, `build_model` picks the clan's configured model.
    `capabilities` (such as the run's memory) are attached to the agent.
    """
    clan = CLANS[name]
    log.info("clan %s starting model=%s", name, cfg.model_for(name))
    started = time.monotonic()
    repo_dir = git.clone_repo(cfg, remote_url=remote_url) if clan.needs_repo else None
    try:
        # Clans without a repo get a placeholder dir only for tools that ignore it.
        tools = clan.tools(cfg, repo_dir or Path.cwd(), remote_url)
        result = agents.run_typed(
            name,
            clan.output,
            instructions=clan.prompt(cfg, repo_dir),
            message=message,
            tools=tools,
            cfg=cfg,
            capabilities=capabilities,
            model=model(name) if model is not None else None,
        )
        log.info("clan %s finished in %.1fs", name, time.monotonic() - started)
        return result
    finally:
        if repo_dir is not None:
            shutil.rmtree(repo_dir.parent, ignore_errors=True)
