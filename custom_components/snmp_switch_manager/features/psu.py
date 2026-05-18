"""PSU status polling."""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..snmp import SwitchSnmpClient

from ..helpers import _parse_numeric, decode_label


async def _walk_labels(client: "SwitchSnmpClient", oid: str) -> dict[int, str]:
    """Walk a label OID and return {idx: label_str} for non-empty values."""
    labels: dict[int, str] = {}
    for lo, lval in await client._async_walk(oid):
        try:
            lidx = int(str(lo).split(".")[-1])
        except Exception:
            continue
        s = decode_label(lval).strip()
        if s:
            labels[lidx] = s.lower()
    return labels


async def poll_psu(client: "SwitchSnmpClient", vendor: str) -> None:
    """Poll PSU status metrics."""
    psu_items = client._get_database_oids("psu", vendor)
    try:
        psu_status: dict[int, int] = {}
        for item in psu_items:
            oid_status = item.get("oid_status")
            if not oid_status or item.get("method") != "walk":
                continue

            filter_str = item.get("filter")
            physical_names: dict[int, str] = {}
            if filter_str and "oid_label" in item:
                physical_names = await _walk_labels(client, item["oid_label"])

            for o, val in await client._async_walk(oid_status):
                try:
                    idx = int(str(o).split(".")[-1])
                except Exception:
                    continue
                if filter_str and filter_str not in physical_names.get(idx, ""):
                    continue
                n = _parse_numeric(val)
                if n is not None:
                    psu_status[idx] = int(n)

        client.cache["env_psu_status"] = psu_status or None
    except Exception:
        client.cache["env_psu_status"] = None
