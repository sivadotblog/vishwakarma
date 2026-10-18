"""Deploy the VK flows to the managed vk-agents work pool: `python deploy.py [--branch B]`."""

import argparse
import re
from collections.abc import Sequence
from typing import Any, cast

from prefect import flow
from prefect.runner.storage import GitRepository

REPO_URL = "https://github.com/sivadotblog/vishwakarma"
WORK_POOL = "vk-agents"
IMAGE = "prefecthq/prefect:3-python3.12"
ENTRYPOINTS = {
    "vk-issue": "packages/vk/prefect_flows/flows.py:vk_issue",
    "vk-review": "packages/vk/prefect_flows/flows.py:vk_review",
}


def deployment_name(branch: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", branch.lower()).strip("-")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deploy the VK flows to Prefect.")
    parser.add_argument("--branch", default="main")
    args = parser.parse_args(argv)
    name = deployment_name(args.branch)
    for flow_name, entrypoint in ENTRYPOINTS.items():
        # from_source is typed as sync-or-async; with no running loop it returns the Flow.
        loaded = cast(
            Any,
            flow.from_source(
                source=GitRepository(url=REPO_URL, branch=args.branch), entrypoint=entrypoint
            ),
        )
        loaded.deploy(name=name, work_pool_name=WORK_POOL, job_variables={"image": IMAGE})
        print(f"prefect deployment run '{flow_name}/{name}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
