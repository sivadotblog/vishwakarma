"""Tests for prefect_flows.stage_tasks: each VK stage runs as a Prefect task."""

import inspect
from collections.abc import Iterator

import pytest
from prefect import flow, get_client
from prefect.cache_policies import NO_CACHE
from prefect.client.schemas.filters import FlowRunFilter, FlowRunFilterId
from prefect.testing.utilities import prefect_test_harness
from prefect_flows.stage_tasks import prefect_stage, stage_task


@pytest.fixture(scope="module", autouse=True)
def harness() -> Iterator[None]:
    with prefect_test_harness():
        yield


def test_stage_task_options() -> None:
    t = stage_task("analyst", lambda: 1)

    assert t.name == "analyst"
    assert t.persist_result is False
    assert t.cache_policy is NO_CACHE
    assert t.retries == 0
    assert inspect.signature(t.fn).parameters == {}


def test_prefect_stage_returns_result() -> None:
    @flow
    def f() -> int:
        return prefect_stage("analyst", lambda: 41) + 1

    assert f() == 42


def test_repeated_stage_runs_twice() -> None:
    values = iter([1, 2])

    @flow
    def f() -> list[int]:
        return [
            prefect_stage("implementer", lambda: next(values)),
            prefect_stage("implementer", lambda: next(values)),
        ]

    state = f(return_state=True)
    flow_run_id = state.state_details.flow_run_id
    assert flow_run_id is not None
    runs = get_client(sync_client=True).read_task_runs(
        flow_run_filter=FlowRunFilter(id=FlowRunFilterId(any_=[flow_run_id]))
    )

    assert state.result() == [1, 2]
    assert len(runs) == 2
    assert all(r.name.startswith("implementer") for r in runs)


def test_failed_stage_fails_task_not_flow() -> None:
    def boom() -> str:
        raise RuntimeError("x")

    @flow
    def f() -> str:
        try:
            return prefect_stage("analyst", boom)
        except RuntimeError:
            return "Stopped"

    state = f(return_state=True)
    flow_run_id = state.state_details.flow_run_id
    assert flow_run_id is not None
    runs = get_client(sync_client=True).read_task_runs(
        flow_run_filter=FlowRunFilter(id=FlowRunFilterId(any_=[flow_run_id]))
    )

    assert state.is_completed()
    assert state.result() == "Stopped"
    assert len(runs) == 1
    assert runs[0].state is not None
    assert runs[0].state.is_failed()
