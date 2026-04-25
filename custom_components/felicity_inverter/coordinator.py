"""Coordinator for Felicity inverter data polling."""

from __future__ import annotations

import asyncio
import logging
from copy import deepcopy
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import FelicityInverterClient, FelicityInverterError
from .const import DEFAULT_SCAN_INTERVAL, DEFAULT_WIFI_BATTERY_STALE_POLLS, DOMAIN
from .wifi_battery import FelicityWifiBatteryClient

LOGGER = logging.getLogger(__name__)


class FelicityInverterDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch and cache Felicity inverter data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: FelicityInverterClient | None,
        wifi_battery_client: FelicityWifiBatteryClient | None = None,
        device_type: str = "inverter",
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.wifi_battery_client = wifi_battery_client
        self.device_type = device_type
        self.has_inverter = client is not None
        self.has_wifi_battery = wifi_battery_client is not None
        self.wifi_battery_host = wifi_battery_client.host if wifi_battery_client is not None else None
        self.wifi_battery_port = wifi_battery_client.port if wifi_battery_client is not None else None
        self._wifi_battery_stale_limit = DEFAULT_WIFI_BATTERY_STALE_POLLS
        self._wifi_battery_failed_polls = 0
        self._last_good_wifi_battery_data: dict[str, Any] | None = None
        self._lock = asyncio.Lock()

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            async with self._lock:
                data = await self._async_read_primary_data()
                return await self._async_merge_wifi_battery(data)
        except FelicityInverterError as err:
            raise UpdateFailed(str(err)) from err

    async def async_set_mode(self, mode: str) -> None:
        if self.client is None:
            raise UpdateFailed("This entry does not expose inverter controls")
        async with self._lock:
            data = await self.hass.async_add_executor_job(self.client.set_mode, mode)
            data = await self._async_merge_wifi_battery(data)
        self.async_set_updated_data(data)

    async def async_set_max_ac_charge_current(self, amps: int) -> None:
        if self.client is None:
            raise UpdateFailed("This entry does not expose inverter controls")
        async with self._lock:
            data = await self.hass.async_add_executor_job(self.client.set_max_ac_charge_current, amps)
            data = await self._async_merge_wifi_battery(data)
        self.async_set_updated_data(data)

    async def async_write_setting(self, field_name: str, value: int | float) -> None:
        if self.client is None:
            raise UpdateFailed("This entry does not expose inverter settings")
        async with self._lock:
            data = await self.hass.async_add_executor_job(self.client.write_setting, field_name, value)
            data = await self._async_merge_wifi_battery(data)
        self.async_set_updated_data(data)

    async def _async_read_primary_data(self) -> dict[str, Any]:
        if self.client is not None:
            data = await self.hass.async_add_executor_job(self.client.read_all)
            data["device_type"] = "inverter"
            return data

        if self.wifi_battery_client is not None:
            battery = await self._async_read_wifi_battery_data()
            return {
                "device_type": "battery",
                "connection": battery["connection"],
                "wifi_battery": battery,
            }

        raise FelicityInverterError("No configured backend for this entry")

    async def _async_merge_wifi_battery(self, data: dict[str, Any]) -> dict[str, Any]:
        if self.wifi_battery_client is None:
            data["wifi_battery"] = None
            return data

        if self.client is None:
            return data

        try:
            data["wifi_battery"] = await self._async_read_wifi_battery_data()
        except FelicityInverterError as err:
            LOGGER.warning("Felicity WiFi battery update failed: %s", err)
            data["wifi_battery"] = self.data.get("wifi_battery") if self.data else None
        return data

    async def _async_read_wifi_battery_data(self) -> dict[str, Any]:
        if self.wifi_battery_client is None:
            raise FelicityInverterError("No configured WiFi battery backend")

        try:
            battery = await self.hass.async_add_executor_job(self.wifi_battery_client.read_all)
        except FelicityInverterError as err:
            cached = self._use_cached_wifi_battery_data()
            if cached is not None:
                LOGGER.warning(
                    "Felicity WiFi battery update failed, reusing cached data (%s/%s): %s",
                    self._wifi_battery_failed_polls,
                    self._wifi_battery_stale_limit,
                    err,
                )
                return cached
            raise

        self._wifi_battery_failed_polls = 0
        self._last_good_wifi_battery_data = deepcopy(battery)
        return self._mark_wifi_battery_fresh(battery)

    def _use_cached_wifi_battery_data(self) -> dict[str, Any] | None:
        if self._last_good_wifi_battery_data is None:
            return None

        self._wifi_battery_failed_polls += 1
        if self._wifi_battery_failed_polls > self._wifi_battery_stale_limit:
            return None

        cached = deepcopy(self._last_good_wifi_battery_data)
        return self._mark_wifi_battery_stale(cached)

    def _mark_wifi_battery_fresh(self, battery: dict[str, Any]) -> dict[str, Any]:
        battery.setdefault("connection", {})
        battery["stale"] = False
        battery["stale_polls"] = 0
        battery["connection"]["stale"] = False
        battery["connection"]["stale_polls"] = 0
        return battery

    def _mark_wifi_battery_stale(self, battery: dict[str, Any]) -> dict[str, Any]:
        battery.setdefault("connection", {})
        battery["stale"] = True
        battery["stale_polls"] = self._wifi_battery_failed_polls
        battery["connection"]["stale"] = True
        battery["connection"]["stale_polls"] = self._wifi_battery_failed_polls
        return battery
