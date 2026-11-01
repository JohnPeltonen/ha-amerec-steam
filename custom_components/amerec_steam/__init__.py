"""Amerec Steam integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from custom_components.amerec_steam.const import CONF_PIN, DOMAIN
from custom_components.amerec_steam.panel import Panel, PanelError, PinRejectedError

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
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PanelConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
