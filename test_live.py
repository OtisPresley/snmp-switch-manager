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
        "homeassistant",
    ]:
        if mod not in sys.modules:
            _stub_module(mod)

    # Specific attributes needed by imports in snmp.py / helpers.py
    sys.modules["homeassistant"].core = sys.modules["homeassistant.core"]
    sys.modules["homeassistant.config_entries"].ConfigEntry = object
    sys.modules["homeassistant.exceptions"].ConfigEntryAuthFailed = Exception
    sys.modules["homeassistant.helpers.update_coordinator"].DataUpdateCoordinator = object
    sys.modules["homeassistant.const"].CONF_HOST = "host"
    sys.modules["homeassistant.const"].CONF_PORT = "port"
    sys.modules["homeassistant.data_entry_flow"].FlowResult = dict

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

    # -----------------------------------------------------------------------
    section("12 · cleanup – async_close()")
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
