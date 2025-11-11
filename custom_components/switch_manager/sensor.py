
from __future__ import annotations

from datetime import timedelta
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

    sysdescr = client.cache.get("sysDescr") or ""
    manufacturer = sysdescr.split()[0] if sysdescr else "Unknown"
    model = None
    firmware = None
    if sysdescr:
        parts = sysdescr.split()
        if len(parts) >= 2:
            model = parts[1]
        if "Version" in parts:
            try:
                firmware = parts[parts.index("Version")+1]
            except Exception:
                pass

    hostname = client.cache.get("sysName")
    uptime_ticks = client.cache.get("sysUpTime")
    uptime_human = None
    try:
        ticks = int(uptime_ticks)
        seconds = ticks // 100
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        uptime_human = f"{days}d {hours}h {minutes}m {seconds}s"
    except Exception:
        uptime_human = str(uptime_ticks) if uptime_ticks is not None else None

    device_info = DeviceInfo(
        identifiers={(DOMAIN, f"{client.host}:{client.port}:{client.community}")},
        manufacturer=manufacturer or None,
        model=model or None,
        sw_version=firmware or None,
        name=hostname or entry.data.get("name") or client.host,
    )

    entities = [
        SimpleTextSensor(coordinator, entry, "manufacturer", manufacturer or "Unknown", device_info),
        SimpleTextSensor(coordinator, entry, "model", model or "Unknown", device_info),
        SimpleTextSensor(coordinator, entry, "firmware", firmware or "Unknown", device_info),
        SimpleTextSensor(coordinator, entry, "uptime", uptime_human or "Unknown", device_info),
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
                ticks = int(ticks)
                seconds = ticks // 100
                d, r = divmod(seconds, 86400)
                h, r = divmod(r, 3600)
                m, s = divmod(r, 60)
                return f"{d}d {h}h {m}m {s}s"
            except Exception:
                return str(ticks)
        if self._key == "manufacturer":
            sysdescr = data.get("sysDescr") or ""
            return (sysdescr.split()[0] if sysdescr else self._value)
        if self._key == "model":
            sysdescr = data.get("sysDescr") or ""
            parts = sysdescr.split()
            return (parts[1] if len(parts) >= 2 else self._value)
        if self._key == "firmware":
            sysdescr = data.get("sysDescr") or ""
            parts = sysdescr.split()
            if "Version" in parts:
                try:
                    return parts[parts.index("Version")+1]
                except Exception:
                    pass
            return self._value
        return self._value
