from __future__ import annotations

import asyncio
import time
import logging
import os
import json
from typing import Any, Dict, Optional, List

from homeassistant.core import HomeAssistant

from .features.cpu import poll_cpu
from .features.memory import poll_memory
from .features.interfaces import poll_interfaces
from .features.ipv4 import poll_ipv4
from .features.power import poll_power
from .features.fans import poll_fans
from .features.psu import poll_psu
from .features.temperature import poll_temperature
from .features.entity_sensor import poll_entity_sensor_fallback
from .features.bandwidth import poll_bandwidth
from .features.poe import poll_poe
from .features.h3c import poll_h3c_environment
from .features.engine import ensure_engine
from .features.device_info import initialize_device_info, refresh_device_info
from .features.auth import build_auth_data

from .snmp_compat import (
    UdpTransportTarget,
    ContextData,
    _do_get_one,
    _do_next_walk,
    _do_set_alias,
    _do_set_admin_status,
    _do_set_poe_admin,
    _do_set_poe_priority,
    _do_set_system_string,
)


# Canonical OIDs from const.py (original repo)
from .const import (
    OID_sysDescr,
    OID_sysName,
    OID_sysUpTime,
    OID_sysContact,
    OID_sysLocation,
    CONF_BW_INCLUDE_STARTS_WITH,
    CONF_BW_INCLUDE_CONTAINS,
    CONF_BW_INCLUDE_ENDS_WITH,
    CONF_BW_EXCLUDE_STARTS_WITH,
    CONF_BW_EXCLUDE_CONTAINS,
    CONF_BW_EXCLUDE_ENDS_WITH,
    CONF_ENV_ENABLE,
    CONF_ENV_MODE,
    CONF_ENV_POLL_INTERVAL,
    ENV_MODE_ATTRIBUTES,
    DEFAULT_ENV_POLL_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

# ---------- client ----------

class SwitchSnmpClient:
    """SNMP client using PySNMP v7 asyncio API."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        snmp_settings: Dict[str, Any],
        custom_oids: Optional[Dict[str, str]] = None,
        bandwidth_options: Optional[Dict[str, Any]] = None,
        poe_options: Optional[Dict[str, Any]] = None,
        env_options: Optional[Dict[str, Any]] = None,
        feature_overrides: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.hass = hass
        self.host = host
        self._snmp_settings = dict(snmp_settings or {})
        self.port = int(self._snmp_settings.get("port") or 161)
        self.custom_oids: Dict[str, str] = dict(custom_oids or {})
        self.feature_overrides: Dict[str, Any] = dict(feature_overrides or {})
        self._database: Dict[str, Any] = {}

        # Bandwidth sensor options (set by config entry options)
        self._bandwidth_options: Dict[str, Any] = dict(bandwidth_options or {})
        
        def _clean_list(key: str) -> tuple[str, ...]:
            return tuple(str(s).strip().lower() for s in (self._bandwidth_options.get(key, []) or []) if str(s).strip())

        self._bw_include_starts = _clean_list(CONF_BW_INCLUDE_STARTS_WITH)
        self._bw_include_contains = _clean_list(CONF_BW_INCLUDE_CONTAINS)
        self._bw_include_ends = _clean_list(CONF_BW_INCLUDE_ENDS_WITH)
        self._bw_exclude_starts = _clean_list(CONF_BW_EXCLUDE_STARTS_WITH)
        self._bw_exclude_contains = _clean_list(CONF_BW_EXCLUDE_CONTAINS)
        self._bw_exclude_ends = _clean_list(CONF_BW_EXCLUDE_ENDS_WITH)

        self._poe_options = poe_options or {}
        self._poe_last_poll: float = 0.0

        self._env_options = env_options or {}
        self._env_last_poll: float = 0.0
        self._bw_last_poll = None  # monotonic timestamp of last bandwidth counter poll
        self._bw_use_hc: Optional[bool] = None
        self._bw_last: Dict[int, Dict[str, Any]] = {}

        self.engine = None
        self.target = None
        self._target_args = ((host, self.port),)
        self._target_kwargs = dict(timeout=1.5, retries=1)

        # SNMP auth/security model (v2c community or v3 USM)
        self.auth_data = self._build_auth_data(self._snmp_settings)
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

        # IPv4 address data rarely changes; throttle refreshes independently.
        self._last_ipv4_poll: float = 0.0
        self._ipv4_poll_interval: float = 300.0

        # Vendor-specific firmware/model OIDs (CBS350, Zyxel, MikroTik) never
        # change at runtime; fetch once during async_initialize and skip on polls.
        self._vendor_oids_fetched: bool = False

    def _load_database(self) -> None:
        """Load OID database from JSON files."""
        self._database = {}
        db_path = os.path.join(os.path.dirname(__file__), "database")
        if not os.path.exists(db_path):
            _LOGGER.warning("Database directory not found: %s", db_path)
            return
        
        for filename in os.listdir(db_path):
            if filename.endswith(".json"):
                key = filename[:-5]
                try:
                    with open(os.path.join(db_path, filename), "r") as f:
                        self._database[key] = json.load(f)
                except Exception as e:
                    _LOGGER.error("Failed to load database file %s: %s", filename, e)

    def _get_vendor_info(self) -> Dict[str, Any]:
        """Determine vendor metadata dynamically based on sysObjectID or sysDescr."""
        sys_obj_id = self.cache.get("sysObjectID") or ""
        sys_descr = self.cache.get("sysDescr") or ""
        vendors_db = self._database.get("vendors", {}).get("vendors", [])

        # 1. Match by sysObjectID prefix first
        for v in vendors_db:
            prefix = v.get("sys_object_id_prefix")
            if prefix and sys_obj_id.startswith(prefix):
                return v

        # 2. Match by keywords in sysDescr or sysObjectID
        for v in vendors_db:
            keywords = v.get("keywords", [])
            for kw in keywords:
                if kw and (kw.lower() in sys_descr.lower() or kw.lower() in sys_obj_id.lower()):
                    return v

        # 3. Match by name in sysDescr
        for v in vendors_db:
            name = v.get("name")
            if name and name.lower() in sys_descr.lower():
                return v

        # Fallback to standard
        for v in vendors_db:
            if v.get("name") == "Standard":
                return v

        return {"name": "Unknown"}

    def _get_vendor(self) -> str:
        """Determine vendor based on sysObjectID from database."""
        return self._get_vendor_info().get("name", "Unknown")

    def _get_database_oids(self, feature: str, vendor: str) -> List[Dict[str, Any]]:
        """Get OIDs for a specific feature and vendor from database."""
        # Check for feature overrides
        if feature in self.feature_overrides:
            override = self.feature_overrides[feature]
            # Ensure vendors list is present for compatibility
            if "vendors" not in override:
                override["vendors"] = [vendor]
            return [override]
            
        db = self._database.get(feature, {}).get(feature, [])
        vendor_lower = vendor.lower()
        return [item for item in db if any(v.lower() == vendor_lower for v in item.get("vendors", []))]

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

    @staticmethod
    def _build_auth_data(settings: Dict[str, Any]):
        """Build pysnmp authData object — delegates to features/auth.py."""
        return build_auth_data(settings)


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
        await ensure_engine(self)

    async def _ensure_target(self) -> None:
        if self.target is None:
            self.target = await UdpTransportTarget.create(*self._target_args, **self._target_kwargs)

    # ---------- lifecycle / fetch ----------

    async def async_close(self) -> None:
        """Release pysnmp resources (transport handles, background tasks).

        Must be called from async_unload_entry to prevent resource leaks on
        integration reload or reconfiguration.
        """
        if self.engine is None:
            return
        try:
            # pysnmp 7.x (v3arch asyncio): close the transport dispatcher.
            dispatcher = getattr(self.engine, "transportDispatcher", None)
            if dispatcher is not None:
                if hasattr(dispatcher, "closeDispatcher"):
                    dispatcher.closeDispatcher()
        except Exception:
            pass
        finally:
            self.engine = None
            self.target = None

    async def async_initialize(self) -> None:
        await self.hass.async_add_executor_job(self._load_database)
        await self._ensure_engine()
        await self._ensure_target()

        # Issue a warm-up GET to flush any remaining lazy pysnmp internal state.
        try:
            await self._async_get_one(OID_sysDescr)
        except Exception:
            pass

        # Build interface table and state first (names, alias, admin/oper)
        await poll_interfaces(self, dynamic_only=False)

        # Build IPv4 maps and attach to interfaces
        await poll_ipv4(self)
        self._last_ipv4_poll = time.monotonic()

        # Populate manufacturer, firmware, model, vendor flags
        await initialize_device_info(self)

    async def _async_get_one(self, oid: str) -> Optional[str]:
        await self._ensure_engine()
        await self._ensure_target()
        return await _do_get_one(self.engine, self.auth_data, self.target, self.context, oid)

    async def _async_walk(self, base_oid: str) -> list[tuple[str, Any]]:
        await self._ensure_engine()
        await self._ensure_target()
        return await _do_next_walk(self.engine, self.auth_data, self.target, self.context, base_oid)




    async def async_refresh_all(self) -> None:
        await self._ensure_engine()
        await self._ensure_target()
        await poll_interfaces(self, dynamic_only=False)
        await poll_ipv4(self)

    async def async_refresh_dynamic(self) -> None:
        await self._ensure_engine()
        await self._ensure_target()
        await poll_interfaces(self, dynamic_only=True)
        # IPv4 data rarely changes; throttle separately (default 300 s).
        now_mono = time.monotonic()
        if (
            self._last_ipv4_poll == 0.0
            or (now_mono - self._last_ipv4_poll) >= self._ipv4_poll_interval
        ):
            self._last_ipv4_poll = now_mono
            await poll_ipv4(self)

    # ---------- coordinator hook ----------
    async def async_poll(self) -> Dict[str, Any]:
        # Keep system/diagnostic fields fresh (e.g., sysUpTime) so diagnostic
        # sensors update without requiring an integration restart.
        await self._ensure_engine()
        await self._ensure_target()

        # sysUpTime can be very "chatty"; poll it less frequently.
        now_mono = time.monotonic()
        poll_uptime = (
            "sysUpTime" not in self.cache
            or (now_mono - self._last_uptime_poll) >= float(self._uptime_poll_interval)
        )

        if poll_uptime:
            self._last_uptime_poll = now_mono

        sysname_oid = self._custom_oid("name") or self._custom_oid("hostname") or OID_sysName
        uptime_oid = self._custom_oid("uptime") or OID_sysUpTime
        syscontact_oid = self._custom_oid("contact") or OID_sysContact
        syslocation_oid = self._custom_oid("location") or OID_sysLocation

        sysdescr, sysname, sysuptime, syscontact, syslocation = await asyncio.gather(
            _do_get_one(self.engine, self.auth_data, self.target, self.context, OID_sysDescr),
            _do_get_one(self.engine, self.auth_data, self.target, self.context, sysname_oid),
            _do_get_one(self.engine, self.auth_data, self.target, self.context, uptime_oid) if poll_uptime else asyncio.sleep(0, result=None),
            _do_get_one(self.engine, self.auth_data, self.target, self.context, syscontact_oid),
            _do_get_one(self.engine, self.auth_data, self.target, self.context, syslocation_oid),
        )
        if (not poll_uptime) and ("sysUpTime" in self.cache):
            sysuptime = self.cache.get("sysUpTime")
        if sysdescr is not None:
            self.cache["sysDescr"] = sysdescr
        if sysname is not None:
            self.cache["sysName"] = sysname
        if sysuptime is not None:
            self.cache["sysUpTime"] = sysuptime
        if syscontact is not None:
            self.cache["sysContact"] = syscontact
        if syslocation is not None:
            self.cache["sysLocation"] = syslocation

        # Re-evaluate manufacturer/firmware from sysDescr on each poll
        await refresh_device_info(self)
        await self.async_refresh_dynamic()

        # Bandwidth counters (optional; per-device)
        await poll_bandwidth(self)

        # PoE (optional)
        await poll_poe(self)


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
                if self._get_vendor_info().get("environment_driver") == "h3c":
                    await poll_h3c_environment(self)
                else:
                    vendor = self.cache.get("vendor", "Unknown")

                    # Memory
                    await poll_memory(self, vendor)

                    # CPU
                    await poll_cpu(self, vendor)

                    # Power
                    await poll_power(self, vendor)

                    # Fans
                    await poll_fans(self, vendor)

                    # PSU
                    await poll_psu(self, vendor)

                    # Temperature
                    await poll_temperature(self, vendor)

                    # Fallback
                    await poll_entity_sensor_fallback(self)





        return self.cache

    # ---------- mutations ----------
    async def set_alias(self, if_index: int, alias: str) -> bool:
        await self._ensure_engine()
        await self._ensure_target()
        ok = await _do_set_alias(self.engine, self.auth_data, self.target, self.context, if_index, alias)
        if ok:
            self.cache.setdefault("ifTable", {}).setdefault(if_index, {})["alias"] = alias
        else:
            _LOGGER.warning("Failed to set alias via SNMP on ifIndex %s", if_index)
        return ok

    async def set_admin_status(self, if_index: int, value: int) -> bool:
        await self._ensure_engine()
        await self._ensure_target()
        return await _do_set_admin_status(self.engine, self.auth_data, self.target, self.context, if_index, value)

    async def set_poe_admin(self, group_index: int, port_index: int, value: int) -> bool:
        await self._ensure_engine()
        await self._ensure_target()
        vendor = self.cache.get("vendor", "Unknown")
        poe_items = self._get_database_oids("poe", vendor)
        standard_item = None
        for item in poe_items:
            if "poe" in self.feature_overrides and item == self.feature_overrides["poe"]:
                standard_item = item
                break
            elif "oid_budget" in item:
                standard_item = item
                break
        custom_oid = (standard_item or {}).get("oid_port_admin")
        ok = await _do_set_poe_admin(self.engine, self.auth_data, self.target, self.context, group_index, port_index, value, custom_oid)
        if ok:
            # Update cache immediately
            ifindex_map = self.cache.get("ifindex_by_baseport", {})
            target_idx = ifindex_map.get(port_index, port_index)
            if target_idx in self.cache.setdefault("poe_ports", {}):
                self.cache["poe_ports"][target_idx]["admin"] = value
        else:
            _LOGGER.warning("Failed to set PoE admin via SNMP on group %s port %s", group_index, port_index)
        return ok

    async def set_poe_priority(self, group_index: int, port_index: int, value: int) -> bool:
        await self._ensure_engine()
        await self._ensure_target()
        vendor = self.cache.get("vendor", "Unknown")
        poe_items = self._get_database_oids("poe", vendor)
        standard_item = None
        for item in poe_items:
            if "poe" in self.feature_overrides and item == self.feature_overrides["poe"]:
                standard_item = item
                break
            elif "oid_budget" in item:
                standard_item = item
                break
        custom_oid = (standard_item or {}).get("oid_port_priority")
        ok = await _do_set_poe_priority(self.engine, self.auth_data, self.target, self.context, group_index, port_index, value, custom_oid)
        if ok:
            # Update cache immediately
            ifindex_map = self.cache.get("ifindex_by_baseport", {})
            target_idx = ifindex_map.get(port_index, port_index)
            if target_idx in self.cache.setdefault("poe_ports", {}):
                self.cache["poe_ports"][target_idx]["priority"] = value
        else:
            _LOGGER.warning("Failed to set PoE priority via SNMP on group %s port %s", group_index, port_index)
        return ok

    async def set_system_string(self, oid: str, value: str) -> bool:
        await self._ensure_engine()
        await self._ensure_target()
        ok = await _do_set_system_string(self.engine, self.auth_data, self.target, self.context, oid, value)
        if ok:
            if oid in (OID_sysName, self._custom_oid("name"), self._custom_oid("hostname")):
                self.cache["sysName"] = value
            elif oid in (OID_sysContact, self._custom_oid("contact")):
                self.cache["sysContact"] = value
            elif oid in (OID_sysLocation, self._custom_oid("location")):
                self.cache["sysLocation"] = value
        else:
            _LOGGER.warning("Failed to set system OID %s to value %s", oid, value)
        return ok
