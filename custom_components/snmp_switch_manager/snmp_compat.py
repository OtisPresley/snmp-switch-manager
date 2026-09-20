# ruff: noqa: F401
"""Compatibility layer for PySNMP to ensure forward compatibility with PySNMP 7+ and legacy versions."""

# Prefer new API (PySNMP >= 7, v3arch asyncio)
try:
    from pysnmp.hlapi.v3arch.asyncio import (
        CommunityData,
        ContextData,
        ObjectIdentity,
        ObjectType,
        OctetString,
        Integer,
        SnmpEngine,
        UdpTransportTarget,
        get_cmd,
        set_cmd,
        next_cmd,
        bulk_cmd,
        walk_cmd,
        bulk_walk_cmd,
        is_end_of_mib,
        UsmUserData,
        # SNMPv3 USM protocol constants
        usmNoAuthProtocol,
        usmHMACMD5AuthProtocol,
        usmHMACSHAAuthProtocol,
        usmNoPrivProtocol,
        usmDESPrivProtocol,
        usmAesCfb128Protocol,
    )
    HAS_V7 = True
except Exception:
    HAS_V7 = False

if not HAS_V7:
    # Legacy fallback (older HA bases). Kept for portability.
    from pysnmp.hlapi.asyncio import (  # type: ignore
        CommunityData,
        ContextData,
        ObjectIdentity,
        ObjectType,
        OctetString,
        Integer,
        SnmpEngine,
        UdpTransportTarget,
        UsmUserData,
        usmNoAuthProtocol,
        usmHMACMD5AuthProtocol,
        usmHMACSHAAuthProtocol,
        usmNoPrivProtocol,
        usmDESPrivProtocol,
        usmAesCfb128Protocol,
        getCmd as _get_cmd,
        setCmd as _set_cmd,
        nextCmd as _next_cmd,
        bulkCmd as _bulk_cmd,
    )

    def is_end_of_mib(*a, **k):
        return True

    async def get_cmd(*a, **k):
        """Legacy wrapper for get_cmd."""
        return await _get_cmd(*a, **k)

    async def set_cmd(*a, **k):
        """Legacy wrapper for set_cmd."""
        return await _set_cmd(*a, **k)

    async def next_cmd(*a, **k):
        """Legacy wrapper for next_cmd."""
        return await _next_cmd(*a, **k)

    async def bulk_cmd(*a, **k):
        """Legacy wrapper for bulk_cmd."""
        return await _bulk_cmd(*a, **k)

    async def walk_cmd(*a, **k):
        """Legacy wrapper for walk_cmd."""
        raise NotImplementedError("walk_cmd not supported in legacy PySNMP")

    async def bulk_walk_cmd(*a, **k):
        """Legacy wrapper for bulk_walk_cmd."""
        raise NotImplementedError("bulk_walk_cmd not supported in legacy PySNMP")

# The __all__ list tells other tools which symbols are public.
__all__ = [
    "CommunityData",
    "ContextData",
    "ObjectIdentity",
    "ObjectType",
    "OctetString",
    "Integer",
    "SnmpEngine",
    "UdpTransportTarget",
    "get_cmd",
    "set_cmd",
    "next_cmd",
    "bulk_cmd",
    "walk_cmd",
    "bulk_walk_cmd",
    "is_end_of_mib",
    "UsmUserData",
    "usmNoAuthProtocol",
    "usmHMACMD5AuthProtocol",
    "usmHMACSHAAuthProtocol",
    "usmNoPrivProtocol",
    "usmDESPrivProtocol",
    "usmAesCfb128Protocol",
    "SnmpAuthError",
    "SnmpConnectionError",
    "_do_get_one",
    "_do_get_many",
    "_do_next_walk",
    "_do_bulk_walk",
    "_do_set_alias",
    "_do_set_admin_status",
    "_do_set_poe_admin",
    "_do_set_poe_priority",
    "_do_set_system_string",
]

from typing import Any, Optional, Dict, Tuple, List

# OIDs required for sets
from .const import (
    OID_ifAlias,
    OID_ifAdminStatus,
    OID_pethPsePortAdminEnable,
    OID_pethPsePortPowerPriority,
)

_AUTH_ERROR_PHRASES = (
    "authorizationerror",
    "authentication failure",
    "decryption error",
    "usm: unknown security name",
    "usm: authentication failure",
    "unsupportedsecuritylevel",
)


class SnmpAuthError(Exception):
    """Raised when SNMP authentication fails."""


class SnmpConnectionError(Exception):
    """Raised when SNMP connection or timeout occurs."""


def _is_auth_error(err_ind: Any) -> bool:
    """Return True when err_ind indicates an SNMP authentication/security failure."""
    if err_ind is None:
        return False
    return any(phrase in str(err_ind).lower() for phrase in _AUTH_ERROR_PHRASES)


async def _do_get_one(engine, community, target, context, oid: str) -> Optional[str]:
    err_ind, err_stat, _err_idx, vbs = await get_cmd(
        engine, community, target, context, ObjectType(ObjectIdentity(oid)), lookupMib=False
    )
    if err_ind:
        if _is_auth_error(err_ind):
            raise SnmpAuthError(str(err_ind))
        raise SnmpConnectionError(str(err_ind))
    if err_stat:
        return None
    return str(vbs[0][1]) if vbs else None


async def _do_get_many(engine, community, target, context, oids: list[str]) -> Dict[str, Optional[str]]:
    import asyncio
    chunk_size = 32
    results = {}

    chunks = [oids[i : i + chunk_size] for i in range(0, len(oids), chunk_size)]

    async def _fetch_chunk(chunk):
        obs = [ObjectType(ObjectIdentity(oid)) for oid in chunk]
        err_ind, err_stat, _err_idx, vbs = await get_cmd(
            engine, community, target, context, *obs, lookupMib=False
        )
        if err_ind:
            if _is_auth_error(err_ind):
                raise SnmpAuthError(str(err_ind))
            if len(chunk) > 1:
                chunk_res = {}
                for oid in chunk:
                    try:
                        chunk_res[oid] = await _do_get_one(engine, community, target, context, oid)
                    except Exception:
                        chunk_res[oid] = None
                return chunk_res
            raise SnmpConnectionError(str(err_ind))
        if err_stat:
            return {oid: None for oid in chunk}
        return {oid: (str(vbs[i][1]) if i < len(vbs) else None) for i, oid in enumerate(chunk)}

    chunk_results = await asyncio.gather(*[_fetch_chunk(c) for c in chunks])
    for r in chunk_results:
        results.update(r)

    return results


# GETBULK sizing. A walk used to be one GETNEXT per row: a 188-port switch
# polled every 10 s cost ~750 round trips and ~400 ms of pysnmp/pyasn1 work on
# the Home Assistant event loop per device per poll. GETBULK returns many rows
# per request, and several columns of the same table can share each request.
#
# The budget is varbinds per request, shared across the columns being walked.
# A compliant agent that cannot fit them all simply returns fewer. Some reply
# tooBig instead (seen: a switch that answers 30 but refuses 60); the budget
# is then halved and the SAME request retried, and the smaller budget is
# remembered on the engine so that device is not asked for 60 again.
BULK_VARBINDS_PER_REQUEST = 60

_WALK_END_TYPES = ("EndOfMibView", "NoSuchObject", "NoSuchInstance")


def _raise_for(err_ind: Any) -> None:
    if _is_auth_error(err_ind):
        raise SnmpAuthError(str(err_ind))
    raise SnmpConnectionError(str(err_ind))


def _oid_tuple(oid: str) -> tuple[int, ...]:
    return tuple(int(x) for x in oid.split(".") if x)


def _remember(engine, name: str, value) -> None:
    try:
        setattr(engine, name, value)
    except Exception:  # noqa: BLE001 - an engine that refuses attributes just relearns next time
        pass


async def _do_next_walk_one(
    engine, community, target, context, base_oid: str, start_oid: Optional[str] = None
) -> List[Tuple[str, Any]]:
    """One row per request. Only for agents that refuse GETBULK outright.

    ``start_oid`` resumes a walk that GETBULK had already taken part of the
    way, so nothing is fetched twice and nothing is lost.
    """
    results = []
    current_oid = start_oid or base_oid
    prefix = base_oid + "."
    last = _oid_tuple(current_oid)
    while True:
        err_ind, err_stat, _err_idx, vbs = await next_cmd(
            engine, community, target, context, ObjectType(ObjectIdentity(current_oid)), lookupMib=False
        )
        if err_ind:
            _raise_for(err_ind)
        if err_stat or not vbs:
            break
        oid, val = vbs[0]
        oid_str = str(oid)
        if not oid_str.startswith(prefix) or type(val).__name__ in _WALK_END_TYPES:
            break
        here = _oid_tuple(oid_str)
        if here <= last:  # an agent answering out of order would loop forever
            break
        results.append((oid_str, val))
        current_oid, last = oid_str, here
    return results


async def _do_bulk_walk(
    engine, community, target, context, base_oids: List[str]
) -> Dict[str, List[Tuple[str, Any]]]:
    """Walk one or more subtrees with GETBULK, several columns per request.

    Returns ``{base_oid: [(oid, value), ...]}`` - exactly what walking each
    base on its own returns, in the same order.

    Columns of one table advance together: each request asks for the next
    rows of every column still running, and the reply is row-major, so reply
    item ``i`` belongs to column ``i % len(columns)``. That holds even when
    the agent truncates the reply mid-row. A column stops at the edge of its
    subtree, at endOfMibView, or if the agent stops advancing.

    An error status shrinks the request and retries it; only an agent that
    refuses even one row per column is walked the old way, from wherever
    GETBULK had got to. A timeout is never a reason to fall back - the slower
    walk would only time out more slowly - so it raises as it always did.
    """
    bases = list(dict.fromkeys(base_oids))
    out: Dict[str, List[Tuple[str, Any]]] = {b: [] for b in bases}
    if not bases:
        return out
    if getattr(engine, "_ssm_no_bulk", False):
        for b in bases:
            out[b] = await _do_next_walk_one(engine, community, target, context, b)
        return out

    budget = int(getattr(engine, "_ssm_bulk_budget", BULK_VARBINDS_PER_REQUEST))
    cursor = {b: b for b in bases}
    last = {b: _oid_tuple(b) for b in bases}
    live = list(bases)
    while live:
        width = len(live)
        reps = max(1, budget // width)
        err_ind, err_stat, _err_idx, vbs = await bulk_cmd(
            engine, community, target, context, 0, reps,
            *[ObjectType(ObjectIdentity(cursor[b])) for b in live],
            lookupMib=False,
        )
        if err_ind:
            if _is_auth_error(err_ind):
                raise SnmpAuthError(str(err_ind))
            # Agent timed out or dropped GETBULK: fall back to GETNEXT and remember
            _remember(engine, "_ssm_no_bulk", True)
            for b in live:
                out[b].extend(await _do_next_walk_one(engine, community, target, context, b, cursor[b]))
            break
        if err_stat:
            if reps > 1:
                budget = max(1, reps // 2) * width
                _remember(engine, "_ssm_bulk_budget", max(width, budget))
                continue
            # Not even one row per column: this agent does not do GETBULK.
            _remember(engine, "_ssm_no_bulk", True)
            for b in live:
                out[b].extend(await _do_next_walk_one(engine, community, target, context, b, cursor[b]))
            break
        if not vbs:
            break
        done = set()
        advanced = False
        for i, (oid, val) in enumerate(vbs):
            b = live[i % width]
            if b in done:
                continue
            oid_str = str(oid)
            if not oid_str.startswith(b + ".") or type(val).__name__ in _WALK_END_TYPES:
                done.add(b)
                continue
            here = _oid_tuple(oid_str)
            if here <= last[b]:
                done.add(b)
                continue
            out[b].append((oid_str, val))
            cursor[b], last[b] = oid_str, here
            advanced = True
        # A column the agent left out of a truncated reply is not finished; it
        # is asked again from where it stands. Only a reply that moved nothing
        # forward at all ends the walk, so a stuck agent cannot loop us.
        live = [b for b in live if b not in done]
        if not advanced:
            break
    return {b: out[b] for b in base_oids}


async def _do_next_walk(engine, community, target, context, base_oid: str) -> List[Tuple[str, Any]]:
    """Walk one subtree. Kept under its old name: every caller now gets GETBULK."""
    return (await _do_bulk_walk(engine, community, target, context, [base_oid]))[base_oid]


async def _do_set_alias(engine, community, target, context, if_index: int, alias: str) -> bool:
    err_ind, err_stat, _err_idx, _vbs = await set_cmd(
        engine, community, target, context,
        ObjectType(ObjectIdentity(f"{OID_ifAlias}.{if_index}"), OctetString(alias)),
        lookupMib=False,
    )
    if err_ind:
        if _is_auth_error(err_ind):
            raise SnmpAuthError(str(err_ind))
        raise SnmpConnectionError(str(err_ind))
    return (not err_ind) and (not err_stat)


async def _do_set_admin_status(engine, community, target, context, if_index: int, state: int) -> bool:
    err_ind, err_stat, _err_idx, _vbs = await set_cmd(
        engine, community, target, context,
        ObjectType(ObjectIdentity(f"{OID_ifAdminStatus}.{if_index}"), Integer(state)),
        lookupMib=False,
    )
    if err_ind:
        if _is_auth_error(err_ind):
            raise SnmpAuthError(str(err_ind))
        raise SnmpConnectionError(str(err_ind))
    return (not err_ind) and (not err_stat)


async def _do_set_poe_admin(engine, community, target, context, group_index: int, port_index: int, state: int, oid: Optional[str] = None) -> bool:
    base_oid = oid or OID_pethPsePortAdminEnable
    err_ind, err_stat, _err_idx, _vbs = await set_cmd(
        engine, community, target, context,
        ObjectType(ObjectIdentity(f"{base_oid}.{group_index}.{port_index}"), Integer(state)),
        lookupMib=False,
    )
    if err_ind:
        if _is_auth_error(err_ind):
            raise SnmpAuthError(str(err_ind))
        raise SnmpConnectionError(str(err_ind))
    return (not err_ind) and (not err_stat)


async def _do_set_poe_priority(engine, community, target, context, group_index: int, port_index: int, priority: int, oid: Optional[str] = None) -> bool:
    base_oid = oid or OID_pethPsePortPowerPriority
    err_ind, err_stat, _err_idx, _vbs = await set_cmd(
        engine, community, target, context,
        ObjectType(ObjectIdentity(f"{base_oid}.{group_index}.{port_index}"), Integer(priority)),
        lookupMib=False,
    )
    if err_ind:
        if _is_auth_error(err_ind):
            raise SnmpAuthError(str(err_ind))
        raise SnmpConnectionError(str(err_ind))
    return (not err_ind) and (not err_stat)


async def _do_set_system_string(engine, community, target, context, oid: str, value: str) -> bool:
    err_ind, err_stat, _err_idx, _vbs = await set_cmd(
        engine, community, target, context,
        ObjectType(ObjectIdentity(oid), OctetString(value)),
        lookupMib=False,
    )
    if err_ind:
        if _is_auth_error(err_ind):
            raise SnmpAuthError(str(err_ind))
        raise SnmpConnectionError(str(err_ind))
    return (not err_ind) and (not err_stat)