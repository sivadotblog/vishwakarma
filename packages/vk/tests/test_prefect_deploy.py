from typing import Any

import pytest
from prefect.runner.storage import GitRepository
from prefect_flows import deploy


def test_deployment_name_slugifies() -> None:
    assert deploy.deployment_name("main") == "main"
    assert deploy.deployment_name("vk/Foo_bar") == "vk-foo-bar"
    assert deploy.deployment_name("--x--") == "x"


def test_main_deploys_both_flows(monkeypatch: pytest.MonkeyPatch) -> None:
    sources: list[tuple[Any, str]] = []
    deploys: list[dict[str, Any]] = []

    class FakeLoaded:
        def deploy(self, **kwargs: Any) -> None:
            deploys.append(kwargs)

    def fake_from_source(source: Any, entrypoint: str) -> FakeLoaded:
        sources.append((source, entrypoint))
        return FakeLoaded()

    monkeypatch.setattr("prefect_flows.deploy.flow.from_source", fake_from_source)

    assert deploy.main(["--branch", "feat/x"]) == 0

    assert [entrypoint for _, entrypoint in sources] == list(deploy.ENTRYPOINTS.values())
    for source, _ in sources:
        assert isinstance(source, GitRepository)
        assert source._branch == "feat/x"
    assert len(deploys) == 2
    for kwargs in deploys:
        assert kwargs == {
            "name": "feat-x",
            "work_pool_name": "vk-agents",
            "job_variables": {"image": "prefecthq/prefect:3-python3.12"},
        }
