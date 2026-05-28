from __future__ import annotations
import asyncio
from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from ..snmp import SwitchSnmpClient

from ..const import (
    OID_ifIndex,
    OID_ifDescr,
    OID_ifName,
    OID_ifAlias,
    OID_ifSpeed,
    OID_ifHighSpeed,
    OID_ifType,
    OID_dot1dBasePortIfIndex,
    OID_dot1qPvid,
    OID_ifAdminStatus,
    OID_ifOperStatus,
    OID_dot1qVlanCurrentEgressPorts,
    OID_dot1qVlanCurrentUntaggedPorts,
    OID_dot1qVlanStaticEgressPorts,
    OID_dot1qVlanStaticUntaggedPorts,
    OID_ifConnectorPresent,
)

try:
    from ..helpers import (
        _parse_numeric,
        _decode_bridge_port_bitmap,
        classify_port_type,
    )
except ImportError:
    from custom_components.snmp_switch_manager.helpers import (
        _parse_numeric,
        _decode_bridge_port_bitmap,
        classify_port_type,
    )

async def poll_interfaces(client: SwitchSnmpClient, dynamic_only: bool = False) -> None:
    """Walk all interfaces and collect state."""
    if not dynamic_only:
        client.cache["ifTable"] = {}

        # Walk all static interface columns in parallel.
        (
            idx_rows,
            descr_rows,
            name_rows,
            alias_rows,
            iftype_rows,
            connector_rows,
        ) = await asyncio.gather(
            client._async_walk(OID_ifIndex),
            client._async_walk(OID_ifDescr),
            client._async_walk(OID_ifName),
            client._async_walk(OID_ifAlias),
            client._async_walk(OID_ifType),
            client._async_walk(OID_ifConnectorPresent),
        )

        # Indexes
        for oid, val in idx_rows:
            idx = int(oid.split(".")[-1])
            client.cache["ifTable"][idx] = {"index": idx}

        # Descriptions
        for oid, val in descr_rows:
            idx = int(oid.split(".")[-1])
            client.cache["ifTable"].setdefault(idx, {})["descr"] = str(val)

        # Names
        for oid, val in name_rows:
            idx = int(oid.split(".")[-1])
            client.cache["ifTable"].setdefault(idx, {})["name"] = str(val)

        # Aliases
        for oid, val in alias_rows:
            idx = int(oid.split(".")[-1])
            client.cache["ifTable"].setdefault(idx, {})["alias"] = str(val)

        # ifType (needed for port classification)
        for oid, val in iftype_rows:
            idx = int(oid.split(".")[-1])
            rec = client.cache["ifTable"].get(idx)
            if rec is not None:
                try:
                    rec["if_type"] = int(val)
                except Exception:
                    rec["if_type"] = None

        # ifConnectorPresent (standard hardware presence indicator)
        for oid, val in connector_rows:
            idx = int(oid.split(".")[-1])
            rec = client.cache["ifTable"].get(idx)
            if rec is not None:
                try:
                    # 1 = True (present/physical), 2 = False (absent/virtual)
                    rec["connector_present"] = int(val) == 1
                except Exception:
                    rec["connector_present"] = None

        # VLAN (PVID) mapping via BRIDGE-MIB / Q-BRIDGE-MIB
        bridge_ifindexes: set[int] = set()
        try:
            baseport_by_ifindex: Dict[int, int] = {}
            for oid, val in await client._async_walk(OID_dot1dBasePortIfIndex):
                try:
                    base_port = int(oid.split(".")[-1])
                except Exception:
                    continue
                try:
                    if_index = int(_parse_numeric(val))
                except Exception:
                    continue
                if if_index > 0 and base_port > 0:
                    baseport_by_ifindex[if_index] = base_port
                    bridge_ifindexes.add(if_index)
            client.cache["ifindex_by_baseport"] = {v: k for k, v in baseport_by_ifindex.items() if v and k}
            if baseport_by_ifindex:
                pvid_by_baseport: Dict[int, int] = {}
                for oid, val in await client._async_walk(OID_dot1qPvid):
                    try:
                        base_port = int(oid.split(".")[-1])
                    except Exception:
                        continue
                    try:
                        pvid = int(_parse_numeric(val))
                    except Exception:
                        continue
                    if pvid > 0:
                        pvid_by_baseport[base_port] = pvid

                allowed_by_baseport: Dict[int, set[int]] = {}
                untagged_by_baseport: Dict[int, set[int]] = {}

                async def _collect_vlan_portlists(oid_base: str, out: Dict[int, set[int]]) -> int:
                    count = 0
                    try:
                        rows = await asyncio.wait_for(client._async_walk(oid_base), timeout=30.0)
                    except asyncio.TimeoutError:
                        return count
                    for oid, val in rows:
                        try:
                            vlan_id = int(oid.split(".")[-1])
                        except Exception:
                            continue
                        if vlan_id <= 0:
                            continue
                        ports = _decode_bridge_port_bitmap(val)
                        if not ports:
                            continue
                        count += 1
                        for bp in ports:
                            out.setdefault(bp, set()).add(vlan_id)
                    return count

                try:
                    await _collect_vlan_portlists(OID_dot1qVlanCurrentEgressPorts, allowed_by_baseport)
                except Exception:
                    pass

                try:
                    await _collect_vlan_portlists(OID_dot1qVlanCurrentUntaggedPorts, untagged_by_baseport)
                except Exception:
                    pass

                # Fall back to static membership when current tables are not implemented.
                try:
                    await _collect_vlan_portlists(OID_dot1qVlanStaticEgressPorts, allowed_by_baseport)
                except Exception:
                    pass
                try:
                    await _collect_vlan_portlists(OID_dot1qVlanStaticUntaggedPorts, untagged_by_baseport)
                except Exception:
                    pass

                if pvid_by_baseport:
                    for if_index, base_port in baseport_by_ifindex.items():
                        rec = client.cache["ifTable"].setdefault(if_index, {})
                        pvid = pvid_by_baseport.get(base_port)

                        if pvid is not None:
                            rec["vlan_id"] = pvid
                            rec["native_vlan"] = pvid

                        allowed = sorted(allowed_by_baseport.get(base_port, set()))
                        if allowed:
                            rec["allowed_vlans"] = allowed

                        untagged = sorted(untagged_by_baseport.get(base_port, set()))
                        if untagged:
                            rec["untagged_vlans"] = untagged

                        tagged_set: set[int] = set()
                        if allowed:
                            if untagged:
                                tagged_set = set(allowed) - set(untagged)
                            elif pvid is not None:
                                tagged_set = set(allowed) - {pvid}
                            else:
                                tagged_set = set(allowed)

                        tagged = sorted(tagged_set)
                        if tagged:
                            rec["tagged_vlans"] = tagged

                        if (len(allowed) > 1) or bool(tagged):
                            rec["is_trunk"] = True

        except Exception:
            pass

        # Display name preference
        for idx, rec in list(client.cache["ifTable"].items()):
            existing = (rec.get("display_name") or "").strip()
            if existing:
                rec["display_name"] = existing
                continue
            nm = (rec.get("name") or "").strip()
            ds = (rec.get("descr") or "").strip()
            rec["display_name"] = nm or ds or f"ifIndex {idx}"

        for idx, rec in client.cache["ifTable"].items():
            if not isinstance(rec, dict):
                continue
            if_type = rec.get("if_type")
            name = str(rec.get("display_name") or rec.get("name") or rec.get("descr") or "")
            is_bridge_port = idx in bridge_ifindexes
            rec["port_type"] = classify_port_type(
                if_type=if_type,
                name=name,
                is_bridge_port=is_bridge_port,
                connector_present=rec.get("connector_present"),
                classification_db=client._database.get("interface_classification") if hasattr(client, "_database") else None,
            )
            rec["is_bridge_port"] = is_bridge_port

    admin_rows, oper_rows, speed_rows, hispeed_rows = await asyncio.gather(
        client._async_walk(OID_ifAdminStatus),
        client._async_walk(OID_ifOperStatus),
        client._async_walk(OID_ifSpeed),
        client._async_walk(OID_ifHighSpeed),
    )

    for oid, val in admin_rows:
        idx = int(oid.split(".")[-1])
        client.cache["ifTable"].setdefault(idx, {})["admin"] = int(val)

    for oid, val in oper_rows:
        idx = int(oid.split(".")[-1])
        client.cache["ifTable"].setdefault(idx, {})["oper"] = int(val)

    # Reset speed_bps for each interface to prevent stale values if speed becomes unknown
    for idx, rec in client.cache["ifTable"].items():
        if isinstance(rec, dict) and "speed_bps" in rec:
            rec.pop("speed_bps", None)

    # Speeds (prefer ifHighSpeed where present; fall back to ifSpeed)
    for oid, val in speed_rows:
        idx = int(oid.split(".")[-1])
        try:
            bps = _parse_numeric(val)
            if not bps or bps <= 0:
                continue
        except Exception:
            continue
        if bps > 0:
            client.cache["ifTable"].setdefault(idx, {})["speed_bps"] = bps

    for oid, val in hispeed_rows:
        idx = int(oid.split(".")[-1])
        try:
            v = int(val)
        except Exception:
            continue
        # ifHighSpeed is defined as Mbps (IF-MIB), but some devices incorrectly return bps.
        # Heuristic: values >= 1,000,000 are treated as bps to avoid 1e6x inflation.
        if v > 0:
            bps = v if v >= 1_000_000 else v * 1_000_000
            client.cache["ifTable"].setdefault(idx, {})["speed_bps"] = bps
    
    # Specialty Math
    for idx, rec in client.cache["ifTable"].items():
        if not isinstance(rec, dict):
            continue
        
        raw_s = float(rec.get("speed_bps", 0))
        high_s = float(rec.get("speed_high", 0))
        
        speed_mbps = high_s if high_s > 0 else (raw_s / 1000000)
        
        rec["speed_mbps"] = speed_mbps
        rec["speed"] = f"{int(speed_mbps)} Mbps" if speed_mbps > 0 else "Down"
