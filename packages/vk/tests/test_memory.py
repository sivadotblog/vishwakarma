"""Per-issue memory: notebooks committed with the run log, a read-only brain, no cross-talk."""

from pathlib import Path

from vk.config import Config
from vk.memory import BRAIN_BUDGET, MAX_FILES, TRUNCATED, Notebook, _brain, folder, open_notebook

from .helpers import (
    BRANCH,
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
        ("write_memory", {"content": NOTE}),
        ("write_memory", {"content": LEARNING, "file": "repo-notes.md"}),
        prefix=f"git checkout -qb {BRANCH} && ",
    )


def test_issue_run_commits_its_notebook_in_the_run_log_commit(cfg: Config, remote: Path) -> None:
    calls: list[Call] = []

    start(cfg, remote, happy_models(calls, implementer=writing_implementer()))

    assert show(remote, f"{folder(7)}/MEMORY.md").strip().endswith(NOTE)
    assert show(remote, f"{folder(7)}/repo-notes.md").strip().endswith(LEARNING)
    head = sh("git", "--git-dir", str(remote), "show", "--name-only", "--format=", BRANCH)
    assert set(head.split()) == {
        "docs/factory/issue-7.md",
        f"{folder(7)}/MEMORY.md",
        f"{folder(7)}/repo-notes.md",
    }
    assert not [p for p in tree(remote) if "memory-operations" in p or ".memory-tmp" in p]
    # Every agent, not only the implementer, carries the memory tools and the guidance.
    assert {c.agent for c in calls} >= {"triage", "classifier", "analyst", "reviewer", "pr_writer"}
    for call in calls:
        assert "write_memory" in call.memory_tools, call.agent
        assert "`repo-notes.md`" in call.instructions, call.agent


def test_notes_written_by_the_pr_writer_are_committed_after_the_pr_text(
    cfg: Config, remote: Path
) -> None:
    calls: list[Call] = []
    models = happy_models(
        calls,
        pr_writer=[
            [("write_memory", {"content": "- the PR body stays short"})],
            [("submit", {"title": "Send reset emails once", "body": "Dedupes."})],
        ],
    )

    _, session = start(cfg, remote, models)

    assert show(remote, f"{folder(7)}/MEMORY.md").strip().endswith("- the PR body stays short")
    assert session.posts("/pulls")


def test_review_round_two_sees_the_note_from_round_one(
    cfg: Config, remote: Path, tmp_path: Path
) -> None:
    seed_branch(remote, tmp_path)
    first = clan_models(
        decider=[
            [("write_memory", {"content": "- alice wants guards on every send"})],
            *decider(decision(101, "wontfix", "Out of scope.")),
        ]
    )
    go(cfg, remote, first, PrSession(routes(comments=[review_comment(101)]), remote))
    assert "alice wants guards" in show(remote, f"{folder(7)}/MEMORY.md")

    calls: list[Call] = []
    second = clan_models(calls=calls, decider=decider(decision(201, "wontfix", "Noted.")))
    go(cfg, remote, second, PrSession(routes(comments=[review_comment(201)]), remote))

    assert "alice wants guards on every send" in calls[0].memory
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


def test_another_issues_repo_notes_are_a_read_only_brain(
    cfg: Config, remote: Path, tmp_path: Path
) -> None:
    seed_main(
        remote,
        tmp_path,
        {
            f"{folder(5)}/repo-notes.md": "- always run make check\n",
            f"{folder(5)}/MEMORY.md": "- private scratch of issue five\n",
        },
    )
    calls: list[Call] = []
    # The run tries to write into issue 5's folder; the memory tool refuses the name.
    sneaky = {"content": "- overwritten", "file": "../issue-5/repo-notes.md"}
    implementer = [[("write_memory", sneaky)], *writing_implementer()]

    start(cfg, remote, happy_models(calls, implementer=implementer))

    for call in calls:
        assert "Factory brain" in call.instructions, call.agent
        assert "- always run make check" in call.instructions, call.agent
        assert "private scratch" not in call.instructions + call.memory, call.agent
        assert "always run make check" not in call.memory, call.agent  # not a writable notebook
    assert show(remote, f"{folder(5)}/repo-notes.md", "main").strip() == "- always run make check"
    assert show(remote, f"{folder(5)}/repo-notes.md").strip() == "- always run make check"
    changed = sh("git", "--git-dir", str(remote), "diff", "--name-only", "main", BRANCH)
    assert set(changed.split()) == {
        "fix.txt",
        "docs/factory/issue-7.md",
        f"{folder(7)}/MEMORY.md",
        f"{folder(7)}/repo-notes.md",
    }


def test_a_notebook_starts_from_the_refs_files_and_shows_them_to_the_agent(
    cfg: Config, remote: Path, tmp_path: Path
) -> None:
    seed_main(remote, tmp_path, {f"{folder(7)}/MEMORY.md": "- from an earlier round\n"})
    calls: list[Call] = []

    start(cfg, remote, happy_models(calls))

    assert all("from an earlier round" in c.memory for c in calls)


def test_the_brain_is_newest_first_and_cut_at_the_budget() -> None:
    brain = _brain({1: "A" * 5000, 2: "B" * 5000, 3: "C" * 5000})

    assert brain.index("issue #3") < brain.index("issue #2") and "issue #1" not in brain
    assert brain.endswith(TRUNCATED)
    assert brain.count("C") == 5000 and 0 < brain.count("B") < 5000
    assert len(brain) < BRAIN_BUDGET + 400  # the header sits outside the budget
    assert _brain({}) == ""


def test_open_notebook_reads_own_files_and_other_issues_notes_only(
    cfg: Config, remote: Path, tmp_path: Path
) -> None:
    seed_main(
        remote,
        tmp_path,
        {
            f"{folder(7)}/MEMORY.md": "mine\n",
            f"{folder(7)}/extra.md": "also mine\n",
            f"{folder(7)}/raw.json": "{}",
            f"{folder(5)}/repo-notes.md": "five's learning\n",
            f"{folder(5)}/MEMORY.md": "five's notebook\n",
            f"{folder(6)}/repo-notes.md": "six's learning\n",
        },
    )

    nb = open_notebook(cfg, 7, "HEAD", remote_url=f"file://{remote}")
    try:
        assert sorted(p.name for p in (nb.root / "issue-7").iterdir()) == ["MEMORY.md", "extra.md"]
        assert not (nb.root / "issue-5").exists()
        assert nb.brain.index("issue #6") < nb.brain.index("issue #5")
        assert "five's notebook" not in nb.brain and "mine" not in nb.brain
        assert nb.changes() == {}
    finally:
        nb.close()
    assert not nb.root.exists()


def test_changes_cover_only_visible_markdown_in_the_issue_folder(tmp_path: Path) -> None:
    nb = Notebook(7, tmp_path, "", {f"{folder(7)}/old.md": "old", f"{folder(7)}/keep.md": "keep"})
    home = tmp_path / "issue-7"
    home.mkdir()
    (home / "keep.md").write_text("keep")
    (home / "MEMORY.md").write_text("new")
    (home / ".memory-operations.json").write_text("{}")
    (home / ".memory-tmp-1").write_text("x")
    (home / "data.json").write_text("{}")
    (home / "link.md").symlink_to(tmp_path / "elsewhere")
    (tmp_path / "issue-8").mkdir()
    (tmp_path / "issue-8" / "MEMORY.md").write_text("not mine")
    (tmp_path / ".memory-operations.json").write_text("{}")

    assert nb.changes() == {f"{folder(7)}/MEMORY.md": "new", f"{folder(7)}/old.md": None}
    nb.mark_saved()
    assert nb.changes() == {}


def test_a_runaway_notebook_is_capped(tmp_path: Path) -> None:
    nb = Notebook(7, tmp_path, "")
    home = tmp_path / "issue-7"
    home.mkdir()
    for n in range(MAX_FILES + 10):
        (home / f"n{n:03}.md").write_text("x")

    assert len(nb.changes()) == MAX_FILES
