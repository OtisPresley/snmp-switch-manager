from __future__ import annotations

import logging
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import SensorEntity

from .const import DOMAIN
from .snmp import SwitchSnmpClient

_LOGGER = logging.getLogger(__name__)

SENSOR_TYPES = {
    "manufacturer": "Manufacturer",
    "model": "Model",
    "firmware": "Firmware Revision",
    "uptime": "Uptime",
    "hostname": "Hostname",
}

async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    client: SwitchSnmpClient = data["client"]
    coordinator = data["coordinator"]

    # Prefer parsed values placed in cache by snmp.py
    manufacturer = client.cache.get("manufacturer") or "Unknown"
    model = client.cache.get("model") or "Unknown"
    firmware = client.cache.get("firmware") or "Unknown"

    hostname = client.cache.get("sysName")
    uptime_ticks = client.cache.get("sysUpTime")

    # Convert sysUpTime (hundredths of seconds) to human string
    def _uptime_human(ticks):
        try:
            t = int(ticks)
            sec = t // 100
            d, r = divmod(sec, 86400)
            h, r = divmod(r, 3600)
            m, s = divmod(r, 60)
            return f"{d}d {h}h {m}m {s}s"
        except Exception:
            return str(ticks) if ticks is not None else "Unknown"

    device_info = DeviceInfo(
        identifiers={(DOMAIN, f"{client.host}:{client.port}:{client.community}")},
        manufacturer=manufacturer if manufacturer != "Unknown" else None,
        model=model if model != "Unknown" else None,
        sw_version=firmware if firmware != "Unknown" else None,
        name=hostname or entry.data.get("name") or client.host,
    )

    entities = [
        SimpleTextSensor(coordinator, entry, "manufacturer", manufacturer, device_info),
        SimpleTextSensor(coordinator, entry, "model", model, device_info),
        SimpleTextSensor(coordinator, entry, "firmware", firmware, device_info),
        SimpleTextSensor(coordinator, entry, "uptime", _uptime_human(uptime_ticks), device_info),
        SimpleTextSensor(coordinator, entry, "hostname", hostname or client.host, device_info),
    ]
    async_add_entities(entities)


class SimpleTextSensor(CoordinatorEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, key, value, device_info: DeviceInfo):
        super().__init__(coordinator)
        self._key = key
        self._value = value
        self._attr_unique_id = f"{entry.entry_id}-{key}"
        self._attr_name = SENSOR_TYPES[key]
        self._attr_device_info = device_info

    @property
    def native_value(self):
        data = self.coordinator.data
        if self._key == "hostname":
            return data.get("sysName") or self._value
        if self._key == "uptime":
            ticks = data.get("sysUpTime")
            try:
                t = int(ticks)
                sec = t // 100
                d, r = divmod(sec, 86400)
                h, r = divmod(r, 3600)
                m, s = divmod(r, 60)
                return f"{d}d {h}h {m}m {s}s"
            except Exception:
                return str(ticks)
        # prefer parsed cache values if present
        if self._key == "manufacturer":
            return data.get("manufacturer") or self._value
        if self._key == "model":
            return data.get("model") or self._value
        if self._key == "firmware":
            return data.get("firmware") or self._value
        return self._value
