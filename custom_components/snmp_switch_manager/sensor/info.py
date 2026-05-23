from __future__ import annotations

import logging
from typing import Any
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import SensorEntity

from ..snmp import SwitchSnmpClient
from ..helpers import uptime_human

_LOGGER = logging.getLogger(__name__)

SENSOR_TYPES = {
    "uptime": "Uptime",
}


class SimpleTextSensor(CoordinatorEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, key, value, device_info: DeviceInfo, hostname: str):
        super().__init__(coordinator)
        self._key = key
        self._value = value
        self._hostname = hostname
        self._attr_unique_id = f"{entry.entry_id}-{key}"
        self._attr_name = f"{hostname} {SENSOR_TYPES[key]}"
        self._attr_device_info = device_info

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        if self._key == "uptime":
            return uptime_human(data.get("sysUpTime"))
        return data.get(self._key) or self._value


class DeviceInformationSensor(CoordinatorEntity, SensorEntity):
    """Consolidated Device Information sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:information-outline"

    def __init__(self, coordinator, entry, device_info: DeviceInfo, hostname: str, client: SwitchSnmpClient):
        super().__init__(coordinator)
        self._entry = entry
        self._client = client
        self._hostname = hostname
        self._attr_unique_id = f"{entry.entry_id}-device-info"
        self._attr_name = f"{hostname} Device Info"
        self._attr_device_info = device_info

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data or {}
        return data.get("sysName") or self._client.host

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        return {
            "Manufacturer": data.get("manufacturer") or self._client.cache.get("manufacturer") or "Unknown",
            "Model": data.get("model") or self._client.cache.get("model") or "Unknown",
            "Firmware Revision": data.get("firmware") or self._client.cache.get("firmware") or "Unknown",
            "Hostname": data.get("sysName") or self._client.cache.get("sysName") or self._client.host,
            "System Name": data.get("sysName") or self._client.cache.get("sysName") or "Unknown",
            "System Contact": data.get("sysContact") or self._client.cache.get("sysContact") or "Unknown",
            "System Location": data.get("sysLocation") or self._client.cache.get("sysLocation") or "Unknown",
        }
