from pathlib import Path

import pytest

from vk.config import Config
from vk.tooling import Tool, ToolError
from vk.tools import (
    MAX_ARTIFACT_LENGTH,
    artifact_path,
    artifact_tools,
    harness_tools,
    html_to_text,
    load_skill,
    preference_tools,
    preferences_path,
)


def by_name(tools: list[Tool]) -> dict[str, Tool]:
    return {t.name: t for t in tools}


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    return Config(
        repo="owner/name",
        github_token="t",
        model="m",
        clan_models={},
        state_dir=tmp_path / "state",
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    (r / "src").mkdir(parents=True)
    (r / "src" / "a.py").write_text("one\ntwo\ntwo\n")
    (r / "b.txt").write_text("hello world\n")
    return r


def test_tool_surfaces(repo: Path) -> None:
    ro = {t.name for t in harness_tools(repo, read_only=True, web=False)}
    assert ro == {"bash", "read_file", "glob", "grep"}
    rw = {t.name for t in harness_tools(repo, read_only=False, web=True)}
    assert rw == ro | {"write_file", "edit_file", "web_fetch"}


def test_bash_runs_in_repo_and_hides_token(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "secret")
    bash = by_name(harness_tools(repo, read_only=True, web=False))["bash"]
    out = bash.fn({"command": 'pwd; echo -n "[$GITHUB_TOKEN]"; exit 3'})
    assert out["exit_code"] == 3
    assert str(repo.resolve()) in out["stdout"] and "[]" in out["stdout"]


def test_read_glob_grep(repo: Path) -> None:
    t = by_name(harness_tools(repo, read_only=True, web=False))
    assert "2\ttwo" in t["read_file"].fn({"path": "src/a.py", "offset": 2})["content"]
    assert t["glob"].fn({"pattern": "**/*.py"})["matches"] == ["src/a.py"]
    hits = t["grep"].fn({"pattern": "tw", "glob": "*.py"})["matches"]
    assert hits == ["src/a.py:2:two", "src/a.py:3:two"]


@pytest.mark.parametrize("bad", ["../x", "/etc/passwd", "src/../../x"])
def test_path_traversal_rejected(repo: Path, bad: str) -> None:
    t = by_name(harness_tools(repo, read_only=False, web=False))
    with pytest.raises(ToolError):
        t["read_file"].fn({"path": bad})
    with pytest.raises(ToolError):
        t["write_file"].fn({"path": bad, "content": "x"})
    with pytest.raises(ToolError):
        t["grep"].fn({"pattern": "x", "path": bad})


def test_symlink_escape_rejected(repo: Path, tmp_path: Path) -> None:
    (tmp_path / "outside.txt").write_text("secret")
    (repo / "link").symlink_to(tmp_path / "outside.txt")
    t = by_name(harness_tools(repo, read_only=True, web=False))
    with pytest.raises(ToolError):
        t["read_file"].fn({"path": "link"})
    with pytest.raises(ToolError):
        t["glob"].fn({"pattern": "../*"})


def test_edit_file_uniqueness(repo: Path) -> None:
    edit = by_name(harness_tools(repo, read_only=False, web=False))["edit_file"]
    path = "src/a.py"
    with pytest.raises(ToolError, match="2 times"):
        edit.fn({"path": path, "old_string": "two", "new_string": "2"})
    with pytest.raises(ToolError, match="not found"):
        edit.fn({"path": path, "old_string": "zzz", "new_string": "2"})
    edit.fn({"path": path, "old_string": "one", "new_string": "1"})
    assert (
        edit.fn({"path": path, "old_string": "two", "new_string": "2", "replace_all": True})[
            "replacements"
        ]
        == 2
    )
    assert (repo / path).read_text() == "1\n2\n2\n"


def test_write_file_creates_dirs_and_blocks_git(repo: Path) -> None:
    write = by_name(harness_tools(repo, read_only=False, web=False))["write_file"]
    write.fn({"path": "new/dir/f.txt", "content": "x"})
    assert (repo / "new/dir/f.txt").read_text() == "x"
    with pytest.raises(ToolError):
        write.fn({"path": ".git/hooks/pre-commit", "content": "x"})


def test_html_to_text() -> None:
    html = (
        "<html><head><title>t</title></head>"
        "<body><script>bad()</script><p>Hi <b>there</b></p></body></html>"
    )
    assert html_to_text(html) == "Hi there"


def test_artifacts_roundtrip_and_no_overwrite(cfg: Config) -> None:
    t = by_name(artifact_tools(cfg, can_save=True))
    saved = t["save_artifact"].fn(
        {"kind": "analysis", "title": "Dedupe reset emails", "markdown": "# x"}
    )
    assert saved["saved"] is True
    assert saved["id"].startswith("analysis-dedupe-reset-emails-")
    got = t["read_artifact"].fn({"id": saved["id"]})
    assert got["found"] is True and got["markdown"] == "# x"
    assert [x.name for x in artifact_tools(cfg, can_save=False)] == ["read_artifact"]


def test_artifact_validation(cfg: Config) -> None:
    save = by_name(artifact_tools(cfg, can_save=True))["save_artifact"]
    assert save.fn({"kind": "bogus", "title": "t", "markdown": "x"})["saved"] is False
    big = "x" * (MAX_ARTIFACT_LENGTH + 1)
    assert save.fn({"kind": "analysis", "title": "t", "markdown": big})["saved"] is False


@pytest.mark.parametrize(
    "bad", ["../factory-brain/abc", "a/b", "a.md", "A-b", "a--b", "-a", "", "x" * 201, "..", "a\n"]
)
def test_artifact_id_containment(cfg: Config, bad: str) -> None:
    assert artifact_path(cfg, bad) is None
    (cfg.state_dir / "factory-brain").mkdir(parents=True)
    read = by_name(artifact_tools(cfg, can_save=False))["read_artifact"]
    assert read.fn({"id": bad}) == {"found": False}


def test_preferences(cfg: Config) -> None:
    anon = by_name(preference_tools(cfg, None))
    got = anon["get_user_preferences"].fn({})
    assert got["found"] is False and "no signed-in user" in got["note"]

    me = by_name(preference_tools(cfg, "alice"))
    assert me["get_user_preferences"].fn({})["found"] is False
    path = preferences_path(cfg, "alice")
    path.parent.mkdir(parents=True)
    path.write_text("terse", encoding="utf-8")
    assert me["get_user_preferences"].fn({}) == {"found": True, "preferences": "terse"}
    other = by_name(preference_tools(cfg, "bob"))
    assert other["get_user_preferences"].fn({})["found"] is False


def test_skills() -> None:
    text = load_skill("writing-quality")
    assert "Reference: references/" in text
    with pytest.raises(ToolError):
        load_skill("../writing-quality")
    with pytest.raises(ToolError):
        load_skill("nope")
