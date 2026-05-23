"""Memory usage polling."""
from __future__ import annotations
import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..snmp import SwitchSnmpClient

from ..helpers import _parse_numeric
from ..const import (
    OID_hrStorageType,
    OID_hrStorageAllocationUnits,
    OID_hrStorageSize,
    OID_hrStorageUsed,
    OID_hrStorageRam,
)


def _walk_to_int_map(rows, filter_set: set[int] | None = None) -> dict[int, int]:
    """Convert walk rows to {idx: int(val)}, optionally filtering by index set."""
    result: dict[int, int] = {}
    for oid, val in rows:
        try:
            idx = int(str(oid).split(".")[-1])
        except Exception:
            continue
        if filter_set is not None and idx not in filter_set:
            continue
        n = _parse_numeric(val)
        if n is not None:
            result[idx] = int(n)
    return result


async def poll_memory(client: "SwitchSnmpClient", vendor: str) -> None:
    """Poll memory usage metrics."""
    mem_items = client._get_database_oids("memory", vendor)
    mem_free_val = mem_total_val = None

    scale = 1.0
    for item in mem_items:
        if item.get("type") == "free_total" and item.get("method") == "get":
            mem_free_val = await client._async_get_one(item.get("oid_free"))
            mem_total_val = await client._async_get_one(item.get("oid_total"))
            scale = float(item.get("scale", 1.0))

    def _to_kb(raw) -> int | None:
        n = _parse_numeric(raw)
        return int(float(n) * scale) if n is not None else None

    client.cache["env_mem_free_kb"] = _to_kb(mem_free_val)
    client.cache["env_mem_total_kb"] = _to_kb(mem_total_val)

    # Fallback: HOST-RESOURCES-MIB hrStorageTable
    if client.cache["env_mem_total_kb"] is None or client.cache["env_mem_free_kb"] is None:
        try:
            # Identify hrStorageRam entries
            ram_idxs: set[int] = set()
            for oid, val in await client._async_walk(OID_hrStorageType):
                try:
                    idx = int(str(oid).split(".")[-1])
                except Exception:
                    continue
                if OID_hrStorageRam in str(val):
                    ram_idxs.add(idx)

            if ram_idxs:
                # Fetch all three columns in parallel, then filter
                alloc_rows, size_rows, used_rows = await asyncio.gather(
                    client._async_walk(OID_hrStorageAllocationUnits),
                    client._async_walk(OID_hrStorageSize),
                    client._async_walk(OID_hrStorageUsed),
                )
                alloc_units = _walk_to_int_map(alloc_rows, ram_idxs)
                sizes = _walk_to_int_map(size_rows, ram_idxs)
                useds = _walk_to_int_map(used_rows, ram_idxs)

                total_bytes = used_bytes = 0
                for idx in ram_idxs:
                    au = alloc_units.get(idx)
                    sz = sizes.get(idx)
                    us = useds.get(idx)
                    if au is None or sz is None or us is None:
                        continue
                    total_bytes += au * sz
                    used_bytes += au * us

                if total_bytes > 0:
                    free_bytes = max(0, total_bytes - used_bytes)
                    if client.cache["env_mem_total_kb"] is None:
                        client.cache["env_mem_total_kb"] = total_bytes // 1024
                    if client.cache["env_mem_free_kb"] is None:
                        client.cache["env_mem_free_kb"] = free_bytes // 1024
        except Exception:
            pass
