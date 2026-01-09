from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    PLATFORMS,
    DEFAULT_POLL_INTERVAL,
    CONF_BANDWIDTH_POLL_INTERVAL,
    DEFAULT_BANDWIDTH_POLL_INTERVAL,
    CONF_CUSTOM_OIDS,
    CONF_OVERRIDE_COMMUNITY,
    CONF_OVERRIDE_PORT,
    CONF_UPTIME_POLL_INTERVAL,
    DEFAULT_UPTIME_POLL_INTERVAL,
    CONF_BW_ENABLE,
    CONF_BW_MODE,
    CONF_BW_INCLUDE_STARTS_WITH,
    CONF_BW_INCLUDE_CONTAINS,
    CONF_BW_INCLUDE_ENDS_WITH,
    CONF_BW_EXCLUDE_STARTS_WITH,
    CONF_BW_EXCLUDE_CONTAINS,
    CONF_BW_EXCLUDE_ENDS_WITH,
    CONF_PORT_RENAME_USER_RULES,
    CONF_PORT_RENAME_DISABLED_DEFAULT_IDS,
    CONF_HIDE_IP_ON_PHYSICAL,
    DEFAULT_PORT_RENAME_RULES,
    CONF_POE_ENABLE,
    CONF_POE_MODE,
    CONF_POE_POLL_INTERVAL,
    POE_MODE_ATTRIBUTES,
    DEFAULT_POE_POLL_INTERVAL,
    CONF_ENV_ENABLE,
    CONF_ENV_MODE,
    CONF_ENV_POLL_INTERVAL,
    ENV_MODE_ATTRIBUTES,
    DEFAULT_ENV_POLL_INTERVAL,
)
from .snmp import SwitchSnmpClient

_LOGGER = logging.getLogger(__name__)

# Use standard aliasing compatible with Python <3.12
SwitchManagerConfigEntry = ConfigEntry

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True


import re as _re


def _build_port_rename_rules(options: dict) -> list[tuple[str, _re.Pattern[str], str]]:
    """Build ordered (id, compiled_regex, replace) rules from config entry options.

    User rules come first (highest priority), followed by enabled built-in defaults.
    """
    rules: list[tuple[str, _re.Pattern[str], str]] = []
    disabled = set(options.get(CONF_PORT_RENAME_DISABLED_DEFAULT_IDS) or [])

    for i, r in enumerate(options.get(CONF_PORT_RENAME_USER_RULES) or []):
        try:
            pattern = str((r or {}).get("pattern") or "").strip()
            replace = str((r or {}).get("replace") or "")
            if not pattern:
                continue
            rules.append((f"user_{i}", _re.compile(pattern, _re.IGNORECASE), replace))
        except Exception:
            continue

    for r in DEFAULT_PORT_RENAME_RULES:
        rid = (r or {}).get("id") or ""
        if not rid or rid in disabled:
            continue
        try:
            pattern = str((r or {}).get("pattern") or "").strip()
            replace = str((r or {}).get("replace") or "")
            if not pattern:
                continue
            rules.append((rid, _re.compile(pattern, _re.IGNORECASE), replace))
        except Exception:
            continue

    return rules


def _apply_port_rename_all(name: str, rules: list[tuple[str, _re.Pattern[str], str]]) -> str:
    """Apply *all* matching rename rules in order (each at most once)."""
    if not name or not rules:
        return name
    out = name
    for _rid, rx, rep in rules:
        if rx.search(out):
            try:
                out = rx.sub(rep, out, count=1)
            except Exception:
                continue
    return out




def _classify_port_type(row: dict, display_name: str) -> str:
    """Classify interface row as physical/virtual/unknown.

    Heuristics (in priority order):
    - ifType indicates virtual (loopback, vlan, LAG, tunnels, propVirtual, etc.)
    - Presence of BRIDGE-MIB base port mapping -> physical
    - Name/descr patterns for virtual interfaces
    """
    try:
        if_type = int(row.get("if_type") or 0)
    except Exception:
        if_type = 0

    VIRTUAL_IFTYPES = {24, 53, 131, 135, 161}  # loopback, propVirtual, tunnel, l2vlan, ieee8023adLag
    if if_type in VIRTUAL_IFTYPES:
        return "virtual"

    # If the interface is present as a bridge port -> likely physical switch port
    if row.get("bridge_port") is not None:
        return "physical"

    nm = (display_name or "").lower()
    # Very conservative name-based virtual detection (fallback only)
    for token in ("vlan", "loopback", "lo", "mgmt", "management", "bridge", "br", "irb", "bdi", "svi", "port-channel", "portchannel", "lag", "bond", "po"):
        if token in nm:
            return "virtual"

    return "unknown"


def _postprocess_if_names(data: dict, options: dict) -> dict:
    """Apply port rename rules and derived fields to ifTable names in coordinator data.

    This is the single source of truth for:
    - Port Name Rules (applied in order; all matches)
    - Preserving trailing spaces in replacements
    - display_name used by entities, sensors, bandwidth attributes, and card data
    - port_type classification (physical/virtual/unknown)
    """
    rules = _build_port_rename_rules(options)
    if_table = (data or {}).get("ifTable")
    if not isinstance(if_table, dict):
        return data

    for idx, row in if_table.items():
        if not isinstance(row, dict):
            continue

        raw = str(row.get("name") or row.get("descr") or "")
        renamed = raw
        if raw and rules:
            renamed = _apply_port_rename_all(raw, rules)

        # Preserve original for debugging / power users
        if raw and renamed != raw and "name_raw" not in row:
            row["name_raw"] = raw

        # Always set name to the renamed value when available
        if renamed:
            row["name"] = renamed

        # Single display field for all consumers (do not strip)
        display = row.get("name") or row.get("descr") or f"ifIndex {idx}"
        row["display_name"] = str(display)

        # Derived port type used by UI/card
        row["port_type"] = _classify_port_type(row, row["display_name"])

    return data


async def async_setup_entry(hass: HomeAssistant, entry: SwitchManagerConfigEntry) -> bool:
    host = entry.data.get("host")
    port = entry.data.get("port")
    community = entry.data.get("community")

    bandwidth_options = {
        CONF_BW_MODE: entry.options.get(CONF_BW_MODE, None),
        CONF_BW_ENABLE: entry.options.get(CONF_BW_ENABLE, False),
        CONF_BW_INCLUDE_STARTS_WITH: entry.options.get(CONF_BW_INCLUDE_STARTS_WITH, []) or [],
        CONF_BW_INCLUDE_CONTAINS: entry.options.get(CONF_BW_INCLUDE_CONTAINS, []) or [],
        CONF_BW_INCLUDE_ENDS_WITH: entry.options.get(CONF_BW_INCLUDE_ENDS_WITH, []) or [],
        CONF_BW_EXCLUDE_STARTS_WITH: entry.options.get(CONF_BW_EXCLUDE_STARTS_WITH, []) or [],
        CONF_BW_EXCLUDE_CONTAINS: entry.options.get(CONF_BW_EXCLUDE_CONTAINS, []) or [],
        CONF_BW_EXCLUDE_ENDS_WITH: entry.options.get(CONF_BW_EXCLUDE_ENDS_WITH, []) or [],
        CONF_BANDWIDTH_POLL_INTERVAL: entry.options.get(CONF_BANDWIDTH_POLL_INTERVAL, DEFAULT_BANDWIDTH_POLL_INTERVAL),
    }

    # Always provide a non-None default for mode values.
    # If the option key exists but its value is None, dict.get() will return None
    # (not the provided default), which breaks downstream comparisons.
    poe_options = {
        CONF_POE_ENABLE: entry.options.get(CONF_POE_ENABLE, False),
        CONF_POE_MODE: entry.options.get(CONF_POE_MODE, POE_MODE_ATTRIBUTES),
        CONF_POE_POLL_INTERVAL: entry.options.get(CONF_POE_POLL_INTERVAL, DEFAULT_POE_POLL_INTERVAL),
    }

    env_options = {
        CONF_ENV_ENABLE: entry.options.get(CONF_ENV_ENABLE, False),
        CONF_ENV_MODE: entry.options.get(CONF_ENV_MODE, ENV_MODE_ATTRIBUTES),
        CONF_ENV_POLL_INTERVAL: entry.options.get(CONF_ENV_POLL_INTERVAL, DEFAULT_ENV_POLL_INTERVAL),
    }

    client = SwitchSnmpClient(
        hass,
        host,
        community,
        port,
        custom_oids=entry.options.get(CONF_CUSTOM_OIDS) or {},
        bandwidth_options=bandwidth_options,
        poe_options=poe_options,
        env_options=env_options,
    )
    await client.async_initialize()

    # Apply per-device option for sysUpTime throttling
    client.set_uptime_poll_interval(entry.options.get(CONF_UPTIME_POLL_INTERVAL, DEFAULT_UPTIME_POLL_INTERVAL))

    async def _update_method():
        data = await client.async_poll()
        data = _postprocess_if_names(data, entry.options)
        # UI display option: hide IP on physical interfaces
        try:
            data["hide_ip_on_physical"] = bool(entry.options.get(CONF_HIDE_IP_ON_PHYSICAL, False))
        except Exception:
            data["hide_ip_on_physical"] = False
        return data

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}-coordinator-{host}",
        update_interval=timedelta(seconds=DEFAULT_POLL_INTERVAL),
        # IMPORTANT: use the client's poll method directly. The client is
        # responsible for handling/guarding poll errors so we don't mark all
        # coordinator-backed entities unavailable.
        update_method=_update_method,
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    # Register services (idempotent)
    await async_register_services(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True

async def _async_update_listener(hass: HomeAssistant, entry: SwitchManagerConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: SwitchManagerConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded

async def async_register_services(hass: HomeAssistant):
    from homeassistant.helpers import entity_registry as er

    async def handle_set_alias(call):
        entity_id = call.data.get("entity_id")
        description = call.data.get("description", "")

        ent_reg = er.async_get(hass)
        ent = ent_reg.async_get(entity_id)
        if not ent:
            return

        # Resolve the integration entry and client from the entity's config_entry_id
        entry_id = ent.config_entry_id
        data = hass.data.get(DOMAIN, {}).get(entry_id)
        if not data:
            return

        client = data["client"]
        # Parse if_index from our unique_id pattern "<entry_id>-if-<index>"
        unique_id = ent.unique_id or ""
        try:
            if_index = int(unique_id.split("-if-")[-1])
        except Exception:
            return

        await client.set_alias(if_index, description)
        await data["coordinator"].async_request_refresh()

    if not hass.services.has_service(DOMAIN, "set_port_description"):
        hass.services.async_register(DOMAIN, "set_port_description", handle_set_alias)
