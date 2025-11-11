from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Iterable, Tuple, List

from homeassistant.core import HomeAssistant

# Use synchronous HLAPI (no dependency change) and offload to executor.
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
    OID_entPhysicalModelName,
)

_LOGGER = logging.getLogger(__name__)


def _do_get_one(engine, community, target, context, oid: str) -> Optional[str]:
    it = getCmd(engine, community, target, context, ObjectType(ObjectIdentity(oid)))
    err_ind, err_stat, err_idx, vbs = next(it)
    if err_ind or err_stat:
        return None
    return str(vbs[0][1])


def _do_next_walk(engine, community, target, context, base_oid: str) -> Iterable[Tuple[str, Any]]:
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


def _do_set_alias(engine, community, target, context, if_index: int, alias: str) -> bool:
    it = setCmd(
        engine,
        community,
        target,
        context,
        ObjectType(ObjectIdentity(f"{OID_ifAlias}.{if_index}"), OctetString(alias)),
    )
    err_ind, err_stat, err_idx, _ = next(it)
    return (not err_ind) and (not err_stat)


def _do_set_admin_status(engine, community, target, context, if_index: int, value: int) -> bool:
    it = setCmd(
        engine,
        community,
        target,
        context,
        ObjectType(ObjectIdentity(f"1.3.6.1.2.1.2.2.1.7.{if_index}"), Integer(value)),
    )
    err_ind, err_stat, err_idx, _ = next(it)
    return (not err_ind) and (not err_stat)


class SwitchSnmpClient:
    """SNMP client using sync HLAPI in an executor; exposes async interface."""

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
            "ifTable": {},
            "ipIndex": {},
            "ipMask": {},
            # parsed fields for diagnostics:
            "manufacturer": None,
            "model": None,
            "firmware": None,
        }

    async def async_initialize(self) -> None:
        self.cache["sysDescr"] = await self._async_get_one(OID_sysDescr)
        self.cache["sysName"] = await self._async_get_one(OID_sysName)
        self.cache["sysUpTime"] = await self._async_get_one(OID_sysUpTime)

        # Pull model from ENTITY-MIB if available (pick a base chassis entry).
        ent_models = await self._async_walk(OID_entPhysicalModelName)
        model_hint = None
        for _oid, val in ent_models:
            s = str(val).strip()
            if s:
                model_hint = s
                break
        self.cache["model"] = model_hint

        # Parse Manufacturer & Firmware Revision from sysDescr string if present
        sd = (self.cache.get("sysDescr") or "").strip()
        manufacturer = None
        firmware = None
        if sd:
            parts = [p.strip() for p in sd.split(",")]
            if len(parts) >= 2:
                firmware = parts[1] or None
            head = parts[0]
            if model_hint and model_hint in head:
                manufacturer = head.replace(model_hint, "").strip()
            else:
                toks = head.split()
                if len(toks) > 1:
                    manufacturer = " ".join(toks[:-1])
        self.cache["manufacturer"] = manufacturer
        self.cache["firmware"] = firmware

        await self._async_walk_interfaces()
        await self._async_walk_ipv4()

    async def async_poll(self) -> Dict[str, Any]:
        await self._async_walk_interfaces(dynamic_only=True)
        await self._async_walk_ipv4()
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

    async def _async_walk_interfaces(self, dynamic_only: bool = False) -> None:
        if not dynamic_only:
            self.cache["ifTable"] = {}

            for oid, val in await self._async_walk(OID_ifIndex):
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

    async def _async_walk_ipv4(self) -> None:
        """
        Populate IPv4 maps for attributes.
        1) Fill from legacy IP-MIB (ipAdEnt*) if present (keeps existing behavior).
        2) Add IPv4s by parsing IP from ipAddressIfIndex (1.3.6.1.2.1.4.34.1.3)
           where instance suffix is: 1.4.a.b.c.d = ifIndex
        3) Add IPv4s from OSPF-MIB ospfIfIpAddress (1.3.6.1.2.1.14.8.1.1)
           where suffix is: a.b.c.d.<ifIndex>.<area...> = a.b.c.d
        4) Resolve mask bits by parsing route prefixes from IP-FORWARD-MIB
           (1.3.6.1.2.1.4.24.7.1.9) – instance carries dest IPv4 and prefixLen:
             ... .1.4.<a>.<b>.<c>.<d>.<prefixLen>.2.0.0.1.4.<nextHop...>
           Choose the most specific network that contains each IP.
        """
        ip_index: Dict[str, int] = {}
        ip_mask: Dict[str, str] = {}  # may be filled only by step 1 or 4

        # ---- (1) Legacy table: ipAdEnt* ----
        legacy_addrs = await self._async_walk(OID_ipAdEntAddr)
        if legacy_addrs:
            for _oid, val in legacy_addrs:
                ip_index[str(val)] = None  # type: ignore[assignment]

            for oid, val in await self._async_walk(OID_ipAdEntIfIndex):
                parts = oid.split(".")[-4:]
                ip = ".".join(parts)
                try:
                    ip_index[ip] = int(val)
                except Exception:
                    continue

            for oid, val in await self._async_walk(OID_ipAdEntNetMask):
                parts = oid.split(".")[-4:]
                ip = ".".join(parts)
                ip_mask[ip] = str(val)

            # We intentionally do NOT return here; continue collecting more IPs below.

        # ---- (2) Modern: parse IP from the OID of ipAddressIfIndex ----
        OID_ipAddressIfIndex = "1.3.6.1.2.1.4.34.1.3"
        try:
            for oid, val in await self._async_walk(OID_ipAddressIfIndex):
                try:
                    suffix = oid[len(OID_ipAddressIfIndex) + 1 :]  # ".1.4.a.b.c.d"
                    parts = [int(x) for x in suffix.split(".")]
                    if len(parts) >= 6 and parts[0] == 1 and parts[1] == 4:
                        a, b, c, d = parts[2], parts[3], parts[4], parts[5]
                        ip = f"{a}.{b}.{c}.{d}"
                        ip_index.setdefault(ip, int(val))
                except Exception:
                    continue
        except Exception:
            pass  # table may be absent; ignore quietly

        # ---- (3) OSPF: loopbacks exposed via ospfIfIpAddress ----
        OID_ospfIfIpAddress = "1.3.6.1.2.1.14.8.1.1"
        try:
            for oid, val in await self._async_walk(OID_ospfIfIpAddress):
                try:
                    suffix = oid[len(OID_ospfIfIpAddress) + 1 :]
                    parts = [int(x) for x in suffix.split(".")]
                    if len(parts) >= 5:
                        a, b, c, d = parts[0], parts[1], parts[2], parts[3]
                        if_index = parts[4]
                        ip = f"{a}.{b}.{c}.{d}"
                        ip_index.setdefault(ip, int(if_index))
                except Exception:
                    continue
        except Exception:
            pass  # OSPF MIB may be absent

        # ---- (4) Derive mask bits from IP-FORWARD-MIB route index (vendor flavor) ----
        # We parse destinations/prefixLen from the INSTANCE of 1.3.6.1.2.1.4.24.7.1.9
        # (any column in that table shares the same index; .9 works well)
        OID_routeCol = "1.3.6.1.2.1.4.24.7.1.9"

        def _bits_to_mask(bits: int) -> str:
            if bits <= 0:
                return "0.0.0.0"
            if bits >= 32:
                return "255.255.255.255"
            mask = (0xFFFFFFFF << (32 - bits)) & 0xFFFFFFFF
            return ".".join(str((mask >> s) & 0xFF) for s in (24, 16, 8, 0))

        def _ip_to_int(ip: str) -> int:
            a, b, c, d = (int(x) for x in ip.split("."))
            return (a << 24) | (b << 16) | (c << 8) | d

        def _int_to_ip(x: int) -> str:
            return ".".join(str((x >> s) & 0xFF) for s in (24, 16, 8, 0))

        # Collect list of (network_int, bits)
        route_prefixes: List[Tuple[int, int]] = []
        try:
            for oid, _val in await self._async_walk(OID_routeCol):
                try:
                    suffix = oid[len(OID_routeCol) + 1 :]  # "...1.4.a.b.c.d.bits.2.0.0.1.4.x.x.x.x"
                    parts = [int(x) for x in suffix.split(".")]
                    # Find a '1,4' pair then 4 octets and a plausible bits (0..32)
                    for i in range(len(parts) - 6):
                        if parts[i] == 1 and parts[i + 1] == 4:
                            a, b, c, d = parts[i + 2 : i + 6]
                            bits = parts[i + 6] if i + 6 < len(parts) else None
                            if bits is None or bits < 0 or bits > 32:
                                continue
                            net_int = _ip_to_int(f"{a}.{b}.{c}.{d}")
                            route_prefixes.append((net_int, bits))
                            break
                except Exception:
                    continue
        except Exception:
            pass  # table may be absent; that's okay

        # Choose the most specific matching prefix for each discovered IP
        if route_prefixes and ip_index:
            # Sort prefixes by descending specificity once
            route_prefixes.sort(key=lambda t: t[1], reverse=True)
            for ip in ip_index.keys():
                ip_int = _ip_to_int(ip)
                # pick first (i.e., most specific) whose network contains ip
                for net_int, bits in route_prefixes:
                    mask_int = (0xFFFFFFFF << (32 - bits)) & 0xFFFFFFFF if bits else 0
                    if bits == 0 or (ip_int & mask_int) == (net_int & mask_int):
                        ip_mask[ip] = _bits_to_mask(bits)
                        break

        # Commit findings
        if ip_index:
            self.cache["ipIndex"] = ip_index
        if ip_mask:
            self.cache["ipMask"] = ip_mask

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


# ---------- helpers for config_flow ----------

async def test_connection(hass: HomeAssistant, host: str, community: str, port: int) -> bool:
    client = SwitchSnmpClient(hass, host, community, port)
    sysname = await client._async_get_one(OID_sysName)
    return sysname is not None


async def get_sysname(hass: HomeAssistant, host: str, community: str, port: int) -> Optional[str]:
    client = SwitchSnmpClient(hass, host, community, port)
    return await client._async_get_one(OID_sysName)
