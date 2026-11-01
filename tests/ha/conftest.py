from collections.abc import AsyncGenerator

import pytest
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from simulated_panel import HOST, IDENTITY, SimulatedPanel

from custom_components.amerec_steam import const, panel as panel_module
from custom_components.amerec_steam.const import CONF_PIN, DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let HA load the integration from custom_components."""


@pytest.fixture
def sim(monkeypatch: pytest.MonkeyPatch) -> SimulatedPanel:
    simulated = SimulatedPanel()
    monkeypatch.setattr(panel_module, "open_udp", simulated.open_udp)
    monkeypatch.setattr(panel_module, "ANNOUNCE_TIMEOUT", 0.05)
    monkeypatch.setattr(panel_module, "REPLY_TIMEOUT", 0.02)
    monkeypatch.setattr(panel_module, "STATE_TIMEOUT", 0.05)
    monkeypatch.setattr(panel_module, "COMMAND_TIMEOUT", 0.02)
    monkeypatch.setattr(const, "DISCOVERY_SECONDS", 0.01)
    return simulated


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Amerec Steam",
        unique_id=IDENTITY.decode().strip("{}"),
        data={CONF_HOST: HOST, CONF_PIN: "0000"},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def loaded(hass: HomeAssistant, sim: SimulatedPanel, entry: MockConfigEntry) -> AsyncGenerator[MockConfigEntry]:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    yield entry
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
