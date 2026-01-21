from __future__ import annotations

import asyncio
import time
import logging
import re
import ipaddress
from typing import Any, Dict, Optional, Iterable, Tuple, List

from homeassistant.core import HomeAssistant

from .helpers import classify_port_type

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
    OID_hwEntityTemperature,
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
    CONF_BW_MODE,
    BW_MODE_SENSORS,
    BW_MODE_ATTRIBUTES,
    CONF_BANDWIDTH_POLL_INTERVAL,
    DEFAULT_BANDWIDTH_POLL_INTERVAL,
    CONF_POE_ENABLE,
    CONF_POE_MODE,
    CONF_POE_POLL_INTERVAL,
    POE_MODE_ATTRIBUTES,
    POE_MODE_SENSORS,
    DEFAULT_POE_POLL_INTERVAL,
    CONF_ENV_ENABLE,
    CONF_ENV_MODE,
    CONF_ENV_POLL_INTERVAL,
    ENV_MODE_ATTRIBUTES,
    ENV_MODE_SENSORS,
    DEFAULT_ENV_POLL_INTERVAL,
    OID_ifType,
)

_LOGGER = logging.getLogger(__name__)


def _entity_sensor_scale_power(scale: int) -> int:
    """ENTITY-SENSOR-MIB entPhySensorScale -> base-10 exponent."""
    # yocto(1) ... yotta(17) with units(9) = 10^0
    scale_map = {
        1: -24,
        2: -21,
        3: -18,
        4: -15,
        5: -12,
        6: -9,
        7: -6,
        8: -3,
        9: 0,
        10: 3,
        11: 6,
        12: 9,
        13: 12,
        14: 15,
        15: 18,
        16: 21,
        17: 24,
    }
    return scale_map.get(int(scale), 0)


def _entity_sensor_value_to_float(raw: Any, scale: int | None, precision: int | None) -> Optional[float]:
    """Convert ENTITY-SENSOR-MIB value/scale/precision to a float."""
    n = _parse_numeric(raw)
    if n is None:
        return None
    try:
        s_pow = _entity_sensor_scale_power(int(scale or 9))
    except Exception:
        s_pow = 0
    try:
        prec = int(precision or 0)
    except Exception:
        prec = 0
    try:
        return float(n) * (10 ** (s_pow - prec))
    except Exception:
        return None

# Q-BRIDGE-MIB VLAN membership tables are not present in some older versions
# of this integration's const.py. Keep these OID strings defined locally to
# avoid import-time failures, while still using standard OIDs.
OID_dot1qVlanCurrentEgressPorts = "1.3.6.1.2.1.17.7.1.4.2.1.4"
OID_dot1qVlanCurrentUntaggedPorts = "1.3.6.1.2.1.17.7.1.4.2.1.5"
# Some platforms (incl. Dell N-series) expose VLAN membership only via the *static* tables.
OID_dot1qVlanStaticEgressPorts = "1.3.6.1.2.1.17.7.1.4.3.1.2"
OID_dot1qVlanStaticUntaggedPorts = "1.3.6.1.2.1.17.7.1.4.3.1.4"

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

    def __init__(self, hass: HomeAssistant, host: str, community: str, port: int, custom_oids: Optional[Dict[str, str]] = None, bandwidth_options: Optional[Dict[str, Any]] = None, poe_options: Optional[Dict[str, Any]] = None, env_options: Optional[Dict[str, Any]] = None) -> None:
        self.hass = hass
        self.host = host
        self.community = community
        self.port = port
        self.custom_oids: Dict[str, str] = dict(custom_oids or {})

        # Bandwidth sensor options (set by config entry options)
        self._bandwidth_options: Dict[str, Any] = dict(bandwidth_options or {})
        self._poe_options = poe_options or {}
        self._poe_last_poll: float = 0.0

        self._env_options = env_options or {}
        self._env_last_poll: float = 0.0
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
                # Pre-load core pysnmp modules off the event loop.
                # Home Assistant flags synchronous FS access (os.listdir/open) from pysnmp's MIB loader
                # when it occurs on the asyncio loop thread. Preloading here ensures pysnmp will not
                # hit the filesystem later during async polling/walks.
                mib_builder.loadModules(
                    "SNMPv2-SMI",
                    "SNMPv2-TC",
                    "SNMPv2-CONF",
                    "SNMPv2-MIB",
                    "__SNMPv2-MIB",
                    "SNMP-FRAMEWORK-MIB",
                    "SNMP-COMMUNITY-MIB",
                    "SNMP-TARGET-MIB",
                    "SNMP-NOTIFICATION-MIB",
                    "SNMPv2-TM",
                    "PYSNMP-SOURCE-MIB",
                )
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
                    bps = _parse_numeric(val)
                    if not bps or bps <= 0:
                        continue
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
                    try:
                        base_port = int(oid.split(".")[-1])
                    except Exception:
                        continue
                    try:
                        if_index = int(_parse_numeric(val))
                    except Exception:
                        continue
                    if if_index > 0 and base_port > 0:
                        baseport_by_ifindex[if_index] = base_port

                if baseport_by_ifindex:
                    pvid_by_baseport: Dict[int, int] = {}
                    for oid, val in await self._async_walk(OID_dot1qPvid):
                        # Instance: ...5.1.1.<basePort>
                        try:
                            base_port = int(oid.split(".")[-1])
                        except Exception:
                            continue
                        try:
                            pvid = int(_parse_numeric(val))
                        except Exception:
                            continue
                        if pvid > 0:
                            pvid_by_baseport[base_port] = pvid

                    # Build VLAN membership maps (per bridge port) when available.
                    # These Q-BRIDGE-MIB tables are indexed by VLAN and return a PortList bitmap.
                    allowed_by_baseport: Dict[int, set[int]] = {}
                    untagged_by_baseport: Dict[int, set[int]] = {}

                    async def _collect_vlan_portlists(oid_base: str, out: Dict[int, set[int]]) -> int:
                        """Walk a Q-BRIDGE PortList table and invert it into port -> {vlans}.

                        Some devices have very large VLAN tables (or respond slowly), which can cause
                        Home Assistant to cancel config entry setup. To keep setup responsive, we cap
                        how long each VLAN PortList walk can run.
                        """
                        count = 0
                        try:
                            rows = await asyncio.wait_for(self._async_walk(oid_base), timeout=30.0)
                        except asyncio.TimeoutError:
                            return count
                        for oid, val in rows:
                            try:
                                vlan_id = int(oid.split(".")[-1])
                            except Exception:
                                continue
                            if vlan_id <= 0:
                                continue
                            ports = _decode_bridge_port_bitmap(val)
                            if not ports:
                                continue
                            count += 1
                            for bp in ports:
                                out.setdefault(bp, set()).add(vlan_id)
                        return count

                    # Prefer "current" VLAN membership tables when present.
                    # Dell N-series (and some others) expose only the "static" tables.
                    try:
                        cur_allowed = await _collect_vlan_portlists(
OID_dot1qVlanCurrentEgressPorts = "1.3.6.1.2.1.17.7.1.4.2.1.4"
                        )
                    except Exception:
                        cur_allowed = 0

                    try:
                        cur_untagged = await _collect_vlan_portlists(
OID_dot1qVlanCurrentUntaggedPorts = "1.3.6.1.2.1.17.7.1.4.2.1.5"
                        )
                    except Exception:
                        cur_untagged = 0

                    # Fall back to static membership when current tables are not implemented.
                    # Some platforms expose richer/complete VLAN membership only via the static tables.
                    # Even when current tables exist, merge static data to avoid missing VLANs (e.g., some JT-COM devices).
                    try:
                        await _collect_vlan_portlists(
                            OID_dot1qVlanStaticEgressPorts, allowed_by_baseport
                        )
                    except Exception:
                        pass
                    try:
                        await _collect_vlan_portlists(
                            OID_dot1qVlanStaticUntaggedPorts, untagged_by_baseport
                        )
                    except Exception:
                        pass
                    if pvid_by_baseport:
                        for if_index, base_port in baseport_by_ifindex.items():
                            rec = self.cache["ifTable"].setdefault(if_index, {})
                            pvid = pvid_by_baseport.get(base_port)

                            # Backwards-compatible: keep vlan_id as the PVID
                            if pvid is not None:
                                rec["vlan_id"] = pvid
                                rec["native_vlan"] = pvid

                            allowed = sorted(allowed_by_baseport.get(base_port, set()))
                            if allowed:
                                rec["allowed_vlans"] = allowed

                            untagged = sorted(untagged_by_baseport.get(base_port, set()))
                            if untagged:
                                rec["untagged_vlans"] = untagged

                            # Tagged VLANs:
                            # - Prefer (allowed - untagged) when untagged data exists
                            # - Fall back to (allowed - {pvid}) when it doesn't
                            tagged_set: set[int] = set()
                            if allowed:
                                if untagged:
                                    tagged_set = set(allowed) - set(untagged)
                                elif pvid is not None:
                                    tagged_set = set(allowed) - {pvid}
                                else:
                                    tagged_set = set(allowed)

                            tagged = sorted(tagged_set)
                            if tagged:
                                rec["tagged_vlans"] = tagged

                            # Trunk-like heuristic
                            if (len(allowed) > 1) or bool(tagged):
                                rec["is_trunk"] = True

            except Exception:
                # VLAN discovery is optional; ignore devices that don't implement these MIBs
                pass

            # Display name preference from original repo
            # If a display_name is already populated, do not overwrite it.
            for idx, rec in list(self.cache["ifTable"].items()):
                existing = (rec.get("display_name") or "").strip()
                if existing:
                    rec["display_name"] = existing
                    continue
                nm = (rec.get("name") or "").strip()
                ds = (rec.get("descr") or "").strip()
                rec["display_name"] = nm or ds or f"ifIndex {idx}"

        # Dynamic state only
            # Interface types (IF-MIB ifType)
            for oid, val in await self._async_walk(OID_ifType):
                idx = int(oid.split(".")[-1])
                rec = self.cache["ifTable"].get(idx)
                if rec is not None:
                    try:
                        rec["if_type"] = int(val)
                    except Exception:
                        rec["if_type"] = None

            # Bridge membership (BRIDGE-MIB dot1dBasePortIfIndex)
            bridge_ifindexes: set[int] = set()
            try:
                for oid, val in await self._async_walk(OID_dot1dBasePortIfIndex):
                    try:
                        bridge_ifindexes.add(int(val))
                    except Exception:
                        continue
            except Exception:
                bridge_ifindexes = set()

            for idx, rec in self.cache["ifTable"].items():
                if not isinstance(rec, dict):
                    continue
                if_type = rec.get("if_type")
                name = str(rec.get("display_name") or rec.get("name") or rec.get("descr") or "")
                is_bridge_port = idx in bridge_ifindexes
                rec["port_type"] = classify_port_type(
                    if_type=if_type,
                    name=name,
                    is_bridge_port=is_bridge_port,
                )
                rec["is_bridge_port"] = is_bridge_port

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


        def _is_usable_ipv4(ip: str) -> bool:
            """Filter out addresses that are almost always meaningless on L2 switch ports."""
            try:
                addr = ipaddress.IPv4Address(ip)
            except Exception:
                return False
            # Exclude loopback/unspecified/link-local/multicast/reserved/broadcast
            if (
                addr.is_loopback
                or addr.is_unspecified
                or addr.is_link_local
                or addr.is_multicast
                or addr.is_reserved
            ):
                return False
            if ip == "255.255.255.255":
                return False
            return True
        # ---- (1) Legacy table: ipAdEnt* ----
        legacy_addrs = await self._async_walk(OID_ipAdEntAddr)
        if legacy_addrs:
            for _oid, val in legacy_addrs:
                ip = _normalize_ipv4(val)
                if not _is_usable_ipv4(ip):
                    continue
                ip_index[ip] = None  # type: ignore[assignment]

            for oid, val in await self._async_walk(OID_ipAdEntIfIndex):
                parts = oid.split(".")[-4:]
                ip = ".".join(parts)
                if not _is_usable_ipv4(ip):
                    continue
                try:
                    ip_index[ip] = int(_parse_numeric(val))
                except Exception:
                    continue


            for oid, val in await self._async_walk(OID_ipAdEntNetMask):
                parts = oid.split(".")[-4:]
                ip = ".".join(parts)
                if not _is_usable_ipv4(ip):
                    continue
                ip_mask[ip] = _normalize_ipv4(val)

        # ---- (2) IP-MIB ipAddressIfIndex: parse instance suffix (1.4.a.b.c.d)
        # OID instance for IPv4 encodes: <addrType=1>.<addrLen=4>.<a>.<b>.<c>.<d>
        # Value is the ifIndex.
        try:
            for oid, val in await self._async_walk(OID_ipAddressIfIndex):
                try:
                    suffix = oid[len(OID_ipAddressIfIndex) + 1 :]
                    parts = [int(x) for x in suffix.split(".") if x]
                    if len(parts) < 6:
                        continue

                    # Find the first occurrence of 1.4 in the suffix (addrType=ipv4, addrLen=4)
                    ip = None
                    for i in range(0, len(parts) - 5):
                        if parts[i] == 1 and parts[i + 1] == 4:
                            a, b, c, d = parts[i + 2 : i + 6]
                            ip = f"{a}.{b}.{c}.{d}"
                            break
                    if not ip or not _is_usable_ipv4(ip):
                        continue

                    idx = _parse_numeric(val)
                    if idx is None:
                        continue
                    ip_index[ip] = int(idx)
                except Exception:
                    continue
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
                        if not _is_usable_ipv4(ip):
                            continue
                        ip_index[ip] = int(if_index)
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

        # Precompute O(1) lookups for entities (performance + consistent display).
        # These are used by the switch entity to display per-interface IP without scanning the full tables.
        ip_by_ifindex: Dict[int, str] = {}
        ip_mask_by_ifindex: Dict[int, str] = {}
        for rec in if_table.values():
            try:
                idx = int(rec.get("index"))
            except Exception:
                continue
            ip = rec.get("ip")
            mask = rec.get("netmask")
            if isinstance(ip, str) and ip:
                ip_by_ifindex[idx] = ip
            if isinstance(mask, str) and mask:
                ip_mask_by_ifindex[idx] = mask
        self.cache["ip_by_ifindex"] = ip_by_ifindex
        self.cache["ip_mask_by_ifindex"] = ip_mask_by_ifindex


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
    OID_hwEntityTemperature,
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

        # PoE (optional)
        #
        # Two data sources may exist:
        # 1) Dell N-Series per-port PoE power (private MIB table) -> cached as poe_power_mw
        # 2) Standard PoE totals + health (POWER-ETHERNET-MIB) -> cached as poe_*_w + poe_health_status
        poe_enabled = bool(self._poe_options.get(CONF_POE_ENABLE, False))
        poe_mode = self._poe_options.get(CONF_POE_MODE, POE_MODE_ATTRIBUTES)
        # Bandwidth mode/enable flags (used by port entities when BW mode is Attributes)
        try:
            bw_enabled = bool(self._bandwidth_options.get(CONF_BW_ENABLE, False))
            bw_mode = self._bandwidth_options.get(CONF_BW_MODE) or BW_MODE_SENSORS
            bw_mode = str(bw_mode).strip().lower()
            if bw_mode not in (BW_MODE_SENSORS, BW_MODE_ATTRIBUTES):
                bw_mode = BW_MODE_SENSORS
        except Exception:
            bw_enabled = False
            bw_mode = BW_MODE_SENSORS
        self.cache['bw_enabled'] = bw_enabled
        self.cache['bw_mode'] = bw_mode

        self.cache["poe_enabled"] = poe_enabled
        self.cache["poe_mode"] = poe_mode

        # Summary/stat keys (Watts)
        # Only set these when we successfully read values; absence means "unsupported".
        # - poe_budget_total_w
        # - poe_power_used_w
        # - poe_power_available_w
        # - poe_health_status (text)
        # - poe_health_status_raw (int)

        # Keep per-port cache stable
        self.cache.setdefault("poe_power_mw", {})

        if not poe_enabled:
            # Clear dynamic values when disabled (keep keys stable where appropriate)
            self.cache["poe_power_mw"] = {}
            for k in ("poe_budget_total_w", "poe_power_used_w", "poe_power_available_w", "poe_health_status", "poe_health_status_raw"):
                self.cache.pop(k, None)
        else:
            # Throttle PoE polling based on the PoE polling interval option
            interval = int(self._poe_options.get(CONF_POE_POLL_INTERVAL, DEFAULT_POE_POLL_INTERVAL))
            interval = max(1, interval)
            now_mono = time.monotonic()
            should_poll = (now_mono - float(self._poe_last_poll or 0.0)) >= interval
            # Always poll once after startup
            should_poll = should_poll or float(self._poe_last_poll or 0.0) == 0.0

            if should_poll:
                self._poe_last_poll = now_mono

                # --- (1) Standard PoE totals + health (POWER-ETHERNET-MIB) ---
                # Standard columns (POWER-ETHERNET-MIB / RFC3621):
                #   pethPsePortGroupIndex is typically the instance suffix (.1, .2, ...)
                # Budget Total (W): 1.3.6.1.2.1.105.1.3.1.1.2.<idx>
                # Power Used (mW):  1.3.6.1.2.1.105.1.3.1.1.4.<idx>
                # Health Status:    1.3.6.1.2.1.105.1.3.1.1.3.<idx>
                poe_budget_col = "1.3.6.1.2.1.105.1.3.1.1.2"
                poe_used_mw_col = "1.3.6.1.2.1.105.1.3.1.1.4"
                poe_health_col = "1.3.6.1.2.1.105.1.3.1.1.3"

                def _worst_poe_health(raw_vals: list[int]) -> Optional[int]:
                    if not raw_vals:
                        return None
                    # Conservative: unknown -> FAULTY
                    rank = {1: 1, 2: 2, 3: 3}
                    worst = 0
                    for v in raw_vals:
                        worst = max(worst, rank.get(int(v), 3))
                    # Map back to 1/2/3
                    inv = {1: 1, 2: 2, 3: 3}
                    return inv.get(worst, 3)

                budget_list: list[float] = []
                used_mw_list: list[float] = []
                health_list: list[int] = []

                try:
                    for oid, val in await self._async_walk(poe_budget_col):
                        n = _parse_numeric(val)
                        if n is None:
                            continue
                        if float(n) >= 0:
                            budget_list.append(float(n))
                except Exception:
                    budget_list = []

                try:
                    for oid, val in await self._async_walk(poe_used_mw_col):
                        n = _parse_numeric(val)
                        if n is None:
                            continue
                        if float(n) >= 0:
                            used_mw_list.append(float(n))
                except Exception:
                    used_mw_list = []

                try:
                    for oid, val in await self._async_walk(poe_health_col):
                        n = _parse_numeric(val)
                        if n is None:
                            continue
                        try:
                            health_list.append(int(n))
                        except Exception:
                            continue
                except Exception:
                    health_list = []

                # If the device doesn't support walking the columns, fall back to scalar index .1.
                if not budget_list and not used_mw_list and not health_list:
                    budget_w = _parse_numeric(await self._async_get_one(poe_budget_col + ".1"))
                    used_mw = _parse_numeric(await self._async_get_one(poe_used_mw_col + ".1"))
                    health_raw = _parse_numeric(await self._async_get_one(poe_health_col + ".1"))
                    if budget_w is not None:
                        budget_list = [float(budget_w)]
                    if used_mw is not None:
                        used_mw_list = [float(used_mw)]
                    if health_raw is not None:
                        try:
                            health_list = [int(health_raw)]
                        except Exception:
                            health_list = []

                # Only publish if at least one value is present (device supports PoE stats)
                if budget_list or used_mw_list or health_list:
                    try:
                        budget_total_w = sum(budget_list) if budget_list else None
                        used_w = (sum(used_mw_list) / 1000.0) if used_mw_list else None

                        if budget_total_w is not None:
                            self.cache["poe_budget_total_w"] = float(budget_total_w)
                        else:
                            self.cache.pop("poe_budget_total_w", None)

                        if used_w is not None:
                            self.cache["poe_power_used_w"] = round(float(used_w), 3)
                        else:
                            self.cache.pop("poe_power_used_w", None)

                        if (budget_total_w is not None) and (used_w is not None):
                            avail_w = float(budget_total_w) - float(used_w)
                            if avail_w < 0:
                                avail_w = 0.0
                            self.cache["poe_power_available_w"] = round(avail_w, 3)
                        else:
                            self.cache.pop("poe_power_available_w", None)

                        hr = _worst_poe_health(health_list)
                        if hr is not None:
                            self.cache["poe_health_status_raw"] = int(hr)
                            self.cache["poe_health_status"] = {1: "HEALTHY", 2: "DISABLED", 3: "FAULTY"}.get(int(hr), str(hr))
                        else:
                            self.cache.pop("poe_health_status_raw", None)
                            self.cache.pop("poe_health_status", None)
                    except Exception:
                        pass
                else:
                    for k in ("poe_budget_total_w", "poe_power_used_w", "poe_power_available_w", "poe_health_status", "poe_health_status_raw"):
                        self.cache.pop(k, None)

                # --- (2) Dell N-Series per-port PoE power (private MIB) ---
                # Keep this for any existing features; not used by new PoE summary entities.
                poe_power_mw: Dict[int, float] = {}
                poe_oid = "1.3.6.1.4.1.674.10895.5000.2.6132.1.1.15.1.1.1.2.1"
                try:
                    poe_table = await self._async_walk(poe_oid)
                    for oid, val in poe_table:
                        try:
                            if_index = int(str(oid).split(".")[-1])
                        except Exception:
                            continue
                        mw = _parse_numeric(val)
                        if mw is None:
                            continue
                        poe_power_mw[if_index] = mw
                except Exception:
                    poe_power_mw = {}

                self.cache["poe_power_mw"] = poe_power_mw


        # Environmental power (Dell N-Series via private MIB)
        env_enabled = bool(self._env_options.get(CONF_ENV_ENABLE, False))
        env_mode = self._env_options.get(CONF_ENV_MODE, ENV_MODE_ATTRIBUTES)
        self.cache["env_enabled"] = env_enabled
        self.cache["env_mode"] = env_mode
        self.cache.setdefault("env_power_mw", {})
        self.cache.setdefault("env_power_mw_total", 0.0)

        if not env_enabled:
            # Keep keys stable, but clear values when disabled
            self.cache["env_power_mw"] = {}
            self.cache["env_power_mw_total"] = 0.0
        else:
            try:
                interval = int(self._env_options.get(CONF_ENV_POLL_INTERVAL, DEFAULT_ENV_POLL_INTERVAL))
            except Exception:
                interval = DEFAULT_ENV_POLL_INTERVAL

            should_poll = (now_mono - float(self._env_last_poll or 0.0)) >= interval
            # Always poll once on startup so we have initial values.
            should_poll = should_poll or float(self._env_last_poll or 0.0) == 0.0

            if should_poll:
                self._env_last_poll = now_mono
                env_power_mw: Dict[int, float] = {}

                # Dell N-Series (observed):
                # 1.3.6.1.4.1.674.10895.5000.2.6132.1.1.43.1.9.1.4.1.<idx> = INTEGER: <mW>
                # This aligns with CLI "show system" Current Power (Watts).
                env_oid = "1.3.6.1.4.1.674.10895.5000.2.6132.1.1.43.1.9.1.4.1"
                env_table = await self._async_walk(env_oid)
                for oid, val in env_table:
                    try:
                        env_idx = int(str(oid).split(".")[-1])
                    except Exception:
                        continue
                    mw = _parse_numeric(val)
                    if mw is None:
                        continue
                    env_power_mw[env_idx] = mw

                self.cache["env_power_mw"] = env_power_mw
                self.cache["env_power_mw_total"] = float(sum(env_power_mw.values()))

                # Dell OS6 CPU / Memory / Fan metrics (best-effort; safe to ignore if not supported)

                # Memory OIDs return values in KB on Dell OS6 (based on observed values).
                # Values may come back as typed strings (e.g. "Gauge32: 12345"); parse numerics defensively.
                try:
                    mem_free_kb_raw = await self._async_get_one("1.3.6.1.4.1.674.10895.5000.2.6132.1.1.1.1.4.1.0")
                    mem_free_kb = _parse_numeric(mem_free_kb_raw)
                    self.cache["env_mem_free_kb"] = int(mem_free_kb) if mem_free_kb is not None else None
                except Exception:
                    self.cache["env_mem_free_kb"] = None

                try:
                    mem_total_kb_raw = await self._async_get_one("1.3.6.1.4.1.674.10895.5000.2.6132.1.1.1.1.4.2.0")
                    mem_total_kb = _parse_numeric(mem_total_kb_raw)
                    self.cache["env_mem_total_kb"] = int(mem_total_kb) if mem_total_kb is not None else None
                except Exception:
                    self.cache["env_mem_total_kb"] = None

                try:
                    cpu_s = str(await self._async_get_one("1.3.6.1.4.1.674.10895.5000.2.6132.1.1.1.1.4.9.0"))
                    self.cache["env_cpu_raw"] = cpu_s
                    # Observed example:
                    #   "    5 Secs ( 10.5746%)   60 Secs ( 11.9951%)  300 Secs ( 12.3370%)"
                    # Use a tolerant parse: grab the first 3 percentage-like numbers.
                    nums = re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*%", cpu_s)
                    if len(nums) >= 3:
                        self.cache["env_cpu_5s"] = float(nums[0])
                        self.cache["env_cpu_60s"] = float(nums[1])
                        self.cache["env_cpu_300s"] = float(nums[2])
                    else:
                        self.cache["env_cpu_5s"] = None
                        self.cache["env_cpu_60s"] = None
                        self.cache["env_cpu_300s"] = None
                except Exception:
                    self.cache["env_cpu_5s"] = None
                    self.cache["env_cpu_60s"] = None
                    self.cache["env_cpu_300s"] = None

                try:
                    fans: dict[int, int] = {}
                    for oid, val in await self._async_walk("1.3.6.1.4.1.674.10895.5000.2.6132.1.1.43.1.6.1.4.1"):
                        try:
                            idx = int(str(oid).split(".")[-1])
                        except Exception:
                            continue
                        n = _parse_numeric(val)
                        if n is None:
                            continue
                        fans[idx] = int(n)
                    self.cache["env_fans_rpm"] = fans or None
                except Exception:
                    self.cache["env_fans_rpm"] = None

                # Fan status (observed: 2 = OK)
                try:
                    fan_status: dict[int, int] = {}
                    for oid, val in await self._async_walk("1.3.6.1.4.1.674.10895.5000.2.6132.1.1.43.1.6.1.3.1"):
                        try:
                            idx = int(str(oid).split(".")[-1])
                        except Exception:
                            continue
                        n = _parse_numeric(val)
                        if n is None:
                            continue
                        fan_status[idx] = int(n)
                    self.cache["env_fans_status"] = fan_status or None
                except Exception:
                    self.cache["env_fans_status"] = None

                # PSU status (observed: 2 = OK)
                try:
                    psu_status: dict[int, int] = {}
                    for oid, val in await self._async_walk("1.3.6.1.4.1.674.10895.5000.2.6132.1.1.43.1.7.1.2.1"):
                        try:
                            idx = int(str(oid).split(".")[-1])
                        except Exception:
                            continue
                        n = _parse_numeric(val)
                        if n is None:
                            continue
                        psu_status[idx] = int(n)
                    self.cache["env_psu_status"] = psu_status or None
                except Exception:
                    self.cache["env_psu_status"] = None

                # Temperatures (C) - includes "System Temperature" at index 0 on Dell OS6
                try:
                    temps_c: dict[int, int] = {}
                    for oid, val in await self._async_walk("1.3.6.1.4.1.674.10895.5000.2.6132.1.1.43.1.8.1.5.1"):
                        try:
                            idx = int(str(oid).split(".")[-1])
                        except Exception:
                            continue
                        n = _parse_numeric(val)
                        if n is None:
                            continue
                        temps_c[idx] = int(n)
                    self.cache["env_temps_c"] = temps_c or None
                except Exception:
                    self.cache["env_temps_c"] = None

                # Unit/System temperature + state (Dell OS6)
                try:
                    raw = await self._async_get_one("1.3.6.1.4.1.674.10895.5000.2.6132.1.1.43.1.15.1.3.1")
                    n = _parse_numeric(raw)
                    self.cache["env_unit_temp_c"] = int(n) if n is not None else None
                except Exception:
                    self.cache["env_unit_temp_c"] = None
                try:
                    raw = await self._async_get_one("1.3.6.1.4.1.674.10895.5000.2.6132.1.1.43.1.15.1.2.1")
                    n = _parse_numeric(raw)
                    self.cache["env_unit_temp_state"] = int(n) if n is not None else None
                except Exception:
                    self.cache["env_unit_temp_state"] = None

                # ---- Cross-vendor fallbacks (only fill missing values) ----
                # 1) ENTITY-SENSOR-MIB (1.3.6.1.2.1.99) for temps/fans/power when available.
                # 2) HOST-RESOURCES-MIB (1.3.6.1.2.1.25) for CPU/memory when available.

                # ENTITY-SENSOR-MIB: entPhySensorType (temperature/fan/power)
                # Only run if we are missing key environmental dicts.
                need_entity_sensor = (
                    self.cache.get("env_temps_c") in (None, {})
                    or self.cache.get("env_fans_rpm") in (None, {})
                    or (float(self.cache.get("env_power_mw_total") or 0.0) == 0.0)
                )

                if need_entity_sensor:
                    ent_type_oid = "1.3.6.1.2.1.99.1.1.1.1"  # entPhySensorType
                    ent_value_oid = "1.3.6.1.2.1.99.1.1.1.4"  # entPhySensorValue
                    ent_scale_oid = "1.3.6.1.2.1.99.1.1.1.3"  # entPhySensorScale
                    ent_prec_oid = "1.3.6.1.2.1.99.1.1.1.2"  # entPhySensorPrecision
                    ent_oper_oid = "1.3.6.1.2.1.99.1.1.1.5"  # entPhySensorOperStatus

                    try:
                        types: dict[int, int] = {}
                        for oid, val in await self._async_walk(ent_type_oid):
                            try:
                                idx = int(str(oid).split(".")[-1])
                            except Exception:
                                continue
                            n = _parse_numeric(val)
                            if n is None:
                                continue
                            types[idx] = int(n)

                        if types:
                            values: dict[int, Any] = {}
                            scales: dict[int, int] = {}
                            precs: dict[int, int] = {}
                            opers: dict[int, int] = {}

                            for oid, val in await self._async_walk(ent_value_oid):
                                try:
                                    idx = int(str(oid).split(".")[-1])
                                except Exception:
                                    continue
                                values[idx] = val

                            for oid, val in await self._async_walk(ent_scale_oid):
                                try:
                                    idx = int(str(oid).split(".")[-1])
                                except Exception:
                                    continue
                                n = _parse_numeric(val)
                                if n is None:
                                    continue
                                scales[idx] = int(n)

                            for oid, val in await self._async_walk(ent_prec_oid):
                                try:
                                    idx = int(str(oid).split(".")[-1])
                                except Exception:
                                    continue
                                n = _parse_numeric(val)
                                if n is None:
                                    continue
                                precs[idx] = int(n)

                            for oid, val in await self._async_walk(ent_oper_oid):
                                try:
                                    idx = int(str(oid).split(".")[-1])
                                except Exception:
                                    continue
                                n = _parse_numeric(val)
                                if n is None:
                                    continue
                                opers[idx] = int(n)

                            # entPhySensorType enums:
                            # celsius(8), rpm(10), watts(6)
                            temps_c: dict[int, int] = {} if self.cache.get("env_temps_c") in (None, {}) else dict(self.cache.get("env_temps_c") or {})
                            fans_rpm: dict[int, int] = {} if self.cache.get("env_fans_rpm") in (None, {}) else dict(self.cache.get("env_fans_rpm") or {})
                            fans_status: dict[int, int] = {} if self.cache.get("env_fans_status") in (None, {}) else dict(self.cache.get("env_fans_status") or {})

                            watts_mw_total = 0.0
                            watts_found = False

                            for idx, t in types.items():
                                v = _entity_sensor_value_to_float(values.get(idx), scales.get(idx), precs.get(idx))
                                if v is None:
                                    continue

                                if t == 8:  # celsius
                                    # Keep sane range to avoid bogus sensors
                                    if -50.0 <= v <= 150.0:
                                        temps_c.setdefault(idx, int(round(v)))
                                elif t == 10:  # rpm
                                    if 0.0 <= v <= 50000.0:
                                        fans_rpm.setdefault(idx, int(round(v)))
                                        # Map entPhySensorOperStatus ok(1)/unavailable(2)/nonoperational(3)
                                        # to our existing fan status convention: 2=OK, 3=FAILED, 1=NOT PRESENT
                                        oper = int(opers.get(idx, 2))
                                        fans_status.setdefault(idx, {1: 2, 2: 1, 3: 3}.get(oper, 3))
                                elif t == 6:  # watts
                                    if 0.0 <= v <= 100000.0:
                                        watts_found = True
                                        watts_mw_total += float(v) * 1000.0

                            if temps_c:
                                self.cache["env_temps_c"] = temps_c
                            if fans_rpm:
                                self.cache["env_fans_rpm"] = fans_rpm
                            if fans_status:
                                self.cache["env_fans_status"] = fans_status

                            # Only populate env_power_mw_total if Dell private table is absent.
                            if watts_found and float(self.cache.get("env_power_mw_total") or 0.0) == 0.0:
                                self.cache["env_power_mw_total"] = float(watts_mw_total)
                    except Exception:
                        pass

                                # Huawei/Quidway fallback: HUAWEI-ENTITY-EXTENT-MIB hwEntityTemperature
                # Only run if temperatures are still missing after ENTITY-SENSOR-MIB.
                if self.cache.get("env_temps_c") in (None, {}):
                    try:
                        temps_c: dict[int, int] = {}
                        for oid, val in await self._async_walk(OID_hwEntityTemperature):
                            try:
                                idx = int(str(oid).split(".")[-1])
                            except Exception:
                                continue
                            n = _parse_numeric(val)
                            if n is None:
                                continue
                            try:
                                v = float(n)
                            except Exception:
                                continue
                            # hwEntityTemperature is typically in degrees Celsius.
                            if -50.0 <= v <= 200.0:
                                temps_c[idx] = int(round(v))
                        if temps_c:
                            self.cache["env_temps_c"] = temps_c
                    except Exception:
                        pass

# HOST-RESOURCES-MIB fallback: CPU + memory (only fill missing).
                # CPU: hrProcessorLoad values 0..100 across processors.
                if self.cache.get("env_cpu_5s") is None and self.cache.get("env_cpu_60s") is None and self.cache.get("env_cpu_300s") is None:
                    try:
                        cpu_vals: list[float] = []
                        for oid, val in await self._async_walk("1.3.6.1.2.1.25.3.3.1.2"):
                            n = _parse_numeric(val)
                            if n is None:
                                continue
                            f = float(n)
                            if 0.0 <= f <= 100.0:
                                cpu_vals.append(f)
                        if cpu_vals:
                            avg = sum(cpu_vals) / float(len(cpu_vals))
                            self.cache["env_cpu_5s"] = avg
                            self.cache["env_cpu_60s"] = avg
                            self.cache["env_cpu_300s"] = avg
                    except Exception:
                        pass

                # Memory: hrStorageTable, selecting hrStorageRam.
                if self.cache.get("env_mem_total_kb") is None or self.cache.get("env_mem_free_kb") is None:
                    try:
                        hr_type_oid = "1.3.6.1.2.1.25.2.3.1.2"
                        hr_alloc_oid = "1.3.6.1.2.1.25.2.3.1.4"
                        hr_size_oid = "1.3.6.1.2.1.25.2.3.1.5"
                        hr_used_oid = "1.3.6.1.2.1.25.2.3.1.6"
                        ram_type = "1.3.6.1.2.1.25.2.1.2"  # hrStorageRam

                        ram_idxs: set[int] = set()
                        for oid, val in await self._async_walk(hr_type_oid):
                            try:
                                idx = int(str(oid).split(".")[-1])
                            except Exception:
                                continue
                            s = str(val)
                            if ram_type in s:
                                ram_idxs.add(idx)

                        if ram_idxs:
                            alloc_units: dict[int, int] = {}
                            sizes: dict[int, int] = {}
                            useds: dict[int, int] = {}

                            for oid, val in await self._async_walk(hr_alloc_oid):
                                try:
                                    idx = int(str(oid).split(".")[-1])
                                except Exception:
                                    continue
                                if idx not in ram_idxs:
                                    continue
                                n = _parse_numeric(val)
                                if n is None:
                                    continue
                                alloc_units[idx] = int(n)

                            for oid, val in await self._async_walk(hr_size_oid):
                                try:
                                    idx = int(str(oid).split(".")[-1])
                                except Exception:
                                    continue
                                if idx not in ram_idxs:
                                    continue
                                n = _parse_numeric(val)
                                if n is None:
                                    continue
                                sizes[idx] = int(n)

                            for oid, val in await self._async_walk(hr_used_oid):
                                try:
                                    idx = int(str(oid).split(".")[-1])
                                except Exception:
                                    continue
                                if idx not in ram_idxs:
                                    continue
                                n = _parse_numeric(val)
                                if n is None:
                                    continue
                                useds[idx] = int(n)

                            total_bytes = 0
                            used_bytes = 0
                            for idx in ram_idxs:
                                au = alloc_units.get(idx)
                                sz = sizes.get(idx)
                                us = useds.get(idx)
                                if au is None or sz is None or us is None:
                                    continue
                                total_bytes += int(au) * int(sz)
                                used_bytes += int(au) * int(us)

                            if total_bytes > 0:
                                free_bytes = max(0, total_bytes - used_bytes)
                                if self.cache.get("env_mem_total_kb") is None:
                                    self.cache["env_mem_total_kb"] = int(total_bytes / 1024)
                                if self.cache.get("env_mem_free_kb") is None:
                                    self.cache["env_mem_free_kb"] = int(free_bytes / 1024)
                    except Exception:
                        pass


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

def _parse_numeric(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        try:
            return int(float(val))
        except (TypeError, ValueError):
            return None


def _as_bytes(val) -> bytes:
    """Best-effort conversion of pysnmp OctetString/bytes/hex-string to raw bytes."""
    if val is None:
        return b""
    if isinstance(val, (bytes, bytearray)):
        return bytes(val)
    # pysnmp OctetString often supports .asOctets()
    try:
        as_octets = getattr(val, "asOctets", None)
        if callable(as_octets):
            return bytes(as_octets())
    except Exception:
        pass
    # Some devices / libs stringify as '0xAABBCC' or 'AA:BB:CC'
    s = str(val).strip()
    # Net-SNMP style: 'Hex-STRING: AA BB CC'
    if s.lower().startswith("hex-string:"):
        s = s.split(":", 1)[1].strip()
    if s.startswith("0x") and len(s) > 2:
        try:
            return bytes.fromhex(s[2:])
        except Exception:
            return b""
    # hex with separators
    if ":" in s and all(len(p) == 2 for p in s.split(":")):
        try:
            return bytes.fromhex(s.replace(":", ""))
        except Exception:
            return b""
    # Space-separated hex bytes: 'AA BB CC'
    parts = s.split()
    if parts and all(len(p) == 2 and all(c in "0123456789abcdefABCDEF" for c in p) for p in parts):
        try:
            return bytes.fromhex("".join(parts))
        except Exception:
            return b""
    # fallback: empty
    return b""


def _decode_bridge_port_bitmap(val) -> set[int]:
    """Decode Q-BRIDGE PortList bitmap into a set of 1-based bridge port numbers."""
    data = _as_bytes(val)
    ports: set[int] = set()
    for oct_i, b in enumerate(data):
        # Q-BRIDGE PortList uses MSB-first within each octet
        for bit in range(8):
            if b & (0x80 >> bit):
                ports.add(oct_i * 8 + bit + 1)
    return ports
