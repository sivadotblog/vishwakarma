"""Run each VK stage as a Prefect task, for visibility only.

No result storage, no caching and no retries: VK retries a stage itself, so one task
covers both attempts and a repeated stage name gives a separate task run each time.
"""

from collections.abc import Callable

from prefect import Task, task
from prefect.cache_policies import NO_CACHE


def stage_task[T](stage: str, call: Callable[[], T]) -> Task[[], T]:
    """Build a Prefect task named `stage` that runs `call`."""

    # No parameters, so prompts, config and secrets never become task inputs.
    def run() -> T:
        return call()

    return task(name=stage, persist_result=False, cache_policy=NO_CACHE, retries=0)(run)


def prefect_stage[T](stage: str, call: Callable[[], T]) -> T:
    """Run `call` as a Prefect task named `stage`; exceptions propagate unchanged."""
    return stage_task(stage, call)()
