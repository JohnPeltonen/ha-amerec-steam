import pytest
from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_HVAC_ACTION,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE, STATE_UNAVAILABLE
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM

from custom_components.amerec_steam import panel as panel_module

CLIMATE = "climate.steam"
REMAINING = "sensor.steam_time_remaining"
HEAT_ON = bytes.fromhex("c24302500b")
HEAT_OFF = bytes.fromhex("c24302500a")


@pytest.fixture(autouse=True)
def fahrenheit(hass):
    hass.config.units = US_CUSTOMARY_SYSTEM


async def call(hass, service, **data):
    await hass.services.async_call(CLIMATE_DOMAIN, service, {ATTR_ENTITY_ID: CLIMATE, **data}, blocking=True)
    await hass.async_block_till_done()


async def test_state_matches_the_panel_in_fahrenheit(hass, sim, loaded):
    state = hass.states.get(CLIMATE)
    assert state.state == HVACMode.OFF
    assert state.attributes[ATTR_TEMPERATURE] == 114
    assert state.attributes[ATTR_CURRENT_TEMPERATURE] == 71
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.OFF
    assert state.attributes[ATTR_MIN_TEMP] == 86
    assert state.attributes[ATTR_MAX_TEMP] == 125
    assert hass.states.get(REMAINING).state == "0"


async def test_state_in_celsius(hass, sim, entry):
    hass.config.units = METRIC_SYSTEM
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(CLIMATE)
    assert state.attributes[ATTR_TEMPERATURE] == 46
    assert state.attributes[ATTR_CURRENT_TEMPERATURE] == 22
    assert state.attributes[ATTR_MAX_TEMP] == 52
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_doesnt_start_the_steamer(hass, sim, loaded):
    assert HEAT_ON not in sim.sent


async def test_turn_on_and_off(hass, sim, loaded):
    await call(hass, SERVICE_TURN_ON)
    assert sim.mode == 11
    state = hass.states.get(CLIMATE)
    assert state.state == HVACMode.HEAT
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.HEATING
    assert hass.states.get(REMAINING).state == "60"

    await call(hass, SERVICE_TURN_OFF)
    assert sim.mode == 10
    assert hass.states.get(CLIMATE).state == HVACMode.OFF
    assert hass.states.get(REMAINING).state == "0"


async def test_heat_while_running_doesnt_send_start_again(hass, sim, loaded):
    await call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)
    sim.sent.clear()
    await call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)
    assert HEAT_ON not in sim.sent


async def test_set_temperature_doesnt_start_the_steamer(hass, sim, loaded):
    await call(hass, SERVICE_SET_TEMPERATURE, temperature=113)
    assert sim.target == 408
    assert hass.states.get(CLIMATE).attributes[ATTR_TEMPERATURE] == 113
    assert HEAT_ON not in sim.sent


async def test_temperature_above_the_range_is_refused(hass, sim, loaded):
    with pytest.raises(ServiceValidationError):
        await call(hass, SERVICE_SET_TEMPERATURE, temperature=126)
    assert sim.target == 413


async def test_change_at_the_wall_panel_shows_up(hass, sim, loaded):
    sim.mode, sim.remaining, sim.target = 11, 60, 418
    sim.push_status()
    await hass.async_block_till_done()
    state = hass.states.get(CLIMATE)
    assert state.state == HVACMode.HEAT
    assert state.attributes[ATTR_TEMPERATURE] == 115
    assert hass.states.get(REMAINING).state == "60"


async def test_start_the_panel_doesnt_confirm_shows_an_error(hass, sim, loaded):
    sim.ignore_start = True
    with pytest.raises(HomeAssistantError):
        await call(hass, SERVICE_TURN_ON)


async def test_stop_the_panel_doesnt_confirm_shows_an_error(hass, sim, loaded):
    await call(hass, SERVICE_TURN_ON)
    sim.ignore_stop = True
    with pytest.raises(HomeAssistantError):
        await call(hass, SERVICE_TURN_OFF)


async def test_entities_become_unavailable_when_the_panel_goes_quiet(hass, sim, loaded, monkeypatch):
    monkeypatch.setattr(panel_module, "OFFLINE_AFTER", -1)
    loaded.runtime_data._notify()
    await hass.async_block_till_done()
    assert hass.states.get(CLIMATE).state == STATE_UNAVAILABLE
    assert hass.states.get(REMAINING).state == STATE_UNAVAILABLE


async def test_unload_closes_the_sockets_and_leaves_the_steamer_alone(hass, sim, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await call(hass, SERVICE_TURN_ON)
    sim.sent.clear()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert all(transport.closed for transport in sim.transports)
    assert sim.mode == 11
    assert HEAT_OFF not in sim.sent


@pytest.mark.parametrize(
    "setup",
    [
        lambda sim: setattr(sim, "pin", "1234"),
        lambda sim: setattr(sim, "silent", True),
        lambda sim: setattr(sim, "announcing", False),
    ],
)
async def test_setup_retries_when_the_panel_cant_be_reached(hass, sim, entry, setup):
    setup(sim)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert all(transport.closed for transport in sim.transports)
