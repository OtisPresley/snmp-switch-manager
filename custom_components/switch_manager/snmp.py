from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Iterable, Tuple

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
        2) If needed, add IPv4s by parsing IP from ipAddressIfIndex (1.3.6.1.2.1.4.34.1.3)
           where instance suffix is: 1.4.a.b.c.d = ifIndex
        3) If still missing (e.g., Loopback), add IPv4s from OSPF-MIB ospfIfIpAddress
           (1.3.6.1.2.1.14.8.1.1) where suffix is: a.b.c.d.<ifIndex>.<area...>
        No mask bits are computed in 2) or 3) – we only add IPs.
        """
        ip_index: Dict[str, int] = {}
        ip_mask: Dict[str, str] = {}  # left untouched unless legacy provides it

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

            self.cache["ipIndex"] = ip_index
            self.cache["ipMask"] = ip_mask
            return

        # ---- (2) Modern fallback: parse IP from the OID of ipAddressIfIndex only ----
        OID_ipAddressIfIndex = "1.3.6.1.2.1.4.34.1.3"
        for oid, val in await self._async_walk(OID_ipAddressIfIndex):
            try:
                suffix = oid[len(OID_ipAddressIfIndex) + 1 :]  # ".1.4.a.b.c.d"
                parts = [int(x) for x in suffix.split(".")]
                if len(parts) >= 6 and parts[0] == 1 and parts[1] == 4:
                    a, b, c, d = parts[2], parts[3], parts[4], parts[5]
                    ip = f"{a}.{b}.{c}.{d}"
                    ip_index[ip] = int(val)
            except Exception:
                continue

        # ---- (3) OSPF fallback for devices that expose loopbacks via OSPF-MIB ----
        # ospfIfIpAddress: 1.3.6.1.2.1.14.8.1.1.<a>.<b>.<c>.<d>.<ifIndex>.<area...> = IpAddress a.b.c.d
        OID_ospfIfIpAddress = "1.3.6.1.2.1.14.8.1.1"
        try:
            for oid, val in await self._async_walk(OID_ospfIfIpAddress):
                try:
                    suffix = oid[len(OID_ospfIfIpAddress) + 1 :]
                    parts = [int(x) for x in suffix.split(".")]
                    # Accept both "a.b.c.d.ifIndex.0" and "a.b.c.d.ifIndex.0.0.0.0" encodings
                    if len(parts) >= 5:
                        a, b, c, d = parts[0], parts[1], parts[2], parts[3]
                        if_index = parts[4]
                        ip = f"{a}.{b}.{c}.{d}"
                        # Only add if not already present
                        if ip not in ip_index:
                            ip_index[ip] = int(if_index)
                except Exception:
                    continue
        except Exception:
            # OSPF MIB might not be present; ignore quietly
            pass

        # Save what we discovered; leave ipMask untouched (no mask bits here)
        if ip_index:
            self.cache["ipIndex"] = ip_index

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
