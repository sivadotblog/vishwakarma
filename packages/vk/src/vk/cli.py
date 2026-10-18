"""Command line: `vk issue|review|ci-fix <N> [--unattended]`."""

import argparse
import logging
import os
import sys
from collections.abc import Sequence

from pydantic_ai.exceptions import UsageLimitExceeded

from vk.approval import Caller
from vk.ci_fix import run_ci_fix
from vk.config import ConfigError, load_config
from vk.github import GitHub, with_bot_identity
from vk.pipeline import run_issue
from vk.pr_review import run_review


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vk")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("issue", "run an issue through the full pipeline"),
        ("review", "handle review comments on a factory PR"),
        ("ci-fix", "fix failing CI on a factory PR"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("number", type=int, help="issue number" if name == "issue" else "PR number")
        p.add_argument("--unattended", action="store_true", help="never ask for approval")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")  # stdout carries the final reply
    logging.basicConfig(
        level=os.environ.get("VK_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    unattended = bool(args.unattended) or not sys.stdin.isatty()
    n: int = args.number
    try:
        cfg = load_config()
        gh = GitHub(cfg)
        cfg = with_bot_identity(cfg, gh)
        if args.command == "issue":
            print(run_issue(cfg, gh, n, Caller(unattended, issue_number=n)))
        elif args.command == "review":
            print(run_review(cfg, gh, n, Caller(unattended, pr_number=n)))
        else:
            print(run_ci_fix(cfg, gh, n, Caller(unattended, pr_number=n)))
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except UsageLimitExceeded as exc:
        print(f"Token budget exceeded: {exc}", file=sys.stderr)
        return 3
    return 0
