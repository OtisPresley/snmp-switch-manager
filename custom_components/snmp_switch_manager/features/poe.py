"""PoE budget and per-port power polling."""
from __future__ import annotations
from typing import TYPE_CHECKING, Dict
import asyncio
import time
import logging

if TYPE_CHECKING:
    from ..snmp import SwitchSnmpClient

from ..const import (
    CONF_POE_ENABLE,
    CONF_POE_MODE,
    CONF_POE_POLL_INTERVAL,
    POE_MODE_ATTRIBUTES,
    OID_pethMainPsePower,
    OID_pethMainPseConsumedPower,
    OID_pethPsePortActualPower,
    OID_pethPsePortAdminEnable,
    OID_pethPsePortPowerPriority,
)
from ..helpers import _parse_numeric

_LOGGER = logging.getLogger(__name__)

def _extract_floats(rows) -> list[float]:
    """Collect non-negative numeric values from SNMP walk rows."""
    result = []
    for _, val in rows:
        n = _parse_numeric(val)
        if n is not None and float(n) >= 0:
            result.append(float(n))
    return result


def _oid_last_idx(oid: str) -> int:
    return int(str(oid).split(".")[-1])


async def poll_poe(client: "SwitchSnmpClient") -> None:
    """Poll PoE budget and per-port power data from device."""
    poe_enabled = bool(client._poe_options.get(CONF_POE_ENABLE, False))
    poe_control_loops = bool(client._poe_options.get("poe_control_loops", False))
    poe_mode = client._poe_options.get(CONF_POE_MODE, POE_MODE_ATTRIBUTES)
    
    client.cache["poe_enabled"] = poe_enabled
    client.cache["poe_control_loops"] = poe_control_loops
    client.cache["poe_mode"] = poe_mode
    client.cache.setdefault("poe_power_mw", {})
    client.cache.setdefault("poe_ports", {})

    if not poe_enabled and not poe_control_loops:
        client.cache["poe_power_mw"] = {}
        client.cache["poe_ports"] = {}
        for k in ("poe_budget_total_w", "poe_power_used_w", "poe_power_available_w",
                  "poe_health_status", "poe_health_status_raw"):
            client.cache.pop(k, None)
        return

    interval = max(1, int(client._poe_options.get(CONF_POE_POLL_INTERVAL, 30)))
    now_mono = time.monotonic()
    last_poll = float(client._poe_last_poll or 0.0)
    if last_poll and (now_mono - last_poll) < interval:
        return

    client._poe_last_poll = now_mono

    # Resolve OIDs from database
    vendor = client.cache.get("vendor", "Unknown")
    poe_items = client._get_database_oids("poe", vendor)
    standard_item = None
    dell_item = None
    for item in poe_items:
        vendors = item.get("vendors", [])
        if "poe" in client.feature_overrides and item == client.feature_overrides["poe"]:
            standard_item = item
        elif "oid_budget" in item and ("Standard" in vendors or vendor in vendors):
            standard_item = item
        elif "oid_port_power" in item and "oid_budget" not in item and vendor in vendors:
            dell_item = item

    tasks = []
    if poe_enabled:
        oid_budget = (standard_item or {}).get("oid_budget") or OID_pethMainPsePower
        oid_used = (standard_item or {}).get("oid_used") or OID_pethMainPseConsumedPower
        oid_std_port = (standard_item or {}).get("oid_port_power") or OID_pethPsePortActualPower
        oid_dell_port = (dell_item or {}).get("oid_port_power") if dell_item else None
        
        tasks.append(client._async_walk(oid_budget))
        tasks.append(client._async_walk(oid_used))
        tasks.append(client._async_walk(oid_dell_port) if oid_dell_port else asyncio.sleep(0, result=[]))
        tasks.append(client._async_walk(oid_std_port))
    else:
        tasks.extend([asyncio.sleep(0, result=[]), asyncio.sleep(0, result=[]), asyncio.sleep(0, result=[]), asyncio.sleep(0, result=[])])

    if poe_control_loops:
        oid_port_admin = (standard_item or {}).get("oid_port_admin") or OID_pethPsePortAdminEnable
        oid_port_priority = (standard_item or {}).get("oid_port_priority") or OID_pethPsePortPowerPriority
        tasks.append(client._async_walk(oid_port_admin))
        tasks.append(client._async_walk(oid_port_priority))
    else:
        tasks.extend([asyncio.sleep(0, result=[]), asyncio.sleep(0, result=[])])

    results = await asyncio.gather(*tasks)
    budget_rows = results[0]
    used_rows = results[1]
    dell_poe_rows = results[2]
    std_poe_rows = results[3]
    admin_rows = results[4] if len(results) > 4 else []
    priority_rows = results[5] if len(results) > 5 else []

    # PoE totals (POWER-ETHERNET-MIB)
    try:
        budget_list = _extract_floats(budget_rows)
        used_list = _extract_floats(used_rows)
    except Exception:
        budget_list = []
        used_list = []

    b_sum = sum(budget_list) if budget_list else 0.0
    u_sum = sum(used_list) if used_list else 0.0

    # Heuristic: Zyxel returns Watts directly; others may return mW
    # Overridable by setting 'scale' or 'scale_budget'/'scale_used' in the database/options.
    custom_scale_b = (standard_item or {}).get("scale_budget") or (standard_item or {}).get("scale")
    custom_scale_u = (standard_item or {}).get("scale_used") or (standard_item or {}).get("scale")
    
    vendor_info = client._get_vendor_info()
    is_zyxel_heuristic = vendor_info.get("poe_scale_heuristic") == "zyxel"

    if custom_scale_b is not None:
        scale_b = float(custom_scale_b)
    elif is_zyxel_heuristic:
        scale_b = 1.0 if b_sum < 2000 else 1000.0
    else:
        scale_b = 1000.0 if b_sum > 5000 else 1.0

    if custom_scale_u is not None:
        scale_u = float(custom_scale_u)
    elif is_zyxel_heuristic:
        scale_u = 1.0 if u_sum < 2000 else 1000.0
    else:
        scale_u = 1000.0 if u_sum > 5000 else 1.0

    if budget_list or used_list:
        client.cache["poe_budget_total_w"] = round(b_sum / scale_b, 1) if budget_list else None
        client.cache["poe_power_used_w"] = round(u_sum / scale_u, 1) if used_list else None
        if budget_list and used_list:
            client.cache["poe_power_available_w"] = round(max(0.0, (b_sum / scale_b) - (u_sum / scale_u)), 1)

    # Per-port PoE power (mW)
    poe_power_mw: Dict[int, float] = {}

    # A) Dell Private MIB
    try:
        for oid, val in dell_poe_rows:
            mw = _parse_numeric(val)
            if mw is not None:
                poe_power_mw[_oid_last_idx(oid)] = float(mw)
    except Exception:
        pass

    # B) Standard POWER-ETHERNET-MIB (with physical port translation)
    try:
        ifindex_map = client.cache.get("ifindex_by_baseport", {})
        for oid, val in std_poe_rows:
            port_idx = _oid_last_idx(oid)
            target_idx = ifindex_map.get(port_idx, port_idx)
            if target_idx not in poe_power_mw:
                mw = _parse_numeric(val)
                if mw is not None:
                    poe_power_mw[target_idx] = float(mw)
    except Exception:
        pass

    client.cache["poe_power_mw"] = poe_power_mw

    # Per-port PoE control loops
    if poe_control_loops:
        admin_map = {}
        for oid, val in admin_rows:
            parts = oid.split(".")
            group_idx = int(parts[-2])
            port_idx = int(parts[-1])
            v = _parse_numeric(val)
            if v is not None:
                admin_map[(group_idx, port_idx)] = int(v)

        priority_map = {}
        for oid, val in priority_rows:
            parts = oid.split(".")
            group_idx = int(parts[-2])
            port_idx = int(parts[-1])
            v = _parse_numeric(val)
            if v is not None:
                priority_map[(group_idx, port_idx)] = int(v)

        poe_ports = {}
        ifindex_map = client.cache.get("ifindex_by_baseport", {})
        for (g_idx, p_idx), admin_val in admin_map.items():
            target_idx = ifindex_map.get(p_idx, p_idx)
            priority_val = priority_map.get((g_idx, p_idx), 3)
            poe_ports[target_idx] = {
                "ifindex": target_idx,
                "group": g_idx,
                "port": p_idx,
                "admin": admin_val,
                "priority": priority_val,
            }
        client.cache["poe_ports"] = poe_ports
    else:
        client.cache["poe_ports"] = {}
