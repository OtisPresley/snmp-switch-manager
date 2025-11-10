from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import Any, Dict, Optional

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# --- helpers -----------------------------------------------------------------

_FW_RE = re.compile(r",\s*([0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?)\b")
_MODEL_RE = re.compile(r'^([\w\s\-&]+?\bN[0-9A-Za-z\-]+)\b')

def _parse_sysdescr(sysdescr: str) -> Dict[str, Optional[str]]:
    """
    Very forgiving parser:
      Dell example: "Dell EMC Networking N3048EP-ON, 6.7.1.31, Linux 4.14.174, v1.0.5"
    We try to pull:
      model ("Dell EMC Networking N3048EP-ON")
      firmware ("6.7.1.31")
    """
    model = None
    fw = None

    m = _MODEL_RE.search(sysdescr.strip())
    if m:
        model = m.group(1).strip()

    m = _FW_RE.search(sysdescr)
    if m:
        fw = m.group(1).strip()

    return {"model": model, "firmware": fw}


def _timeticks_to_seconds(ticks: str) -> Optional[int]:
    # ticks can be "Timeticks: (341184840) 39 days, 11:44:08.40" or just an integer string
    try:
        if " " in ticks and "(" in ticks and ")" in ticks:
            # extract number in parentheses
            inner = ticks.split("(")[1].split(")")[0]
            return int(inner)
        # otherwise assume raw seconds or timeticks already numeric
        return int(ticks)
    except Exception:
        return None


# --- setup -------------------------------------------------------------------

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    dom = hass.data.get(DOMAIN, {})
    node = (dom.get("entries") or {}).get(entry.entry_id) or dom.get(entry.entry_id)
    if not node:
        _LOGGER.debug("sensor.py: no node for entry_id=%s yet; delaying add", entry.entry_id)
        return

    coordinator = node["coordinator"]
    device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=(coordinator.data.get("system") or {}).get("sysName") or entry.title,
    )

    async_add_entities(
        [
            _FirmwareSensor(coordinator, entry, device_info),
            _HostnameSensor(coordinator, entry, device_info),
            _ModelSensor(coordinator, entry, device_info),
            _UptimeSensor(coordinator, entry, device_info),
        ],
        True,
    )


# --- entities ----------------------------------------------------------------

class _BaseSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry, device_info: DeviceInfo) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = device_info


class _FirmwareSensor(_BaseSensor):
    _attr_name = "Firmware Rev"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_firmware"

    @property
    def native_value(self) -> Optional[str]:
        sys_descr = (self.coordinator.data.get("system") or {}).get("sysDescr") or ""
        return _parse_sysdescr(sys_descr).get("firmware")


class _HostnameSensor(_BaseSensor):
    _attr_name = "Hostname"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_hostname"

    @property
    def native_value(self) -> Optional[str]:
        return (self.coordinator.data.get("system") or {}).get("sysName") or None


class _ModelSensor(_BaseSensor):
    _attr_name = "Manufacturer & Model"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_model"

    @property
    def native_value(self) -> Optional[str]:
        sys_descr = (self.coordinator.data.get("system") or {}).get("sysDescr") or ""
        return _parse_sysdescr(sys_descr).get("model")


class _UptimeSensor(_BaseSensor):
    _attr_name = "Uptime"
    _attr_device_class = SensorDeviceClass.DURATION

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_uptime"

    @property
    def native_unit_of_measurement(self) -> str:
        # seconds so HA can render human-friendly durations
        return "s"

    @property
    def native_value(self) -> Optional[int]:
        ticks = (self.coordinator.data.get("system") or {}).get("sysUpTime")
        if not ticks:
            return None
        return _timeticks_to_seconds(ticks)
