"""GET /api/engines: the capability flags of the optional engines."""

from collections.abc import Iterator

import pytest
from clipforge import engines
from clipforge.engines import Engine, InstallStatus
from fastapi.testclient import TestClient


class SwitchEngine(Engine):
    """An engine that the test installs and uninstalls."""

    def __init__(self) -> None:
        super().__init__("switch", "Switch")
        self.installed = False

    def install_check(self) -> InstallStatus:
        if self.installed:
            return InstallStatus(installed=True, version="2")
        return InstallStatus(installed=False, error="switch is off")


@pytest.fixture
def switch(monkeypatch: pytest.MonkeyPatch) -> Iterator[SwitchEngine]:
    engine = SwitchEngine()
    monkeypatch.setitem(engines.ENGINES, "switch", engine)
    engines.clear_cache()
    yield engine
    engines.clear_cache()


def flags(client: TestClient, query: str = "") -> dict[str, dict[str, object]]:
    response = client.get(f"/api/engines{query}")
    assert response.status_code == 200
    return {item["name"]: item for item in response.json()}


def test_lists_every_registered_engine(client: TestClient) -> None:
    found = flags(client)

    assert set(found) == set(engines.ENGINES)
    for item in found.values():
        assert isinstance(item["installed"], bool)
        assert item["doc_anchor"] == f"engine-{str(item['name']).replace('_', '-')}"
        assert (item["error"] is None) == item["installed"]


def test_flag_is_cached_until_refresh(client: TestClient, switch: SwitchEngine) -> None:
    assert flags(client)["switch"]["installed"] is False

    switch.installed = True
    assert flags(client)["switch"]["installed"] is False
    refreshed = flags(client, "?refresh=true")["switch"]

    assert refreshed["installed"] is True
    assert refreshed["version"] == "2"
    assert refreshed["error"] is None
    assert flags(client)["switch"]["installed"] is True


def test_not_installed_engine_says_why(
    client: TestClient, switch: SwitchEngine
) -> None:
    item = flags(client)["switch"]

    assert item["installed"] is False
    assert item["version"] is None
    assert item["error"] == "switch is off"
