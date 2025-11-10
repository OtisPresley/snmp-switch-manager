from __future__ import annotations

import logging
import re
import ipaddress
from typing import Any, Dict, List

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _resolve_coordinator(hass, entry):
    dom: Dict[str, Any] | None = hass.data.get(DOMAIN)
    if isinstance(dom, dict) and "entries" in dom:
        entries = dom.get("entries")
        if isinstance(entries, dict):
            node = entries.get(entry.entry_id)
            if node is not None:
                if isinstance(node, dict) and "coordinator" in node:
                    return node["coordinator"]
                if hasattr(node, "async_request_refresh") and hasattr(node, "data"):
                    return node
    if isinstance(dom, dict):
        node = dom.get(entry.entry_id)
        if node is not None:
            if isinstance(node, dict) and "coordinator" in node:
                return node["coordinator"]
            if hasattr(node, "async_request_refresh") and hasattr(node, "data"):
                return node
        if "coordinator" in dom and hasattr(dom["coordinator"], "async_request_refresh"):
            return dom["coordinator"]
    runtime = getattr(entry, "runtime_data", None)
    if runtime is not None:
        if hasattr(runtime, "async_request_refresh") and hasattr(runtime, "data"):
            return runtime
        if hasattr(runtime, "coordinator"):
            return getattr(runtime, "coordinator")
    _LOGGER.error("Could not resolve coordinator for entry_id=%s", entry.entry_id)
    raise KeyError(entry.entry_id)


_VLAN_PATTERNS = (
    r"\bVlan\s*([0-9]+)\b",
    r"\bVLAN\s*([0-9]+)\b",
    r"\bVl([0-9]+)\b",
    r"^\s*V([0-9]+)\s*$",
)


def _detect_vlan_id(text: str) -> int | None:
    for pat in _VLAN_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return None
    return None


def _short_intf_name(long_name: str, alias: str) -> str | None:
    """Return friendly short name, including VLAN/loopback logic."""
    name = long_name or ""
    alt = alias or ""

    # VLANs
    vid = _detect_vlan_id(name)
    if vid is None and alt:
        vid = _detect_vlan_id(alt)
    if vid is not None:
        return name.strip() if name.strip() else f"Vl{vid}"

    # Loopback
    if "software loopback" in name.lower() or "loopback" in name.lower():
        return "Lo0"

    # Port-channels (aggregates)
    if "port-channel" in name.lower() or "link aggregate" in name.lower():
        m = re.search(r"(\d+)", name)
        if m:
            return f"Po{m.group(1)}"
        return "Po"

    # Physicals
    m = re.search(r"Unit:\s*(\d+)\s+Slot:\s*(\d+)\s+Port:\s*(\d+)\s+(.*)", name)
    if not m:
        return None
    unit, slot, port, tail = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
    t = tail.lower()
    if "20g" in t or "20 g" in t:
        itype = "Tw"
    elif "10g" in t or "ten" in t or "tengig" in t or "ten-gig" in t or "ten gig" in t:
        itype = "Te"
    elif "fast" in t or "100m" in t:
        itype = "Fa"
    else:
        itype = "Gi"
    return f"{itype}{unit}/{slot}/{port}"


def _should_exclude(name: str, alias: str, include: List[str], exclude: List[str]) -> bool:
    """Exclude CPU or link-aggregates; allow loopback."""
    text = f"{name} {alias}".lower()
    if "cpu" in text:
        return True
    if include and not any(pat.lower() in text for pat in include):
        return True
    if exclude and any(pat.lower() in text for pat in exclude):
        return True
    return False


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = _resolve_coordinator(hass, entry)
    ports = coordinator.data.get("ports", {})

    include_opt = (entry.options.get("include") or "").strip()
    exclude_opt = (entry.options.get("exclude") or "").strip()
    include = [s.strip() for s in (include_opt.split(",") if include_opt else [])]
    exclude = [s.strip() for s in (exclude_opt.split(",") if exclude_opt else [])]

    entities: list[SwitchManagerPort] = []
    iterable = ports.values() if isinstance(ports, dict) else ports
    seen_indices: set[int] = set()

    for port in iterable:
        if not isinstance(port, dict):
            continue
        idx = int(port.get("index", 0))
        if idx in seen_indices:
            continue
        seen_indices.add(idx)

        name = str(port.get("name") or "")
        alias = str(port.get("alias") or "")

        if _should_exclude(name, alias, include, exclude):
            continue

        short = _short_intf_name(name, alias)
        friendly = short or (alias if alias else f"Port {idx}")
        entities.append(SwitchManagerPort(coordinator, entry, idx, friendly))

    async_add_entities(entities)


class SwitchManagerPort(CoordinatorEntity, SwitchEntity):
    _attr_should_poll = False

    def __init__(self, coordinator, entry, port_index: int, friendly_name: str):
        super().__init__(coordinator)
        self._entry = entry
        self._port_index = port_index
        self._attr_unique_id = f"{entry.entry_id}_{port_index}"
        self._attr_name = friendly_name

    @property
    def device_info(self) -> Dict[str, Any]:
        sysinfo = self.coordinator.data.get("system", {}) if hasattr(self.coordinator, "data") else {}
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": sysinfo.get("hostname") or (self._entry.title or "Switch"),
            "manufacturer": sysinfo.get("manufacturer"),
            "model": sysinfo.get("model"),
            "sw_version": sysinfo.get("firmware"),
        }

    @property
    def is_on(self) -> bool:
        ports = self.coordinator.data.get("ports", {})
        port = ports.get(self._port_index) if isinstance(ports, dict) else None
        if isinstance(port, dict):
            return port.get("admin") == 1
        return False

    async def async_turn_on(self, **kwargs) -> None:
        client = getattr(self.coordinator, "client", None)
        if client is None:
            return
        await client.async_set_octet_string(f"1.3.6.1.2.1.2.2.1.7.{self._port_index}", 1)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        client = getattr(self.coordinator, "client", None)
        if client is None:
            return
        await client.async_set_octet_string(f"1.3.6.1.2.1.2.2.1.7.{self._port_index}", 2)
        await self.coordinator.async_request_refresh()

    @staticmethod
    def _cidrs_from_ipv4_list(records: List[Dict[str, str]]) -> List[str]:
        out: List[str] = []
        for rec in records or []:
            addr = str(rec.get("address", ""))
            mask = str(rec.get("netmask", ""))
            try:
                prefix = ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen
                out.append(f"{ipaddress.IPv4Address(addr)}/{prefix}")
            except Exception:
                continue
        return out

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Only port-centric attributes (no system-level fields)."""
        ports = self.coordinator.data.get("ports", {})
        port = ports.get(self._port_index) if isinstance(ports, dict) else None

        attrs: dict[str, Any] = {}
        if isinstance(port, dict):
            attrs.update({
                "index": port.get("index", self._port_index),
                "name": port.get("name"),
                "alias": port.get("alias"),
                "admin": port.get("admin"),
                "oper": port.get("oper"),
            })

            ipv4 = port.get("ipv4") or []
            if ipv4:
                first = ipv4[0] or {}
                if first.get("address"):
                    attrs["ip_address"] = first.get("address")
                if first.get("netmask"):
                    attrs["netmask"] = first.get("netmask")
            cidrs = self._cidrs_from_ipv4_list(ipv4)
            if cidrs:
                attrs["ip_cidr_primary"] = cidrs[0]
                attrs["ipv4_cidrs"] = cidrs

        return attrs
