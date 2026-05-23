from __future__ import annotations

import ipaddress
import logging
from typing import Any, Dict, Optional

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers import entity_registry as er

from ..const import (
    DOMAIN,
    CONF_LEGACY_DEVICE_ID,
    CONF_ICON_RULES,
    CONF_INCLUDE_STARTS_WITH,
    CONF_INCLUDE_CONTAINS,
    CONF_INCLUDE_ENDS_WITH,
    CONF_EXCLUDE_STARTS_WITH,
    CONF_EXCLUDE_CONTAINS,
    CONF_EXCLUDE_ENDS_WITH,
    CONF_DISABLED_VENDOR_FILTER_RULE_IDS,
    CONF_POE_CONTROL_LOOPS,
)
from ..snmp import SwitchSnmpClient
from ..helpers import format_interface_name, check_interface_filter_rules
from .admin import IfAdminSwitch
from .poe import PoePortSwitch

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = entry.runtime_data
    client: SwitchSnmpClient = runtime.client
    coordinator = runtime.coordinator

    entities: list[Any] = []
    desired_if_indexes: set[int] = set()
    display_names: dict[int, str] = {}
    iftable = client.cache.get("ifTable", {})
    hostname = client.cache.get("sysName") or entry.data.get("name") or client.host

    # Device identifiers must be stable.
    identifiers = {(DOMAIN, entry.entry_id)}
    legacy_device_id = str(
        entry.data.get(CONF_LEGACY_DEVICE_ID) or entry.options.get(CONF_LEGACY_DEVICE_ID) or ""
    ).strip()
    if legacy_device_id:
        identifiers.add((DOMAIN, legacy_device_id))

    device_info = DeviceInfo(identifiers=identifiers, name=hostname)

    ip_index = client.cache.get("ipIndex", {})
    ip_mask = client.cache.get("ipMask", {})

    ip_by_ifindex = {}
    for ip, idx in ip_index.items():
        try:
            ip_by_ifindex[int(idx)] = ip
        except Exception:
            pass

    # Include/Exclude interface rules (simple string match; include wins over exclude)
    include_starts = tuple(str(s).strip().lower() for s in (entry.options.get(CONF_INCLUDE_STARTS_WITH, []) or []) if str(s).strip())
    include_contains = [str(s).strip().lower() for s in (entry.options.get(CONF_INCLUDE_CONTAINS, []) or []) if str(s).strip()]
    include_ends = tuple(str(s).strip().lower() for s in (entry.options.get(CONF_INCLUDE_ENDS_WITH, []) or []) if str(s).strip())

    exclude_starts = tuple(str(s).strip().lower() for s in (entry.options.get(CONF_EXCLUDE_STARTS_WITH, []) or []) if str(s).strip())
    exclude_contains = [str(s).strip().lower() for s in (entry.options.get(CONF_EXCLUDE_CONTAINS, []) or []) if str(s).strip()]
    exclude_ends = tuple(str(s).strip().lower() for s in (entry.options.get(CONF_EXCLUDE_ENDS_WITH, []) or []) if str(s).strip())

    any_include_rules = bool(include_starts or include_contains or include_ends)

    disabled_vendor_filter_ids = set(entry.options.get(CONF_DISABLED_VENDOR_FILTER_RULE_IDS, []) or [])

    icon_rules = entry.options.get(CONF_ICON_RULES, []) or []

    def _matches_any(name_l: str, starts: tuple[str, ...], contains: list[str], ends: tuple[str, ...]) -> bool:
        if starts and name_l.startswith(starts):
            return True
        if ends and name_l.endswith(ends):
            return True
        if contains and any(x in name_l for x in contains):
            return True
        return False

    vendor = client.cache.get("vendor", "Unknown")
    manufacturer = client.cache.get("manufacturer") or ""
    sys_descr = client.cache.get("sysDescr") or ""
    db_filters = client._database if hasattr(client, "_database") else None

    for idx, row in sorted(iftable.items()):
        raw_name = row.get("display_name") or row.get("name") or row.get("descr") or f"if{idx}"
        alias = row.get("alias") or ""

        normalized_name = (raw_name or "").strip().lower()
        ip_str = _ip_for_index(idx, ip_by_ifindex, ip_mask)

        include_hit = _matches_any(normalized_name, include_starts, include_contains, include_ends)
        exclude_hit = _matches_any(normalized_name, exclude_starts, exclude_contains, exclude_ends)

        # Exclude rules always win.
        if exclude_hit:
            continue

        # If include rules exist, only matching interfaces are created.
        if any_include_rules and not include_hit:
            continue

        is_port_channel = (
            (normalized_name.startswith("po") and not normalized_name.startswith("port"))
            or normalized_name.startswith("port-channel")
            or normalized_name.startswith("link aggregate")
        )
        if is_port_channel and not (ip_str or alias):
            keep_empty = False
            vendor_info = client._get_vendor_info() if hasattr(client, "_get_vendor_info") else {}
            kw = vendor_info.get("keep_empty_port_channels_if_keyword")
            if kw and (kw.lower() in (manufacturer or "").lower() or kw.lower() in (sys_descr or "").lower()):
                keep_empty = True
            if not keep_empty:
                continue

        admin = row.get("admin")
        oper = row.get("oper")
        has_ip = bool(ip_str)

        include, raw_name = check_interface_filter_rules(
            normalized_name=normalized_name,
            raw_name=raw_name,
            admin=admin,
            oper=oper,
            has_ip=has_ip,
            vendor=vendor,
            manufacturer=manufacturer,
            sys_descr=sys_descr,
            disabled_vendor_filter_ids=disabled_vendor_filter_ids,
            classification_db=db_filters,
        )

        if not include and not include_hit:
            continue

        raw_for_display = (raw_name or "").strip()

        # Try to parse Gi1/0/1 style to preserve unit/slot/port in display name
        unit = 1
        slot = 0
        port = None
        try:
            if "/" in raw_for_display and raw_for_display[2:3].isdigit():
                parts = raw_for_display[2:].split("/")
                if len(parts) >= 3:
                    unit = int(parts[0])
                    slot = int(parts[1])
                    port = int(parts[2])
        except Exception:
            pass

        db = client._database.get("interface_classification") if hasattr(client, "_database") else None
        display = format_interface_name(raw_for_display, unit=unit, slot=slot, port=port, classification_db=db)
        display_names[idx] = display

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
                icon_rules=icon_rules,
            )
        )

        desired_if_indexes.add(idx)

    # PoE Control Loops switches
    desired_poe_indexes: set[int] = set()
    poe_control_loops = entry.options.get(CONF_POE_CONTROL_LOOPS, False)
    if poe_control_loops:
        poe_ports = client.cache.get("poe_ports", {})
        for idx in desired_if_indexes:
            if idx in poe_ports:
                port_info = poe_ports[idx]
                group_idx = port_info.get("group")
                port_idx = port_info.get("port")
                if group_idx is not None and port_idx is not None:
                    row = iftable.get(idx, {})
                    raw_name = row.get("display_name") or row.get("name") or row.get("descr") or f"if{idx}"
                    entities.append(
                        PoePortSwitch(
                            coordinator=coordinator,
                            entry_id=entry.entry_id,
                            if_index=idx,
                            raw_name=raw_name,
                            display_name=display_names.get(idx, f"if{idx}"),
                            group_idx=group_idx,
                            port_idx=port_idx,
                            device_info=device_info,
                            client=client,
                            hostname=hostname,
                        )
                    )
                    desired_poe_indexes.add(idx)

    # Remove any previously-created switch entities that are no longer desired
    ent_reg = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if ent.domain != "switch":
            continue
        unique_id = ent.unique_id or ""
        if unique_id.startswith(f"{entry.entry_id}-if-"):
            try:
                old_idx = int(unique_id.split("-if-", 1)[1])
            except Exception:
                continue
            if old_idx not in desired_if_indexes:
                ent_reg.async_remove(ent.entity_id)
        elif unique_id.startswith(f"{entry.entry_id}-poe-"):
            try:
                old_idx = int(unique_id.split("-poe-", 1)[1])
            except Exception:
                continue
            if old_idx not in desired_poe_indexes:
                ent_reg.async_remove(ent.entity_id)

    async_add_entities(entities)


def _ip_for_index(if_index: int, ip_by_ifindex: Dict[int, str], ip_mask: Dict[str, str]) -> Optional[str]:
    """Return IP/maskbits string for an ifIndex if present."""
    ip = ip_by_ifindex.get(if_index)
    if not ip:
        return None
    mask = ip_mask.get(ip)
    if not mask:
        return ip
    try:
        mask_parts = [int(p) for p in mask.split(".")]
        if len(mask_parts) == 4:
            prefix_len = sum(bin(x).count('1') for x in mask_parts)
            return f"{ip}/{prefix_len}"
    except Exception:
        pass

    try:
        net = ipaddress.IPv4Network((ip, mask), strict=False)
        return f"{ip}/{net.prefixlen}"
    except Exception:
        return ip
