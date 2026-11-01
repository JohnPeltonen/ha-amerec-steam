"""Amerec Steam integration."""

import logging
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from custom_components.amerec_steam.const import CONF_PIN, DOMAIN
from custom_components.amerec_steam.panel import Panel, PanelError, PinRejectedError

logger = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE, Platform.SENSOR]

type PanelConfigEntry = ConfigEntry[Panel]


async def async_setup_entry(hass: HomeAssistant, entry: PanelConfigEntry) -> bool:
    panel = Panel(entry.data[CONF_HOST], entry.data[CONF_PIN])
    try:
        await panel.connect()
    except PinRejectedError as exc:
        raise ConfigEntryNotReady(translation_domain=DOMAIN, translation_key="wrong_pin") from exc
    except (PanelError, OSError) as exc:
        raise ConfigEntryNotReady(translation_domain=DOMAIN, translation_key="no_answer") from exc
    # Closing leaves a running steamer alone. The panel's own timer ends the run.
    entry.async_on_unload(panel.close)
    entry.runtime_data = panel

    # The panel's clock runs fast. 3:00 is after the daylight saving change.
    async def sync_clock(_now: datetime | None = None) -> None:
        try:
            if not await panel.sync_clock(dt_util.now()):
                logger.debug("Left the clock alone, because the steamer isn't off")
        except PanelError:
            logger.debug("Couldn't set the panel's clock", exc_info=True)

    await sync_clock()
    entry.async_on_unload(async_track_time_change(hass, sync_clock, hour=3, minute=0, second=0))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PanelConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
