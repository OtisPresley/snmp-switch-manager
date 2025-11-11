from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Iterable, Tuple

from homeassistant.core import HomeAssistant

# Use synchronous HLAPI and offload to an executor (no dependency changes).
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

# --- Fallback OIDs (kept local to avoid touching const.py) ---
# IP-MIB (modern) columns
_OID_ipAddressAddr = "1.3.6.1.2.1.4.34.1.2"       # OCTET STRING (IPv4: 4 bytes)
_OID_ipAddressIfIndex = "1.3.6.1.2.1.4.34.1.3"    # Integer (ifIndex)
# IP-FORWARD-MIB ipCidrRouteTable columns
_OID_ipCidrRoutePrefixLength = "1.3.6.1.2.1.4.24.4.1.3"  # Integer (bits)
_OID_ipCidrRouteIfIndex      = "1.3.6.1.2.1.4.24.4.1.7"  # Integer (ifIndex)


# ------------------ low-level sync helpers ------------------

def _do_get_one(
    engine: SnmpEngine,
    community: CommunityData,
    target: UdpTransportTarget,
    context: ContextData,
    oid: str,
) -> Optional[str]:
    it = getCmd(engine, community, target, context, ObjectType(ObjectIdentity(oid)))
    err_ind, err_stat, err_idx, vbs = next(it)
    if err_ind or err_stat:
        return None
    return str(vbs[0][1])


def _do_next_walk(
    engine: SnmpEngine,
    community: CommunityData,
    target: UdpTransportTarget,
    context: ContextData,
    base_oid: str,
) -> Iterable[Tuple[str, Any]]:
    it = nextCmd(
        engine,
        community,
        target,
        context,
        ObjectType(ObjectIdentity(base_oid)),
        lexicographicMode=False,
    )
    for err_ind, err_stat, err_idx, vbs in it:
        if err_ind or err_stat:
            break
        for vb in vbs:
            oid_obj, val = vb
            yield str(oid_obj), val


def _do_set_alias(
    engine: SnmpEngine,
    community: CommunityData,
    target: UdpTransportTarget,
    context: ContextData,
    if_index: int,
    alias: str,
) -> bool:
    it = setCmd(
        engine,
        community,
        target,
        context,
        ObjectType(ObjectIdentity(f"{OID_ifAlias}.{if_index}"), OctetString(alias)),
    )
    err_ind, err_stat, err_idx, _ = next(it)
    return (not err_ind) and (not err_stat)


def _do_set_admin_status(
    engine: SnmpEngine,
    community: CommunityData,
    target: UdpTransportTarget,
    context: ContextData,
    if_index: int,
    value: int,
) -> bool:
    it = setCmd(
        engine,
        community,
        target,
        context,
        ObjectType(ObjectIdentity(f"1.3.6.1.2.1.2.2.1.7.{if_index}"), Integer(value)),
    )
    err_ind, err_stat, err_idx, _ = next(it)
    return (not err_ind) and (not err_stat)


# ------------------ small utils ------------------

def _octets_to_ipv4(val: Any) -> Optional[str]:
    """Coerce an OCTET STRING value to dotted IPv4 if exactly 4 bytes."""
    try:
        bs = bytes(val)
    except Exception:
        try:
            bs = val.asOctets()  # type: ignore[attr-defined]
        except Exception:
            s = str(val)
            return s if s.count(".") == 3 else None
    if len(bs) == 4:
        return ".".join(str(b) for b in bs)
    return None


def _bits_to_mask(bits: int) -> str:
    """Convert CIDR bits (0..32) to dotted mask."""
    if bits <= 0:
        return "0.0.0.0"
    if bits >= 32:
        return "255.255.255.255"
    mask = (0xffffffff << (32 - bits)) & 0xffffffff
    return ".".join(str((mask >> shift) & 0xff) for shift in (24, 16, 8, 0))


# ------------------ client ------------------

class SwitchSnmpClient:
    """SNMP client that exposes async methods by offloading sync pysnmp calls to a thread."""

    def __init__(self, hass: HomeAssistant, host: str, community: str, port: int) -> None:
        self.hass = hass
        self.host = host
        self.community = community
        self.port = port

        self.engine = SnmpEngine()
        self.target = UdpTransportTarget((host, port), timeout=1.5, retries=1)
        self.community_data = CommunityData(community, mpModel=1)  # v2c
        self.context = ContextData()

        self.cache: Dict[str, Any] = {
            "sysDescr": None,
            "sysName": None,
            "sysUpTime": None,
            "ifTable": {},     # index -> dict
            "ipIndex": {},     # ip -> ifIndex
            "ipMask": {},      # ip -> dotted mask
        }

    async def async_initialize(self) -> None:
        self.cache["sysDescr"] = await self._async_get_one(OID_sysDescr)
        self.cache["sysName"] = await self._async_get_one(OID_sysName)
        self.cache["sysUpTime"] = await self._async_get_one(OID_sysUpTime)
        await self._walk_interfaces()
        await self._walk_ipv4()

    async def async_poll(self) -> Dict[str, Any]:
        await self._walk_interfaces(dynamic_only=True)
        await self._walk_ipv4()
        return self.cache

    # ---------- async wrappers over sync calls ----------

    async def _async_get_one(self, oid: str) -> Optional[str]:
        return await self.hass.async_add_executor_job(
            _do_get_one, self.engine, self.community_data, self.target, self.context, oid
        )

    async def _async_walk(self, base_oid: str) -> list[tuple[str, Any]]:
        def _collect():
            return list(_do_next_walk(self.engine, self.community_data, self.target, self.context, base_oid))
        return await self.hass.async_add_executor_job(_collect)

    # ---------- walkers ----------

    async def _walk_interfaces(self, dynamic_only: bool = False) -> None:
        if not dynamic_only:
            self.cache["ifTable"] = {}
            for _oid, val in await self._async_walk(OID_ifIndex):
                idx = int(str(val))
                self.cache["ifTable"][idx] = {"index": idx}
            for oid, val in await self._async_walk(OID_ifDescr):
                idx = int(oid.split(".")[-1])
                self.cache["ifTable"].setdefault(idx, {})["descr"] = str(val)
            for oid, val in await self._async_walk(OID_ifName):
                idx = int(oid.split(".")[-1])
                self.cache["ifTable"].setdefault(idx, {})["name"] = str(val)
            for oid, val in await self._async_walk(OID_ifAlias):
                idx = int(oid.split(".")[-1])
                self.cache["ifTable"].setdefault(idx, {})["alias"] = str(val)

        for oid, val in await self._async_walk(OID_ifAdminStatus):
            idx = int(oid.split(".")[-1])
            self.cache["ifTable"].setdefault(idx, {})["admin"] = int(val)

        for oid, val in await self._async_walk(OID_ifOperStatus):
            idx = int(oid.split(".")[-1])
            self.cache["ifTable"].setdefault(idx, {})["oper"] = int(val)

    async def _walk_ipv4(self) -> None:
        """Populate ipIndex/ipMask. Prefer legacy ipAdEnt*, else fallback to ipAddress+ipCidrRoute join."""
        ip_to_index: Dict[str, int | None] = {}
        ip_to_mask: Dict[str, str] = {}

        # ---- Legacy table first (preferred if present) ----
        legacy_addrs = await self._async_walk(OID_ipAdEntAddr)
        if legacy_addrs:
            for _oid, val in legacy_addrs:
                ip_to_index[str(val)] = None
            for oid, val in await self._async_walk(OID_ipAdEntIfIndex):
                parts = oid.split(".")[-4:]
                ip = ".".join(parts)
                ip_to_index[ip] = int(val)
            for oid, val in await self._async_walk(OID_ipAdEntNetMask):
                parts = oid.split(".")[-4:]
                ip = ".".join(parts)
                ip_to_mask[ip] = str(val)

            self.cache["ipIndex"] = ip_to_index
            self.cache["ipMask"] = ip_to_mask
            return

        # ---- Fallback: modern tables ----
        # 1) ipAddressIfIndex + ipAddressAddr -> ip -> ifIndex
        addr_map_suffix_to_ip: Dict[str, str] = {}
        for oid, val in await self._async_walk(_OID_ipAddressAddr):
            ip = _octets_to_ipv4(val)
            if not ip:
                continue  # skip IPv6/other
            suffix = oid[len(_OID_ipAddressAddr) + 1 :]
            addr_map_suffix_to_ip[suffix] = ip

        for oid, val in await self._async_walk(_OID_ipAddressIfIndex):
            suffix = oid[len(_OID_ipAddressIfIndex) + 1 :]
            ip = addr_map_suffix_to_ip.get(suffix)
            if not ip:
                continue
            ip_to_index[ip] = int(val)

        # 2) ipCidrRoutePrefixLength + ipCidrRouteIfIndex -> choose most specific prefix per ifIndex
        most_specific_bits: Dict[int, int] = {}
        bits_by_suffix: Dict[str, int] = {}
        for oid, val in await self._async_walk(_OID_ipCidrRoutePrefixLength):
            suffix = oid[len(_OID_ipCidrRoutePrefixLength) + 1 :]
            try:
                bits_by_suffix[suffix] = int(val)
            except Exception:
                continue

        for oid, val in await self._async_walk(_OID_ipCidrRouteIfIndex):
            suffix = oid[len(_OID_ipCidrRouteIfIndex) + 1 :]
            if_index = int(val)
            bits = bits_by_suffix.get(suffix)
            if bits is None:
                continue
            # keep the most specific prefix for this ifIndex
            prev = most_specific_bits.get(if_index, -1)
            if bits > prev:
                most_specific_bits[if_index] = bits

        # 3) Assign dotted masks to each IP based on its ifIndex' most specific prefix
        for ip, if_index in list(ip_to_index.items()):
            bits = most_specific_bits.get(if_index or -1)
            if bits is None:
                continue
            ip_to_mask[ip] = _bits_to_mask(bits)

        self.cache["ipIndex"] = ip_to_index
        self.cache["ipMask"] = ip_to_mask

    # ------------------ public helpers ------------------

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


# ------------------ helpers for config_flow ------------------

async def test_connection(hass: HomeAssistant, host: str, community: str, port: int) -> bool:
    client = SwitchSnmpClient(hass, host, community, port)
    sysname = await client._async_get_one(OID_sysName)
    return sysname is not None


async def get_sysname(hass: HomeAssistant, host: str, community: str, port: int) -> Optional[str]:
    client = SwitchSnmpClient(hass, host, community, port)
    return await client._async_get_one(OID_sysName)
