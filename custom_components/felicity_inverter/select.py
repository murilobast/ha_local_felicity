"""Select platform for inverter mode control."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import FelicityInverterError
from .const import DOMAIN, MODE_BY_REGISTER_PAIR, MODES
from .coordinator import FelicityInverterDataCoordinator
from .entity import FelicityInverterEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the inverter mode select."""
    coordinator: FelicityInverterDataCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FelicityModeSelect(coordinator, entry.entry_id)])


class FelicityModeSelect(FelicityInverterEntity, SelectEntity):
    """Select entity that controls the inverter mode presets."""

    def __init__(self, coordinator: FelicityInverterDataCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "mode")
        self._attr_has_entity_name = True
        self._attr_name = "Preset Mode"
        self._attr_options = list(MODES)
        self._attr_icon = "mdi:transmission-tower"

    @property
    def current_option(self) -> str | None:
        """Return the currently active mode if it matches a known preset."""
        settings = self.coordinator.data["settings"]["fields"]
        pair = (
            settings.get("output_source_priority"),
            settings.get("charge_source_priority"),
        )
        return MODE_BY_REGISTER_PAIR.get(pair)

    async def async_select_option(self, option: str) -> None:
        """Apply the selected inverter mode."""
        if option not in MODES:
            raise HomeAssistantError(f"Unsupported mode: {option}")

        try:
            await self.coordinator.async_set_mode(option)
        except FelicityInverterError as err:
            raise HomeAssistantError(str(err)) from err

    @property
    def extra_state_attributes(self) -> dict[str, int | str | None]:
        """Expose the raw register pair and actual inverter working mode."""
        status = self.coordinator.data["status"]["fields"]
        settings = self.coordinator.data["settings"]["fields"]
        return {
            "output_source_priority": settings.get("output_source_priority"),
            "charge_source_priority": settings.get("charge_source_priority"),
            "working_mode": status.get("working_mode"),
            "working_mode_label": status.get("working_mode_label"),
        }
