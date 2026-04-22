"""Constants for the Felicity inverter integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "felicity_inverter"
DEFAULT_NAME = "Felicity Inverter"
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_TIMEOUT = 2.0
SERIAL_BAUD_RATE = 2400
SERIAL_DEVICE_GLOB = "/dev/ttyUSB*"

CONF_DEVICE = "device"
CONF_SCAN_INTERVAL = "scan_interval"

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SELECT, Platform.NUMBER]

MODES: dict[str, tuple[int, int]] = {
    "grid_charge": (0, 2),
    "grid_only": (0, 0),
    "battery": (2, 3),
}

MODE_BY_REGISTER_PAIR = {value: key for key, value in MODES.items()}
