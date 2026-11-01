"""Minutes left on the panel's timer."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.amerec_steam import PanelConfigEntry
from custom_components.amerec_steam.entity import PanelEntity
from custom_components.amerec_steam.panel import Panel


async def async_setup_entry(
    hass: HomeAssistant, entry: PanelConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([TimeRemainingSensor(entry.runtime_data)])


class TimeRemainingSensor(PanelEntity, SensorEntity):
    _attr_translation_key = "time_remaining"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(self, panel: Panel) -> None:
        super().__init__(panel, "time_remaining")

    @property
    def native_value(self) -> int | None:
        return self.panel.status.remaining_minutes
