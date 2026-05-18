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
)
from ..helpers import _parse_numeric

_LOGGER = logging.getLogger(__name__)

# Fallback OIDs when poe.json does not match the current vendor
_OID_BUDGET_DEFAULT = "1.3.6.1.2.1.105.1.3.1.1.2"
_OID_USED_DEFAULT = "1.3.6.1.2.1.105.1.3.1.1.4"
_OID_STD_PORT_DEFAULT = "1.3.6.1.2.1.105.1.1.1.1.15"


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
    poe_mode = client._poe_options.get(CONF_POE_MODE, POE_MODE_ATTRIBUTES)
    client.cache["poe_enabled"] = poe_enabled
    client.cache["poe_mode"] = poe_mode
    client.cache.setdefault("poe_power_mw", {})

    if not poe_enabled:
        client.cache["poe_power_mw"] = {}
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
    poe_items = client._database.get("poe", {}).get("poe", [])
    standard_item = None
    dell_item = None
    for item in poe_items:
        vendors = item.get("vendors", [])
        if "oid_budget" in item and ("Standard" in vendors or vendor in vendors):
            standard_item = item
        elif "oid_port_power" in item and "oid_budget" not in item and vendor in vendors:
            dell_item = item

    oid_budget = (standard_item or {}).get("oid_budget", _OID_BUDGET_DEFAULT)
    oid_used = (standard_item or {}).get("oid_used", _OID_USED_DEFAULT)
    oid_std_port = (standard_item or {}).get("oid_port_power", _OID_STD_PORT_DEFAULT)
    oid_dell_port = (dell_item or {}).get("oid_port_power") if dell_item else None

    budget_rows, used_rows, dell_poe_rows, std_poe_rows = await asyncio.gather(
        client._async_walk(oid_budget),
        client._async_walk(oid_used),
        client._async_walk(oid_dell_port) if oid_dell_port else asyncio.sleep(0, result=[]),
        client._async_walk(oid_std_port),
    )

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
    if getattr(client, "_is_zyxel", False):
        scale_b = 1.0 if b_sum < 2000 else 1000.0
        scale_u = 1.0 if u_sum < 2000 else 1000.0
    else:
        scale_b = 1000.0 if b_sum > 5000 else 1.0
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
