from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResultType
from simulated_panel import HOST

from custom_components.amerec_steam.const import CONF_PIN, DOMAIN


def suggested(result) -> dict:
    return {
        key.schema: key.description["suggested_value"]
        for key in result["data_schema"].schema
        if key.description and "suggested_value" in key.description
    }


async def start(hass):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})


async def test_form_is_filled_in_from_discovery(hass, sim):
    result = await start(hass)
    assert (result["type"], result["step_id"]) == (FlowResultType.FORM, "user")
    assert suggested(result) == {CONF_HOST: HOST, CONF_PIN: "0000"}
    hass.config_entries.flow.async_abort(result["flow_id"])


async def test_form_opens_when_no_panel_is_found(hass, sim):
    sim.announcing = False
    result = await start(hass)
    assert suggested(result) == {CONF_HOST: "", CONF_PIN: "0000"}
    hass.config_entries.flow.async_abort(result["flow_id"])


async def test_form_opens_when_the_port_cant_be_opened(hass, sim):
    sim.open_error = OSError("address in use")
    result = await start(hass)
    assert result["step_id"] == "user"
    hass.config_entries.flow.async_abort(result["flow_id"])


async def test_user_flow_creates_the_entry_and_closes_the_test_connection(hass, sim):
    result = await start(hass)
    with patch("custom_components.amerec_steam.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: f" {HOST} ", CONF_PIN: "0000"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Amerec Steam"
    assert result["data"] == {CONF_HOST: HOST, CONF_PIN: "0000"}
    assert all(transport.closed for transport in sim.transports)


@pytest.mark.parametrize(
    ("pin", "setup", "error"),
    [
        ("9999", lambda sim: None, "wrong_pin"),
        ("12a4", lambda sim: None, "invalid_pin"),
        ("0000", lambda sim: setattr(sim, "silent", True), "no_answer"),
    ],
)
async def test_user_flow_errors(hass, sim, pin, setup, error):
    result = await start(hass)
    setup(sim)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST, CONF_PIN: pin})
    assert (result["step_id"], result["errors"]) == ("user", {"base": error})
    assert all(transport.closed for transport in sim.transports)
    hass.config_entries.flow.async_abort(result["flow_id"])


async def test_the_same_panel_cant_be_added_twice(hass, sim, entry):
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST, CONF_PIN: "0000"})
    assert (result["type"], result["reason"]) == (FlowResultType.ABORT, "already_configured")


async def test_reconfigure_changes_the_pin(hass, sim, loaded):
    sim.pin = "1234"
    result = await loaded.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST, CONF_PIN: "1234"})
    assert (result["type"], result["reason"]) == (FlowResultType.ABORT, "reconfigure_successful")
    assert loaded.data[CONF_PIN] == "1234"
    await hass.async_block_till_done()


async def test_reconfigure_shows_a_wrong_pin(hass, sim, loaded):
    result = await loaded.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST, CONF_PIN: "9999"})
    assert (result["step_id"], result["errors"]) == ("reconfigure", {"base": "wrong_pin"})
    assert loaded.data[CONF_PIN] == "0000"
    hass.config_entries.flow.async_abort(result["flow_id"])
