"""The base of every entity. The panel pushes changes, so nothing polls."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from custom_components.amerec_steam.const import DOMAIN
from custom_components.amerec_steam.panel import Panel


class PanelEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, panel: Panel, key: str) -> None:
        self.panel = panel
        self._attr_unique_id = f"{panel.identity}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(panel.identity))},
            name=panel.name or "Steam",
            manufacturer="Amerec",
            model="Elite (A6)",
            sw_version=panel.version,
        )

    @property
    def available(self) -> bool:
        return self.panel.available

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.panel.add_listener(self.async_write_ha_state))
