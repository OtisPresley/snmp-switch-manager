from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Iterable, Tuple

from homeassistant.core import HomeAssistant

# NOTE: keep dependency unchanged; use the synchronous HLAPI to avoid importing
# pysnmp's asyncio transport (which breaks on newer Python).
from pysnmp.hlapi import (  # type: ignore[import]
    CommunityData,
    SnmpEngine,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    getCmd,
    nextCmd,
    setCmd,
)
from pysnmp.proto.rfc1902 import OctetString, Integer  # type: ignore[import]

from .const import (
    OID_sysDescr,
    OID_sysName,
    OID_sysUpTime,
    OID_ifIndex,
    OID_ifDescr,
    OID_ifAdminStatus,
    OID_ifOperStatus,
    OID_ifName,
    OID_ifAlias,
    OID_ipAdEntAddr,
    OID_ipAdEntIfIndex,
    OID_ipAdEntNetMask,
)

_LOGGER = logging.getLogger(__name__)


def _do_get_one(
    engine: SnmpEngine,
    community: CommunityData,
    target: UdpTransportTarget,
    context: ContextData,
    oid: str,
) -> Optional[str]:
    """Blocking SNMP GET; returns string value or None."""
    iterator = getCmd(
        engine,
        community,
        target,
        context,
        ObjectType(ObjectIdentity(oid)),
    )
    error_indication, error_status, error_index, var_binds = next(iterator)
    if error_indication or error_status:
        return None
    return str(var_binds[0][1])


def _do_next_walk(
    engine: SnmpEngine,
    community: CommunityData,
    target: UdpTransportTarget,
    context: ContextData,
    base_oid: str,
) -> Iterable[Tuple[str, Any]]:
    """Blocking SNMP WALK (nextCmd); yields (oid_str, value)."""
    iterator = nextCmd(
        engine,
        community,
        target,
        context,
        ObjectType(ObjectIdentity(base_oid)),
        lexicographicMode=False,
    )
    for error_indication, error_status, error_index, var_binds in iterator:
        if error_indication or error_status:
            break
        for var_bind in var_binds:
            oid_obj, val = var_bind
            yield str(oid_obj), val


def _do_set_alias(
    engine: SnmpEngine,
    community: CommunityData,
    target: UdpTransportTarget,
    context: ContextData,
    if_index: int,
    alias: str,
) -> bool:
    """Blocking SNMP SET for ifAlias."""
    iterator = setCmd(
        engine,
        community,
        target,
        context,
        ObjectType(ObjectIdentity(f"{OID_ifAlias}.{if_index}"), OctetString(alias)),
    )
    error_indication, error_status, error_index, _ = next(iterator)
    return (not error_indication) and (not error_status)


def _do_set_admin_status(
    engine: SnmpEngine,
    community: CommunityData,
    target: UdpTransportTarget,
    context: ContextData,
    if_index: int,
    value: int,
) -> bool:
    """Blocking SNMP SET for ifAdminStatus (1=up, 2=down)."""
    iterator = setCmd(
        engine,
        community,
        target,
        context,
        ObjectType(ObjectIdentity(f"1.3.6.1.2.1.2.2.1.7.{if_index}"), Integer(value)),
    )
    error_indication, error_status, error_index, _ = next(iterator)
    return (not error_indication) and (not error_status)


class SwitchSnmpClient:
    """SNMP client that exposes async methods by offloading sync pysnmp calls to a thread."""

    def __init__(self, hass: HomeAssistant, host: str, community: str, port: int) -> None:
        self.hass = hass
        self.host = host
        self.community = community
        self.port = port

        # Synchronous HLAPI objects
        self.engine = SnmpEngine()
        self.target = UdpTransportTarget((host, port), timeout=1.5, retries=1)
        self.community_data = CommunityData(community, mpModel=1)  # v2c
        self.context = ContextData()

        self.cache: Dict[str, Any] = {
            "sysDescr": None,
            "sysName": None,
            "sysUpTime": None,
            "ifTable": {},  # index -> dict
            "ipIndex": {},  # ip -> ifIndex
            "ipMask": {},   # ip -> netmask
        }

    async def async_initialize(self) -> None:
        self.cache["sysDescr"] = await self._async_get_one(OID_sysDescr)
        self.cache["sysName"] = await self._async_get_one(OID_sysName)
        self.cache["sysUpTime"] = await self._async_get_one(OID_sysUpTime)
        await self._async_walk_interfaces()
        await self._async_walk_ipv4()

    async def async_poll(self) -> Dict[str, Any]:
        await self._async_walk_interfaces(dynamic_only=True)
        await self._async_walk_ipv4()
        return self.cache

    # ---------------------- internal async wrappers ----------------------

    async def _async_get_one(self, oid: str) -> Optional[str]:
        return await self.hass.async_add_executor_job(
            _do_get_one, self.engine, self.community_data, self.target, self.context, oid
        )

    async def _async_walk(self, base_oid: str) -> list[tuple[str, Any]]:
        # Collect results in thread, return list of (oid, value)
        def _collect():
            return list(_do_next_walk(self.engine, self.community_data, self.target, self.context, base_oid))

        return await self.hass.async_add_executor_job(_collect)

    async def _async_walk_interfaces(self, dynamic_only: bool = False) -> None:
        if not dynamic_only:
            self.cache["ifTable"] = {}

            # ifIndex
            for oid, val in await self._async_walk(OID_ifIndex):
                idx = int(str(val))
                self.cache["ifTable"][idx] = {"index": idx}

            # ifDescr
            for oid, val in await self._async_walk(OID_ifDescr):
                idx = int(oid.split(".")[-1])
                self.cache["ifTable"].setdefault(idx, {})["descr"] = str(val)

            # ifName (ifXTable)
            for oid, val in await self._async_walk(OID_ifName):
                idx = int(oid.split(".")[-1])
                self.cache["ifTable"].setdefault(idx, {})["name"] = str(val)

            # ifAlias (RW)
            for oid, val in await self._async_walk(OID_ifAlias):
                idx = int(oid.split(".")[-1])
                self.cache["ifTable"].setdefault(idx, {})["alias"] = str(val)

        # Dynamic bits
        for oid, val in await self._async_walk(OID_ifAdminStatus):
            idx = int(oid.split(".")[-1])
            self.cache["ifTable"].setdefault(idx, {})["admin"] = int(val)

        for oid, val in await self._async_walk(OID_ifOperStatus):
            idx = int(oid.split(".")[-1])
            self.cache["ifTable"].setdefault(idx, {})["oper"] = int(val)

    async def _async_walk_ipv4(self) -> None:
        ip_to_index: Dict[str, int | None] = {}
        ip_to_mask: Dict[str, str] = {}

        for _oid, val in await self._async_walk(OID_ipAdEntAddr):
            ip_to_index[str(val)] = None

        for oid, val in await self._async_walk(OID_ipAdEntIfIndex):
            # last 4 numbers form the IPv4
            parts = oid.split(".")[-4:]
            ip = ".".join(parts)
            ip_to_index[ip] = int(val)

        for oid, val in await self._async_walk(OID_ipAdEntNetMask):
            parts = oid.split(".")[-4:]
            ip = ".".join(parts)
            ip_to_mask[ip] = str(val)

        self.cache["ipIndex"] = ip_to_index
        self.cache["ipMask"] = ip_to_mask

    # ---------------------- public helper methods ----------------------

    async def set_alias(self, if_index: int, alias: str) -> bool:
        ok = await self.hass.async_add_executor_job(
            _do_set_alias, self.engine, self.community_data, self.target, self.context, if_index, alias
        )
        if ok:
            self.cache["ifTable"].setdefault(if_index, {})["alias"] = alias
        else:
            _LOGGER.warning("Failed to set alias via SNMP on ifIndex %s", if_index)
        return ok

    async def set_admin_status(self, if_index: int, value: int) -> bool:
        return await self.hass.async_add_executor_job(
            _do_set_admin_status, self.engine, self.community_data, self.target, self.context, if_index, value
        )


# ---------------------- helpers for config_flow ----------------------

async def test_connection(hass: HomeAssistant, host: str, community: str, port: int) -> bool:
    client = SwitchSnmpClient(hass, host, community, port)
    sysname = await client._async_get_one(OID_sysName)
    return sysname is not None


async def get_sysname(hass: HomeAssistant, host: str, community: str, port: int) -> Optional[str]:
    client = SwitchSnmpClient(hass, host, community, port)
    return await client._async_get_one(OID_sysName)
