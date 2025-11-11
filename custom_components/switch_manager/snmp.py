from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from pysnmp.hlapi import (  # pinned via manifest/const
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

# -----------------------------------------------------------------------------
# Exceptions / dependency check (names kept exactly as before)
# -----------------------------------------------------------------------------

class SnmpDependencyError(RuntimeError):
    """Raised when pysnmp cannot be used at runtime."""


class SnmpError(RuntimeError):
    """Generic SNMP runtime error."""


def ensure_snmp_available() -> None:
    """Raise SnmpDependencyError if pysnmp is not usable."""
    try:
        _ = SnmpEngine()
    except Exception as exc:  # pragma: no cover
        raise SnmpDependencyError(f"pysnmp.hlapi import failed: {exc}") from exc


# -----------------------------------------------------------------------------
# OIDs (same families you were using)
# -----------------------------------------------------------------------------

# SNMPv2-MIB (system)
SYS_DESCR = "1.3.6.1.2.1.1.1.0"
SYS_NAME = "1.3.6.1.2.1.1.5.0"
SYS_UPTIME = "1.3.6.1.2.1.1.3.0"

# IF-MIB
IF_DESCR = "1.3.6.1.2.1.2.2.1.2"
IF_SPEED = "1.3.6.1.2.1.2.2.1.5"
IF_ADMIN = "1.3.6.1.2.1.2.2.1.7"
IF_OPER = "1.3.6.1.2.1.2.2.1.8"
IF_ALIAS = "1.3.6.1.2.1.31.1.1.1.18"

# Legacy IP-MIB (IPv4) — widely supported and sufficient for SVIs/loopback
IP_ADDR    = "1.3.6.1.2.1.4.20.1.1"  # ipAdEntAddr
IP_IFINDEX = "1.3.6.1.2.1.4.20.1.2"  # ipAdEntIfIndex
IP_NETMASK = "1.3.6.1.2.1.4.20.1.3"  # ipAdEntNetMask


# -----------------------------------------------------------------------------
# Internal helpers (kept local; no public contract changes)
# -----------------------------------------------------------------------------

def _snmp_get(host: str, port: int, community: str, oid: str) -> Optional[str]:
    try:
        engine = SnmpEngine()
        target = UdpTransportTarget((host, port), timeout=2, retries=1)
        cdata = CommunityData(community, mpModel=1)  # SNMPv2c
        ctx = ContextData()
        error_indication, error_status, _, var_binds = next(
            getCmd(engine, cdata, target, ctx, ObjectType(ObjectIdentity(oid)))
        )
        if error_indication or error_status:
            return None
        for _, val in var_binds:
            return str(val.prettyPrint())
    except Exception as exc:  # pragma: no cover
        _LOGGER.debug("SNMP get error (%s): %s", oid, exc)
    return None


def _snmp_walk(host: str, port: int, community: str, base_oid: str) -> List[Tuple[str, str]]:
    """Return [(oid, value), ...] under base_oid."""
    rows: List[Tuple[str, str]] = []
    try:
        engine = SnmpEngine()
        target = UdpTransportTarget((host, port), timeout=2, retries=1)
        cdata = CommunityData(community, mpModel=1)
        ctx = ContextData()
        for (err_ind, err_stat, _, vbs) in nextCmd(
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
                rows.append((str(name.prettyPrint()), str(val.prettyPrint())))
    except Exception as exc:  # pragma: no cover
        _LOGGER.debug("SNMP walk error (%s): %s", base_oid, exc)
    return rows


# --- IPv4 adornment (surgical) ------------------------------------------------

def _mask_to_prefix(mask: Optional[str]) -> Optional[int]:
    if not mask:
        return None
    try:
        octs = [int(x) for x in mask.split(".")]
        if len(octs) != 4 or any(o < 0 or o > 255 for o in octs):
            return None
        bits = "".join(f"{o:08b}" for o in octs)
        return bits.count("1")
    except Exception:
        return None


def _format_ip_display(ips: List[Tuple[str, Optional[str], Optional[int]]]) -> Optional[str]:
    """Use the first IP for a simple 'a.b.c.d/yy' (or just IP) attribute."""
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
) -> Dict[int, List[Tuple[str, Optional[str], Optional[int]]]]:
    """
    Legacy IPv4 table → { ifIndex: [(ip, mask, prefix_or_None), ...] }.
    """
    addr_rows = _snmp_walk(host, port, community, IP_ADDR)
    ifidx_rows = _snmp_walk(host, port, community, IP_IFINDEX)
    mask_rows = _snmp_walk(host, port, community, IP_NETMASK)

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


# -----------------------------------------------------------------------------
# Client (public names/signatures kept exactly the same)
# -----------------------------------------------------------------------------

class SwitchSnmpClient:
    """Thin SNMP client used by coordinator/sensors."""

    def __init__(self, hass, host: str, port: int, community: str) -> None:
        self._hass = hass
        self._host = host
        self._port = port
        self._community = community

    @classmethod
    async def async_create(cls, hass, host: str, port: int, community: str) -> "SwitchSnmpClient":
        ensure_snmp_available()
        return cls(hass, host, port, community)

    async def async_get_system_info(self) -> Dict[str, Any]:
        """Return system details for sensors (unchanged keys)."""

        def _read() -> Dict[str, Any]:
            sys_descr = _snmp_get(self._host, self._port, self._community, SYS_DESCR) or ""
            sys_name = _snmp_get(self._host, self._port, self._community, SYS_NAME) or ""
            sys_uptime = _snmp_get(self._host, self._port, self._community, SYS_UPTIME) or ""

            firmware = ""
            manufacturer_model = sys_descr
            try:
                parts = [p.strip() for p in sys_descr.split(",")]
                if len(parts) >= 2:
                    manufacturer_model = parts[0]
                    firmware = parts[1]
            except Exception:
                pass

            human = ""
            try:
                # Timeticks: (341184840) 39 days, 11:44:08.40
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

    async def async_get_port_data(self) -> List[Dict[str, Any]]:
        """
        Return list of port dicts; keys preserved from your working build:
          index, descr, alias, admin, oper, plus:
          - ips: [(ip, mask, None), ...]
          - ip_display: 'a.b.c.d/yy'   (if derivable)
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

            # IP adornment (NEW; does not change existing keys)
            idx_to_ips = _build_ip_index_map(self._host, self._port, self._community)

            ports: List[Dict[str, Any]] = []
            for idx in sorted(descr.keys()):
                # Skip CPU interface (not user configurable)
                if idx == 661:
                    continue

                p: Dict[str, Any] = {
                    "index": idx,
                    "descr": descr.get(idx, ""),
                    "alias": alias.get(idx),
                    "admin": admin.get(idx),
                    "oper":  oper.get(idx),
                }

                ips = idx_to_ips.get(idx, [])
                if ips:
                    p["ips"] = ips
                    disp = _format_ip_display(ips)
                    if disp:
                        p["ip_display"] = disp

                ports.append(p)

            return ports

        return await self._hass.async_add_executor_job(_collect)

    async def async_set_admin_state(self, if_index: int, admin_up: bool) -> None:
        """Set ifAdminStatus (requires write community on device)."""
        value = 1 if admin_up else 2

        def _write() -> None:
            try:
                engine = SnmpEngine()
                target = UdpTransportTarget((self._host, self._port), timeout=2, retries=1)
                cdata = CommunityData(self._community, mpModel=1)
                ctx = ContextData()
                oid = f"{IF_ADMIN}.{if_index}"
                err_ind, err_stat, _, _ = next(
                    getCmd(engine, cdata, target, ctx, ObjectType(ObjectIdentity(oid), Integer(value)))
                )
                if err_ind or err_stat:
                    _LOGGER.debug("SNMP set ifAdminStatus failed: %s %s", err_ind, err_stat)
            except Exception as exc:  # pragma: no cover
                _LOGGER.debug("SNMP set error: %s", exc)

        await self._hass.async_add_executor_job(_write)
