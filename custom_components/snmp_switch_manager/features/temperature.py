"""Temperature polling."""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional, Any

if TYPE_CHECKING:
    from ..snmp import SwitchSnmpClient

from ..helpers import _parse_numeric, decode_label


def _parse_temperature(
    val: Any,
    scale: float,
    invalid_values: set[int],
    min_temp: float = -20.0,
    max_temp: float = 100.0,
) -> Optional[int]:
    """Parse, filter invalid values, scale, and range-check a temperature reading."""
    n = _parse_numeric(val)
    if n is None or n in invalid_values:
        return None
    temp_c = float(n) * scale
    if not (min_temp <= temp_c <= max_temp):
        return None
    return int(round(temp_c))


async def poll_temperature(client: "SwitchSnmpClient", vendor: str) -> None:
    """Poll temperature metrics."""
    temp_items = client._get_database_oids("temperature", vendor)
    try:
        temps_c: dict[int, int] = {}
        unit_temp_c: Optional[int] = None
        unit_temp_state: Optional[int] = None

        for item in temp_items:
            oid = item.get("oid")
            scale = float(item.get("scale", 1.0))
            invalid_raw = item.get("invalid_values", [])
            invalid_values = {
                p for iv in invalid_raw if (p := _parse_numeric(iv)) is not None
            }
            min_temp = float(item.get("min_temp", -20.0))
            max_temp = float(item.get("max_temp", 100.0))

            if item.get("method") == "walk" and oid:
                for o, val in await client._async_walk(oid):
                    try:
                        idx = int(str(o).split(".")[-1])
                    except Exception:
                        continue
                    t = _parse_temperature(val, scale, invalid_values, min_temp, max_temp)
                    if t is not None:
                        temps_c[idx] = t

                if "oid_label" in item:
                    temp_labels: dict[int, str] = {}
                    for lo, lval in await client._async_walk(item["oid_label"]):
                        try:
                            lidx = int(str(lo).split(".")[-1])
                        except Exception:
                            continue
                        s = decode_label(lval).strip()
                        if s:
                            temp_labels[lidx] = s
                    if temp_labels:
                        client.cache.setdefault("env_temp_labels", {}).update(temp_labels)

            elif item.get("method") == "get":
                if oid:
                    raw = await client._async_get_one(oid)
                    parsed_temp = _parse_temperature(raw, scale, invalid_values, min_temp, max_temp)
                    if parsed_temp is not None:
                        unit_temp_c = parsed_temp
                if "oid_state" in item:
                    raw_s = await client._async_get_one(item["oid_state"])
                    n = _parse_numeric(raw_s)
                    if n is not None:
                        unit_temp_state = int(n)

        client.cache["env_temps_c"] = temps_c or None
        client.cache["env_unit_temp_c"] = unit_temp_c
        client.cache["env_unit_temp_state"] = unit_temp_state

    except Exception:
        client.cache["env_temps_c"] = None
        client.cache["env_unit_temp_c"] = None
        client.cache["env_unit_temp_state"] = None
