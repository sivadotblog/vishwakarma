"""Thin GitHub REST client and the `github__*` tool surface (port of extensions/github.ts)."""

import base64
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import quote

import requests

from vk.approval import Caller, Confirm, default_confirm, policy_for
from vk.config import Config
from vk.tooling import Tool, ToolError, ToolFn

log = logging.getLogger(__name__)

API = "https://api.github.com"
API_VERSION = "2022-11-28"
FAILED = {"failure", "timed_out", "cancelled", "action_required"}


class GitHubError(ToolError):
    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


class GitHub:
    def __init__(self, cfg: Config, session: requests.Session | None = None) -> None:
        self.cfg = cfg
        self.session = session or requests.Session()
        self.repo_path = f"/repos/{cfg.repo}"
        self._login: str | None = cfg.bot_login

    def _send(self, method: str, path: str, **kw: Any) -> requests.Response:
        headers = {
            "Authorization": f"Bearer {self.cfg.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
        }
        try:
            timeout = self.cfg.settings.github.timeout_s
            resp = self.session.request(method, API + path, headers=headers, timeout=timeout, **kw)
        except requests.RequestException as exc:
            log.warning("github %s %s failed: %s", method, path, type(exc).__name__)
            raise GitHubError(f"GitHub request failed: {exc}", 0) from exc
        log.debug("github %s %s -> %d", method, path, resp.status_code)
        if not 200 <= resp.status_code < 300:
            log.warning("github %s %s -> %d", method, path, resp.status_code)
            try:
                message = resp.json().get("message", resp.text)
            except (ValueError, AttributeError):
                message = resp.text
            raise GitHubError(f"GitHub {resp.status_code}: {message}", resp.status_code)
        return resp

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        """Call `path` (relative to the API root); returns parsed JSON or None."""
        resp = self._send(method, path, params=params, json=body)
        return None if resp.status_code == 204 or not resp.content else resp.json()

    def text(self, path: str) -> str:
        return self._send("GET", path).text

    def repo(self, suffix: str = "") -> str:
        return self.repo_path + suffix

    def me(self) -> str:
        if self._login is None:
            self._login = str(self.request("GET", "/user")["login"])
        return self._login


def with_bot_identity(cfg: Config, gh: GitHub) -> Config:
    """`cfg` with the git author set to the `bot_login` user, so GitHub links VK's commits to it.

    The noreply email needs the user's numeric id (`<id>+<login>@users.noreply.github.com`),
    from `GET /users/{login}`, which an app installation token can call. Without a `bot_login`,
    or when the lookup fails, `cfg` is returned unchanged and commits keep the default identity.
    """
    login = cfg.bot_login
    if not login:
        return cfg
    try:
        uid = int(gh.request("GET", f"/users/{quote(login, safe='[]')}")["id"])
    except (ToolError, KeyError, TypeError, ValueError) as exc:
        log.warning("could not look up %s; commits keep the default author: %s", login, exc)
        return cfg
    return replace(cfg, bot_name=login, bot_email=f"{uid}+{login}@users.noreply.github.com")


Args = dict[str, Any]
Handler = Callable[[GitHub, Args], Any]


def _drop_none(args: Args, *keys: str) -> Args:
    return {k: args[k] for k in keys if args.get(k) is not None}


def _paged(args: Args, *keys: str) -> Args:
    return {"per_page": args.get("per_page", 30), **_drop_none(args, *keys)}


def _file_content(gh: GitHub, a: Args) -> Any:
    data = gh.request("GET", gh.repo(f"/contents/{quote(a['path'])}"), params=_drop_none(a, "ref"))
    if isinstance(data, dict) and data.get("encoding") == "base64":
        text = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return {"path": data["path"], "sha": data["sha"], "content": text}
    return data


def _issue_context(gh: GitHub, a: Args) -> Any:
    n = a["issue_number"]
    issue = gh.request("GET", gh.repo(f"/issues/{n}"))
    comments = gh.request("GET", gh.repo(f"/issues/{n}/comments"), params={"per_page": 100})
    return {"issue": issue, "labels": issue.get("labels", []), "comments": comments}


def _pr_context(gh: GitHub, a: Args) -> Any:
    n = a["pull_number"]
    return {
        "pull_request": gh.request("GET", gh.repo(f"/pulls/{n}")),
        "comments": gh.request("GET", gh.repo(f"/issues/{n}/comments"), params={"per_page": 100}),
        "reviews": gh.request("GET", gh.repo(f"/pulls/{n}/reviews"), params={"per_page": 100}),
    }


def _create_pr(gh: GitHub, a: Args) -> Any:
    base = a.get("base") or gh.request("GET", gh.repo())["default_branch"]
    body = {"title": a["title"], "head": a["head"], "base": base, "draft": a.get("draft", False)}
    return gh.request("POST", gh.repo("/pulls"), body={**body, **_drop_none(a, "body")})


def _update_pr(gh: GitHub, a: Args) -> Any:
    n = a["pull_number"]
    fields = _drop_none(a, "title", "body", "state", "base")
    result = gh.request("PATCH", gh.repo(f"/pulls/{n}"), body=fields) if fields else None
    if a.get("draft") is False:  # REST cannot flip draft; GraphQL can.
        node = gh.request("GET", gh.repo(f"/pulls/{n}"))["node_id"]
        query = (
            "mutation($id: ID!) { markPullRequestReadyForReview(input: {pullRequestId: $id})"
            " { pullRequest { number isDraft } } }"
        )
        result = gh.request("POST", "/graphql", body={"query": query, "variables": {"id": node}})
    return result or gh.request("GET", gh.repo(f"/pulls/{n}"))


def _check_runs(gh: GitHub, a: Args) -> Any:
    return gh.request("GET", gh.repo(f"/commits/{quote(a['ref'])}/check-runs"), params=_paged(a))


def _ci_failure_context(gh: GitHub, a: Args) -> Any:
    pr = gh.request("GET", gh.repo(f"/pulls/{a['pull_number']}"))
    sha = pr["head"]["sha"]
    runs = gh.request("GET", gh.repo(f"/commits/{sha}/check-runs"), params={"per_page": 100})
    failed = []
    for run in runs.get("check_runs", []):
        if run.get("conclusion") not in FAILED:
            continue
        annotations = gh.request(
            "GET", gh.repo(f"/check-runs/{run['id']}/annotations"), params={"per_page": 50}
        )
        try:  # for GitHub Actions the check run id is the job id
            job_log = gh.text(gh.repo(f"/actions/jobs/{run['id']}/logs"))
            log_tail = job_log[-gh.cfg.settings.github.log_tail_chars :]
        except ToolError:
            log_tail = None
        failed.append(
            {
                "name": run["name"],
                "conclusion": run["conclusion"],
                "html_url": run.get("html_url"),
                "summary": (run.get("output") or {}).get("summary"),
                "annotations": annotations,
                "log_tail": log_tail,
            }
        )
    return {"head_sha": sha, "failed_check_runs": failed}


def _review_comments(gh: GitHub, a: Args) -> Any:
    raw = gh.request(
        "GET", gh.repo(f"/pulls/{a['pull_number']}/comments"), params={"per_page": 100}
    )
    me = gh.me()

    def root(c: Args) -> int:
        return int(c.get("in_reply_to_id") or c["id"])

    mine = [c for c in raw if c["user"]["login"] == me]
    out = []
    for c in raw:
        own = c["user"]["login"] == me
        answered = own or any(root(m) == root(c) and m["id"] > c["id"] for m in mine)
        out.append(
            {
                "id": c["id"],
                "path": c.get("path"),
                "line": c.get("line") or c.get("original_line"),
                "diff_hunk": c.get("diff_hunk"),
                "body": c["body"],
                "user": c["user"]["login"],
                "user_type": c["user"].get("type"),
                "in_reply_to_id": c.get("in_reply_to_id"),
                "answered": answered,
            }
        )
    return out


def _collaborator_permission(gh: GitHub, a: Args) -> Any:
    login = a["username"]
    try:
        data = gh.request("GET", gh.repo(f"/collaborators/{quote(login, safe='')}/permission"))
    except GitHubError as exc:
        if exc.status != 404:
            raise
        return {"login": login, "role_name": "none"}  # not a collaborator: no access
    return {"login": login, "role_name": (data or {}).get("role_name", "none")}


def _ensure_label(gh: GitHub, a: Args) -> Any:
    try:
        gh.request("GET", gh.repo(f"/labels/{quote(a['name'])}"))
        return {"name": a["name"], "created": False}
    except GitHubError as exc:
        if exc.status != 404:
            raise
    body = {"name": a["name"], **_drop_none(a, "color", "description")}
    gh.request("POST", gh.repo("/labels"), body=body)
    return {"name": a["name"], "created": True}


def _list_issues(gh: GitHub, a: Args) -> Any:
    params = {"state": a.get("state", "open"), **_paged(a, "labels", "assignee")}
    return [
        i for i in gh.request("GET", gh.repo("/issues"), params=params) if "pull_request" not in i
    ]


def _search(kind: str) -> Handler:
    def run(gh: GitHub, a: Args) -> Any:
        q = f"{a['query']} repo:{gh.cfg.repo}"
        return gh.request("GET", f"/search/{kind}", params={"q": q, **_paged(a)})

    return run


def _get(path: str, *keys: str, paged: bool = True) -> Handler:
    """GET `path` (format-string over args); remaining `keys` become query params."""

    def run(gh: GitHub, a: Args) -> Any:
        params = _paged(a, *keys) if paged else _drop_none(a, *keys)
        target = path.format(**{k: quote(str(v), safe="") for k, v in a.items()})
        return gh.request("GET", gh.repo(target), params=params)

    return run


def _send(method: str, path: str, *keys: str) -> Handler:
    """`method` `path` with `keys` from the args as the JSON body."""

    def run(gh: GitHub, a: Args) -> Any:
        return gh.request(method, gh.repo(path.format(**a)), body=_drop_none(a, *keys))

    return run


def _remove_label(gh: GitHub, a: Args) -> Any:
    return gh.request("DELETE", gh.repo(f"/issues/{a['issue_number']}/labels/{quote(a['name'])}"))


def _close_issue(gh: GitHub, a: Args) -> Any:
    body = {"state": "closed", "state_reason": a.get("reason", "completed")}
    return gh.request("PATCH", gh.repo(f"/issues/{a['issue_number']}"), body=body)


def _remove_assignees(gh: GitHub, a: Args) -> Any:
    return gh.request(
        "DELETE",
        gh.repo(f"/issues/{a['issue_number']}/assignees"),
        body={"assignees": a["assignees"]},
    )


def _schema(required: list[str], **props: str | Args) -> Args:
    def one(spec: str | Args) -> Args:
        if isinstance(spec, dict):
            return spec
        if spec == "strings":
            return {"type": "array", "items": {"type": "string"}}
        return {"type": spec}

    return {
        "type": "object",
        "properties": {k: one(v) for k, v in props.items()},
        "required": required,
    }


_ISSUE = {"issue_number": "integer"}
_PR = {"pull_number": "integer"}


@dataclass(frozen=True)
class Spec:
    name: str
    description: str
    parameters: Args
    handler: Handler


def _specs() -> list[Spec]:
    s = _schema
    return [
        Spec(
            "getRepository",
            "Get repository metadata (default branch, description).",
            s([]),
            _get("", paged=False),
        ),
        Spec(
            "getRepositoryTree",
            "List the repository file tree at a ref. Not recursive unless `recursive` is true.",
            s([], ref="string", recursive="boolean"),
            lambda gh, a: gh.request(
                "GET",
                gh.repo(f"/git/trees/{quote(a.get('ref', 'HEAD'))}"),
                params={"recursive": "1"} if a.get("recursive", False) else None,
            ),
        ),
        Spec(
            "getFileContent",
            "Read a file's decoded text at an optional ref.",
            s(["path"], path="string", ref="string"),
            _file_content,
        ),
        Spec(
            "searchCode",
            "Search code in this repository.",
            s(["query"], query="string", per_page="integer"),
            _search("code"),
        ),
        Spec("listBranches", "List branches.", s([], per_page="integer"), _get("/branches")),
        Spec(
            "listCommits",
            "List commits, optionally by branch/sha or path.",
            s([], sha="string", path="string", per_page="integer"),
            _get("/commits", "sha", "path"),
        ),
        Spec(
            "getCommit",
            "Get one commit with its files.",
            s(["ref"], ref="string"),
            _get("/commits/{ref}", paged=False),
        ),
        Spec(
            "compareCommits",
            "Compare two refs (base...head).",
            s(["base", "head"], base="string", head="string"),
            _get("/compare/{base}...{head}", paged=False),
        ),
        Spec(
            "searchIssues",
            "Search issues and pull requests in this repository.",
            s(["query"], query="string", per_page="integer"),
            _search("issues"),
        ),
        Spec(
            "listIssues",
            "List issues (no pull requests).",
            s([], state="string", labels="string", assignee="string", per_page="integer"),
            _list_issues,
        ),
        Spec(
            "getIssueContext",
            "Get an issue with its comments and labels.",
            s(["issue_number"], **_ISSUE),
            _issue_context,
        ),
        Spec(
            "listIssueComments",
            "List comments on an issue or PR.",
            s(["issue_number"], **_ISSUE, per_page="integer"),
            _get("/issues/{issue_number}/comments"),
        ),
        Spec(
            "createIssue",
            "Create an issue.",
            s(["title"], title="string", body="string", labels="strings", assignees="strings"),
            _send("POST", "/issues", "title", "body", "labels", "assignees"),
        ),
        Spec(
            "updateIssue",
            "Update an issue (title, body, state, state_reason).",
            s(
                ["issue_number"],
                **_ISSUE,
                title="string",
                body="string",
                state="string",
                state_reason="string",
            ),
            _send("PATCH", "/issues/{issue_number}", "title", "body", "state", "state_reason"),
        ),
        Spec(
            "closeIssue",
            "Close an issue (reason: completed or not_planned).",
            s(["issue_number"], **_ISSUE, reason="string"),
            _close_issue,
        ),
        Spec(
            "addIssueComment",
            "Comment on an issue.",
            s(["issue_number", "body"], **_ISSUE, body="string"),
            _send("POST", "/issues/{issue_number}/comments", "body"),
        ),
        Spec(
            "listLabels",
            "List the repository's labels.",
            s([], per_page="integer"),
            _get("/labels"),
        ),
        Spec(
            "addLabels",
            "Add labels to an issue or PR.",
            s(["issue_number", "labels"], **_ISSUE, labels="strings"),
            _send("POST", "/issues/{issue_number}/labels", "labels"),
        ),
        Spec(
            "removeLabel",
            "Remove one label from an issue or PR.",
            s(["issue_number", "name"], **_ISSUE, name="string"),
            _remove_label,
        ),
        Spec(
            "ensureLabel",
            "Create a label if it does not exist.",
            s(["name"], name="string", color="string", description="string"),
            _ensure_label,
        ),
        Spec(
            "addAssignees",
            "Assign users to an issue.",
            s(["issue_number", "assignees"], **_ISSUE, assignees="strings"),
            _send("POST", "/issues/{issue_number}/assignees", "assignees"),
        ),
        Spec(
            "removeAssignees",
            "Unassign users from an issue.",
            s(["issue_number", "assignees"], **_ISSUE, assignees="strings"),
            _remove_assignees,
        ),
        Spec(
            "listPullRequests",
            "List pull requests.",
            s([], state="string", head="string", base="string", per_page="integer"),
            _get("/pulls", "state", "head", "base"),
        ),
        Spec(
            "getPullRequestContext",
            "Get a PR with its comments and reviews.",
            s(["pull_number"], **_PR),
            _pr_context,
        ),
        Spec(
            "listPullRequestFiles",
            "List files changed in a PR.",
            s(["pull_number"], **_PR, per_page="integer"),
            _get("/pulls/{pull_number}/files"),
        ),
        Spec(
            "listPullRequestReviews",
            "List reviews on a PR.",
            s(["pull_number"], **_PR, per_page="integer"),
            _get("/pulls/{pull_number}/reviews"),
        ),
        Spec(
            "createPullRequest",
            "Open a pull request (draft must be true for unattended runs).",
            s(
                ["title", "head"],
                title="string",
                head="string",
                base="string",
                body="string",
                draft="boolean",
            ),
            _create_pr,
        ),
        Spec(
            "updatePullRequest",
            "Update a PR; draft=false marks it ready for review.",
            s(
                ["pull_number"],
                **_PR,
                title="string",
                body="string",
                state="string",
                base="string",
                draft="boolean",
            ),
            _update_pr,
        ),
        Spec(
            "addPullRequestComment",
            "Comment on a pull request.",
            s(["pull_number", "body"], **_PR, body="string"),
            _send("POST", "/issues/{pull_number}/comments", "body"),
        ),
        Spec(
            "requestReviewers",
            "Request reviewers on a PR.",
            s(["pull_number"], **_PR, reviewers="strings", team_reviewers="strings"),
            _send(
                "POST", "/pulls/{pull_number}/requested_reviewers", "reviewers", "team_reviewers"
            ),
        ),
        Spec(
            "listCheckRuns",
            "List check runs for a ref.",
            s(["ref"], ref="string", per_page="integer"),
            _check_runs,
        ),
        Spec(
            "getCiFailureContext",
            "Failed check runs with annotations and log tail for a PR head.",
            s(["pull_number"], **_PR),
            _ci_failure_context,
        ),
        Spec(
            "listReviewComments",
            "List inline review comments on a PR, each with its diff hunk and an `answered` flag.",
            s(["pull_number"], **_PR),
            _review_comments,
        ),
        Spec(
            "getCollaboratorPermission",
            "A user's role on this repository (admin, maintain, write, triage, read or none).",
            s(["username"], username="string"),
            _collaborator_permission,
        ),
        Spec(
            "replyToReviewComment",
            "Reply in an inline review comment thread.",
            s(["pull_number", "comment_id", "body"], **_PR, comment_id="integer", body="string"),
            _send("POST", "/pulls/{pull_number}/comments/{comment_id}/replies", "body"),
        ),
    ]


def _guard(spec: Spec, gh: GitHub, caller: Caller, confirm: Confirm) -> ToolFn:
    def run(args: Args) -> Any:
        decision = policy_for(spec.name, args, caller)
        if decision == "deny":
            raise ToolError(f"denied: {spec.name} is not permitted for this run")
        if decision == "ask":
            summary = json.dumps(args, default=str)[:300]
            if not confirm(f"Allow github__{spec.name} {summary}?"):
                raise ToolError(f"denied: {spec.name} was not approved")
        return spec.handler(gh, args)

    return run


def github_tools(gh: GitHub, caller: Caller, confirm: Confirm | None = None) -> list[Tool]:
    """All `github__*` tools, each call gated by `policy_for(caller)`."""
    ask = confirm or default_confirm
    tools = []
    for spec in _specs():
        tools.append(
            Tool(
                name=f"github__{spec.name}",
                description=spec.description,
                parameters=spec.parameters,
                fn=_guard(spec, gh, caller, ask),
            )
        )
    return tools
