"""GitHub client and tool wrappers against a fake requests.Session."""

import base64
from pathlib import Path
from typing import Any

import pytest
import requests

from vk.approval import Caller
from vk.config import Config
from vk.github import GitHub, github_tools, with_bot_identity
from vk.tooling import Tool, ToolError

CFG = Config(repo="o/r", github_token="tok", model="m", clan_models={}, state_dir=Path("/tmp/x"))
ATTENDED = Caller(unattended=False)
UNATTENDED = Caller(unattended=True, issue_number=42, pr_number=57)


class FakeResponse:
    def __init__(self, status: int, data: Any = None, text: str = "") -> None:
        self.status_code = status
        self._data = data
        self.text = text or ("" if data is None else str(data))
        self.content = b"x" if data is not None or text else b""

    def json(self) -> Any:
        return self._data


class FakeSession(requests.Session):
    def __init__(self, routes: dict[tuple[str, str], FakeResponse]) -> None:
        super().__init__()
        self.routes = routes
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kw: Any) -> Any:  # type: ignore[override]
        path = url.removeprefix("https://api.github.com")
        self.calls.append({"method": method, "path": path, **kw})
        return self.routes.get((method, path), FakeResponse(404, {"message": "Not Found"}))


def tools(session: FakeSession, caller: Caller = ATTENDED, confirm: Any = None) -> dict[str, Tool]:
    return {t.name: t for t in github_tools(GitHub(CFG, session), caller, confirm)}


def test_auth_headers_and_error_message() -> None:
    session = FakeSession({})
    gh = GitHub(CFG, session)
    with pytest.raises(ToolError, match="Not Found"):
        gh.request("GET", "/repos/o/r")
    headers = session.calls[0]["headers"]
    assert headers["Authorization"] == "Bearer tok"
    assert headers["X-GitHub-Api-Version"]


def test_get_file_content_decodes() -> None:
    body = {
        "path": "a.txt",
        "sha": "s",
        "encoding": "base64",
        "content": base64.b64encode(b"hi").decode(),
    }
    t = tools(FakeSession({("GET", "/repos/o/r/contents/a.txt"): FakeResponse(200, body)}))
    assert t["github__getFileContent"].fn({"path": "a.txt"})["content"] == "hi"


def test_add_comment_posts_body() -> None:
    session = FakeSession({("POST", "/repos/o/r/issues/5/comments"): FakeResponse(201, {"id": 1})})
    tools(session)["github__addIssueComment"].fn({"issue_number": 5, "body": "hello"})
    assert session.calls[0]["json"] == {"body": "hello"}


def _review_comment(cid: int, login: str, reply_to: int | None = None) -> dict[str, Any]:
    return {
        "id": cid,
        "path": "f.py",
        "line": 3,
        "body": f"c{cid}",
        "user": {"login": login},
        "in_reply_to_id": reply_to,
    }


def test_review_comments_answered() -> None:
    comments = [
        _review_comment(1, "alice"),  # answered by bot reply 2
        _review_comment(2, "bot", 1),
        _review_comment(3, "alice"),  # unanswered
        _review_comment(4, "alice"),  # thread root, bot reply 5 exists but earlier thread reply...
        _review_comment(5, "bot", 4),
        _review_comment(6, "alice", 4),  # later follow-up in answered thread, after bot's reply
    ]
    session = FakeSession(
        {
            ("GET", "/user"): FakeResponse(200, {"login": "bot"}),
            ("GET", "/repos/o/r/pulls/7/comments"): FakeResponse(200, comments),
        }
    )
    out = tools(session)["github__listReviewComments"].fn({"pull_number": 7})
    answered = {c["id"]: c["answered"] for c in out}
    assert answered == {1: True, 2: True, 3: False, 4: True, 5: True, 6: False}
    assert out[0]["user"] == "alice" and out[0]["line"] == 3
    assert out[0]["user_type"] is None  # the fake comments carry no account type


def _bot_tools(comments: list[dict[str, Any]]) -> dict[str, Tool]:
    cfg = Config(**{**CFG.__dict__, "bot_login": "vk-app[bot]"})
    session = FakeSession({("GET", "/repos/o/r/pulls/7/comments"): FakeResponse(200, comments)})
    return {t.name: t for t in github_tools(GitHub(cfg, session), ATTENDED, None)}


def test_me_uses_bot_login_without_http() -> None:
    session = FakeSession({})
    gh = GitHub(Config(**{**CFG.__dict__, "bot_login": "vk-app[bot]"}), session)
    assert gh.me() == "vk-app[bot]"
    assert session.calls == []


def test_owner_comment_unanswered_when_bot_login_differs() -> None:
    out = _bot_tools([_review_comment(1, "owner")])["github__listReviewComments"].fn(
        {"pull_number": 7}
    )
    assert out[0]["answered"] is False


def test_owner_comment_answered_by_later_bot_reply() -> None:
    comments = [_review_comment(1, "owner"), _review_comment(2, "vk-app[bot]", 1)]
    out = _bot_tools(comments)["github__listReviewComments"].fn({"pull_number": 7})
    assert {c["id"]: c["answered"] for c in out} == {1: True, 2: True}


def test_reply_to_review_comment() -> None:
    route = ("POST", "/repos/o/r/pulls/7/comments/9/replies")
    session = FakeSession({route: FakeResponse(201, {"id": 10})})
    tools(session)["github__replyToReviewComment"].fn(
        {"pull_number": 7, "comment_id": 9, "body": "done"}
    )
    assert session.calls[0]["json"] == {"body": "done"}


def test_ensure_label_creates_only_when_missing() -> None:
    session = FakeSession({("POST", "/repos/o/r/labels"): FakeResponse(201, {"name": "vk:x"})})
    out = tools(session)["github__ensureLabel"].fn({"name": "vk:x", "color": "ededed"})
    assert out["created"] is True
    exists = FakeSession({("GET", "/repos/o/r/labels/vk%3Ax"): FakeResponse(200, {"name": "vk:x"})})
    assert tools(exists)["github__ensureLabel"].fn({"name": "vk:x"})["created"] is False
    assert [c["method"] for c in exists.calls] == ["GET"]


def test_wrapped_tool_denied_raises_without_calling_api() -> None:
    session = FakeSession({})
    with pytest.raises(ToolError, match="denied"):
        tools(session, UNATTENDED)["github__createIssue"].fn({"title": "t"})
    with pytest.raises(ToolError, match="denied"):
        tools(session, UNATTENDED)["github__createPullRequest"].fn(
            {"title": "t", "head": "h", "draft": False}
        )
    assert session.calls == []


def test_ask_uses_confirm() -> None:
    route = ("POST", "/repos/o/r/pulls")
    session = FakeSession({route: FakeResponse(201, {"number": 1})})
    args = {"title": "t", "head": "h", "base": "main", "draft": False}
    prompts: list[str] = []

    def no(prompt: str) -> bool:
        prompts.append(prompt)
        return False

    with pytest.raises(ToolError, match="not approved"):
        tools(session, ATTENDED, no)["github__createPullRequest"].fn(args)
    assert session.calls == [] and "createPullRequest" in prompts[0]
    tools(session, ATTENDED, lambda _: True)["github__createPullRequest"].fn(args)
    assert session.calls[0]["json"]["draft"] is False


def test_default_confirm_refuses_without_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    session = FakeSession({})
    with pytest.raises(ToolError, match="not approved"):
        tools(session)["github__updatePullRequest"].fn({"pull_number": 1, "draft": False})


def test_unattended_draft_pr_runs() -> None:
    session = FakeSession({("POST", "/repos/o/r/pulls"): FakeResponse(201, {"number": 3})})
    out = tools(session, UNATTENDED)["github__createPullRequest"].fn(
        {"title": "t", "head": "vk/x", "base": "main", "draft": True}
    )
    assert out == {"number": 3}


def test_ci_failure_context_collects_failed_runs() -> None:
    runs = {
        "check_runs": [
            {"id": 1, "name": "lint", "conclusion": "failure"},
            {"id": 2, "name": "ok", "conclusion": "success"},
        ]
    }
    session = FakeSession(
        {
            ("GET", "/repos/o/r/pulls/7"): FakeResponse(200, {"head": {"sha": "abc"}}),
            ("GET", "/repos/o/r/commits/abc/check-runs"): FakeResponse(200, runs),
            ("GET", "/repos/o/r/check-runs/1/annotations"): FakeResponse(200, [{"message": "bad"}]),
            ("GET", "/repos/o/r/actions/jobs/1/logs"): FakeResponse(200, text="x" * 5000 + "TAIL"),
        }
    )
    out = tools(session)["github__getCiFailureContext"].fn({"pull_number": 7})
    assert [r["name"] for r in out["failed_check_runs"]] == ["lint"]
    assert out["failed_check_runs"][0]["log_tail"].endswith("TAIL")
    assert len(out["failed_check_runs"][0]["log_tail"]) == 4000


def test_collaborator_permission_reports_the_role_and_treats_404_as_none() -> None:
    session = FakeSession(
        {
            ("GET", "/repos/o/r/collaborators/alice/permission"): FakeResponse(
                200, {"role_name": "triage", "permission": "read"}
            )
        }
    )
    get = tools(session)["github__getCollaboratorPermission"].fn

    assert get({"username": "alice"}) == {"login": "alice", "role_name": "triage"}
    assert get({"username": "mallory"}) == {"login": "mallory", "role_name": "none"}


def _app_cfg() -> Config:
    return Config(**{**CFG.__dict__, "bot_login": "vk-app[bot]"})


def test_bot_identity_comes_from_the_users_endpoint() -> None:
    session = FakeSession({("GET", "/users/vk-app[bot]"): FakeResponse(200, {"id": 4242})})

    cfg = with_bot_identity(_app_cfg(), GitHub(_app_cfg(), session))

    assert cfg.bot_name == "vk-app[bot]"
    assert cfg.bot_email == "4242+vk-app[bot]@users.noreply.github.com"


def test_bot_identity_is_skipped_without_a_bot_login() -> None:
    session = FakeSession({})

    assert with_bot_identity(CFG, GitHub(CFG, session)) is CFG
    assert session.calls == []


@pytest.mark.parametrize(
    "response", [FakeResponse(404, {"message": "Not Found"}), FakeResponse(200, {"login": "x"})]
)
def test_bot_identity_falls_back_when_the_lookup_fails(response: FakeResponse) -> None:
    cfg = _app_cfg()
    session = FakeSession({("GET", "/users/vk-app[bot]"): response})

    assert with_bot_identity(cfg, GitHub(cfg, session)) is cfg
