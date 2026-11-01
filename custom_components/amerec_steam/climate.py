"""The steamer as a climate entity: on and off, target temperature, current temperature."""

from typing import Any

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACAction, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, PRECISION_WHOLE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.amerec_steam import PanelConfigEntry
from custom_components.amerec_steam.const import DOMAIN
from custom_components.amerec_steam.entity import PanelEntity
from custom_components.amerec_steam.panel import (
    MODE_OFF,
    MODE_ON,
    NotConfirmedError,
    Panel,
    PanelError,
    celsius_to_raw,
    fahrenheit_to_raw,
    raw_to_celsius,
    raw_to_fahrenheit,
)

MIN_FAHRENHEIT = 86
MAX_FAHRENHEIT = 125
MIN_CELSIUS = 30
MAX_CELSIUS = 52


async def async_setup_entry(
    hass: HomeAssistant, entry: PanelConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([SteamClimate(entry.runtime_data, hass.config.units.temperature_unit)])


class SteamClimate(PanelEntity, ClimateEntity):
    _attr_name = None
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
    )
    _attr_precision = PRECISION_WHOLE
    _attr_target_temperature_step = 1

    def __init__(self, panel: Panel, unit: str) -> None:
        super().__init__(panel, "climate")
        # Work in the unit HA shows, so the number on the dashboard matches the number on the panel.
        self._attr_temperature_unit = unit
        self._fahrenheit = unit == UnitOfTemperature.FAHRENHEIT
        self._attr_min_temp = MIN_FAHRENHEIT if self._fahrenheit else MIN_CELSIUS
        self._attr_max_temp = MAX_FAHRENHEIT if self._fahrenheit else MAX_CELSIUS

    def _from_raw(self, raw: int | None) -> int | None:
        if raw is None:
            return None
        return raw_to_fahrenheit(raw) if self._fahrenheit else raw_to_celsius(raw)

    @property
    def hvac_mode(self) -> HVACMode | None:
        mode = self.panel.status.mode
        if mode is None:
            return None
        return HVACMode.OFF if mode == MODE_OFF else HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction | None:
        mode = self.panel.status.mode
        if mode is None:
            return None
        return HVACAction.OFF if mode == MODE_OFF else HVACAction.HEATING

    @property
    def target_temperature(self) -> int | None:
        return self._from_raw(self.panel.status.target_raw)

    @property
    def current_temperature(self) -> int | None:
        return self._from_raw(self.panel.status.current_raw)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        try:
            if hvac_mode == HVACMode.OFF:
                await self.panel.stop()
            elif self.panel.status.mode != MODE_ON:
                await self.panel.start()
        except NotConfirmedError as exc:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="not_confirmed") from exc
        except PanelError as exc:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="no_answer") from exc

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = round(kwargs[ATTR_TEMPERATURE])
        raw = fahrenheit_to_raw(temperature) if self._fahrenheit else celsius_to_raw(temperature)
        try:
            await self.panel.set_target(raw)
        except NotConfirmedError as exc:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="not_confirmed") from exc
        except PanelError as exc:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="no_answer") from exc
