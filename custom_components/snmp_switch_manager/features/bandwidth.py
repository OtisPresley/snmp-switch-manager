"""Bandwidth counter polling."""
from __future__ import annotations
from typing import TYPE_CHECKING, Dict, Any
import time
import logging

if TYPE_CHECKING:
    from ..snmp import SwitchSnmpClient

from ..const import (
    CONF_BW_ENABLE,
    CONF_BANDWIDTH_POLL_INTERVAL,
    DEFAULT_BANDWIDTH_POLL_INTERVAL,
    OID_ifHCInOctets,
    OID_ifInOctets,
    OID_ifHCOutOctets,
    OID_ifOutOctets,
)
from ..helpers import _do_get_many

_LOGGER = logging.getLogger(__name__)


def _matches_any(name_l: str, starts: tuple, contains: tuple, ends: tuple) -> bool:
    """Return True if name_l matches any of the supplied filter tuples."""
    if starts and name_l.startswith(starts):
        return True
    if ends and name_l.endswith(ends):
        return True
    return contains and any(x in name_l for x in contains)


def _counter_delta(cur: int, prev: int, use_hc: bool) -> int:
    """Compute a monotonic counter delta, handling 32-bit wrap when not HC."""
    delta = cur - prev
    if not use_hc and delta < 0:
        delta += 2 ** 32
    return delta


async def poll_bandwidth(client: "SwitchSnmpClient") -> None:
    """Poll per-interface bandwidth counters."""
    if not bool(client._bandwidth_options.get(CONF_BW_ENABLE, False)):
        return

    poll_interval = int(
        client._bandwidth_options.get(CONF_BANDWIDTH_POLL_INTERVAL, DEFAULT_BANDWIDTH_POLL_INTERVAL)
        or DEFAULT_BANDWIDTH_POLL_INTERVAL
    )
    now = time.monotonic()
    if client._bw_last_poll is not None and (now - client._bw_last_poll) < poll_interval:
        _LOGGER.debug("Skipping bandwidth counter poll; interval=%ss", poll_interval)
        return

    client._bw_last_poll = now
    try:
        iftable = client.cache.get("ifTable") or {}
        has_includes = client._bw_include_starts or client._bw_include_contains or client._bw_include_ends

        selected: list[int] = []
        for idx, row in iftable.items():
            try:
                idx_i = int(idx)
            except Exception:
                continue
            raw_name = str(row.get("name") or "").strip()
            if not raw_name:
                continue
            nl = raw_name.lower()

            # Include filter: if any rules defined, interface must match at least one
            if has_includes and not _matches_any(nl, client._bw_include_starts, client._bw_include_contains, client._bw_include_ends):
                continue

            # Exclude always wins
            if _matches_any(nl, client._bw_exclude_starts, client._bw_exclude_contains, client._bw_exclude_ends):
                continue

            selected.append(idx_i)

        # Detect 64-bit counter support once per session
        if client._bw_use_hc is None:
            client._bw_use_hc = False
            if selected:
                probe_oid = f"{OID_ifHCInOctets}.{selected[0]}"
                try:
                    probe_val = await client._async_get_one(probe_oid)
                    if probe_val is not None:
                        int(probe_val)  # validate numeric
                        client._bw_use_hc = True
                except Exception:
                    pass

        now_ts = time.time()
        use_hc = bool(client._bw_use_hc)
        rx_base = OID_ifHCInOctets if use_hc else OID_ifInOctets
        tx_base = OID_ifHCOutOctets if use_hc else OID_ifOutOctets

        oids = [oid for idx_i in selected for oid in (f"{rx_base}.{idx_i}", f"{tx_base}.{idx_i}")]
        got = await _do_get_many(client.engine, client.auth_data, client.target, client.context, oids)

        bw_out: Dict[int, Dict[str, Any]] = {}
        for idx_i in selected:
            rx_v = got.get(f"{rx_base}.{idx_i}")
            tx_v = got.get(f"{tx_base}.{idx_i}")
            if rx_v is None and tx_v is None:
                continue

            rx_oct = _safe_int(rx_v)
            tx_oct = _safe_int(tx_v)

            last = client._bw_last.get(idx_i) or {}
            last_ts = float(last.get("ts") or 0.0)
            dt = (now_ts - last_ts) if last_ts else 0.0

            rx_bps = tx_bps = None
            if dt > 0:
                if rx_oct is not None and last.get("rx") is not None:
                    rx_bps = (_counter_delta(rx_oct, int(last["rx"]), use_hc) * 8.0) / dt
                if tx_oct is not None and last.get("tx") is not None:
                    tx_bps = (_counter_delta(tx_oct, int(last["tx"]), use_hc) * 8.0) / dt

            client._bw_last[idx_i] = {"ts": now_ts, "rx": rx_oct, "tx": tx_oct}
            bw_out[idx_i] = {
                "ts": now_ts,
                "rx_octets": rx_oct,
                "tx_octets": tx_oct,
                "rx_bps": rx_bps,
                "tx_bps": tx_bps,
                "use_hc": use_hc,
            }

        client.cache["bandwidth"] = bw_out
    except Exception as e:
        _LOGGER.debug("Bandwidth polling failed: %s", e)
        client.cache["bandwidth"] = {}


def _safe_int(v) -> int | None:
    try:
        return int(v) if v is not None else None
    except Exception:
        return None
