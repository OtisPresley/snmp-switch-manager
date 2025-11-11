from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

# pysnmp (lextudio) — pinned via manifest/const REQUIREMENTS
from pysnmp.hlapi import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    getCmd,
    nextCmd,
)
from pysnmp.smi.rfc1902 import Integer

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Errors & dependency guard
# ---------------------------------------------------------------------------

class SnmpDependencyError(RuntimeError):
    """Raised when pysnmp cannot be imported/used at runtime."""


class SnmpError(RuntimeError):
    """Generic SNMP runtime error."""


def ensure_snmp_available() -> None:
    """Minimal runtime check for pysnmp availability."""
    try:
        _ = SnmpEngine()  # touch engine so import/runtime issues surface
    except Exception as exc:  # pragma: no cover
        raise SnmpDependencyError(f"pysnmp.hlapi import failed: {exc}") from exc


# ---------------------------------------------------------------------------
# OIDs (IF-MIB, IP-MIB, SNMPv2-MIB system)
# ---------------------------------------------------------------------------

# System
SYS_DESCR = "1.3.6.1.2.1.1.1.0"
SYS_NAME = "1.3.6.1.2.1.1.5.0"
SYS_UPTIME = "1.3.6.1.2.1.1.3.0"

# IF-MIB
IF_DESCR = "1.3.6.1.2.1.2.2.1.2"
IF_SPEED = "1.3.6.1.2.1.2.2.1.5"
IF_ADMIN = "1.3.6.1.2.1.2.2.1.7"
IF_OPER = "1.3.6.1.2.1.2.2.1.8"
IF_ALIAS = "1.3.6.1.2.1.31.1.1.1.18"

# IP-MIB (legacy) — IPv4 only, but widely supported across switches
IP_ADDR      = "1.3.6.1.2.1.4.20.1.1"  # ipAdEntAddr
IP_IFINDEX   = "1.3.6.1.2.1.4.20.1.2"  # ipAdEntIfIndex
IP_NETMASK   = "1.3.6.1.2.1.4.20.1.3"  # ipAdEntNetMask


# ---------------------------------------------------------------------------
# Tiny helpers (only for IP display enrichment)
# ---------------------------------------------------------------------------

def _mask_to_prefix(mask: Optional[str]) -> Optional[int]:
    """Convert dotted mask to /prefix length, return None if unknown."""
    if not mask:
        return None
    try:
        octets = [int(x) for x in mask.split(".")]
        if len(octets) != 4 or any(o < 0 or o > 255 for o in octets):
            return None
        bits = "".join(f"{o:08b}" for o in octets)
        return bits.count("1")
    except Exception:
        return None


def _format_ip_display(ips: List[Tuple[str, Optional[str], Optional[int]]]) -> Optional[str]:
    """
    Given [(ip, mask, prefix_or_None), ...] return the first as 'a.b.c.d/yy'
    (or just 'a.b.c.d' if we cannot determine prefix).
    """
    if not ips:
        return None
    ip, mask, pfx = ips[0]
    if pfx is None:
        pfx = _mask_to_prefix(mask)
    return f"{ip}/{pfx}" if pfx is not None else ip


def _build_ip_index_map(
    host: str,
    port: int,
    community: str,
    walk_func,  # _snmp_walk
) -> Dict[int, List[Tuple[str, Optional[str], Optional[int]]]]:
    """
    Return { ifIndex: [(ip, mask, prefix_or_None), ...] } by walking legacy IP-MIB.
    """
    addr_rows = walk_func(host, port, community, IP_ADDR)
    ifidx_rows = walk_func(host, port, community, IP_IFINDEX)
    mask_rows = walk_func(host, port, community, IP_NETMASK)

    def _ip_from_oid(oid: str, base: str) -> Optional[str]:
        try:
            return ".".join(oid.split(".")[len(base.split(".")) :])
        except Exception:
            return None

    ip_to_ifidx: Dict[str, int] = {}
    ip_to_mask: Dict[str, str] = {}

    for oid, val in ifidx_rows:
        ip = _ip_from_oid(oid, IP_IFINDEX)
        if ip:
            try:
                ip_to_ifidx[ip] = int(val)
            except Exception:
                pass

    for oid, val in mask_rows:
        ip = _ip_from_oid(oid, IP_NETMASK)
        if ip:
            ip_to_mask[ip] = val

    idx_to_ips: Dict[int, List[Tuple[str, Optional[str], Optional[int]]]] = {}
    for _, ip in addr_rows:
        if ip in ip_to_ifidx:
            idx = ip_to_ifidx[ip]
            mask = ip_to_mask.get(ip)
            idx_to_ips.setdefault(idx, []).append((ip, mask, None))

    return idx_to_ips


# ---------------------------------------------------------------------------
# Low-level SNMP helpers
# ---------------------------------------------------------------------------

def _snmp_get(host: str, port: int, community: str, oid: str) -> Optional[str]:
    try:
        engine = SnmpEngine()
        target = UdpTransportTarget((host, port), timeout=2, retries=1)
        cdata = CommunityData(community, mpModel=1)  # SNMPv2c
        ctx = ContextData()

        error_indication, error_status, error_index, var_binds = next(
            getCmd(engine, cdata, target, ctx, ObjectType(ObjectIdentity(oid)))
        )
        if error_indication or error_status:
            return None
        for _, val in var_binds:
            return str(val.prettyPrint())
    except Exception as exc:  # pragma: no cover
        _LOGGER.debug("SNMP get error for %s: %s", oid, exc)
    return None


def _snmp_walk(host: str, port: int, community: str, base_oid: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    try:
        engine = SnmpEngine()
        target = UdpTransportTarget((host, port), timeout=2, retries=1)
        cdata = CommunityData(community, mpModel=1)
        ctx = ContextData()

        for (err_ind, err_stat, err_idx, vbs) in nextCmd(
            engine,
            cdata,
            target,
            ctx,
            ObjectType(ObjectIdentity(base_oid)),
            lexicographicMode=False,
        ):
            if err_ind or err_stat:
                break
            for name, val in vbs:
                out.append((str(name.prettyPrint()), str(val.prettyPrint())))
    except Exception as exc:  # pragma: no cover
        _LOGGER.debug("SNMP walk error for %s: %s", base_oid, exc)
    return out


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class SwitchSnmpClient:
    """Thin SNMP client used by the coordinator/sensors."""

    def __init__(self, hass, host: str, port: int, community: str) -> None:
        self._hass = hass
        self._host = host
        self._port = port
        self._community = community

    # Factory expected by config flow / setup
    @classmethod
    async def async_create(cls, hass, host: str, port: int, community: str) -> "SwitchSnmpClient":
        ensure_snmp_available()
        return cls(hass, host, port, community)

    # ----- System info for sensors -----

    async def async_get_system_info(self) -> Dict[str, Any]:
        def _read() -> Dict[str, Any]:
            sys_descr = _snmp_get(self._host, self._port, self._community, SYS_DESCR) or ""
            sys_name = _snmp_get(self._host, self._port, self._community, SYS_NAME) or ""
            sys_uptime = _snmp_get(self._host, self._port, self._community, SYS_UPTIME) or ""

            firmware = ""
            manufacturer_model = ""
            if sys_descr:
                parts = [p.strip() for p in sys_descr.split(",")]
                if len(parts) >= 2:
                    manufacturer_model = parts[0]
                    firmware = parts[1]
                else:
                    manufacturer_model = sys_descr

            # expose both raw ticks and a best-effort human string (sensor can pick)
            human = ""
            try:
                # sysUpTime is Timeticks: (NNN) 3 days, 10:11:12.34 or plain NNN
                if "days" in sys_uptime or ":" in sys_uptime:
                    human = sys_uptime.split(")")[1].strip() if ")" in sys_uptime else sys_uptime
                else:
                    human = sys_uptime
            except Exception:
                human = sys_uptime

            return {
                "sysDescr": sys_descr,
                "hostname": sys_name,
                "firmware": firmware,
                "manufacturer_model": manufacturer_model,
                "uptime_human": human,
                "uptime_ticks": sys_uptime,
            }

        return await self._hass.async_add_executor_job(_read)

    # ----- Interfaces / ports -----

    async def async_get_port_data(self) -> List[Dict[str, Any]]:
        """
        Return list of ports:
          {
            "index": int,
            "descr": str,
            "alias": str|None,
            "admin": int|None,
            "oper": int|None,
            "ips": [(ip, mask, None), ...],   # NEW
            "ip_display": "a.b.c.d/yy"        # NEW (if available)
          }
        """
        def _collect() -> List[Dict[str, Any]]:
            descr_rows = _snmp_walk(self._host, self._port, self._community, IF_DESCR)
            admin_rows = _snmp_walk(self._host, self._port, self._community, IF_ADMIN)
            oper_rows  = _snmp_walk(self._host, self._port, self._community, IF_OPER)
            alias_rows = _snmp_walk(self._host, self._port, self._community, IF_ALIAS)

            def _idx(oid: str) -> Optional[int]:
                try:
                    return int(oid.split(".")[-1])
                except Exception:
                    return None

            descr = { _idx(oid): val for oid, val in descr_rows if _idx(oid) is not None }
            admin = { _idx(oid): int(val) for oid, val in admin_rows if _idx(oid) is not None }
            oper  = { _idx(oid): int(val) for oid, val in oper_rows  if _idx(oid) is not None }
            alias = { _idx(oid): val for oid, val in alias_rows if _idx(oid) is not None }

            # Build IP mapping once
            idx_to_ips = _build_ip_index_map(self._host, self._port, self._community, _snmp_walk)

            ports: List[Dict[str, Any]] = []
            for idx in sorted(descr.keys()):
                # Skip CPU interface 661 (not user-configurable)
                if idx == 661:
                    continue

                p: Dict[str, Any] = {
                    "index": idx,
                    "descr": descr.get(idx, ""),
                    "alias": alias.get(idx),
                    "admin": admin.get(idx),
                    "oper":  oper.get(idx),
                }

                # NEW: attach IP tuples and a preformatted display value
                p["ips"] = idx_to_ips.get(idx, [])
                ip_disp = _format_ip_display(p["ips"])
                if ip_disp:
                    p["ip_display"] = ip_disp

                ports.append(p)

            return ports

        return await self._hass.async_add_executor_job(_collect)

    # ----- Admin state write (best effort; requires write community) -----

    async def async_set_admin_state(self, if_index: int, admin_up: bool) -> None:
        value = 1 if admin_up else 2

        def _write() -> None:
            try:
                engine = SnmpEngine()
                target = UdpTransportTarget((self._host, self._port), timeout=2, retries=1)
                cdata = CommunityData(self._community, mpModel=1)
                ctx = ContextData()
                oid = f"{IF_ADMIN}.{if_index}"
                err_ind, err_stat, err_idx, _ = next(
                    getCmd(engine, cdata, target, ctx, ObjectType(ObjectIdentity(oid), Integer(value)))
                )
                if err_ind or err_stat:
                    _LOGGER.debug("SNMP set ifAdminStatus failed: %s %s", err_ind, err_stat)
            except Exception as exc:  # pragma: no cover
                _LOGGER.debug("SNMP set error: %s", exc)

        await self._hass.async_add_executor_job(_write)
