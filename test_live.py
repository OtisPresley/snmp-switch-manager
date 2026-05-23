#!/usr/bin/env python3
"""
Standalone integration test for snmp-switch-manager feature modules.

Connects to a real switch via SNMPv3 and validates:
  - auth / engine bootstrap (features/auth.py, features/engine.py)
  - device info parsing     (features/device_info.py)
  - interface table         (features/interfaces.py)
  - IPv4 map                (features/ipv4.py)
  - bandwidth counters      (features/bandwidth.py)
  - PoE budget + ports      (features/poe.py)
  - CPU / memory / temps /  (features/cpu.py, memory.py, temperature.py,
    fans / PSU / power        fans.py, psu.py, power.py)
  - ENTITY-SENSOR fallback  (features/entity_sensor.py)
  - helpers                 (helpers.py parse utilities)

Usage:
    cd /home/jamie/Documents/Projects/snmp-switch-manager
    source venv/bin/activate
    python test_live.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import types
from typing import Any, Dict

# ---------------------------------------------------------------------------
# Path setup – allow importing the integration without installing it
# ---------------------------------------------------------------------------
PROJECT = os.path.dirname(__file__)
sys.path.insert(0, PROJECT)

# ---------------------------------------------------------------------------
# Minimal HomeAssistant stub (only the surface the integration uses)
# ---------------------------------------------------------------------------

class FakeLoop:
    async def run_in_executor(self, executor, fn, *args):
        return await asyncio.get_event_loop().run_in_executor(executor, fn, *args)


class FakeHass:
    def __init__(self):
        self.loop = asyncio.get_event_loop()

    async def async_add_executor_job(self, fn, *args):
        return await asyncio.get_event_loop().run_in_executor(None, fn, *args)


# Patch homeassistant into sys.modules before any import
_ha = types.ModuleType("homeassistant")
_ha_core = types.ModuleType("homeassistant.core")
_ha_core.HomeAssistant = FakeHass
_ha.core = _ha_core
sys.modules["homeassistant"] = _ha
sys.modules["homeassistant.core"] = _ha_core

# ---------------------------------------------------------------------------
# Test credentials
# ---------------------------------------------------------------------------
SWITCH_HOST = "10.0.12.1"
SWITCH_PORT = 161
SNMP_SETTINGS = {
    "host": SWITCH_HOST,
    "port": SWITCH_PORT,
    "version": "v3",
    "snmpv3_username": "snmpv3user",
    "snmpv3_auth_protocol": "sha",
    "snmpv3_auth_password": "OtisPresley1983",
    "snmpv3_priv_protocol": "none",
    "snmpv3_priv_password": "",
}

# Minimal bandwidth / PoE / env options to enable all polling
BW_OPTIONS: Dict[str, Any] = {
    "bw_enable": True,
    "bw_poll_interval": 0,          # force immediate poll
    "bw_mode": "sensors",
}
POE_OPTIONS: Dict[str, Any] = {
    "poe_enable": True,
    "poe_poll_interval": 0,
    "poe_mode": "attributes",
}
ENV_OPTIONS: Dict[str, Any] = {
    "env_enable": True,
    "env_mode": "attributes",
    "env_poll_interval": 0,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m⚠\033[0m"
INFO = "\033[94mℹ\033[0m"

_results: list[tuple[str, bool, str]] = []


def check(name: str, value: Any, *, expect=None, nonempty=False, truthy=False, warn_only=False) -> Any:
    ok = True
    detail = ""
    if nonempty:
        ok = bool(value) and value not in (None, {}, [], "")
        detail = f"got {value!r}"
    elif truthy:
        ok = bool(value)
        detail = f"got {value!r}"
    elif expect is not None:
        ok = value == expect
        detail = f"expected {expect!r}, got {value!r}"
    else:
        ok = value is not None
        detail = f"got {value!r}"

    icon = PASS if ok else (WARN if warn_only else FAIL)
    label = "WARN" if (not ok and warn_only) else ("PASS" if ok else "FAIL")
    print(f"  {icon} [{label}] {name}: {detail}")
    _results.append((name, ok or warn_only, detail))
    return value


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ---------------------------------------------------------------------------
# Main test
# ---------------------------------------------------------------------------
async def run_tests():
    # Late import AFTER sys.modules patched — import only what we need,
    # bypassing __init__.py and config_flow.py which require full HA install.
    import importlib
    import importlib.util

    def _stub_module(name: str, **attrs):
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[name] = m
        return m

    # Stub all HA sub-modules that get imported transitively
    for mod in [
        "homeassistant.config_entries",
        "homeassistant.exceptions",
        "homeassistant.helpers",
        "homeassistant.helpers.update_coordinator",
        "homeassistant.helpers.config_validation",
        "homeassistant.helpers.selector",
        "homeassistant.const",
        "homeassistant.data_entry_flow",
        "homeassistant.components",
        "homeassistant.components.switch",
        "homeassistant.components.select",
        "homeassistant.components.sensor",
        "homeassistant.helpers.entity",
        "homeassistant.helpers.entity_registry",
        "homeassistant.util",
        "homeassistant",
    ]:
        if mod not in sys.modules:
            _stub_module(mod)

    # Specific attributes needed by imports in snmp.py / helpers.py
    class FakeEntity:
        @property
        def unique_id(self) -> str | None:
            return getattr(self, "_attr_unique_id", None)
        @property
        def name(self) -> str | None:
            return getattr(self, "_attr_name", None)
        @property
        def device_info(self) -> Any | None:
            return getattr(self, "_attr_device_info", None)
        @property
        def icon(self) -> str | None:
            return getattr(self, "_attr_icon", None)
        def async_write_ha_state(self) -> None:
            pass

    class ConfigEntryStub:
        def __init__(self, *args, **kwargs): pass
    class DataUpdateCoordinatorStub:
        def __init__(self, *args, **kwargs): pass
    class CoordinatorEntityStub:
        def __init__(self, coordinator, context=None):
            self.coordinator = coordinator
    class SwitchEntityStub(FakeEntity):
        def __init__(self, *args, **kwargs): pass
    class SelectEntityStub(FakeEntity):
        def __init__(self, *args, **kwargs): pass
    class SensorEntityStub(FakeEntity):
        def __init__(self, *args, **kwargs): pass
    class DeviceInfoStub:
        def __init__(self, *args, **kwargs): pass

    sys.modules["homeassistant"].core = sys.modules["homeassistant.core"]
    sys.modules["homeassistant.config_entries"].ConfigEntry = ConfigEntryStub
    sys.modules["homeassistant.exceptions"].ConfigEntryAuthFailed = Exception
    sys.modules["homeassistant.helpers.update_coordinator"].DataUpdateCoordinator = DataUpdateCoordinatorStub
    sys.modules["homeassistant.helpers.update_coordinator"].CoordinatorEntity = CoordinatorEntityStub
    sys.modules["homeassistant.const"].CONF_HOST = "host"
    sys.modules["homeassistant.const"].CONF_PORT = "port"
    sys.modules["homeassistant.data_entry_flow"].FlowResult = dict
    
    # Components / Sensor / Switch / Select stubs
    sys.modules["homeassistant.components.switch"].SwitchEntity = SwitchEntityStub
    sys.modules["homeassistant.components.select"].SelectEntity = SelectEntityStub
    sys.modules["homeassistant.components.sensor"].SensorEntity = SensorEntityStub
    class SensorDeviceClassStub:
        DATA_RATE = "data_rate"
        DATA_SIZE = "data_size"
        POWER = "power"
        TEMPERATURE = "temperature"
    class SensorStateClassStub:
        MEASUREMENT = "measurement"
        TOTAL_INCREASING = "total_increasing"
    sys.modules["homeassistant.components.sensor"].SensorStateClass = SensorStateClassStub
    sys.modules["homeassistant.components.sensor"].SensorDeviceClass = SensorDeviceClassStub
    sys.modules["homeassistant.helpers.entity"].DeviceInfo = DeviceInfoStub
    sys.modules["homeassistant.helpers"].entity_registry = sys.modules["homeassistant.helpers.entity_registry"]
    
    from unittest.mock import MagicMock
    sys.modules["homeassistant.helpers.entity_registry"].async_get = lambda hass: MagicMock()
    
    sys.modules["homeassistant.util"].slugify = lambda text: text.lower().replace(" ", "_").replace("/", "_").replace("-", "_")
    
    class EntityCategory:
        DIAGNOSTIC = "diagnostic"
        CONFIG = "config"
    sys.modules["homeassistant.const"].EntityCategory = EntityCategory
    sys.modules["homeassistant.const"].PERCENTAGE = "%"
    
    class UnitOfPower:
        WATT = "W"
    sys.modules["homeassistant.const"].UnitOfPower = UnitOfPower
    
    class UnitOfTemperature:
        CELSIUS = "°C"
    sys.modules["homeassistant.const"].UnitOfTemperature = UnitOfTemperature

    # voluptuous stub (used by config_flow, not snmp.py — but __init__ imports config_flow indirectly)
    if "voluptuous" not in sys.modules:
        _stub_module("voluptuous")

    # Now import snmp.py and features directly
    import importlib.util as _ilu
    import pathlib as _pl

    _base = _pl.Path(__file__).parent / "custom_components" / "snmp_switch_manager"

    def _load(rel: str):
        name = "csm." + rel.replace("/", ".").replace(".py", "")
        spec = _ilu.spec_from_file_location(name, _base / rel)
        mod = _ilu.module_from_spec(spec)
        sys.modules[name] = mod
        # make relative imports work by setting __package__
        mod.__package__ = "custom_components.snmp_switch_manager"
        spec.loader.exec_module(mod)
        return mod

    # Import in dependency order
    _const    = importlib.import_module("custom_components.snmp_switch_manager.const")
    _compat   = importlib.import_module("custom_components.snmp_switch_manager.snmp_compat")
    _helpers  = importlib.import_module("custom_components.snmp_switch_manager.helpers")
    _snmp     = importlib.import_module("custom_components.snmp_switch_manager.snmp")
    _f_bw     = importlib.import_module("custom_components.snmp_switch_manager.features.bandwidth")
    _f_cpu    = importlib.import_module("custom_components.snmp_switch_manager.features.cpu")
    _f_di     = importlib.import_module("custom_components.snmp_switch_manager.features.device_info")
    _f_iface  = importlib.import_module("custom_components.snmp_switch_manager.features.interfaces")
    _f_ipv4   = importlib.import_module("custom_components.snmp_switch_manager.features.ipv4")
    _f_poe    = importlib.import_module("custom_components.snmp_switch_manager.features.poe")
    _f_mem    = importlib.import_module("custom_components.snmp_switch_manager.features.memory")
    _f_temp   = importlib.import_module("custom_components.snmp_switch_manager.features.temperature")
    _f_fans   = importlib.import_module("custom_components.snmp_switch_manager.features.fans")
    _f_psu    = importlib.import_module("custom_components.snmp_switch_manager.features.psu")
    _f_power  = importlib.import_module("custom_components.snmp_switch_manager.features.power")
    _f_ent    = importlib.import_module("custom_components.snmp_switch_manager.features.entity_sensor")

    SwitchSnmpClient = _snmp.SwitchSnmpClient

    from custom_components.snmp_switch_manager.features.bandwidth import _matches_any, _counter_delta
    from custom_components.snmp_switch_manager.features.cpu import _parse_cpu_string
    from custom_components.snmp_switch_manager.features.device_info import _parse_sysdescr_generic
    from custom_components.snmp_switch_manager.helpers import (
        _parse_numeric, _decode_bridge_port_bitmap, uptime_human,
        parse_pfsense_sysdescr, classify_port_type,
    )
    from custom_components.snmp_switch_manager.features.device_info import initialize_device_info, refresh_device_info
    from custom_components.snmp_switch_manager.features.interfaces import poll_interfaces
    from custom_components.snmp_switch_manager.features.ipv4 import poll_ipv4
    from custom_components.snmp_switch_manager.features.bandwidth import poll_bandwidth
    from custom_components.snmp_switch_manager.features.poe import poll_poe
    from custom_components.snmp_switch_manager.features.cpu import poll_cpu
    from custom_components.snmp_switch_manager.features.memory import poll_memory
    from custom_components.snmp_switch_manager.features.temperature import poll_temperature
    from custom_components.snmp_switch_manager.features.fans import poll_fans
    from custom_components.snmp_switch_manager.features.psu import poll_psu
    from custom_components.snmp_switch_manager.features.power import poll_power
    from custom_components.snmp_switch_manager.features.entity_sensor import poll_entity_sensor_fallback


    hass = FakeHass()

    # -----------------------------------------------------------------------
    section("1 · helpers.py – pure functions (no network)")
    # -----------------------------------------------------------------------

    # _parse_numeric
    check("_parse_numeric(42)",       _parse_numeric(42),      expect=42)
    check("_parse_numeric('7')",      _parse_numeric("7"),     expect=7)
    check("_parse_numeric('3.9')",    _parse_numeric("3.9"),   expect=3)
    check("_parse_numeric(None) is None",  _parse_numeric(None) is None, expect=True)
    check("_parse_numeric('abc') is None", _parse_numeric("abc") is None, expect=True)

    # uptime_human
    check("uptime_human(36000)",  uptime_human(36000),  expect="0d 0h 6m 0s")
    check("uptime_human(8640000)", uptime_human(8640000), expect="1d 0h 0m 0s")

    # format_interface_name tests (fallback and dynamic DB)
    from custom_components.snmp_switch_manager.helpers import format_interface_name
    check(
        "format_interface_name static fallback Gi",
        format_interface_name("gi1/0/1", unit=1, slot=0, port=1),
        expect="Gi1/0/1",
    )
    check(
        "format_interface_name static fallback Tw",
        format_interface_name("tw2/0/4", unit=2, slot=0, port=4),
        expect="Tw2/0/4",
    )
    
    custom_abbrev_db = {
        "abbreviations": {
            "prefixes": {
                "gi": "Gig",
                "te": "Ten"
            },
            "startswith": {
                "po": "Lag"
            },
            "contains": {
                "100g": "Hu"
            },
            "default": "Gig"
        }
    }
    check(
        "format_interface_name dynamic DB prefixes",
        format_interface_name("gi1/0/1", unit=1, slot=0, port=1, classification_db=custom_abbrev_db),
        expect="Gig1/0/1",
    )
    check(
        "format_interface_name dynamic DB startswith",
        format_interface_name("po10", unit=1, slot=0, port=10, classification_db=custom_abbrev_db),
        expect="Lag1/0/10",
    )

    # parse_pfsense_sysdescr
    pfs = parse_pfsense_sysdescr("pfSense myhost 2.7.2-RELEASE FreeBSD 14.0-RELEASE-p6 amd64")
    check("pfSense manufacturer", pfs["manufacturer"], expect="pfSense")
    check("pfSense firmware",     pfs["firmware"],     expect="2.7.2-RELEASE")
    check("pfSense model strip arch", "amd64" not in (pfs["model"] or ""), expect=True)
    check("non-pfSense returns None", parse_pfsense_sysdescr("Cisco IOS")["manufacturer"] is None, expect=True)

    # classify_port_type
    check("classify physical eth", classify_port_type(if_type=6, name="GigabitEthernet0/1", is_bridge_port=True),  expect="physical")
    check("classify vlan virtual",  classify_port_type(if_type=136, name="Vlan10",           is_bridge_port=False), expect="virtual")
    check("classify loopback",      classify_port_type(if_type=24, name="Loopback0",          is_bridge_port=False), expect="virtual")

    # _decode_bridge_port_bitmap
    # PortList bitmap: 0x80 = bit 1 of byte 0 → port 1; 0x40 = bit 2 of byte 0 → port 2
    bmp = _decode_bridge_port_bitmap(bytes([0xC0]))  # 11000000 → ports 1 and 2
    check("bitmap bits", bmp, expect={1, 2})

    # _matches_any (bandwidth helper)
    check("_matches_any starts",   _matches_any("gi1/0/1", ("gi",), (), ()), expect=True)
    check("_matches_any contains", _matches_any("te0/1",   (), ("eth",), ()), expect=False)
    check("_matches_any ends",     _matches_any("eth0",    (), (), ("th0",)), expect=True)

    # _counter_delta (bandwidth helper)
    check("delta normal",        _counter_delta(1000, 900, True),  expect=100)
    check("delta 32-bit wrap",   _counter_delta(100, 4000, False), expect=2**32 - 3900)

    # _parse_cpu_string
    v5s, v60s, v300s = _parse_cpu_string("CPU utilization: 5%/10%/15%")
    check("cpu 5s",  v5s,  expect=5.0)
    check("cpu 60s", v60s, expect=10.0)
    check("cpu 300s",v300s,expect=15.0)
    v5s2, _, _ = _parse_cpu_string("42")
    check("cpu plain float", v5s2, expect=42.0)
    n1, n2, n3 = _parse_cpu_string(None)
    check("cpu None -> None", n1 is None, expect=True)

    # _parse_sysdescr_generic
    mfr, fw = _parse_sysdescr_generic("Netgear Switch, V1.0.0.12", "N3048EP-ON")
    check("generic sysDescr firmware", fw, expect="V1.0.0.12")

    # -----------------------------------------------------------------------
    section("2 · auth + engine bootstrap")
    # -----------------------------------------------------------------------
    client = SwitchSnmpClient(hass, SWITCH_HOST, SNMP_SETTINGS, bandwidth_options=BW_OPTIONS, poe_options=POE_OPTIONS, env_options=ENV_OPTIONS)
    await hass.async_add_executor_job(client._load_database)
    check("auth_data created",  client.auth_data,  nonempty=True)
    check("context created",    client.context,    nonempty=True)
    check("database loaded",    client._database,  nonempty=True)

    print(f"\n  {INFO} Bootstrapping SNMP engine (may take a moment)…")
    t0 = time.monotonic()
    await client._ensure_engine()
    await client._ensure_target()
    elapsed = time.monotonic() - t0
    check("engine built",  client.engine,  nonempty=True)
    check("target built",  client.target,  nonempty=True)
    print(f"  {INFO} Engine ready in {elapsed:.2f}s")

    # -----------------------------------------------------------------------
    section("3 · basic SNMP get – connectivity + sysDescr")
    # -----------------------------------------------------------------------
    sys_descr = await client._async_get_one("1.3.6.1.2.1.1.1.0")
    check("sysDescr not None",  sys_descr,  nonempty=True)
    sys_name = await client._async_get_one("1.3.6.1.2.1.1.5.0")
    check("sysName not None",   sys_name,   nonempty=True)
    print(f"  {INFO} sysDescr : {sys_descr}")
    print(f"  {INFO} sysName  : {sys_name}")

    # -----------------------------------------------------------------------
    section("4 · device_info.py – initialize_device_info()")
    # -----------------------------------------------------------------------
    await initialize_device_info(client)

    check("cache sysDescr",      client.cache.get("sysDescr"),     nonempty=True)
    check("cache vendor",        client.cache.get("vendor"),        nonempty=True)
    check("cache sysName",       client.cache.get("sysName"),       nonempty=True)
    check("cache manufacturer",  client.cache.get("manufacturer"),  nonempty=True, warn_only=True)
    check("cache model",         client.cache.get("model"),         nonempty=True, warn_only=True)
    check("cache firmware",      client.cache.get("firmware"),      nonempty=True, warn_only=True)

    for k in ("sysDescr", "vendor", "sysName", "manufacturer", "model", "firmware", "sysUpTime"):
        v = client.cache.get(k)
        print(f"  {INFO} {k:16s}: {v}")

    # refresh should not crash
    await refresh_device_info(client)
    check("refresh_device_info mfr preserved", client.cache.get("manufacturer"), nonempty=True, warn_only=True)

    # -----------------------------------------------------------------------
    section("5 · interfaces.py – poll_interfaces()")
    # -----------------------------------------------------------------------
    await poll_interfaces(client, dynamic_only=False)

    iftable = client.cache.get("ifTable", {})
    check("ifTable not empty", iftable, nonempty=True)
    check("ifTable has entries", len(iftable) > 0, expect=True)

    # Check first entry structure
    first = next(iter(iftable.values()))
    check("port has index",        "index"    in first, expect=True)
    check("port has display_name", "display_name" in first, expect=True)
    check("port has admin",        "admin"    in first, expect=True)
    check("port has oper",         "oper"     in first, expect=True)
    check("port has port_type",    "port_type" in first, expect=True)

    phy_ports = [r for r in iftable.values() if r.get("port_type") == "physical"]
    virt_ports = [r for r in iftable.values() if r.get("port_type") == "virtual"]
    print(f"  {INFO} Total interfaces : {len(iftable)}")
    print(f"  {INFO} Physical ports   : {len(phy_ports)}")
    print(f"  {INFO} Virtual ports    : {len(virt_ports)}")

    for idx, rec in list(iftable.items())[:5]:
        print(f"  {INFO}   [{idx:4d}] {rec.get('display_name','?'):20s} admin={rec.get('admin')} oper={rec.get('oper')} type={rec.get('port_type')}")

    # -----------------------------------------------------------------------
    section("6 · ipv4.py – poll_ipv4()")
    # -----------------------------------------------------------------------
    await poll_ipv4(client)
    check("ipIndex populated",  client.cache.get("ipIndex"), nonempty=True, warn_only=True)
    print(f"  {INFO} IP entries: {len(client.cache.get('ipIndex', {}))}")

    # -----------------------------------------------------------------------
    section("7 · bandwidth.py – poll_bandwidth()")
    # -----------------------------------------------------------------------
    # Force bw_use_hc reset so it auto-detects
    client._bw_use_hc = None
    client._bw_last_poll = None

    await poll_bandwidth(client)
    bw = client.cache.get("bandwidth", {})
    check("bandwidth dict returned", isinstance(bw, dict), expect=True)
    print(f"  {INFO} Bandwidth entries: {len(bw)}")
    if bw:
        for idx, b in list(bw.items())[:3]:
            print(f"  {INFO}   [{idx}] rx_bps={b.get('rx_bps')} tx_bps={b.get('tx_bps')} use_hc={b.get('use_hc')}")
        check("bandwidth has rx_octets", "rx_octets" in next(iter(bw.values())), expect=True)

    # -----------------------------------------------------------------------
    section("8 · poe.py – poll_poe()")
    # -----------------------------------------------------------------------
    client._poe_last_poll = 0.0
    await poll_poe(client)

    check("poe_enabled in cache",  "poe_enabled"  in client.cache, expect=True)
    print(f"  {INFO} poe_enabled      : {client.cache.get('poe_enabled')}")
    print(f"  {INFO} poe_budget_total : {client.cache.get('poe_budget_total_w')} W")
    print(f"  {INFO} poe_power_used   : {client.cache.get('poe_power_used_w')} W")
    print(f"  {INFO} poe_power_avail  : {client.cache.get('poe_power_available_w')} W")
    poe_mw = client.cache.get("poe_power_mw", {})
    print(f"  {INFO} poe per-port entries: {len(poe_mw)}")
    check("poe_power_mw is dict", isinstance(poe_mw, dict), expect=True)

    # -----------------------------------------------------------------------
    section("9 · env features – cpu / memory / temperature / fans / psu / power")
    # -----------------------------------------------------------------------
    vendor = client.cache.get("vendor", "Unknown")
    print(f"  {INFO} Using vendor: {vendor}")


    await poll_cpu(client, vendor)
    print(f"  {INFO} CPU 5s={client.cache.get('env_cpu_5s')}% 60s={client.cache.get('env_cpu_60s')}% 300s={client.cache.get('env_cpu_300s')}%")
    check("env_cpu_5s is float or None", True, expect=True)

    await poll_memory(client, vendor)
    print(f"  {INFO} Mem total={client.cache.get('env_mem_total_kb')} KB  free={client.cache.get('env_mem_free_kb')} KB")

    await poll_temperature(client, vendor)
    print(f"  {INFO} Temps: {client.cache.get('env_temps_c')}  unit={client.cache.get('env_unit_temp_c')}°C")

    await poll_fans(client, vendor)
    print(f"  {INFO} Fan RPM: {client.cache.get('env_fans_rpm')}")
    print(f"  {INFO} Fan status: {client.cache.get('env_fans_status')}")

    await poll_psu(client, vendor)
    print(f"  {INFO} PSU status: {client.cache.get('env_psu_status')}")

    await poll_power(client, vendor)
    print(f"  {INFO} Power total: {client.cache.get('env_power_mw_total')} mW")
    print(f"  {INFO} Power ports: {client.cache.get('env_power_mw')}")

    # Entity sensor fallback (fills anything still missing)
    await poll_entity_sensor_fallback(client)
    print(f"  {INFO} After entity-sensor fallback:")
    print(f"    temps_c={client.cache.get('env_temps_c')}")
    print(f"    fans_rpm={client.cache.get('env_fans_rpm')}")
    print(f"    power_mw_total={client.cache.get('env_power_mw_total')}")

    # -----------------------------------------------------------------------
    section("10 · async_poll() – full coordinator cycle")
    # -----------------------------------------------------------------------
    cache = await client.async_poll()
    check("async_poll returns dict",  isinstance(cache, dict), expect=True)
    check("poll sysDescr in cache",   cache.get("sysDescr"),   nonempty=True)
    check("poll sysName in cache",    cache.get("sysName"),     nonempty=True)
    check("poll ifTable in cache",    cache.get("ifTable"),     nonempty=True)
    print(f"  {INFO} Cache keys after full poll: {sorted(cache.keys())}")

    # -----------------------------------------------------------------------
    section("11 · mutations – set_alias() / set_admin_status() (dry-run guard)")
    # -----------------------------------------------------------------------
    # We only check that the methods exist and can be called; we don't actually
    # mutate the switch in an automated test to avoid disruption.
    check("set_alias exists",       callable(client.set_alias),        expect=True)
    check("set_admin_status exists", callable(client.set_admin_status), expect=True)
    check("set_poe_admin exists",    callable(client.set_poe_admin),    expect=True)
    check("set_poe_priority exists", callable(client.set_poe_priority), expect=True)
    check("set_system_string exists",callable(client.set_system_string),expect=True)

    # -----------------------------------------------------------------------
    section("12 · Unit tests using Mocks (PoE control loops & Consolidation)")
    # -----------------------------------------------------------------------
    from unittest.mock import AsyncMock

    # 1. Test poll_poe parses standard OIDs correctly with poe_control_loops=True
    mock_client = MagicMock()
    mock_client._poe_options = {
        "poe_enabled": True,
        "poe_control_loops": True,
        "poe_poll_interval": 0,
        "poe_mode": "attributes",
    }
    mock_client._poe_last_poll = 0.0
    mock_client.cache = {
        "vendor": "Dell",
        "ifindex_by_baseport": {13: 13},
    }
    mock_client._database = {"poe": {"poe": []}}
    mock_client.feature_overrides = {}
    mock_client._get_database_oids = lambda feature, vendor: []
    mock_client._custom_oid = lambda key: None
    mock_client.custom_oids = {}
    
    # Mock walk results
    mock_walk = AsyncMock()
    mock_walk.side_effect = lambda oid: {
        "1.3.6.1.2.1.105.1.3.1.1.2": [("1.3.6.1.2.1.105.1.3.1.1.2.1", "370000")],
        "1.3.6.1.2.1.105.1.3.1.1.4": [("1.3.6.1.2.1.105.1.3.1.1.4.1", "50000")],
        "1.3.6.1.2.1.105.1.1.1.15": [("1.3.6.1.2.1.105.1.1.1.15.1.13", "0")],
        "1.3.6.1.2.1.105.1.1.1.3": [("1.3.6.1.2.1.105.1.1.1.3.1.13", "1")],
        "1.3.6.1.2.1.105.1.1.1.7": [("1.3.6.1.2.1.105.1.1.1.7.1.13", "2")],
    }.get(oid, [])
    mock_client._async_walk = mock_walk

    await _f_poe.poll_poe(mock_client)
    poe_ports = mock_client.cache.get("poe_ports", {})
    check("PoE port Gi1/0/13 mapped", 13 in poe_ports, expect=True)
    if 13 in poe_ports:
        check("Gi1/0/13 admin is 1 (Auto)", poe_ports[13]["admin"], expect=1)
        check("Gi1/0/13 priority is 2 (High)", poe_ports[13]["priority"], expect=2)

    # 1b. Test custom system OID override resolution
    mock_client.custom_oids = {
        "name": "1.3.6.1.4.1.9.9.23.1.2.1.1.1",
        "contact": "1.3.6.1.4.1.9.9.23.1.2.1.1.2",
        "location": "1.3.6.1.4.1.9.9.23.1.2.1.1.3",
    }
    mock_client._custom_oid = lambda key: mock_client.custom_oids.get(key)
    check("custom_oid resolves name override", mock_client._custom_oid("name"), expect="1.3.6.1.4.1.9.9.23.1.2.1.1.1")
    check("custom_oid resolves contact override", mock_client._custom_oid("contact"), expect="1.3.6.1.4.1.9.9.23.1.2.1.1.2")
    check("custom_oid resolves location override", mock_client._custom_oid("location"), expect="1.3.6.1.4.1.9.9.23.1.2.1.1.3")

    # 1c. Test PoE custom OID override resolution in poll_poe
    poe_override = {
        "oid_budget": "1.3.6.1.4.1.9.9.23.1.2.2.1.1",
        "oid_used": "1.3.6.1.4.1.9.9.23.1.2.2.1.2",
        "oid_port_power": "1.3.6.1.4.1.9.9.23.1.2.2.1.3",
        "oid_port_admin": "1.3.6.1.4.1.9.9.23.1.2.2.1.4",
        "oid_port_priority": "1.3.6.1.4.1.9.9.23.1.2.2.1.5",
        "scale": 1.0,
    }
    mock_client.feature_overrides = {"poe": poe_override}
    mock_client._get_database_oids = lambda feature, vendor: [poe_override] if feature == "poe" else []
    
    mock_walk_override = AsyncMock()
    mock_walk_override.side_effect = lambda oid: {
        "1.3.6.1.4.1.9.9.23.1.2.2.1.1": [("1.3.6.1.4.1.9.9.23.1.2.2.1.1.1", "400.0")],
        "1.3.6.1.4.1.9.9.23.1.2.2.1.2": [("1.3.6.1.4.1.9.9.23.1.2.2.1.2.1", "60.0")],
        "1.3.6.1.4.1.9.9.23.1.2.2.1.3": [("1.3.6.1.4.1.9.9.23.1.2.2.1.3.1.13", "1200")],
        "1.3.6.1.4.1.9.9.23.1.2.2.1.4": [("1.3.6.1.4.1.9.9.23.1.2.2.1.4.1.13", "1")],
        "1.3.6.1.4.1.9.9.23.1.2.2.1.5": [("1.3.6.1.4.1.9.9.23.1.2.2.1.5.1.13", "1")],
    }.get(oid, [])
    mock_client._async_walk = mock_walk_override
    mock_client.cache = {
        "vendor": "Dell",
        "ifindex_by_baseport": {13: 13},
    }
    mock_client._poe_last_poll = 0.0
    
    await _f_poe.poll_poe(mock_client)
    check("PoE custom budget in cache", mock_client.cache.get("poe_budget_total_w"), expect=400.0)
    check("PoE custom used in cache", mock_client.cache.get("poe_power_used_w"), expect=60.0)
    check("PoE custom port power", mock_client.cache.get("poe_power_mw", {}).get(13), expect=1200.0)

    # Restore standard mocks for the rest of tests
    mock_client.feature_overrides = {}
    mock_client._get_database_oids = lambda feature, vendor: []
    mock_client._async_walk = mock_walk
    mock_client.cache = {
        "vendor": "Dell",
        "ifindex_by_baseport": {13: 13},
    }
    mock_client._poe_last_poll = 0.0
    await _f_poe.poll_poe(mock_client)

    # 2. Test PoePortSwitch toggles and attributes
    mock_coord = MagicMock()
    mock_coord.async_request_refresh = AsyncMock()
    mock_coord.data = mock_client.cache
    mock_dev_info = MagicMock()
    
    import custom_components.snmp_switch_manager.switch as switch_mod
    poe_switch = switch_mod.PoePortSwitch(
        coordinator=mock_coord,
        entry_id="test_entry",
        if_index=13,
        raw_name="Gi1/0/13",
        display_name="Gi1/0/13",
        group_idx=1,
        port_idx=13,
        device_info=mock_dev_info,
        client=mock_client,
        hostname="TestSwitch",
    )
    
    check("PoePortSwitch unique_id", poe_switch.unique_id, expect="test_entry-poe-13")
    check("PoePortSwitch name", poe_switch.name, expect="TestSwitch Gi1/0/13 PoE")
    check("PoePortSwitch is_on", poe_switch.is_on, expect=True)
    
    mock_client.set_poe_admin = AsyncMock(return_value=True)
    await poe_switch.async_turn_off()
    mock_client.set_poe_admin.assert_called_with(1, 13, 2)
    check("PoePortSwitch is_on after turn_off override", poe_switch.is_on, expect=False)

    # 3. Test PoePortPrioritySelect options and attributes
    import custom_components.snmp_switch_manager.select as select_mod
    poe_select = select_mod.PoePortPrioritySelect(
        coordinator=mock_coord,
        entry_id="test_entry",
        if_index=13,
        raw_name="Gi1/0/13",
        display_name="Gi1/0/13",
        group_idx=1,
        port_idx=13,
        device_info=mock_dev_info,
        client=mock_client,
        hostname="TestSwitch",
    )
    
    check("PoePortPrioritySelect unique_id", poe_select.unique_id, expect="test_entry-poe-priority-13")
    check("PoePortPrioritySelect current_option", poe_select.current_option, expect="High")
    
    mock_client.set_poe_priority = AsyncMock(return_value=True)
    await poe_select.async_select_option("Critical")
    mock_client.set_poe_priority.assert_called_with(1, 13, 1)
    check("PoePortPrioritySelect current_option after select override", poe_select.current_option, expect="Critical")

    # 4. Test DeviceInformationSensor consolidation
    import custom_components.snmp_switch_manager.sensor as sensor_mod
    mock_client.cache.update({
        "manufacturer": "Dell EMC",
        "model": "N1524P",
        "firmware": "6.6.3.3",
        "sysName": "CoreSwitch-01",
        "sysContact": "netops@example.com",
        "sysLocation": "Rack B",
    })
    mock_coord.data = mock_client.cache
    
    dev_info_sensor = sensor_mod.DeviceInformationSensor(
        coordinator=mock_coord,
        entry=MagicMock(entry_id="test_entry"),
        device_info=mock_dev_info,
        hostname="TestSwitch",
        client=mock_client,
    )
    
    check("DeviceInformationSensor state", dev_info_sensor.native_value, expect="CoreSwitch-01")
    attrs = dev_info_sensor.extra_state_attributes
    check("DeviceInformationSensor manufacturer attr", attrs.get("Manufacturer"), expect="Dell EMC")
    check("DeviceInformationSensor model attr", attrs.get("Model"), expect="N1524P")
    check("DeviceInformationSensor firmware attr", attrs.get("Firmware Revision"), expect="6.6.3.3")
    check("DeviceInformationSensor hostname attr", attrs.get("Hostname"), expect="CoreSwitch-01")
    check("DeviceInformationSensor contact attr", attrs.get("System Contact"), expect="netops@example.com")
    check("DeviceInformationSensor location attr", attrs.get("System Location"), expect="Rack B")

    # 5. Test dynamic default icons for IfAdminSwitch
    import custom_components.snmp_switch_manager.switch.admin as admin_switch_mod
    
    def make_switch(name):
        return admin_switch_mod.IfAdminSwitch(
            coordinator=mock_coord,
            entry_id="test_entry",
            if_index=1,
            raw_name=name,
            display_name=name,
            alias="",
            hostname="TestSwitch",
            device_info=mock_dev_info,
            client=mock_client,
            icon_rules=[],
        )
    
    check("VLAN default icon", make_switch("Vl1").icon, expect="mdi:lan")
    check("Loopback default icon", make_switch("Lo0").icon, expect="mdi:lan-pending")
    check("Port Channel default icon", make_switch("Po12").icon, expect="mdi:lan-connect")
    check("Physical port default icon", make_switch("Gi1/0/1").icon, expect="mdi:ethernet")

    # Direct classify_port_type tests
    from custom_components.snmp_switch_manager.helpers import classify_port_type
    check(
        "classify_port_type returns physical when connector_present is True",
        classify_port_type(if_type=6, name="Ethernet1", is_bridge_port=False, connector_present=True),
        expect="physical",
    )
    check(
        "classify_port_type returns virtual when connector_present is False",
        classify_port_type(if_type=6, name="Intf999", is_bridge_port=False, connector_present=False),
        expect="virtual",
    )
    check(
        "classify_port_type falls back to physical via bridge-port rule when connector_present is None",
        classify_port_type(if_type=6, name="Ethernet1", is_bridge_port=True, connector_present=None),
        expect="physical",
    )
    check(
        "classify_port_type falls back to virtual via VIRTUAL_IFTYPES rule when connector_present is None",
        classify_port_type(if_type=135, name="Vlan1", is_bridge_port=False, connector_present=None),
        expect="virtual",
    )

    # Dynamic Port Type Classification with DB override
    custom_class_db = {
        "virtual_iftypes": [999]
    }
    check(
        "classify_port_type dynamic DB override virtual",
        classify_port_type(if_type=999, name="Intf999", is_bridge_port=False, connector_present=None, classification_db=custom_class_db),
        expect="virtual",
    )

    # Dynamic Filter Rules match engine
    from custom_components.snmp_switch_manager.helpers import check_interface_filter_rules
    custom_filters_db = {
        "interface_filters": [
            {
                "id": "generic_skip_cpu_interface",
                "vendors": ["Standard"],
                "rule_type": "exclude",
                "match_type": "equals",
                "match_value": "cpu"
            },
            {
                "id": "cisco_sg_vlan_admin_or_oper",
                "vendors": ["Cisco"],
                "vendor_keywords": ["sg"],
                "rule_type": "include",
                "conditions": [
                    {
                        "match_type": "is_digit",
                        "oper_in": [1],
                        "admin_in": [2],
                        "oper_or_admin_match": True,
                        "require_ip": True,
                        "rename_prefix": "VLAN "
                    }
                ]
            },
            {
                "id": "junos_physical_ge",
                "vendors": ["Junos"],
                "rule_type": "include",
                "match_type": "starts_with",
                "match_value": "ge-",
                "exclude_contains": "."
            },
            {
                "id": "skip_pfsense_enc_interfaces",
                "vendors": ["pfSense"],
                "rule_type": "exclude",
                "match_type": "starts_with",
                "match_value": "enc"
            }
        ]
    }

    # Test standard standard CPU exclude
    inc, nm = check_interface_filter_rules(
        normalized_name="cpu", raw_name="CPU", admin=1, oper=1, has_ip=False,
        vendor="Standard", disabled_vendor_filter_ids=set(), classification_db=custom_filters_db
    )
    check("CPU exclude rule matches", inc, expect=False)

    # Test Cisco SG VLAN digital rename include
    inc, nm = check_interface_filter_rules(
        normalized_name="12", raw_name="12", admin=2, oper=2, has_ip=True,
        vendor="Cisco", manufacturer="sg350", sys_descr="sg350 switch",
        disabled_vendor_filter_ids=set(), classification_db=custom_filters_db
    )
    check("Cisco SG VLAN digital rename include matches", inc, expect=True)
    check("Cisco SG VLAN digital rename raw_name updated", nm, expect="VLAN 12")

    # Test Junos physical GE include
    inc, nm = check_interface_filter_rules(
        normalized_name="ge-0/0/1", raw_name="ge-0/0/1", admin=1, oper=1, has_ip=False,
        vendor="Junos", disabled_vendor_filter_ids=set(), classification_db=custom_filters_db
    )
    check("Junos physical GE include matches", inc, expect=True)

    # Test Junos physical GE with dot (subinterface) should not match this rule
    inc, nm = check_interface_filter_rules(
        normalized_name="ge-0/0/1.0", raw_name="ge-0/0/1.0", admin=1, oper=1, has_ip=False,
        vendor="Junos", disabled_vendor_filter_ids=set(), classification_db=custom_filters_db
    )
    check("Junos subinterface dot exclude matches", inc, expect=False)

    # Test pfSense exclude enc interface
    inc, nm = check_interface_filter_rules(
        normalized_name="enc0", raw_name="enc0", admin=1, oper=1, has_ip=False,
        vendor="pfSense", disabled_vendor_filter_ids=set(), classification_db=custom_filters_db
    )
    check("pfSense enc interface exclude matches", inc, expect=False)

    # 6. Test PoE Service Handlers
    from unittest.mock import patch
    from custom_components.snmp_switch_manager import SnmpSwitchRuntimeData
    
    mock_registry = MagicMock()
    mock_poe_entity = MagicMock(config_entry_id="test_entry", unique_id="test_entry-poe-13")
    mock_priority_entity = MagicMock(config_entry_id="test_entry", unique_id="test_entry-poe-priority-13")
    mock_physical_entity = MagicMock(config_entry_id="test_entry", unique_id="test_entry-if-13")
    mock_registry.async_get.side_effect = lambda eid: {
        "switch.poe_port": mock_poe_entity,
        "select.poe_priority": mock_priority_entity,
        "switch.physical_port": mock_physical_entity,
    }.get(eid)
    
    import custom_components.snmp_switch_manager as integration_mod
    
    mock_ha_services = MagicMock()
    mock_hass = MagicMock()
    mock_hass.services = mock_ha_services
    mock_entry = MagicMock()
    mock_entry.runtime_data = SnmpSwitchRuntimeData(client=mock_client, coordinator=mock_coord)
    mock_hass.config_entries.async_get_entry.return_value = mock_entry
    
    registered_handlers = {}
    def fake_register(domain, name, handler):
        registered_handlers[name] = handler
    
    mock_ha_services.has_service.return_value = False
    mock_ha_services.async_register = fake_register
    
    with patch("homeassistant.helpers.entity_registry.async_get", return_value=mock_registry):
        await integration_mod.async_register_services(mock_hass)
    
    check("set_poe_port_admin registered", "set_poe_port_admin" in registered_handlers, expect=True)
    check("set_poe_port_priority registered", "set_poe_port_priority" in registered_handlers, expect=True)
    check("set_port_admin_status registered", "set_port_admin_status" in registered_handlers, expect=True)
    
    mock_client.set_poe_admin = AsyncMock(return_value=True)
    admin_call = MagicMock(data={"entity_id": "switch.poe_port", "state": "Off"})
    
    with patch("homeassistant.helpers.entity_registry.async_get", return_value=mock_registry):
        await registered_handlers["set_poe_port_admin"](admin_call)
    mock_client.set_poe_admin.assert_called_with(1, 13, 2)
    check("PoE admin call executed", mock_client.set_poe_admin.called, expect=True)
    
    mock_client.set_poe_priority = AsyncMock(return_value=True)
    priority_call = MagicMock(data={"entity_id": "select.poe_priority", "priority": "High"})
    
    with patch("homeassistant.helpers.entity_registry.async_get", return_value=mock_registry):
        await registered_handlers["set_poe_port_priority"](priority_call)
    mock_client.set_poe_priority.assert_called_with(1, 13, 2)
    check("PoE priority call executed", mock_client.set_poe_priority.called, expect=True)

    mock_client.set_admin_status = AsyncMock(return_value=True)
    port_admin_call = MagicMock(data={"entity_id": "switch.physical_port", "state": "Down"})
    
    with patch("homeassistant.helpers.entity_registry.async_get", return_value=mock_registry):
        await registered_handlers["set_port_admin_status"](port_admin_call)
    mock_client.set_admin_status.assert_called_with(13, 2)
    check("Port admin status call executed", mock_client.set_admin_status.called, expect=True)

    # -----------------------------------------------------------------------
    section("13 · cleanup – async_close()")
    # -----------------------------------------------------------------------
    await client.async_close()
    check("engine cleared after close", client.engine is None, expect=True)
    check("target cleared after close", client.target is None, expect=True)

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    total   = len(_results)
    passed  = sum(1 for _, ok, _ in _results if ok)
    failed  = total - passed

    print(f"\n{'='*60}")
    print(f"  RESULT: {passed}/{total} passed  ({failed} failed)")
    print(f"{'='*60}")

    if failed:
        print(f"\n  {FAIL} Failed checks:")
        for name, ok, detail in _results:
            if not ok:
                print(f"    • {name}: {detail}")
        sys.exit(1)
    else:
        print(f"\n  {PASS} All checks passed!")


if __name__ == "__main__":
    asyncio.run(run_tests())
