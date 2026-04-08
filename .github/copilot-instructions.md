# Copilot Instructions

## What this is

A Home Assistant custom integration that manages SNMP-enabled network switches. It discovers interfaces via SNMP and exposes them as HA entities: switch entities (port admin up/down), diagnostic sensors (hostname, model, firmware, uptime), optional bandwidth sensors (RX/TX throughput), environmental sensors (CPU, memory, temperature, fans, PSU), and PoE statistics. A custom Lovelace card provides a physical switch visualization.

Integration domain: `snmp_switch_manager`  
Minimum HA version: `2025.11.2`  
SNMP library: `pysnmp 7.x` (auto-installed by HA; compatibility shim in `snmp_compat.py`)

## Build, lint, and validation

**Check for Python syntax errors:**
```bash
python -m compileall custom_components/snmp_switch_manager/
```

**CI runs automatically via GitHub Actions on push/PR:**
- `.github/workflows/ci.yaml` — Python compile check + Node lint
- `.github/workflows/hassfest.yaml` — HA integration schema validation
- `.github/workflows/hacs.yaml` — HACS repository compliance

There are no unit tests or pytest setup. Validation is via HA's `hassfest` tool and Python compile checks only.

## Architecture

### Data flow

```
SwitchSnmpClient (snmp.py)
  └─ client.cache          ← single source of truth for all SNMP state
       ├─ ifTable           ← interface records keyed by ifIndex
       ├─ bandwidth         ← per-interface throughput counters
       ├─ poe_*             ← PoE budget/used/available
       └─ env_*             ← CPU, memory, temperature, fans, PSU

DataUpdateCoordinator (__init__.py)
  └─ calls client.async_poll() on each update interval
  └─ entities read from coordinator.data (which is client.cache)
```

All entities are **read-only consumers of `client.cache`** — they never call SNMP directly. The coordinator drives all polling.

### Polling strategy

The main coordinator polls every 10 seconds (default). Within each poll, different data types are throttled independently:

| Data | Default interval | Config key |
|------|-----------------|------------|
| Interface state (admin/oper) | 10s (every poll) | `CONF_POLL_INTERVAL` |
| Uptime | 300s | `CONF_UPTIME_POLL_INTERVAL` |
| Bandwidth counters | 30s | `CONF_BW_POLL_INTERVAL` |
| PoE stats | 30s | `CONF_POE_POLL_INTERVAL` |
| Environmental | 30s | `CONF_ENV_POLL_INTERVAL` |

Bandwidth, PoE, and environmental polling only activate when their respective features are enabled in options.

### Entity ID patterns

- Port switches: `switch.{hostname}_{interface_name}`
- Sensors: `sensor.{hostname}_{metric}`
- Unique IDs: `{entry_id}-if-{ifIndex}` (stable across restarts; must not change)

### Config flow structure

`config_flow.py` (1,779 lines) implements a **hierarchical options menu** via `OptionsFlowHandler`. The flow uses a mutable `_options` dict and only triggers a reload if options actually changed. Top-level menu branches:

- Connection & Name
- Manage Interfaces (include/exclude/rename rules, icon rules, IP display)
- Bandwidth Sensors (enable/mode/poll interval/rules)
- Environmental Sensors (enable/PoE/env modes and intervals)
- Custom OIDs (per-device diagnostic OID overrides)

## Key conventions

### Naming
- Constants: `CONF_*` (config keys), `OID_*` (SNMP OIDs), `DEFAULT_*` (defaults) — all in `const.py`
- Async methods: `async_*` prefix (e.g., `async_poll`, `async_initialize`)
- Private methods/attributes: `_` prefix

### Adding a new sensor type
1. Define any new OIDs in `const.py`
2. Collect the data in `snmp.py` — add to `async_poll()` and store in `self.cache`
3. Add config keys to `const.py` and expose them in `config_flow.py` if user-configurable
4. Create the entity class in `sensor.py` (or `switch.py`) reading from `coordinator.data`
5. Register the entity in `async_setup_entry()` in `__init__.py`

### SNMP operations
- All SNMP calls are `async`; use `UdpTransportTarget.create()` (pysnmp 7.x via `snmp_compat.py`)
- Multi-OID GETs are chunked to avoid PDU size limits
- Missing OIDs must be handled gracefully — never crash polling; use fallback chains
- Vendor-specific OIDs follow a cascade: vendor OID → standard MIB → `None`

### Rule engine
Interface include/exclude and rename rules are stored as user-readable pattern strings but compiled to regexes at runtime. Rules are applied in `__init__.py` (`_postprocess_if_names`, `_apply_port_rename_all`) after each coordinator update, not inside `snmp.py`.

### Options flow state
`OptionsFlowHandler` accumulates changes in `self._options` (a copy of `entry.options`). Changes are only written back to the config entry — and a reload triggered — if the new options dict differs from the current one.

### ifTable record structure
Each entry in `client.cache["ifTable"]` (keyed by `ifIndex` int) contains:
```python
{
    "index": int, "name": str, "descr": str, "alias": str,
    "speed_bps": int, "admin": int, "oper": int,
    "vlan_id": int, "allowed_vlans": [int], "is_trunk": bool,
    "port_type": str,   # "physical", "virtual", "unknown"
    "if_type": int,     # IF-MIB ifType value
    "ipv4": [...], "ip": str, "netmask": str, "cidr": int,
    "display_name": str
}
```
`display_name` is the post-processed name after rename rules are applied; use it for entity names and attributes.

## Versioning

Follows semantic versioning. Version is in `custom_components/snmp_switch_manager/manifest.json`. Update `CHANGELOG.md` with each release using the existing format.
