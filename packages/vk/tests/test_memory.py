"""Factory memory: one wiki, a page per issue; only the run's own page is committed."""

from pathlib import Path

from pydantic_ai import ModelMessage, ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel

from vk.config import Config
from vk.memory import MEMORY_DIR, RESTORED, Notebook, open_notebook, page_name

from .helpers import (
    BRANCH,
    CLS,
    REVIEW,
    Call,
    PrSession,
    clan_models,
    implementer_turns,
    seed_branch,
    sh,
)
from .test_issue_pipeline import happy_models, start
from .test_pr_review import (
    comment as review_comment,
)
from .test_pr_review import (
    decider,
    decision,
    go,
    revisions,
    routes,
)

PAGE = "issue-7-reset-emails-sent-twice.md"
PR_PAGE = "issue-7-send-reset-emails-once.md"
NOTE = "- reset sends dedupe on the token"
LEARNING = "- run the full check before pushing, the lint step is slow"


def tree(remote: Path, ref: str = BRANCH) -> list[str]:
    git = ["git", "--git-dir", str(remote)]
    return sh(*git, "ls-tree", "-r", "--name-only", ref).split("\n")


def show(remote: Path, path: str, ref: str = BRANCH) -> str:
    return sh("git", "--git-dir", str(remote), "show", f"{ref}:{path}")


def seed_main(remote: Path, tmp_path: Path, files: dict[str, str]) -> None:
    work = tmp_path / "seed-main"
    sh("git", "clone", str(remote), str(work))
    for path, text in files.items():
        (work / path).parent.mkdir(parents=True, exist_ok=True)
        (work / path).write_text(text)
    sh("git", "add", ".", cwd=work)
    sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "notes", cwd=work)
    sh("git", "push", "origin", "HEAD:main", cwd=work)


def writing_implementer() -> list[object]:
    return implementer_turns(
        ("write_memory", {"content": NOTE, "file": PAGE}),
        ("write_memory", {"content": LEARNING, "file": PAGE}),
        prefix=f"git checkout -qb {BRANCH} && ",
    )


def test_issue_run_commits_only_its_own_page_in_the_run_log_commit(
    cfg: Config, remote: Path
) -> None:
    calls: list[Call] = []

    start(cfg, remote, happy_models(calls, implementer=writing_implementer()))

    page = show(remote, f"{MEMORY_DIR}/{PAGE}")
    assert NOTE in page and page.strip().endswith(LEARNING)
    head = sh("git", "--git-dir", str(remote), "show", "--name-only", "--format=", BRANCH)
    assert set(head.split()) == {"docs/factory/issue-7.md", f"{MEMORY_DIR}/{PAGE}"}
    assert not [p for p in tree(remote) if "memory-operations" in p or ".memory-tmp" in p]
    # Every agent, not only the implementer, carries the memory tools and the page name.
    assert {c.agent for c in calls} >= {"triage", "classifier", "analyst", "reviewer", "pr_writer"}
    for call in calls:
        assert "write_memory" in call.memory_tools, call.agent
        assert "search_memory" in call.memory_tools, call.agent
        assert f"`{PAGE}`" in call.instructions and "{" not in call.instructions, call.agent


def test_notes_written_by_the_pr_writer_are_committed_after_the_pr_text(
    cfg: Config, remote: Path
) -> None:
    calls: list[Call] = []
    models = happy_models(
        calls,
        pr_writer=[
            [("write_memory", {"content": "- the PR body stays short", "file": PAGE})],
            [("submit", {"title": "Send reset emails once", "body": "Dedupes."})],
        ],
    )

    _, session = start(cfg, remote, models)

    assert show(remote, f"{MEMORY_DIR}/{PAGE}").strip().endswith("- the PR body stays short")
    assert session.posts("/pulls")


def test_review_round_two_finds_the_page_round_one_wrote(
    cfg: Config, remote: Path, tmp_path: Path
) -> None:
    seed_branch(remote, tmp_path)
    first = clan_models(
        decider=[
            [("write_memory", {"content": "- alice wants guards on every send", "file": PR_PAGE})],
            *decider(decision(101, "wontfix", "Out of scope.")),
        ]
    )
    go(cfg, remote, first, PrSession(routes(comments=[review_comment(101)]), remote))
    assert "alice wants guards" in show(remote, f"{MEMORY_DIR}/{PR_PAGE}")

    calls: list[Call] = []
    second = clan_models(calls=calls, decider=decider(decision(201, "wontfix", "Noted.")))
    go(cfg, remote, second, PrSession(routes(comments=[review_comment(201)]), remote))

    assert PR_PAGE in calls[0].memory and f"`{PR_PAGE}`" in calls[0].instructions
    assert "## Review round 2" in show(remote, "docs/factory/issue-7.md")


def test_a_fix_run_still_reaches_memory_through_every_clan(
    cfg: Config, remote: Path, tmp_path: Path
) -> None:
    seed_branch(remote, tmp_path)
    calls: list[Call] = []
    models = clan_models(
        calls=calls,
        decider=decider(decision(101, "fix", "Right.", "Guard it.")),
        implementer=revisions(0),
        reviewer=[[("submit", REVIEW)]],
    )

    go(cfg, remote, models, PrSession(routes(comments=[review_comment(101)]), remote))

    assert [c.agent for c in calls] == ["decider", "implementer", "reviewer"]
    assert all("write_memory" in c.memory_tools for c in calls)


def searching(query: str, seen: list[str]) -> Model:
    """A classifier that searches memory once, records what came back, then answers."""

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        returned = [
            str(p.content)
            for m in messages
            if isinstance(m, ModelRequest)
            for p in m.parts
            if isinstance(p, ToolReturnPart)
        ]
        if not returned:
            return ModelResponse(parts=[ToolCallPart("search_memory", {"query": query})])
        seen.extend(returned)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, CLS)])

    return FunctionModel(fn)


def test_search_memory_finds_another_issues_page(cfg: Config, remote: Path, tmp_path: Path) -> None:
    seed_main(
        remote,
        tmp_path,
        {
            f"{MEMORY_DIR}/MEMORY.md": "Factory note: search before you start.\n",
            f"{MEMORY_DIR}/issue-5-lint-setup.md": "- always run make check\n",
        },
    )
    calls: list[Call] = []
    seen: list[str] = []
    base = happy_models(calls)

    def models(name: str) -> Model:
        return searching("make check", seen) if name == "classifier" else base(name)

    start(cfg, remote, models)

    assert "issue-5-lint-setup.md" in "".join(seen)
    for call in calls:  # the factory note and the listing cover every issue
        assert "Factory note: search before you start." in call.memory, call.agent
        assert "issue-5-lint-setup.md" in call.memory, call.agent


def test_only_the_runs_own_page_is_committed(cfg: Config, remote: Path, tmp_path: Path) -> None:
    seed_main(
        remote,
        tmp_path,
        {
            f"{MEMORY_DIR}/MEMORY.md": "Factory note.\n",
            f"{MEMORY_DIR}/issue-5-lint-setup.md": "- always run make check\n",
        },
    )
    implementer = implementer_turns(
        ("write_memory", {"content": "- scribble on the factory note"}),  # defaults to MEMORY.md
        ("write_memory", {"content": "- scribble on issue five", "file": "issue-5-lint-setup.md"}),
        ("write_memory", {"content": "- sneaky", "file": "../MEMORY.md"}),  # refused by the tool
        ("write_memory", {"content": NOTE, "file": PAGE}),
        prefix=f"git checkout -qb {BRANCH} && ",
    )

    start(cfg, remote, happy_models([], implementer=implementer))

    changed = sh("git", "--git-dir", str(remote), "diff", "--name-only", "main", BRANCH)
    assert set(changed.split()) == {"fix.txt", "docs/factory/issue-7.md", f"{MEMORY_DIR}/{PAGE}"}
    assert show(remote, f"{MEMORY_DIR}/MEMORY.md") == "Factory note."
    assert show(remote, f"{MEMORY_DIR}/issue-5-lint-setup.md") == "- always run make check"


def test_an_existing_page_is_reused_and_shown_to_the_agents(
    cfg: Config, remote: Path, tmp_path: Path
) -> None:
    seed_main(remote, tmp_path, {f"{MEMORY_DIR}/issue-7-older-title.md": "- earlier round\n"})
    calls: list[Call] = []
    implementer = implementer_turns(
        ("write_memory", {"content": NOTE, "file": "issue-7-older-title.md"}),
        prefix=f"git checkout -qb {BRANCH} && ",
    )

    start(cfg, remote, happy_models(calls, implementer=implementer))

    assert all("`issue-7-older-title.md`" in c.instructions for c in calls)
    assert all("issue-7-older-title.md" in c.memory for c in calls)
    assert not [p for p in tree(remote) if p.endswith(PAGE)]
    page = show(remote, f"{MEMORY_DIR}/issue-7-older-title.md")
    assert "- earlier round" in page and NOTE in page


def test_page_names_are_short_ascii_slugs() -> None:
    assert page_name(7, "Reset emails sent twice!") == "issue-7-reset-emails-sent-twice.md"
    assert page_name(7, "Ünïcode, émojis 🎉 & more") == "issue-7-n-code-mojis-more.md"
    assert page_name(7, "") == "issue-7-notes.md"
    long = page_name(7, "word " * 40)
    assert len(long) <= 80 and long.endswith("word.md") and "--" not in long


def test_open_notebook_reads_flat_pages_and_picks_the_issues_own(
    cfg: Config, remote: Path, tmp_path: Path
) -> None:
    seed_main(
        remote,
        tmp_path,
        {
            f"{MEMORY_DIR}/MEMORY.md": "factory note\n",
            f"{MEMORY_DIR}/issue-1-short.md": "one\n",
            f"{MEMORY_DIR}/issue-17-long.md": "seventeen\n",
            f"{MEMORY_DIR}/raw.json": "{}",
            f"{MEMORY_DIR}/old/issue-1-nested.md": "nested\n",
        },
    )

    nb = open_notebook(cfg, 17, "Ignored title", "HEAD", remote_url=f"file://{remote}")
    try:
        assert nb.page == "issue-17-long.md"
        assert sorted(p.name for p in (nb.root / "factory").iterdir()) == [
            "MEMORY.md",
            "issue-1-short.md",
            "issue-17-long.md",
        ]
        assert nb.changes() == {}
    finally:
        nb.close()
    assert not nb.root.exists()
    fresh = open_notebook(cfg, 3, "A new one", "HEAD", remote_url=f"file://{remote}")
    try:
        assert fresh.page == "issue-3-a-new-one.md" and fresh.changes() == {}
    finally:
        fresh.close()


def started(tmp_path: Path, before: str, after: str | None) -> Notebook:
    """A notebook whose page started as `before` and now holds `after` (None = deleted)."""
    nb = Notebook("issue-7-x.md", tmp_path, start=before, saved=before)
    (tmp_path / "factory").mkdir()
    if after is not None:
        (tmp_path / "factory" / "issue-7-x.md").write_text(after)
    return nb


PATH = f"{MEMORY_DIR}/issue-7-x.md"


def test_a_new_page_is_committed_and_then_settled(tmp_path: Path) -> None:
    nb = started(tmp_path, "", "- first\n")

    assert nb.changes() == {PATH: "- first\n"}
    nb.mark_saved()
    assert nb.changes() == {}


def test_a_page_the_run_never_wrote_is_not_committed(tmp_path: Path) -> None:
    assert started(tmp_path, "", None).changes() == {}


def test_a_rewrite_that_drops_lines_gets_them_restored(tmp_path: Path) -> None:
    before = "## Round 0\n- first note\n\n- second note\n"
    nb = started(tmp_path, before, "## Round 1\n- fresh note\n")

    got = nb.changes()[PATH]

    assert got == (
        f"## Round 1\n- fresh note\n\n{RESTORED}\n\n## Round 0\n- first note\n- second note\n"
    )
    nb.mark_saved()
    assert nb.changes() == {}  # the restored text is what counts as committed


def test_deleting_the_page_restores_all_of_it(tmp_path: Path) -> None:
    nb = started(tmp_path, "- a\n- b\n", None)

    assert nb.changes() == {PATH: f"{RESTORED}\n\n- a\n- b\n"}


def test_a_pure_append_is_committed_unchanged(tmp_path: Path) -> None:
    nb = started(tmp_path, "- a\n", "- a\n- b\n")

    assert nb.changes() == {PATH: "- a\n- b\n"}


def test_correcting_one_line_also_restores_the_old_line(tmp_path: Path) -> None:
    # Accepted trade-off: the guard cannot tell a correction from a drop, so the wrong line
    # comes back under the heading and a reviewer prunes it.
    nb = started(tmp_path, "- keep\n- wrong\n", "- keep\n- right\n")

    assert nb.changes() == {PATH: f"- keep\n- right\n\n{RESTORED}\n\n- wrong\n"}


def test_capabilities_carry_the_guidance_with_the_exact_page() -> None:
    (memory,) = Notebook("issue-7-x.md", Path(".")).capabilities()

    text = str(memory.get_instructions())
    assert "`issue-7-x.md`" in text and "{" not in text
    assert "without `old_text`" in text and "Never remove or rewrite earlier" in text
    assert "## Repo notes" in text
