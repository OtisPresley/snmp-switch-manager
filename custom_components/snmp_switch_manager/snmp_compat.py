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
        get_cmd as _get_cmd,
        set_cmd as _set_cmd,
        next_cmd as _next_cmd,
        bulk_cmd as _bulk_cmd,
        walk_cmd as _walk_cmd,
        bulk_walk_cmd as _bulk_walk_cmd,
        is_end_of_mib,
    )

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
        return await _walk_cmd(*a, **k)

    async def bulk_walk_cmd(*a, **k):
        """Legacy wrapper for bulk_walk_cmd."""
        return await _bulk_walk_cmd(*a, **k)

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
            raise SnmpConnectionError(str(err_ind))
        if err_stat:
            return {oid: None for oid in chunk}
        return {oid: (str(vbs[i][1]) if i < len(vbs) else None) for i, oid in enumerate(chunk)}

    chunk_results = await asyncio.gather(*[_fetch_chunk(c) for c in chunks])
    for r in chunk_results:
        results.update(r)

    return results


async def _do_next_walk(engine, community, target, context, base_oid: str) -> List[Tuple[str, Any]]:
    results = []
    current_oid = base_oid
    while True:
        err_ind, err_stat, _err_idx, vbs = await next_cmd(
            engine, community, target, context, ObjectType(ObjectIdentity(current_oid)), lookupMib=False
        )
        if err_ind:
            if _is_auth_error(err_ind):
                raise SnmpAuthError(str(err_ind))
            raise SnmpConnectionError(str(err_ind))
        if err_stat or not vbs:
            break
        oid, val = vbs[0]
        oid_str = str(oid)
        if not oid_str.startswith(base_oid):
            break
        results.append((oid_str, val))
        current_oid = oid_str
    return results


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