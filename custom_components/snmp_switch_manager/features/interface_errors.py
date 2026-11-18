"""Interface error and discard counter polling (IF-MIB)."""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from ..snmp import SwitchSnmpClient

from ..const import (
    CONF_IF_ERRORS_ENABLE,
    CONF_IF_ERRORS_INCLUDE_DISCARDS,
    CONF_IF_ERRORS_MODE,
    CONF_IF_ERRORS_POLL_INTERVAL,
    DEFAULT_IF_ERRORS_POLL_INTERVAL,
    IF_ERRORS_MODE_ATTRIBUTES,
    IF_ERRORS_MODE_SENSORS,
    OID_ifInDiscards,
    OID_ifInErrors,
    OID_ifOutDiscards,
    OID_ifOutErrors,
)
from ..helpers import matches_interface_rules
from ..snmp_compat import _do_get_many

_LOGGER = logging.getLogger(__name__)


def _safe_int(val: Any) -> int | None:
    try:
        return int(val) if val is not None else None
    except Exception:
        return None


def _resolve_error_oids(client: "SwitchSnmpClient") -> tuple[str, str, str, str]:
    """Resolve error/discard OIDs from overrides, database, or IF-MIB defaults."""
    vendor = client._get_vendor() if hasattr(client, "_get_vendor") else "Standard"
    db_entries = client._get_database_oids("interface_errors", vendor) if hasattr(client, "_get_database_oids") else []
    if not db_entries and vendor.lower() != "standard" and hasattr(client, "_get_database_oids"):
        db_entries = client._get_database_oids("interface_errors", "Standard")

    cfg = db_entries[0] if db_entries else {}

    def _oid(key: str, default: str) -> str:
        raw = str(cfg.get(key) or default).strip()
        return raw.lstrip(".") or default

    return (
        _oid("oid_in_errors", OID_ifInErrors),
        _oid("oid_out_errors", OID_ifOutErrors),
        _oid("oid_in_discards", OID_ifInDiscards),
        _oid("oid_out_discards", OID_ifOutDiscards),
    )


async def poll_interface_errors(client: "SwitchSnmpClient") -> None:
    """Poll per-interface error (and optional discard) counters."""
    opts = getattr(client, "_if_errors_options", {}) or {}
    enabled = bool(opts.get(CONF_IF_ERRORS_ENABLE, False))
    mode = str(opts.get(CONF_IF_ERRORS_MODE) or IF_ERRORS_MODE_SENSORS).strip().lower()
    if mode not in (IF_ERRORS_MODE_SENSORS, IF_ERRORS_MODE_ATTRIBUTES):
        mode = IF_ERRORS_MODE_SENSORS
    include_discards = bool(opts.get(CONF_IF_ERRORS_INCLUDE_DISCARDS, False))

    client.cache["if_errors_enabled"] = enabled
    client.cache["if_errors_mode"] = mode
    client.cache["if_errors_include_discards"] = include_discards

    if not enabled:
        client.cache["interface_errors"] = {}
        return

    poll_interval = int(
        opts.get(CONF_IF_ERRORS_POLL_INTERVAL, DEFAULT_IF_ERRORS_POLL_INTERVAL)
        or DEFAULT_IF_ERRORS_POLL_INTERVAL
    )
    now = time.monotonic()
    last_poll = getattr(client, "_if_errors_last_poll", None)
    if last_poll is not None and (now - last_poll) < poll_interval:
        _LOGGER.debug("Skipping interface error counter poll; interval=%ss", poll_interval)
        return

    client._if_errors_last_poll = now
    try:
        iftable = client.cache.get("ifTable") or {}
        inc_s = getattr(client, "_if_errors_include_starts", ())
        inc_c = getattr(client, "_if_errors_include_contains", ())
        inc_e = getattr(client, "_if_errors_include_ends", ())
        exc_s = getattr(client, "_if_errors_exclude_starts", ())
        exc_c = getattr(client, "_if_errors_exclude_contains", ())
        exc_e = getattr(client, "_if_errors_exclude_ends", ())
        has_includes = bool(inc_s or inc_c or inc_e)

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

            if has_includes and not matches_interface_rules(nl, inc_s, inc_c, inc_e):
                continue
            if matches_interface_rules(nl, exc_s, exc_c, exc_e):
                continue

            selected.append(idx_i)

        if not selected:
            client.cache["interface_errors"] = {}
            return

        oid_in_err, oid_out_err, oid_in_disc, oid_out_disc = _resolve_error_oids(client)

        oids: list[str] = []
        for idx_i in selected:
            oids.append(f"{oid_in_err}.{idx_i}")
            oids.append(f"{oid_out_err}.{idx_i}")
            if include_discards:
                oids.append(f"{oid_in_disc}.{idx_i}")
                oids.append(f"{oid_out_disc}.{idx_i}")

        got = await _do_get_many(client.engine, client.auth_data, client.target, client.context, oids)
        now_ts = time.time()

        out: Dict[int, Dict[str, Any]] = {}
        for idx_i in selected:
            rx_err = _safe_int(got.get(f"{oid_in_err}.{idx_i}"))
            tx_err = _safe_int(got.get(f"{oid_out_err}.{idx_i}"))
            rx_disc = _safe_int(got.get(f"{oid_in_disc}.{idx_i}")) if include_discards else None
            tx_disc = _safe_int(got.get(f"{oid_out_disc}.{idx_i}")) if include_discards else None

            if rx_err is None and tx_err is None and rx_disc is None and tx_disc is None:
                continue

            row_out: Dict[str, Any] = {
                "ts": now_ts,
                "rx_errors": rx_err,
                "tx_errors": tx_err,
            }
            if include_discards:
                row_out["rx_discards"] = rx_disc
                row_out["tx_discards"] = tx_disc
            out[idx_i] = row_out

        client.cache["interface_errors"] = out
    except Exception as e:
        _LOGGER.debug("Interface error polling failed: %s", e)
        client.cache["interface_errors"] = {}
