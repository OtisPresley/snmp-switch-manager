from __future__ import annotations

import logging
from typing import Any, Dict, List

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .snmp import IANA_IFTYPE_SOFTWARE_LOOPBACK, IANA_IFTYPE_IEEE8023AD_LAG

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    node = hass.data[DOMAIN].get(entry.entry_id)
    if not node:
        _LOGGER.error("Switch setup: missing node for entry_id=%s", entry.entry_id)
        return
    coordinator = node["coordinator"]

    ports: List[Dict[str, Any]] = (coordinator.data or {}).get("ports", []) or []
    if not ports:
        _LOGGER.warning("No ports returned from coordinator yet")
        return

    entities: List[SwitchEntity] = []
    for p in ports:
        # Skip unconfigured LAGs (common nuisance)
        if int(p.get("iftype", 0)) == IANA_IFTYPE_IEEE8023AD_LAG and not p.get("alias"):
            continue
        entities.append(SwitchManagerPort(coordinator, entry, p))
    async_add_entities(entities)


class SwitchManagerPort(CoordinatorEntity, SwitchEntity):
    _attr_icon = "mdi:ethernet"

    def __init__(self, coordinator, entry: ConfigEntry, port: Dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._index = int(port["index"])
        self._iftype = int(port.get("iftype", 0))
        self._name_raw = port.get("name", "")
        self._alias = port.get("alias", "")
        self._attr_unique_id = f"{entry.entry_id}-port-{self._index}"
        self._attr_name = self._friendly_name(self._name_raw, self._iftype, self._index)

    @staticmethod
    def _friendly_name(descr: str, iftype: int, index: int) -> str:
        text = descr or ""
        lower = text.lower()
        # VLANs like "Vl11"
        if lower.startswith("vl"):
            return text.upper()
        # loopback
        if iftype == IANA_IFTYPE_SOFTWARE_LOOPBACK or "loopback" in lower:
            return "Lo0"
        # 1G / 10G common patterns
        if "gigabit" in lower or lower.startswith("gi"):
            # try to keep Gi1/0/46 style if present in description
            return "Gi" + "".join(ch for ch in text if ch.isdigit() or ch in "/")
        if "20g" in lower or "tengig" in lower or lower.startswith("te"):
            return "Te" + "".join(ch for ch in text if ch.isdigit() or ch in "/")
        if "port-channel" in lower or lower.startswith("po"):
            return "Po" + "".join(ch for ch in text if ch.isdigit())
        # fallback
        return text or f"Port {index}"

    @property
    def is_on(self) -> bool:
        state = int(self._port_data.get("oper", 0))
        return state == 1

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        attrs = {
            "Index": self._index,
            "Name": self._name_raw,
            "Alias": self._port_data.get("alias", ""),
            "Admin": int(self._port_data.get("admin", 0)),
            "Oper": int(self._port_data.get("oper", 0)),
        }
        ip = self._port_data.get("ip") or self._port_data.get("ip_address")
        if ip:
            attrs["IP address"] = ip
        return attrs

    # ------------- internals -------------

    @property
    def _port_data(self) -> Dict[str, Any]:
        ports: List[Dict[str, Any]] = (self.coordinator.data or {}).get("ports", []) or []
        for p in ports:
            if int(p.get("index", -1)) == self._index:
                return p
        return {}

