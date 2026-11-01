"""Setup screens: the panel's address and PIN. Reconfigure changes either one later."""

import logging
from typing import Any

import probatio
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST

from custom_components.amerec_steam import const
from custom_components.amerec_steam.const import CONF_PIN, DEFAULT_PIN, DOMAIN
from custom_components.amerec_steam.panel import Panel, PanelError, PinRejectedError, discover_panels

logger = logging.getLogger(__name__)

TITLE = "Amerec Steam"

SCHEMA = probatio.Schema({probatio.Required(CONF_HOST): str, probatio.Required(CONF_PIN): str})


async def check_panel(host: str, pin: str) -> tuple[str | None, str | None]:
    """Connect once. Returns (panel identity, None) or (None, error key)."""
    if not pin.isascii() or not pin.isdigit():
        return None, "invalid_pin"
    panel = Panel(host, pin)
    try:
        await panel.connect()
    except PinRejectedError:
        return None, "wrong_pin"
    except (PanelError, OSError):
        return None, "no_answer"
    except Exception:
        logger.exception("Unexpected error checking the panel at %s", host)
        return None, "unknown"
    panel.close()
    return panel.identity, None


class AmerecSteamConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered_host = ""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is None:
            try:
                panels = await discover_panels(const.DISCOVERY_SECONDS)
            except OSError:
                logger.debug("Couldn't listen for panel announcements", exc_info=True)
                panels = {}
            self._discovered_host = next(iter(panels), "")
            suggested = {CONF_HOST: self._discovered_host, CONF_PIN: DEFAULT_PIN}
        else:
            suggested = user_input
            identity, error = await check_panel(user_input[CONF_HOST].strip(), user_input[CONF_PIN])
            if error is None:
                await self.async_set_unique_id(identity)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=TITLE, data={CONF_HOST: user_input[CONF_HOST].strip(), CONF_PIN: user_input[CONF_PIN]}
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(SCHEMA, suggested),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            identity, error = await check_panel(host, user_input[CONF_PIN])
            if error is None:
                await self.async_set_unique_id(identity)
                self._abort_if_unique_id_mismatch(reason="wrong_panel")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_HOST: host, CONF_PIN: user_input[CONF_PIN]}
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(SCHEMA, user_input or entry.data),
            errors=errors,
        )
