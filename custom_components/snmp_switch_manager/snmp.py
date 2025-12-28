from __future__ import annotations

import asyncio
import time
import logging
from typing import Any, Dict, Optional, Iterable, Tuple, List

from homeassistant.core import HomeAssistant

from .snmp_compat import (
    CommunityData,
    SnmpEngine,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    get_cmd,
    next_cmd,
    set_cmd,
    OctetString,
    Integer,
)

# Canonical OIDs from const.py (original repo)
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
    OID_ifSpeed,
    OID_ifHighSpeed,
    OID_dot1dBasePortIfIndex,
    OID_dot1qPvid,
    OID_ipAdEntAddr,
    OID_ipAdEntIfIndex,
    OID_ipAdEntNetMask,
    OID_entPhysicalModelName,
    OID_entPhysicalSoftwareRev_CBS350,
    OID_mikrotik_software_version,
    OID_mikrotik_model,
    OID_entPhysicalMfgName_Zyxel,
    OID_zyxel_firmware_version,
    OID_ifInOctets,
    OID_ifOutOctets,
    OID_ifHCInOctets,
    OID_ifHCOutOctets,
    CONF_BW_ENABLE,
    CONF_BW_INCLUDE_STARTS_WITH,
    CONF_BW_INCLUDE_CONTAINS,
    CONF_BW_INCLUDE_ENDS_WITH,
    CONF_BW_EXCLUDE_STARTS_WITH,
    CONF_BW_EXCLUDE_CONTAINS,
    CONF_BW_EXCLUDE_ENDS_WITH,
    CONF_BANDWIDTH_POLL_INTERVAL,
    DEFAULT_BANDWIDTH_POLL_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

# Extra OIDs used in the original repo’s IP logic (not in const.py)
# (2) ipAddressIfIndex index suffix encodes IPv4 as: 1.4.a.b.c.d
OID_ipAddressIfIndex = "1.3.6.1.2.1.4.34.1.3"
# (3) OSPF-MIB ip address (suffix carries a.b.c.d.<ifIndex>.<area...>)
OID_ospfIfIpAddress = "1.3.6.1.2.1.14.8.1.1"
# (4) IP-FORWARD-MIB route column – instance includes dest + prefixLen (vendor-variant index)
# we read column 9 (.9) because any column shares the same index layout
OID_routeCol = "1.3.6.1.2.1.4.24.7.1.9"


# ---------- low-level sync helpers offloaded by compat -------------

async def _do_get_one(engine, community, target, context, oid: str) -> Optional[str]:
    err_ind, err_stat, err_idx, vbs = await get_cmd(
        engine,
        community,
        target,
        context,
        ObjectType(ObjectIdentity(oid)),
        lookupMib=False,  # <<< prevent FS MIB access
    )
    if err_ind or err_stat:
        return None
    for vb in vbs:
        return str(vb[1])
    return None


async def _do_get_many(engine, community, target, context, oids: list[str]) -> Dict[str, Optional[str]]:
    """Fetch many OIDs, chunked to avoid oversized PDUs.

    Returns a mapping of oid string -> value string (or None).
    """

    out: Dict[str, Optional[str]] = {oid: None for oid in oids}
    if not oids:
        return out

    async def _fetch_chunk(chunk: list[str]) -> None:
        """Fetch a chunk of OIDs.

        Some vendors return errors for larger multi-OID GET requests.
        We handle that by recursively splitting chunks until they succeed
        (or down to single-OID requests).
        """
        if not chunk:
            return

        var_binds = [ObjectType(ObjectIdentity(oid)) for oid in chunk]
        err_ind, err_stat, err_idx, vbs = await get_cmd(
            engine,
            community,
            target,
            context,
            *var_binds,
            lookupMib=False,  # prevent FS MIB access
        )

        if err_ind or err_stat:
            # Split & retry (down to per-OID).
            if len(chunk) == 1:
                return
            mid = max(1, len(chunk) // 2)
            await _fetch_chunk(chunk[:mid])
            await _fetch_chunk(chunk[mid:])
            return

        for oid_obj, val in vbs:
            try:
                s = val.prettyPrint() if hasattr(val, "prettyPrint") else str(val)
            except Exception:
                s = str(val)
            if not s:
                out[str(oid_obj)] = None
                continue
            s_low = s.lower()
            if "no such" in s_low or "nosuch" in s_low or "endofmib" in s_low:
                out[str(oid_obj)] = None
                continue
            out[str(oid_obj)] = s

    # Keep requests reasonably sized; we'll split further on vendor errors.
    CHUNK = 20
    for i in range(0, len(oids), CHUNK):
        await _fetch_chunk(oids[i : i + CHUNK])

    return out


async def _do_next_walk(
    engine, community, target, context, base_oid: str
) -> Iterable[Tuple[str, Any]]:
    current_oid = base_oid
    seen: set[str] = set()
    while True:
        err_ind, err_stat, err_idx, vbs = await next_cmd(
            engine,
            community,
            target,
            context,
            ObjectType(ObjectIdentity(current_oid)),
            lexicographicMode=False,
            lookupMib=False,  # <<< prevent FS MIB access
        )
        if err_ind or err_stat or not vbs:
            break

        advanced = False
        for vb in vbs:
            oid_obj, val = vb
            oid_str = str(oid_obj)
            if not (oid_str == base_oid or oid_str.startswith(base_oid + ".")):
                return
            if oid_str in seen:
                return
            seen.add(oid_str)
            yield oid_str, val
            current_oid = oid_str
            advanced = True

        if not advanced:
            break


async def _do_set_alias(
    engine, community, target, context, if_index: int, alias: str
) -> bool:
    err_ind, err_stat, err_idx, _ = await set_cmd(
        engine,
        community,
        target,
        context,
        ObjectType(ObjectIdentity(f"{OID_ifAlias}.{if_index}"), OctetString(alias)),
        lookupMib=False,  # <<< prevent FS MIB access
    )
    return (not err_ind) and (not err_stat)


async def _do_set_admin_status(
    engine, community, target, context, if_index: int, value: int
) -> bool:
    err_ind, err_stat, err_idx, _ = await set_cmd(
        engine,
        community,
        target,
        context,
        ObjectType(
            ObjectIdentity(f"{OID_ifAdminStatus}.{if_index}"),
            Integer(value),
        ),
        lookupMib=False,  # <<< prevent FS MIB access
    )
    return (not err_ind) and (not err_stat)


# ---------- client ----------

class SwitchSnmpClient:
    """SNMP client using PySNMP v7 asyncio API."""

    def __init__(self, hass: HomeAssistant, host: str, community: str, port: int, custom_oids: Optional[Dict[str, str]] = None, bandwidth_options: Optional[Dict[str, Any]] = None) -> None:
        self.hass = hass
        self.host = host
        self.community = community
        self.port = port
        self.custom_oids: Dict[str, str] = dict(custom_oids or {})

        # Bandwidth sensor options (set by config entry options)
        self._bandwidth_options: Dict[str, Any] = dict(bandwidth_options or {})
        self._bw_last_poll = None  # monotonic timestamp of last bandwidth counter poll
        self._bw_use_hc: Optional[bool] = None
        self._bw_last: Dict[int, Dict[str, Any]] = {}

        self.engine = None
        self.target = None
        self._target_args = ((host, port),)
        self._target_kwargs = dict(timeout=1.5, retries=1)

        self.community_data = CommunityData(community, mpModel=1)  # v2c
        self.context = ContextData()

        self.cache: Dict[str, Any] = {
            "sysDescr": None,
            "sysName": None,
            "sysUpTime": None,
            "ifTable": {},
            "ipIndex": {},
            "ipMask": {},
            "manufacturer": None,
            "model": None,
            "firmware": None,
        }

        # sysUpTime updates continuously; to avoid excessive churn in Home
        # Assistant, we throttle polling separately from the main coordinator.
        # These are used by async_poll().
        self._last_uptime_poll: float = 0.0
        self._uptime_poll_interval: float = 300.0

    def _custom_oid(self, key: str) -> Optional[str]:
        val = (self.custom_oids or {}).get(key)
        if not val:
            return None
        v = str(val).strip()
        if not v:
            return None
        if v.startswith("."):
            v = v[1:]
        return v


    def set_uptime_poll_interval(self, seconds: float | int) -> None:
        """Set the sysUpTime throttling interval (seconds)."""
        try:
            val = float(seconds)
        except Exception:
            val = 300.0
        # Guard against non-positive or NaN values
        if not (val > 0):
            val = 300.0
        self._uptime_poll_interval = val

    async def _ensure_engine(self) -> None:
        if self.engine is not None:
            return

        def _build_engine_with_minimal_preload():
            eng = SnmpEngine()
            try:
                mib_builder = eng.getMibBuilder()
                try:
                    mib_builder.setMibSources()  # clear FS sources
                except TypeError:
                    pass
                try:
                    mib_builder.loadModules("SNMPv2-SMI", "SNMPv2-MIB", "__SNMPv2-MIB", "PYSNMP-SOURCE-MIB")
                except Exception:
                    pass
            except Exception:
                pass
            return eng

        self.engine = await self.hass.async_add_executor_job(_build_engine_with_minimal_preload)

    async def _ensure_target(self) -> None:
        if self.target is None:
            self.target = await UdpTransportTarget.create(*self._target_args, **self._target_kwargs)

    # ---------- lifecycle / fetch ----------

    async def async_initialize(self) -> None:
        await self._ensure_engine()
        await self._ensure_target()

        # Build interface table and state first (names, alias, admin/oper)
        await self._async_walk_interfaces(dynamic_only=False)

        # Build IPv4 maps and attach to interfaces (original repo logic)
        await self._async_walk_ipv4()
        self._attach_ipv4_to_interfaces()

        # System fields
        self.cache["sysDescr"] = await self._async_get_one(OID_sysDescr)
        self.cache["sysName"] = await self._async_get_one(self._custom_oid("hostname") or OID_sysName)
        self.cache["sysUpTime"] = await self._async_get_one(self._custom_oid("uptime") or OID_sysUpTime)

        # Model hint (optional)
        ent_models = await self._async_walk(OID_entPhysicalModelName)
        model_hint = None
        for _oid, val in ent_models:
            s = str(val).strip()
            if s:
                model_hint = s
                break
        self.cache["model"] = model_hint

        # Manufacturer / firmware parsing from sysDescr (unchanged behavior)
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

        # Cisco CBS350: prefer ENTITY-MIB software revision when available.
        # This uses the documented entPhysicalSoftwareRev OID for the base chassis.
        if (model_hint and "CBS" in model_hint) or ("CBS" in sd):
            try:
                sw_rev = await self._async_get_one(OID_entPhysicalSoftwareRev_CBS350)
            except Exception:
                sw_rev = None
            if sw_rev:
                firmware = sw_rev.strip() or firmware

        # Zyxel: prefer vendor-specific manufacturer/firmware OIDs when detected
        if "zyxel" in sd.lower():
            try:
                zy_mfg = await self._async_get_one(OID_entPhysicalMfgName_Zyxel)
            except Exception:
                zy_mfg = None
            if zy_mfg:
                manufacturer = zy_mfg.strip() or manufacturer

            try:
                zy_fw = await self._async_get_one(OID_zyxel_firmware_version)
            except Exception:
                zy_fw = None
            if zy_fw:
                firmware = zy_fw.strip() or firmware

        # MikroTik RouterOS: override using MIKROTIK-MIB when detected
        if "mikrotik" in sd.lower() or "routeros" in sd.lower():
            # Manufacturer should be a clean vendor name, not "RouterOS".
            manufacturer = "MikroTik"

            # Firmware version from routerBoardInfoSoftwareVersion (e.g. "7.20.6")
            try:
                mk_ver = await self._async_get_one(OID_mikrotik_software_version)
            except Exception:
                mk_ver = None
            if mk_ver:
                firmware = mk_ver.strip() or firmware

            # Model name from routerBoardInfoModel (e.g. "CRS305-1G-4S+")
            try:
                mk_model = await self._async_get_one(OID_mikrotik_model)
            except Exception:
                mk_model = None
            if mk_model:
                self.cache["model"] = mk_model.strip() or self.cache.get("model")

        # Custom OIDs: per-device overrides take precedence over vendor logic and generic parsing
        try:
            mfg_oid = self._custom_oid("manufacturer")
            if mfg_oid:
                mfg_val = await self._async_get_one(mfg_oid)
                if mfg_val:
                    manufacturer = mfg_val.strip() or manufacturer
        except Exception:
            pass

        try:
            fw_oid = self._custom_oid("firmware")
            if fw_oid:
                fw_val = await self._async_get_one(fw_oid)
                if fw_val:
                    firmware = fw_val.strip() or firmware
        except Exception:
            pass

        try:
            model_oid = self._custom_oid("model")
            if model_oid:
                model_val = await self._async_get_one(model_oid)
                if model_val:
                    self.cache["model"] = model_val.strip() or self.cache.get("model")
        except Exception:
            pass

        self.cache["manufacturer"] = manufacturer
        self.cache["firmware"] = firmware

    async def _async_get_one(self, oid: str) -> Optional[str]:
        await self._ensure_engine()
        await self._ensure_target()
        return await _do_get_one(self.engine, self.community_data, self.target, self.context, oid)

    async def _async_walk(self, base_oid: str) -> list[tuple[str, Any]]:
        await self._ensure_engine()
        await self._ensure_target()
        out: list[tuple[str, Any]] = []
        async for oid_str, val in _do_next_walk(self.engine, self.community_data, self.target, self.context, base_oid):
            out.append((oid_str, val))
        return out

    async def _async_walk_interfaces(self, dynamic_only: bool = False) -> None:
        if not dynamic_only:
            self.cache["ifTable"] = {}

            # Indexes
            for oid, val in await self._async_walk(OID_ifIndex):
                idx = int(oid.split(".")[-1])
                self.cache["ifTable"][idx] = {"index": idx}

            # Descriptions
            for oid, val in await self._async_walk(OID_ifDescr):
                idx = int(oid.split(".")[-1])
                self.cache["ifTable"].setdefault(idx, {})["descr"] = str(val)

            # Names
            for oid, val in await self._async_walk(OID_ifName):
                idx = int(oid.split(".")[-1])
                self.cache["ifTable"].setdefault(idx, {})["name"] = str(val)

            # Aliases
            for oid, val in await self._async_walk(OID_ifAlias):
                idx = int(oid.split(".")[-1])
                self.cache["ifTable"].setdefault(idx, {})["alias"] = str(val)

            # Speeds (prefer ifHighSpeed where present; fall back to ifSpeed)
            for oid, val in await self._async_walk(OID_ifSpeed):
                idx = int(oid.split(".")[-1])
                try:
                    bps = int(val)
                except Exception:
                    continue
                if bps > 0:
                    self.cache["ifTable"].setdefault(idx, {})["speed_bps"] = bps

            for oid, val in await self._async_walk(OID_ifHighSpeed):
                idx = int(oid.split(".")[-1])
                try:
                    v = int(val)
                except Exception:
                    continue
                # ifHighSpeed is defined as Mbps (IF-MIB), but some devices incorrectly return bps.
                # Heuristic: values >= 1,000,000 are treated as bps to avoid 1e6x inflation.
                if v > 0:
                    bps = v if v >= 1_000_000 else v * 1_000_000
                    self.cache["ifTable"].setdefault(idx, {})["speed_bps"] = bps

            # VLAN (PVID) mapping via BRIDGE-MIB / Q-BRIDGE-MIB
            # Map ifIndex -> dot1dBasePort -> dot1qPvid (untagged VLAN)
            try:
                baseport_by_ifindex: Dict[int, int] = {}
                for oid, val in await self._async_walk(OID_dot1dBasePortIfIndex):
                    # Instance: ...1.4.1.2.<basePort>
                    base_port = int(oid.split(".")[-1])
                    if_index = int(val)
                    if if_index > 0 and base_port > 0:
                        baseport_by_ifindex[if_index] = base_port

                if baseport_by_ifindex:
                    pvid_by_baseport: Dict[int, int] = {}
                    for oid, val in await self._async_walk(OID_dot1qPvid):
                        # Instance: ...5.1.1.<basePort>
                        base_port = int(oid.split(".")[-1])
                        try:
                            pvid = int(val)
                        except Exception:
                            continue
                        if pvid > 0:
                            pvid_by_baseport[base_port] = pvid

                    if pvid_by_baseport:
                        for if_index, base_port in baseport_by_ifindex.items():
                            pvid = pvid_by_baseport.get(base_port)
                            if pvid is not None:
                                self.cache["ifTable"].setdefault(if_index, {})["vlan_id"] = pvid
            except Exception:
                # VLAN discovery is optional; ignore devices that don't implement these MIBs
                pass

            # Display name preference from original repo
            for idx, rec in list(self.cache["ifTable"].items()):
                nm = (rec.get("name") or "").strip()
                ds = (rec.get("descr") or "").strip()
                rec["display_name"] = nm or ds or f"ifIndex {idx}"

        # Dynamic state only
        for oid, val in await self._async_walk(OID_ifAdminStatus):
            idx = int(oid.split(".")[-1])
            self.cache["ifTable"].setdefault(idx, {})["admin"] = int(val)

        for oid, val in await self._async_walk(OID_ifOperStatus):
            idx = int(oid.split(".")[-1])
            self.cache["ifTable"].setdefault(idx, {})["oper"] = int(val)

    async def _async_walk_ipv4(self) -> None:
        """
        ORIGINAL REPO LOGIC, adapted to asyncio:
        1) Legacy IP-MIB ipAdEnt* for IPv4 list + masks when present.
        2) IP-MIB ipAddressIfIndex: parse IPv4 from instance suffix (1.4.a.b.c.d).
        3) OSPF-MIB ospfIfIpAddress: also yields a.b.c.d with suffix carrying ifIndex.
        4) Derive mask bits by parsing IP-FORWARD-MIB route instances (.7.1.9) and
           choosing the most specific network that contains each discovered IP.
        """
        ip_index: Dict[str, int] = {}
        ip_mask: Dict[str, str] = {}  # primarily from (1) and (4)

        def _normalize_ipv4(val: Any) -> str:
            """Convert SNMP IPv4 values to dotted-quad strings.
        
            Some vendors (e.g., Cisco CBS series, Arista) return ipAdEntAddr/ipAdEntNetMask
            as raw octets instead of a printable IpAddress. This helper keeps existing
            behavior for vendors that already return dotted strings."""
            s = str(val)
            parts = s.split(".")
            if len(parts) == 4 and all(p.isdigit() for p in parts):
                # Already a normal dotted-decimal IPv4 string
                return s
        
            # Try to interpret as 4 raw octets
            b: Optional[bytes] = None
        
            # Fast path for native bytes/bytearray
            if isinstance(val, (bytes, bytearray)):
                b = bytes(val)
            else:
                try:
                    # pysnmp types often support __bytes__
                    b = bytes(val)  # type: ignore[arg-type]
                except Exception:
                    # On some vendors (e.g. Arista) IpAddress may come back
                    # as a 4-character Python str like "C;U[" – treat each
                    # character as a raw octet.
                    if isinstance(val, str):
                        try:
                            b = val.encode("latin-1")
                        except Exception:
                            b = None
                    if b is None:
                        try:
                            b = val.asOctets()  # type: ignore[attr-defined]
                        except Exception:
                            b = None
        
            if b and len(b) == 4:
                return ".".join(str(x) for x in b)
        
            # Fallback: give the original string representation
            return s

        # ---- (1) Legacy table: ipAdEnt* ----
        legacy_addrs = await self._async_walk(OID_ipAdEntAddr)
        if legacy_addrs:
            for _oid, val in legacy_addrs:
                ip_index[_normalize_ipv4(val)] = None  # type: ignore[assignment]

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
                ip_mask[ip] = _normalize_ipv4(val)

        # ---- (2) IP-MIB ipAddressIfIndex: parse instance suffix (1.4.a.b.c.d)
        try:
            for oid, val in await self._async_walk(OID_ipAddressIfIndex):
                suffix = oid[len(OID_ipAddressIfIndex) + 1 :]
                parts = [int(x) for x in suffix.split(".") if x]
                for i in range(len(parts) - 6 + 1):
                    if parts[i] == 1 and parts[i + 1] == 4:
                        a, b, c, d = parts[i + 2 : i + 6]
                        ip = f"{a}.{b}.{c}.{d}"
                        try:
                            idx = int(val)
                            ip_index.setdefault(ip, idx)
                        except Exception:
                            pass
                        break
        except Exception:
            pass  # IP-MIB may be absent

        # ---- (3) OSPF-MIB ospfIfIpAddress: suffix a.b.c.d.<ifIndex>.<area...>
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
            pass  # OSPF-MIB may be absent

        # ---- (4) Derive mask bits from IP-FORWARD-MIB route instances (.7.1.9)
        route_prefixes: List[Tuple[int, int]] = []

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

        try:
            for oid, _val in await self._async_walk(OID_routeCol):
                try:
                    suffix = oid[len(OID_routeCol) + 1 :]
                    parts = [int(x) for x in suffix.split(".") if x]

                    for i in range(len(parts) - 7):
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
            pass  # table may be absent on some vendors

        if route_prefixes and ip_index:
            route_prefixes.sort(key=lambda t: t[1], reverse=True)
            for ip in list(ip_index.keys()):
                ip_int = _ip_to_int(ip)
                for net_int, bits in route_prefixes:
                    mask_int = (0xFFFFFFFF << (32 - bits)) & 0xFFFFFFFF if bits else 0
                    if bits == 0 or (ip_int & mask_int) == (net_int & mask_int):
                        ip_mask[ip] = _bits_to_mask(bits)
                        break

        # Commit maps to cache
        if ip_index:
            self.cache["ipIndex"] = ip_index
        if ip_mask:
            self.cache["ipMask"] = ip_mask

    def _attach_ipv4_to_interfaces(self) -> None:
        if_table: Dict[int, Dict[str, Any]] = self.cache.get("ifTable", {})
        ip_idx: Dict[str, Optional[int]] = self.cache.get("ipIndex", {})
        ip_mask: Dict[str, str] = self.cache.get("ipMask", {})

        # Clear prior fields to avoid stale data
        for rec in if_table.values():
            for k in (
                "ipv4", "ip", "netmask", "cidr",
                "ip_address", "ipv4_address", "ipv4_netmask", "ipv4_cidr",
                "ip_cidr_str",
            ):
                rec.pop(k, None)

        def _mask_to_prefix(mask: str | None) -> Optional[int]:
            if not mask:
                return None
            try:
                parts = [int(p) for p in mask.split(".")]
                if len(parts) != 4 or any(p < 0 or p > 255 for p in parts):
                    return None
                bits = "".join(f"{p:08b}" for p in parts)
                if "01" in bits:
                    return None
                return bits.count("1")
            except Exception:
                return None

        # Attach; if mask present convert to prefix bits for /cidr string
        for ip, idx in ip_idx.items():
            if not idx:
                continue
            rec = if_table.get(idx)
            if not rec:
                continue
            mask = ip_mask.get(ip)
            prefix = _mask_to_prefix(mask)
            rec.setdefault("ipv4", []).append({"ip": ip, "netmask": mask, "cidr": prefix})

        # Convenience single-address fields for UI (unchanged behavior)
        for rec in if_table.values():
            addrs = rec.get("ipv4") or []
            if len(addrs) == 1:
                ip = addrs[0]["ip"]
                mask = addrs[0]["netmask"]
                prefix = addrs[0]["cidr"]
                rec["ip"] = ip
                rec["netmask"] = mask
                rec["cidr"] = prefix
                rec["ip_address"] = ip
                rec["ipv4_address"] = ip
                rec["ipv4_netmask"] = mask
                rec["ipv4_cidr"] = prefix
                if prefix is not None:
                    rec["ip_cidr_str"] = f"{ip}/{prefix}"

    async def async_refresh_all(self) -> None:
        await self._ensure_engine()
        await self._ensure_target()
        await self._async_walk_interfaces(dynamic_only=False)
        await self._async_walk_ipv4()
        self._attach_ipv4_to_interfaces()

    async def async_refresh_dynamic(self) -> None:
        await self._ensure_engine()
        await self._ensure_target()
        await self._async_walk_interfaces(dynamic_only=True)
        await self._async_walk_ipv4()
        self._attach_ipv4_to_interfaces()

    # ---------- coordinator hook ----------
    async def async_poll(self) -> Dict[str, Any]:
        # Keep system/diagnostic fields fresh (e.g., sysUpTime) so diagnostic
        # sensors update without requiring an integration restart.
        await self._ensure_engine()
        await self._ensure_target()

        # Refresh common system fields with minimal overhead.
                # Refresh common system fields with minimal overhead.
        # sysUpTime can be very "chatty" (updates constantly), so poll it less frequently.
        now_mono = time.monotonic()
        poll_uptime = (
            "sysUpTime" not in self.cache
            or (now_mono - self._last_uptime_poll) >= float(self._uptime_poll_interval)
        )

        if poll_uptime:
            self._last_uptime_poll = now_mono

        sysname_oid = self._custom_oid("hostname") or OID_sysName
        uptime_oid = self._custom_oid("uptime") or OID_sysUpTime

        sysdescr, sysname, sysuptime = await asyncio.gather(
            _do_get_one(self.engine, self.community_data, self.target, self.context, OID_sysDescr),
            _do_get_one(self.engine, self.community_data, self.target, self.context, sysname_oid),
            _do_get_one(self.engine, self.community_data, self.target, self.context, uptime_oid) if poll_uptime else asyncio.sleep(0, result=None),
        )
        if (not poll_uptime) and ("sysUpTime" in self.cache):
            sysuptime = self.cache.get("sysUpTime")
        if sysdescr is not None:
            self.cache["sysDescr"] = sysdescr
        if sysname is not None:
            self.cache["sysName"] = sysname
        if sysuptime is not None:
            self.cache["sysUpTime"] = sysuptime

        # Re-evaluate manufacturer/firmware from sysDescr so diagnostic sensors
        # reflect device changes over time.
        sd = (self.cache.get("sysDescr") or "").strip()
        if sd:
            model_hint = self.cache.get("model")

            manufacturer = None
            firmware = None
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

            # Cisco CBS350: prefer ENTITY-MIB software revision when available.
            if (model_hint and "CBS" in model_hint) or ("CBS" in sd):
                try:
                    sw_rev = await _do_get_one(
                        self.engine,
                        self.community_data,
                        self.target,
                        self.context,
                        OID_entPhysicalSoftwareRev_CBS350,
                    )
                except Exception:
                    sw_rev = None
                if sw_rev:
                    firmware = sw_rev.strip() or firmware

            # Zyxel: prefer vendor-specific manufacturer/firmware OIDs when detected
            if "zyxel" in sd.lower():
                try:
                    zy_mfg = await _do_get_one(
                        self.engine,
                        self.community_data,
                        self.target,
                        self.context,
                        OID_entPhysicalMfgName_Zyxel,
                    )
                except Exception:
                    zy_mfg = None
                if zy_mfg:
                    manufacturer = zy_mfg.strip() or manufacturer

                try:
                    zy_fw = await _do_get_one(
                        self.engine,
                        self.community_data,
                        self.target,
                        self.context,
                        OID_zyxel_firmware_version,
                    )
                except Exception:
                    zy_fw = None
                if zy_fw:
                    firmware = zy_fw.strip() or firmware

            # MikroTik RouterOS: override using MIKROTIK-MIB when detected
            if "mikrotik" in sd.lower() or "routeros" in sd.lower():
                manufacturer = "MikroTik"
                try:
                    mk_ver = await _do_get_one(
                        self.engine,
                        self.community_data,
                        self.target,
                        self.context,
                        OID_mikrotik_software_version,
                    )
                except Exception:
                    mk_ver = None
                if mk_ver:
                    firmware = mk_ver.strip() or firmware
                try:
                    mk_model = await _do_get_one(
                        self.engine,
                        self.community_data,
                        self.target,
                        self.context,
                        OID_mikrotik_model,
                    )
                except Exception:
                    mk_model = None
                if mk_model:
                    self.cache["model"] = mk_model.strip() or self.cache.get("model")

            # Custom OIDs: per-device overrides take precedence over vendor logic and generic parsing
            try:
                mfg_oid = self._custom_oid("manufacturer")
                if mfg_oid:
                    mfg_val = await _do_get_one(
                        self.engine,
                        self.community_data,
                        self.target,
                        self.context,
                        mfg_oid,
                    )
                    if mfg_val:
                        manufacturer = mfg_val.strip() or manufacturer
            except Exception:
                pass

            try:
                fw_oid = self._custom_oid("firmware")
                if fw_oid:
                    fw_val = await _do_get_one(
                        self.engine,
                        self.community_data,
                        self.target,
                        self.context,
                        fw_oid,
                    )
                    if fw_val:
                        firmware = fw_val.strip() or firmware
            except Exception:
                pass

            self.cache["manufacturer"] = manufacturer
            self.cache["firmware"] = firmware

        await self.async_refresh_dynamic()

        # Bandwidth sensors (optional; per-device)
        if bool(self._bandwidth_options.get(CONF_BW_ENABLE, False)):
            poll_interval = int(self._bandwidth_options.get(CONF_BANDWIDTH_POLL_INTERVAL, DEFAULT_BANDWIDTH_POLL_INTERVAL) or DEFAULT_BANDWIDTH_POLL_INTERVAL)
            now = time.monotonic()
            if self._bw_last_poll is not None and (now - self._bw_last_poll) < poll_interval:
                _LOGGER.debug("Skipping bandwidth counter poll; interval=%ss", poll_interval)
            else:
                self._bw_last_poll = now
                try:
                    iftable = self.cache.get("ifTable", {}) or {}

                    def _clean_list(key: str) -> list[str]:
                        return [str(s).strip().lower() for s in (self._bandwidth_options.get(key, []) or []) if str(s).strip()]

                    include_starts = _clean_list(CONF_BW_INCLUDE_STARTS_WITH)
                    include_contains = _clean_list(CONF_BW_INCLUDE_CONTAINS)
                    include_ends = _clean_list(CONF_BW_INCLUDE_ENDS_WITH)
                    exclude_starts = _clean_list(CONF_BW_EXCLUDE_STARTS_WITH)
                    exclude_contains = _clean_list(CONF_BW_EXCLUDE_CONTAINS)
                    exclude_ends = _clean_list(CONF_BW_EXCLUDE_ENDS_WITH)

                    def _matches_any(name_l: str, starts: list[str], contains: list[str], ends: list[str]) -> bool:
                        return (
                            any(name_l.startswith(x) for x in starts)
                            or any(x in name_l for x in contains)
                            or any(name_l.endswith(x) for x in ends)
                        )

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
                        include_hit = _matches_any(nl, include_starts, include_contains, include_ends)
                        exclude_hit = _matches_any(nl, exclude_starts, exclude_contains, exclude_ends)

                        # If include rules are defined, only include matches.
                        if (include_starts or include_contains or include_ends):
                            if not include_hit:
                                continue

                        # Exclude always wins
                        if exclude_hit:
                            continue

                        selected.append(idx_i)

                    # Detect whether 64-bit counters are supported (once)
                    if self._bw_use_hc is None:
                        self._bw_use_hc = False
                        probe_idx = selected[0] if selected else None
                        if probe_idx is not None:
                            probe_oid = f"{OID_ifHCInOctets}.{probe_idx}"
                            try:
                                probe_val = await _do_get_one(self.engine, self.community_data, self.target, self.context, probe_oid)
                                if probe_val is not None:
                                    int(probe_val)  # validate numeric
                                    self._bw_use_hc = True
                            except Exception:
                                self._bw_use_hc = False

                    now_ts = time.time()
                    use_hc = bool(self._bw_use_hc)

                    rx_base = OID_ifHCInOctets if use_hc else OID_ifInOctets
                    tx_base = OID_ifHCOutOctets if use_hc else OID_ifOutOctets

                    oids: list[str] = []
                    for idx_i in selected:
                        oids.append(f"{rx_base}.{idx_i}")
                        oids.append(f"{tx_base}.{idx_i}")

                    got = await _do_get_many(self.engine, self.community_data, self.target, self.context, oids)

                    bw_out: Dict[int, Dict[str, Any]] = {}
                    for idx_i in selected:
                        rx_oid = f"{rx_base}.{idx_i}"
                        tx_oid = f"{tx_base}.{idx_i}"
                        rx_v = got.get(rx_oid)
                        tx_v = got.get(tx_oid)
                        if rx_v is None and tx_v is None:
                            continue
                        try:
                            rx_oct = int(rx_v) if rx_v is not None else None
                        except Exception:
                            rx_oct = None
                        try:
                            tx_oct = int(tx_v) if tx_v is not None else None
                        except Exception:
                            tx_oct = None

                        last = self._bw_last.get(idx_i) or {}
                        last_ts = float(last.get("ts") or 0.0)
                        dt = (now_ts - last_ts) if last_ts else 0.0

                        rx_bps = None
                        tx_bps = None
                        if dt > 0:
                            if rx_oct is not None and last.get("rx") is not None:
                                prev = int(last.get("rx"))
                                cur = int(rx_oct)
                                delta = cur - prev
                                if not use_hc and delta < 0:
                                    delta += 2 ** 32
                                rx_bps = (delta * 8.0) / dt
                            if tx_oct is not None and last.get("tx") is not None:
                                prev = int(last.get("tx"))
                                cur = int(tx_oct)
                                delta = cur - prev
                                if not use_hc and delta < 0:
                                    delta += 2 ** 32
                                tx_bps = (delta * 8.0) / dt

                        self._bw_last[idx_i] = {"ts": now_ts, "rx": rx_oct, "tx": tx_oct}

                        bw_out[idx_i] = {
                            "ts": now_ts,
                            "rx_octets": rx_oct,
                            "tx_octets": tx_oct,
                            "rx_bps": rx_bps,
                            "tx_bps": tx_bps,
                            "use_hc": use_hc,
                        }

                    self.cache["bandwidth"] = bw_out
                except Exception as e:
                    _LOGGER.debug("Bandwidth polling failed: %s", e)
                    self.cache["bandwidth"] = {}

        return self.cache

    # ---------- mutations ----------
    async def set_alias(self, if_index: int, alias: str) -> bool:
        await self._ensure_engine()
        await self._ensure_target()
        ok = await _do_set_alias(self.engine, self.community_data, self.target, self.context, if_index, alias)
        if ok:
            self.cache.setdefault("ifTable", {}).setdefault(if_index, {})["alias"] = alias
        else:
            _LOGGER.warning("Failed to set alias via SNMP on ifIndex %s", if_index)
        return ok

    async def set_admin_status(self, if_index: int, value: int) -> bool:
        await self._ensure_engine()
        await self._ensure_target()
        return await _do_set_admin_status(self.engine, self.community_data, self.target, self.context, if_index, value)


# ---------- helpers for config_flow ----------

async def test_connection(hass: HomeAssistant, host: str, community: str, port: int) -> bool:
    client = SwitchSnmpClient(hass, host, community, port)
    sysname = await client._async_get_one(OID_sysName)
    return sysname is not None


async def get_sysname(hass: HomeAssistant, host: str, community: str, port: int) -> Optional[str]:
    client = SwitchSnmpClient(hass, host, community, port)
    return await client._async_get_one(OID_sysName)
