from __future__ import annotations

import asyncio
import importlib
import logging
import re
from typing import Iterable, Tuple, Any, Optional, Dict, List

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "SnmpError",
    "SnmpDependencyError",
    "SwitchSnmpClient",
    "ensure_snmp_available",
    "validate_environment_or_raise",
    "reset_backend_cache",
    "snmp_get",
    "snmp_walk",
    "snmp_set_octet_string",
]

class SnmpError(RuntimeError):
    pass

class SnmpDependencyError(SnmpError):
    pass

_IMPORTS_CACHE: Optional[tuple] = None

def _imports():
    global _IMPORTS_CACHE
    if _IMPORTS_CACHE is not None:
        return _IMPORTS_CACHE
    try:
        pysnmp_mod = importlib.import_module("pysnmp")
        _LOGGER.debug(
            "Switch Manager using pysnmp from %s (version=%s)",
            getattr(pysnmp_mod, "__file__", "?"),
            getattr(pysnmp_mod, "__version__", "?"),
        )
        from pysnmp.hlapi import (  # type: ignore
            SnmpEngine,
            CommunityData,
            UdpTransportTarget,
            ContextData,
            ObjectType,
            ObjectIdentity,
            getCmd,
            nextCmd,
            setCmd,
        )
    except Exception as e:
        raise SnmpDependencyError(f"pysnmp.hlapi import failed: {e}")
    _IMPORTS_CACHE = (
        SnmpEngine,
        CommunityData,
        UdpTransportTarget,
        ContextData,
        ObjectType,
        ObjectIdentity,
        getCmd,
        nextCmd,
        setCmd,
    )
    return _IMPORTS_CACHE

def reset_backend_cache() -> None:
    global _IMPORTS_CACHE
    _IMPORTS_CACHE = None

def ensure_snmp_available() -> None:
    _imports()

def validate_environment_or_raise() -> None:
    ensure_snmp_available()

def snmp_get(host: str, community: str, port: int, oid: str) -> Any:
    (SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
     ObjectType, ObjectIdentity, getCmd, _nextCmd, _setCmd) = _imports()
    iterator = getCmd(
        SnmpEngine(),
        CommunityData(community, mpModel=1),
        UdpTransportTarget((host, int(port))),
        ContextData(),
        ObjectType(ObjectIdentity(oid)),
    )
    ei, es, ei_idx, vb = next(iterator)
    if ei:
        raise SnmpError(ei)
    if es:
        where = vb[int(ei_idx) - 1][0] if ei_idx else "?"
        raise SnmpError(f"{es.prettyPrint()} at {where}")
    return vb[0][1]

def snmp_walk(host: str, community: str, port: int, base_oid: str) -> Iterable[Tuple[str, Any]]:
    (SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
     ObjectType, ObjectIdentity, _getCmd, nextCmd, _setCmd) = _imports()
    for (ei, es, ei_idx, vb) in nextCmd(
        SnmpEngine(),
        CommunityData(community, mpModel=1),
        UdpTransportTarget((host, int(port))),
        ContextData(),
        ObjectType(ObjectIdentity(base_oid)),
        lexicographicMode=False,
    ):
        if ei:
            raise SnmpError(ei)
        if es:
            where = vb[int(ei_idx) - 1][0] if ei_idx else "?"
            raise SnmpError(f"{es.prettyPrint()} at {where}")
        for name, val in vb:
            yield (str(name), val)

def snmp_set_octet_string(host: str, community: str, port: int, oid: str, value) -> None:
    (SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
     ObjectType, ObjectIdentity, _getCmd, _nextCmd, setCmd) = _imports()
    ei, es, ei_idx, vb = next(
        setCmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            UdpTransportTarget((host, int(port))),
            ContextData(),
            ObjectType(ObjectIdentity(oid), value),
        )
    )
    if ei:
        raise SnmpError(ei)
    if es:
        where = vb[int(ei_idx) - 1][0] if ei_idx else "?"
        raise SnmpError(f"{es.prettyPrint()} at {where}")

class SwitchSnmpClient:
    # IF-MIB
    OID_ifDescr        = "1.3.6.1.2.1.2.2.1.2"
    OID_ifAdminStatus  = "1.3.6.1.2.1.2.2.1.7"
    OID_ifOperStatus   = "1.3.6.1.2.1.2.2.1.8"
    OID_ifAlias        = "1.3.6.1.2.1.31.1.1.1.18"
    # SNMPv2-MIB::system
    OID_sysDescr       = "1.3.6.1.2.1.1.1.0"
    OID_sysObjectID    = "1.3.6.1.2.1.1.2.0"
    OID_sysUpTime      = "1.3.6.1.2.1.1.3.0"
    OID_sysName        = "1.3.6.1.2.1.1.5.0"
    # IP-MIB (IPv4)
    OID_ipAdEntAddr    = "1.3.6.1.2.1.4.20.1.1"
    OID_ipAdEntIfIndex = "1.3.6.1.2.1.4.20.1.2"
    OID_ipAdEntNetMask = "1.3.6.1.2.1.4.20.1.3"

    def __init__(self, hass, host: str, community: str, port: int = 161) -> None:
        self._hass = hass
        self._host = host
        self._community = community
        self._port = int(port)

    @classmethod
    async def async_create(cls, *args):
        hass = None
        host = ""
        community = ""
        port = 161
        if not args:
            raise SnmpError("async_create requires arguments")
        first = args[0]
        if hasattr(first, "async_add_executor_job"):
            hass = first
            host = args[1]; community = args[2]; port = int(args[3]) if len(args) > 3 else 161
        else:
            host = args[0]; community = args[1]; port = int(args[2]) if len(args) > 2 else 161
            hass = args[3] if len(args) > 3 and hasattr(args[3], "async_add_executor_job") else None
        if hass is not None:
            await hass.async_add_executor_job(ensure_snmp_available)
        else:
            ensure_snmp_available()
        return cls(hass, host, community, port)

    def get(self, oid: str) -> Any:
        return snmp_get(self._host, self._community, self._port, oid)

    def walk(self, base_oid: str) -> Iterable[Tuple[str, Any]]:
        return snmp_walk(self._host, self._community, self._port, base_oid)

    def set_octet_string(self, oid: str, value) -> None:
        snmp_set_octet_string(self._host, self._community, self._port, oid, value)

    async def async_get(self, oid: str) -> Any:
        if self._hass is not None:
            return await self._hass.async_add_executor_job(
                snmp_get, self._host, self._community, self._port, oid
            )
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, snmp_get, self._host, self._community, self._port, oid)

    async def async_walk(self, base_oid: str) -> Iterable[Tuple[str, Any]]:
        if self._hass is not None:
            return await self._hass.async_add_executor_job(
                lambda: list(snmp_walk(self._host, self._community, self._port, base_oid))
            )
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: list(snmp_walk(self._host, self._community, self._port, base_oid)))

    async def async_set_octet_string(self, oid: str, value) -> None:
        if self._hass is not None:
            await self._hass.async_add_executor_job(
                snmp_set_octet_string, self._host, self._community, self._port, oid, value
            )
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, snmp_set_octet_string, self._host, self._community, self._port, oid, value)

    def _get_ipv4_table(self) -> Dict[int, List[Dict[str, str]]]:
        """Build { ifIndex: [ {address, netmask}, ... ] } from IP-MIB ipAddrTable."""
        by_addr_if = {str(addr): int(idx) for addr, idx in self.walk(self.OID_ipAdEntIfIndex)}
        by_addr_mask = {str(addr): str(mask) for addr, mask in self.walk(self.OID_ipAdEntNetMask)}
        result: Dict[int, List[Dict[str, str]]] = {}
        for addr, ifindex in by_addr_if.items():
            result.setdefault(ifindex, []).append({
                "address": addr,
                "netmask": by_addr_mask.get(addr, ""),
            })
        return result

    def get_port_data(self) -> Dict[int, Dict[str, Any]]:
        """Return dict keyed by ifIndex with: index,name,admin,oper,alias,ipv4(list)."""
        descr = {int(oid.split(".")[-1]): str(val) for oid, val in self.walk(self.OID_ifDescr)}
        admin = {int(oid.split(".")[-1]): int(val) for oid, val in self.walk(self.OID_ifAdminStatus)}
        oper  = {int(oid.split(".")[-1]): int(val) for oid, val in self.walk(self.OID_ifOperStatus)}
        alias = {int(oid.split(".")[-1]): str(val) for oid, val in self.walk(self.OID_ifAlias)}
        ipv4  = self._get_ipv4_table()
        indices = set(descr) | set(admin) | set(oper) | set(alias) | set(ipv4)
        out: Dict[int, Dict[str, Any]] = {}
        for idx in sorted(indices):
            out[idx] = {
                "index": idx,
                "name": descr.get(idx, ""),
                "admin": admin.get(idx, 0),
                "oper": oper.get(idx, 0),
                "alias": alias.get(idx, ""),
                "ipv4": ipv4.get(idx, []),
            }
        return out

    async def async_get_port_data(self) -> Dict[int, Dict[str, Any]]:
        if self._hass is not None:
            return await self._hass.async_add_executor_job(self.get_port_data)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.get_port_data)

    @staticmethod
    def _parse_sys_fields(sys_descr: str) -> Dict[str, str]:
        """
        Parse 'Dell EMC Networking N3048EP-ON, 6.7.1.31, Linux 4.14.174, v1.0.5'
        -> manufacturer+model='Dell EMC Networking N3048EP-ON', firmware='6.7.1.31'
        """
        manufacturer = ""
        model = ""
        firmware = ""
        mmm = sys_descr.split(",", 1)[0].strip()
        if mmm:
            manufacturer = " ".join(mmm.split()[:-1]) or mmm
            model = mmm.split()[-1] if " " in mmm else ""
        mfw = re.search(r"\b\d+\.\d+(?:\.\d+){0,2}\b", sys_descr)
        if mfw:
            firmware = mfw.group(0)
        return {"manufacturer": manufacturer, "model": model, "firmware": firmware}

    @staticmethod
    def _format_uptime(ticks: int) -> str:
        # ticks are hundredths of a second
        total_centis = int(ticks)
        total_secs = total_centis // 100
        days, rem = divmod(total_secs, 86400)
        hours, rem = divmod(rem, 3600)
        mins, secs = divmod(rem, 60)
        centis = total_centis % 100
        return f"{days} days, {hours:02d}:{mins:02d}:{secs:02d}.{centis:02d}"

    def get_system_info(self) -> Dict[str, Any]:
        sys_descr = str(self.get(self.OID_sysDescr))
        sys_object_id = str(self.get(self.OID_sysObjectID))
        sys_name = str(self.get(self.OID_sysName))
        uptime_ticks = int(self.get(self.OID_sysUpTime))
        uptime_seconds = int(uptime_ticks // 100)
        fields = self._parse_sys_fields(sys_descr)
        return {
            **fields,
            "hostname": sys_name,
            "uptime_seconds": uptime_seconds,
            "uptime_ticks": uptime_ticks,
            "uptime": self._format_uptime(uptime_ticks),
            "sys_descr": sys_descr,
            "sys_object_id": sys_object_id,
        }

    async def async_get_system_info(self) -> Dict[str, Any]:
        if self._hass is not None:
            return await self._hass.async_add_executor_job(self.get_system_info)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.get_system_info)
