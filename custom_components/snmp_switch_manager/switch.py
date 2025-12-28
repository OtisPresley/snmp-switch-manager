from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    CONF_PORT_RENAME_USER_RULES,
    CONF_PORT_RENAME_DISABLED_DEFAULT_IDS,
    DEFAULT_PORT_RENAME_RULES,
    CONF_INCLUDE_STARTS_WITH,
    CONF_INCLUDE_CONTAINS,
    CONF_INCLUDE_ENDS_WITH,
    CONF_EXCLUDE_STARTS_WITH,
    CONF_EXCLUDE_CONTAINS,
    CONF_EXCLUDE_ENDS_WITH,
    CONF_DISABLED_VENDOR_FILTER_RULE_IDS,
)
from .snmp import SwitchSnmpClient
from .helpers import format_interface_name

_LOGGER = logging.getLogger(__name__)


def _format_bps(bps: Any) -> str:
    """Format an integer bits-per-second value into a human-friendly string."""
    try:
        v = int(bps)
    except Exception:
        return "Unknown"
    if v <= 0:
        return "Unknown"
    if v >= 1_000_000_000:
        g = v / 1_000_000_000
        return f"{g:g} Gbps"
    if v >= 1_000_000:
        m = v / 1_000_000
        return f"{m:g} Mbps"
    if v >= 1_000:
        k = v / 1_000
        return f"{k:g} Kbps"
    return f"{v} bps"

ADMIN_STATE = {1: "Up", 2: "Down", 3: "Testing"}
OPER_STATE = {
    1: "Up",
    2: "Down",
    3: "Testing",
    4: "Unknown",
    5: "Dormant",
    6: "NotPresent",
    7: "LowerLayerDown",
}


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    client: SwitchSnmpClient = data["client"]
    coordinator = data["coordinator"]

    entities: list[IfAdminSwitch] = []
    desired_if_indexes: set[int] = set()
    iftable = client.cache.get("ifTable", {})
    hostname = client.cache.get("sysName") or entry.data.get("name") or client.host

    device_info = DeviceInfo(
        identifiers={(DOMAIN, f"{client.host}:{client.port}:{client.community}")},
        name=hostname,
    )

    ip_index = client.cache.get("ipIndex", {})
    ip_mask = client.cache.get("ipMask", {})

    def _build_port_rename_rules() -> list[tuple[str, re.Pattern[str], str]]:
        """Return ordered (id, compiled_regex, replace) rules for this entry."""
        rules: list[tuple[str, re.Pattern[str], str]] = []

        disabled = set(entry.options.get(CONF_PORT_RENAME_DISABLED_DEFAULT_IDS) or [])

        # User rules first (highest priority)
        for i, r in enumerate(entry.options.get(CONF_PORT_RENAME_USER_RULES) or []):
            try:
                pattern = str(r.get("pattern") or "").strip()
                replace = str(r.get("replace") or "")
                if not pattern:
                    continue
                rules.append((f"user_{i}", re.compile(pattern, re.IGNORECASE), replace))
            except Exception:
                # Ignore invalid user rules (they should be validated in the UI)
                continue

        # Built-in defaults next
        for r in DEFAULT_PORT_RENAME_RULES:
            rid = r.get("id") or ""
            if not rid or rid in disabled:
                continue
            try:
                pattern = str(r.get("pattern") or "").strip()
                replace = str(r.get("replace") or "")
                if not pattern:
                    continue
                rules.append((rid, re.compile(pattern, re.IGNORECASE), replace))
            except Exception:
                continue

        return rules

    port_rename_rules = _build_port_rename_rules()

    # Include/Exclude interface rules (simple string match; include wins over exclude)
    include_starts = [str(s).strip().lower() for s in (entry.options.get(CONF_INCLUDE_STARTS_WITH, []) or []) if str(s).strip()]
    include_contains = [str(s).strip().lower() for s in (entry.options.get(CONF_INCLUDE_CONTAINS, []) or []) if str(s).strip()]
    include_ends = [str(s).strip().lower() for s in (entry.options.get(CONF_INCLUDE_ENDS_WITH, []) or []) if str(s).strip()]

    exclude_starts = [str(s).strip().lower() for s in (entry.options.get(CONF_EXCLUDE_STARTS_WITH, []) or []) if str(s).strip()]
    exclude_contains = [str(s).strip().lower() for s in (entry.options.get(CONF_EXCLUDE_CONTAINS, []) or []) if str(s).strip()]
    exclude_ends = [str(s).strip().lower() for s in (entry.options.get(CONF_EXCLUDE_ENDS_WITH, []) or []) if str(s).strip()]

    any_include_rules = bool(include_starts or include_contains or include_ends)

    disabled_vendor_filter_ids = set(entry.options.get(CONF_DISABLED_VENDOR_FILTER_RULE_IDS, []) or [])

    def _matches_any(name_l: str, starts: list[str], contains: list[str], ends: list[str]) -> bool:
        return (
            any(name_l.startswith(x) for x in starts)
            or any(x in name_l for x in contains)
            or any(name_l.endswith(x) for x in ends)
        )

    def _apply_port_rename(display_name: str) -> str:
        """Apply the first matching rename rule to the base display name."""
        if not display_name or not port_rename_rules:
            return display_name
        for _rid, rx, rep in port_rename_rules:
            if rx.search(display_name):
                try:
                    return rx.sub(rep, display_name, count=1)
                except Exception:
                    return display_name
        return display_name

    # Vendor detection
    manufacturer = (client.cache.get("manufacturer") or "").lower()
    sys_descr = (client.cache.get("sysDescr") or "").lower()

    # Cisco SG family
    is_cisco_sg = manufacturer.startswith("sg") and sys_descr.startswith("sg")

    # Detect Junos / Juniper EX series
    manufacturer = (client.cache.get("manufacturer") or "").lower()
    sys_descr = (client.cache.get("sysDescr") or "").lower()
    is_junos = "juniper" in manufacturer or "junos" in sys_descr or "ex2200" in sys_descr

    for idx, row in sorted(iftable.items()):
        raw_name = row.get("name") or row.get("descr") or f"if{idx}"
        alias = row.get("alias") or ""

        # Skip internal CPU pseudo-interface
        if raw_name.strip().upper() == "CPU":
            continue

        lower = (raw_name or "").lower()
        ip_str = _ip_for_index(idx, ip_index, ip_mask)

        name_l = (raw_name or "").strip().lower()
        include_hit = _matches_any(name_l, include_starts, include_contains, include_ends)
        exclude_hit = _matches_any(name_l, exclude_starts, exclude_contains, exclude_ends)

        # Exclude rules always win.
        if exclude_hit:
            continue

        # If include rules exist, only matching interfaces are created.
        if any_include_rules and not include_hit:
            continue

        is_port_channel = (
            lower.startswith("po")
            or lower.startswith("port-channel")
            or lower.startswith("link aggregate")
        )
        if is_port_channel and not (ip_str or alias):
            # Only create PortChannel entity if configured (alias or IP present)
            continue

        # Get interface details
        name = raw_name.strip()
        lower_name = name.lower()
        admin = row.get("admin")
        oper = row.get("oper")
        has_ip = bool(ip_str)
        include = False
        

        # Cisco SG interface selection rules (can disable individual built-in rules)
        if is_cisco_sg:
            enable_physical = "cisco_sg_physical_fa_gi" not in disabled_vendor_filter_ids
            enable_vlan = "cisco_sg_vlan_admin_or_oper" not in disabled_vendor_filter_ids
            enable_has_ip = "cisco_sg_other_has_ip" not in disabled_vendor_filter_ids

            if enable_physical or enable_vlan or enable_has_ip:
                name = raw_name.strip()
                lower_name = name.lower()
                admin = row.get("admin")
                oper = row.get("oper")
                has_ip = bool(ip_str)
                include = False

                if enable_physical and (lower_name.startswith("fa") or lower_name.startswith("gi")):
                    include = True

                elif enable_vlan and lower_name.startswith("vlan"):
                    if oper == 1 or admin == 2:
                        include = True

                elif enable_has_ip and has_ip:
                    include = True

                if not include and not include_hit:
                    continue



        # Junos (e.g. EX2200) interface selection rules (can disable individual built-in rules)
        if is_junos:
            enable_physical = "junos_physical_ge" not in disabled_vendor_filter_ids
            enable_l3_subif = "junos_l3_subif_has_ip" not in disabled_vendor_filter_ids
            enable_vlan = "junos_vlan_admin_or_oper" not in disabled_vendor_filter_ids
            enable_has_ip = "junos_other_has_ip" not in disabled_vendor_filter_ids

            if enable_physical or enable_l3_subif or enable_vlan or enable_has_ip:
                name = raw_name.strip()
                lower_name = name.lower()
                admin = row.get("admin")
                oper = row.get("oper")
                has_ip = bool(ip_str)
                include = False

                # 1) Physical front-panel ports: ge-0/0/X (no subinterface suffix)
                if enable_physical and lower_name.startswith("ge-") and "." not in name:
                    include = True

                # 2) L3 subinterfaces: ge-0/0/X.Y – only keep non-.0 with an IP address
                elif enable_l3_subif and lower_name.startswith("ge-") and "." in name:
                    base, sub = name.split(".", 1)
                    if sub != "0" and has_ip:
                        include = True

                # 3) VLAN interfaces that are operationally up or administratively disabled
                elif enable_vlan and lower_name.startswith("vlan"):
                    if oper == 1 or admin == 2:
                        include = True

                # 4) Any other non-physical interface with an IP address configured
                elif enable_has_ip and has_ip:
                    include = True

                if not include and not include_hit:
                    continue


                # Apply per-device port rename rules to the *raw* interface name first.
        # This allows rules to match vendor-specific raw strings (e.g. "Unit: ...") before any normalization.
        # _apply_port_rename() closes over port_rename_rules
        raw_for_display = _apply_port_rename((raw_name or "").strip())

# Try to parse Gi1/0/1 style to preserve unit/slot/port in display name
        unit = 1
        slot = 0
        port = None
        try:
            # e.g., "Gi1/0/1" -> parts after the first two letters
            if "/" in raw_for_display and raw_for_display[2:3].isdigit():
                parts = raw_for_display[2:].split("/")
                if len(parts) >= 3:
                    unit = int(parts[0])
                    slot = int(parts[1])
                    port = int(parts[2])
        except Exception:
            pass

        display = format_interface_name(raw_for_display, unit=unit, slot=slot, port=port)
        display = _apply_port_rename(display)

        entities.append(
            IfAdminSwitch(
                coordinator=coordinator,
                entry_id=entry.entry_id,
                if_index=idx,
                raw_name=raw_name,
                display_name=display,
                alias=alias,
                hostname=hostname,
                device_info=device_info,
                client=client,
            )
        )

        desired_if_indexes.add(idx)

    # Remove any previously-created switch entities that are no longer desired
    # (e.g. excluded by user rules). Without this, Home Assistant keeps the old
    # entities around even if we stop creating them.
    ent_reg = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if ent.domain != "switch":
            continue
        if not (ent.unique_id or "").startswith(f"{entry.entry_id}-if-"):
            continue
        try:
            old_idx = int((ent.unique_id or "").split("-if-", 1)[1])
        except Exception:
            continue
        if old_idx not in desired_if_indexes:
            ent_reg.async_remove(ent.entity_id)

    async_add_entities(entities)

def _ip_for_index(if_index: int, ip_index: Dict[str, int], ip_mask: Dict[str, str]) -> Optional[str]:
    """Return IP/maskbits string for an ifIndex if present."""
    for ip, idx in ip_index.items():
        if idx == if_index:
            mask = ip_mask.get(ip)
            if not mask:
                return ip
            try:
                import ipaddress

                net = ipaddress.IPv4Network((ip, mask), strict=False)
                return f"{ip}/{net.prefixlen}"
            except Exception:
                return ip
    return None


class IfAdminSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(
        self,
        coordinator,
        entry_id: str,
        if_index: int,
        raw_name: str,
        display_name: str,
        alias: str,
        hostname: str,
        device_info: DeviceInfo,
        client: SwitchSnmpClient,
    ):
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._if_index = if_index
        self._raw_name = raw_name
        self._display = display_name
        self._alias = alias
        self._hostname = hostname
        self._client = client

        self._attr_unique_id = f"{entry_id}-if-{if_index}"
        # Name includes hostname so entity_id becomes e.g. switch.switch1_gi1_0_1
        self._attr_name = f"{hostname} {display_name}"
        self._attr_device_info = device_info

    @property
    def is_on(self) -> bool:
        row = self.coordinator.data.get("ifTable", {}).get(self._if_index, {})
        return row.get("admin") == 1

    async def async_turn_on(self, **kwargs):
        ok = await self._client.set_admin_status(self._if_index, 1)
        if ok:
            self.coordinator.data["ifTable"].setdefault(self._if_index, {})["admin"] = 1
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        ok = await self._client.set_admin_status(self._if_index, 2)
        if ok:
            self.coordinator.data["ifTable"].setdefault(self._if_index, {})["admin"] = 2
            self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        row = self.coordinator.data.get("ifTable", {}).get(self._if_index, {})
        attrs: Dict[str, Any] = {
            "Index": self._if_index,
            "Name": self._display,
            "Alias": row.get("alias") or "",
            "Admin": ADMIN_STATE.get(row.get("admin", 0), "Unknown"),
            "Oper": OPER_STATE.get(row.get("oper", 0), "Unknown"),
            "Speed": _format_bps(row.get("speed_bps")),
        }

        vlan_id = row.get("vlan_id")
        if vlan_id is not None:
            try:
                vlan_int = int(vlan_id)
            except Exception:
                vlan_int = None
            if vlan_int:
                attrs["VLAN ID"] = vlan_int
        ip = _ip_for_index(
            self._if_index,
            self.coordinator.data.get("ipIndex", {}),
            self.coordinator.data.get("ipMask", {}),
        )
        if ip:
            attrs["IP"] = ip
        return attrs
