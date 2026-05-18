"""Temperature polling."""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..snmp import SwitchSnmpClient

from ..helpers import _parse_numeric, decode_label


async def poll_temperature(client: "SwitchSnmpClient", vendor: str) -> None:
    """Poll temperature metrics."""
    temp_items = client._get_database_oids("temperature", vendor)
    try:
        temps_c: dict[int, int] = {}
        unit_temp_c: Optional[int] = None
        unit_temp_state: Optional[int] = None

        for item in temp_items:
            oid = item.get("oid")
            if item.get("method") == "walk" and oid:
                for o, val in await client._async_walk(oid):
                    try:
                        idx = int(str(o).split(".")[-1])
                    except Exception:
                        continue
                    n = _parse_numeric(val)
                    if n is not None:
                        temps_c[idx] = int(n)

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
                    n = _parse_numeric(raw)
                    unit_temp_c = int(n) if n is not None else None
                if "oid_state" in item:
                    raw_s = await client._async_get_one(item["oid_state"])
                    n = _parse_numeric(raw_s)
                    unit_temp_state = int(n) if n is not None else None

        client.cache["env_temps_c"] = temps_c or None
        client.cache["env_unit_temp_c"] = unit_temp_c
        client.cache["env_unit_temp_state"] = unit_temp_state

    except Exception:
        client.cache["env_temps_c"] = None
        client.cache["env_unit_temp_c"] = None
        client.cache["env_unit_temp_state"] = None
