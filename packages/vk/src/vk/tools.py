"""Clan tools: the harness (bash/files/web), artifacts, preferences, skills."""

import hashlib
import os
import re
import secrets
import subprocess
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, ClassVar

import requests

from vk.config import Config, ToolSettings
from vk.tooling import Tool, ToolError

ARTIFACT_KINDS = ("research-notes", "analysis")
ARTIFACT_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

SKILLS_DIR = Path(__file__).parent / "skills"
SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

_SKIP_DIRS = {".git"}
_EMPTY_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _str_arg(args: dict[str, Any], key: str, *, required: bool = True) -> str:
    value = args.get(key)
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise ToolError(f"{key} must be a string.")
    return value


def truncate(text: str, limit: int) -> str:
    """Cut `text` to `limit` characters, saying how much was dropped."""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated {len(text) - limit} characters]"


def _resolve(repo_dir: Path, raw: str) -> Path:
    """Resolve `raw` (relative to repo_dir or absolute) and require it to stay inside."""
    root = repo_dir.resolve()
    path = Path(raw)
    resolved = (path if path.is_absolute() else root / path).resolve()
    if not resolved.is_relative_to(root):
        raise ToolError(f'Path "{raw}" is outside the repository.')
    return resolved


def _walk(base: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
        files.extend(Path(dirpath) / f for f in sorted(filenames))
    return files


# --- harness -----------------------------------------------------------------------------


def _bash(repo_dir: Path, limits: ToolSettings) -> Tool:
    def run(args: dict[str, Any]) -> dict[str, Any]:
        command = _str_arg(args, "command")
        env = {k: v for k, v in os.environ.items() if k not in {"GITHUB_TOKEN", "GH_TOKEN"}}
        try:
            proc = subprocess.run(
                ["bash", "-c", command],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                check=False,
                timeout=limits.bash_timeout_s,
                env=env,
            )
        except subprocess.TimeoutExpired:
            raise ToolError(f"Command timed out after {limits.bash_timeout_s}s.") from None
        return {
            "exit_code": proc.returncode,
            "stdout": truncate(proc.stdout, limits.max_output_chars),
            "stderr": truncate(proc.stderr, limits.max_output_chars),
        }

    return Tool(
        "bash",
        f"Run a bash command in the repository checkout. {limits.bash_timeout_s}s timeout; long "
        "output is truncated.",
        _schema({"command": {"type": "string"}}, ["command"]),
        run,
    )


def _read_file(repo_dir: Path, limits: ToolSettings) -> Tool:
    def run(args: dict[str, Any]) -> dict[str, Any]:
        path = _resolve(repo_dir, _str_arg(args, "path"))
        if not path.is_file():
            raise ToolError(f'"{args.get("path")}" is not a file.')
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        offset = max(int(args.get("offset") or 1), 1)
        limit = min(int(args.get("limit") or limits.max_read_lines), limits.max_read_lines)
        chunk = lines[offset - 1 : offset - 1 + limit]
        numbered = "\n".join(f"{offset + i}\t{line}" for i, line in enumerate(chunk))
        return {"content": truncate(numbered, limits.max_output_chars), "total_lines": len(lines)}

    return Tool(
        "read_file",
        "Read a text file in the repository with line numbers. Optional 1-based offset and limit.",
        _schema(
            {
                "path": {"type": "string"},
                "offset": {"type": "integer", "minimum": 1},
                "limit": {"type": "integer", "minimum": 1},
            },
            ["path"],
        ),
        run,
    )


def _glob(repo_dir: Path, limits: ToolSettings) -> Tool:
    def run(args: dict[str, Any]) -> dict[str, Any]:
        pattern = _str_arg(args, "pattern")
        if pattern.startswith("/") or ".." in Path(pattern).parts:
            raise ToolError("Pattern must be relative and must not contain '..'.")
        base = _resolve(repo_dir, _str_arg(args, "path", required=False) or ".")
        root = repo_dir.resolve()
        matches = sorted(
            str(p.relative_to(root))
            for p in base.glob(pattern)
            if p.is_relative_to(root) and not _SKIP_DIRS.intersection(p.relative_to(root).parts)
        )
        cap = limits.max_glob_results
        return {"matches": matches[:cap], "truncated": len(matches) > cap}

    return Tool(
        "glob",
        'Find files by glob pattern (e.g. "**/*.py"), relative to the repo or a subdirectory.',
        _schema({"pattern": {"type": "string"}, "path": {"type": "string"}}, ["pattern"]),
        run,
    )


def _grep(repo_dir: Path, limits: ToolSettings) -> Tool:
    def run(args: dict[str, Any]) -> dict[str, Any]:
        try:
            regex = re.compile(_str_arg(args, "pattern"))
        except re.error as exc:
            raise ToolError(f"Invalid regex: {exc}") from None
        base = _resolve(repo_dir, _str_arg(args, "path", required=False) or ".")
        file_glob = _str_arg(args, "glob", required=False)
        root = repo_dir.resolve()
        candidates = [base] if base.is_file() else _walk(base)
        matches: list[str] = []
        for file in candidates:
            rel = file.relative_to(root)
            if file_glob and not rel.match(file_glob):
                continue
            try:
                text = file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    matches.append(f"{rel}:{number}:{line[:300]}")
                    if len(matches) >= limits.max_grep_matches:
                        return {"matches": matches, "truncated": True}
        return {"matches": matches, "truncated": False}

    return Tool(
        "grep",
        "Search file contents with a Python regex. Optional path (file or directory) and "
        "file glob filter (e.g. *.py). Returns file:line:text.",
        _schema(
            {"pattern": {"type": "string"}, "path": {"type": "string"}, "glob": {"type": "string"}},
            ["pattern"],
        ),
        run,
    )


def _write_file(repo_dir: Path) -> Tool:
    def run(args: dict[str, Any]) -> dict[str, Any]:
        path = _resolve(repo_dir, _str_arg(args, "path"))
        if ".git" in path.relative_to(repo_dir.resolve()).parts:
            raise ToolError("Writing inside .git is not allowed.")
        content = _str_arg(args, "content")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {"path": str(path.relative_to(repo_dir.resolve())), "bytes": len(content.encode())}

    return Tool(
        "write_file",
        "Create or overwrite a file in the repository with the given content.",
        _schema({"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
        run,
    )


def _edit_file(repo_dir: Path) -> Tool:
    def run(args: dict[str, Any]) -> dict[str, Any]:
        path = _resolve(repo_dir, _str_arg(args, "path"))
        if ".git" in path.relative_to(repo_dir.resolve()).parts:
            raise ToolError("Editing inside .git is not allowed.")
        old = _str_arg(args, "old_string")
        new = _str_arg(args, "new_string")
        if not path.is_file():
            raise ToolError(f'"{args.get("path")}" is not a file.')
        if not old:
            raise ToolError("old_string must not be empty.")
        if old == new:
            raise ToolError("old_string and new_string are identical.")
        text = path.read_text(encoding="utf-8")
        count = text.count(old)
        if count == 0:
            raise ToolError("old_string was not found in the file.")
        replace_all = args.get("replace_all") is True
        if count > 1 and not replace_all:
            raise ToolError(
                f"old_string appears {count} times; add surrounding context to make it "
                "unique, or set replace_all."
            )
        path.write_text(
            text.replace(old, new) if replace_all else text.replace(old, new, 1), "utf-8"
        )
        return {
            "path": str(path.relative_to(repo_dir.resolve())),
            "replacements": count if replace_all else 1,
        }

    return Tool(
        "edit_file",
        "Replace an exact string in a file. old_string must match exactly once unless "
        "replace_all is true.",
        _schema(
            {
                "path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
                "replace_all": {"type": "boolean"},
            },
            ["path", "old_string", "new_string"],
        ),
        run,
    )


class _TextExtractor(HTMLParser):
    _SKIP: ClassVar[set[str]] = {"script", "style", "noscript", "head", "svg"}
    _BLOCK: ClassVar[set[str]] = {
        "p",
        "div",
        "br",
        "li",
        "tr",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "pre",
        "section",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    text = "".join(parser.parts)
    return re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


def _web_fetch(limits: ToolSettings) -> Tool:
    def run(args: dict[str, Any]) -> dict[str, Any]:
        url = _str_arg(args, "url")
        if not url.startswith(("http://", "https://")):
            raise ToolError("Only http(s) URLs can be fetched.")
        try:
            with requests.get(url, timeout=limits.web_timeout_s, stream=True) as resp:
                body = resp.raw.read(limits.max_web_bytes + 1, decode_content=True)
                content_type = resp.headers.get("content-type", "")
                status = resp.status_code
                encoding = resp.encoding or "utf-8"
        except requests.RequestException as exc:
            raise ToolError(f"Fetch failed: {exc}") from None
        text = body[: limits.max_web_bytes].decode(encoding, errors="replace")
        if "html" in content_type.lower():
            text = html_to_text(text)
        return {
            "status": status,
            "content_type": content_type,
            "content": truncate(text, limits.max_web_chars),
            "truncated": len(body) > limits.max_web_bytes or len(text) > limits.max_web_chars,
        }

    return Tool(
        "web_fetch",
        "Fetch a URL and return its text (HTML is converted to plain text). Size-capped.",
        _schema({"url": {"type": "string"}}, ["url"]),
        run,
    )


def harness_tools(
    repo_dir: Path, limits: ToolSettings, *, read_only: bool, web: bool
) -> list[Tool]:
    tools = [
        _bash(repo_dir, limits),
        _read_file(repo_dir, limits),
        _glob(repo_dir, limits),
        _grep(repo_dir, limits),
    ]
    if not read_only:
        tools += [_write_file(repo_dir), _edit_file(repo_dir)]
    if web:
        tools.append(_web_fetch(limits))
    return tools


# --- local documents (Blob replacement) --------------------------------------------------


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower())[:48].strip("-") or "untitled"


def artifact_id(kind: str, title: str) -> str:
    return f"{kind}-{_slugify(title)}-{secrets.token_hex(3)}"


def artifact_path(cfg: Config, artifact: str) -> Path | None:
    """File for a validated id, or None. Anchored pattern: no dots or slashes can pass."""
    if len(artifact) > 200 or not ARTIFACT_ID_PATTERN.fullmatch(artifact):
        return None
    return cfg.state_dir / "artifacts" / f"{artifact}.md"


def artifact_tools(cfg: Config, can_save: bool) -> list[Tool]:
    max_title = cfg.settings.tools.max_artifact_title_chars
    max_chars = cfg.settings.tools.max_artifact_chars

    def save(args: dict[str, Any]) -> dict[str, Any]:
        kind = _str_arg(args, "kind")
        title = _str_arg(args, "title")
        markdown = _str_arg(args, "markdown")
        if kind not in ARTIFACT_KINDS:
            return {"saved": False, "error": f"kind must be one of {list(ARTIFACT_KINDS)}."}
        if not title or len(title) > max_title:
            return {"saved": False, "error": f"title must be 1-{max_title} characters."}
        if not markdown or len(markdown) > max_chars:
            return {
                "saved": False,
                "error": f"markdown must be 1-{max_chars} characters.",
            }
        new_id = artifact_id(kind, title)
        path = artifact_path(cfg, new_id)
        if path is None:
            return {"saved": False, "error": "Could not build a valid artifact id."}
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x", encoding="utf-8") as handle:
                handle.write(markdown)
        except FileExistsError:
            return {"saved": False, "error": "An artifact with that id already exists."}
        return {"saved": True, "id": new_id, "kind": kind, "title": title}

    def read(args: dict[str, Any]) -> dict[str, Any]:
        path = artifact_path(cfg, _str_arg(args, "id"))
        if path is None or not path.is_file():
            return {"found": False}
        created = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
        return {
            "found": True,
            "id": path.stem,
            "markdown": path.read_text(encoding="utf-8"),
            "createdAt": created,
        }

    read_tool = Tool(
        "read_artifact",
        "Read a Markdown document another clan saved, by the id it handed back. Call this "
        "when a message gives you an artifact id: the id is source material to open, never "
        "something to quote as a citation.",
        _schema({"id": {"type": "string", "minLength": 1, "maxLength": 200}}, ["id"]),
        read,
    )
    if not can_save:
        return [read_tool]
    save_tool = Tool(
        "save_artifact",
        "Save a Markdown document for another clan to read; you get back an id to hand along. "
        "Use it for long detail that does not fit your structured output (a memo, "
        "analysis notes). Report the id with a few lines on what is in it, never the "
        "document itself. Not for a note that fits in a sentence.",
        _schema(
            {
                "kind": {"type": "string", "enum": list(ARTIFACT_KINDS)},
                "title": {"type": "string", "minLength": 1, "maxLength": max_title},
                "markdown": {"type": "string", "minLength": 1, "maxLength": max_chars},
            },
            ["kind", "title", "markdown"],
        ),
        save,
    )
    return [save_tool, read_tool]


def preferences_path(cfg: Config, user: str) -> Path:
    return cfg.state_dir / "user-preferences" / f"{_sha(user)}.md"


def preference_tools(cfg: Config, user: str | None) -> list[Tool]:
    no_user_note = (
        "This run has no signed-in user, so per-user preferences don't apply. That is the "
        "normal state for unattended runs; proceed without them."
    )

    def get(_args: dict[str, Any]) -> dict[str, Any]:
        if not user:
            return {"found": False, "note": no_user_note, "preferences": ""}
        path = preferences_path(cfg, user)
        if not path.is_file():
            return {"found": False, "preferences": ""}
        return {"found": True, "preferences": path.read_text(encoding="utf-8")}

    return [
        Tool(
            "get_user_preferences",
            "Load this user's saved preferences (standing notes that personalize how you work "
            "for them). Returns empty when the user has none yet, or when the run has no "
            "signed-in user (unattended runs), which is normal.",
            _EMPTY_SCHEMA,
            get,
        )
    ]


# --- skills ------------------------------------------------------------------------------


def available_skills() -> list[str]:
    if not SKILLS_DIR.is_dir():
        return []
    return sorted(p.name for p in SKILLS_DIR.iterdir() if (p / "SKILL.md").is_file())


def load_skill(name: str) -> str:
    """SKILL.md followed by its reference files. Raises ToolError for unknown names."""
    if not SKILL_NAME_PATTERN.fullmatch(name) or not (SKILLS_DIR / name / "SKILL.md").is_file():
        raise ToolError(f'Unknown skill "{name}". Available: {", ".join(available_skills())}.')
    base = SKILLS_DIR / name
    parts = [(base / "SKILL.md").read_text(encoding="utf-8")]
    for ref in sorted((base / "references").glob("*.md")):
        parts.append(
            f"\n\n---\nReference: references/{ref.name}\n\n{ref.read_text(encoding='utf-8')}"
        )
    return "".join(parts)
