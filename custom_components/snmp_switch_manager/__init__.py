from __future__ import annotations
import re as _re

from dataclasses import dataclass
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import homeassistant.helpers.config_validation as cv
try:
    from homeassistant.components.http import StaticPathConfig
except ImportError:
    StaticPathConfig = None

from .const import (
    DOMAIN,
    PLATFORMS,
    DEFAULT_POLL_INTERVAL,
    CONF_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
    MAX_POLL_INTERVAL,
    CONF_BANDWIDTH_POLL_INTERVAL,
    DEFAULT_BANDWIDTH_POLL_INTERVAL,
    CONF_FEATURE_OVERRIDES,
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
    CONF_POE_ENABLE,
    CONF_POE_CONTROL_LOOPS,
    CONF_POE_MODE,
    CONF_POE_POLL_INTERVAL,
    POE_MODE_ATTRIBUTES,
    DEFAULT_POE_POLL_INTERVAL,
    CONF_ENV_ENABLE,
    CONF_ENV_MODE,
    CONF_ENV_POLL_INTERVAL,
    ENV_MODE_ATTRIBUTES,
    DEFAULT_ENV_POLL_INTERVAL,
    CONF_HIDE_IP_ON_PHYSICAL,
    CONF_HIDE_IP_ON_PHYSICAL_INTERFACES,
    OID_sysName,
    OID_sysContact,
    OID_sysLocation,
)
from .snmp import SwitchSnmpClient
from .snmp_compat import SnmpAuthError, SnmpConnectionError
from .helpers import get_snmp_connection_settings

_LOGGER = logging.getLogger(__name__)


@dataclass
class SnmpSwitchRuntimeData:
    """Runtime data stored on a config entry (replaces hass.data[DOMAIN][entry_id])."""

    client: SwitchSnmpClient
    coordinator: DataUpdateCoordinator


# Use standard aliasing compatible with Python <3.12
SwitchManagerConfigEntry = ConfigEntry

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    await async_register_services(hass)

    # Register static path to serve offline image & assets
    static_dir = hass.config.path("custom_components/snmp_switch_manager/static")
    if StaticPathConfig is not None and hasattr(hass.http, "async_register_static_paths"):
        await hass.http.async_register_static_paths([
            StaticPathConfig(
                url_path="/snmp_switch_manager_static",
                path=static_dir,
                cache_headers=False
            )
        ])
    else:
        hass.http.register_static_path(
            "/snmp_switch_manager_static",
            static_dir,
            cache_headers=False
        )
    return True

def _build_port_rename_rules(options: dict, default_rules: list[dict[str, str]] | None = None) -> list[tuple[str, _re.Pattern[str], str]]:
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

    for r in (default_rules or []):
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


def _postprocess_if_names(data: dict, options: dict, rules: list[tuple[str, _re.Pattern[str], str]]) -> dict:
    """Apply port rename rules to ifTable names in coordinator data."""
    # Persist option flags for downstream consumers
    data["hide_ip_on_physical"] = bool(
        options.get(
            CONF_HIDE_IP_ON_PHYSICAL_INTERFACES,
            options.get(CONF_HIDE_IP_ON_PHYSICAL, False),
        )
    )

    if not rules:
        return data
    if_table = (data or {}).get("ifTable")
    if not isinstance(if_table, dict):
        return data
    for idx, row in if_table.items():
        if not isinstance(row, dict):
            continue
        raw = str(row.get("name") or row.get("descr") or "")
        if not raw:
            continue
        renamed = _apply_port_rename_all(raw, rules)
        # Preserve original for debugging / power users
        if renamed != raw and "name_raw" not in row:
            row["name_raw"] = raw
        row["name"] = renamed
        # Keep display_name in sync so platform consumers don't re-apply rules.
        row["display_name"] = renamed
    return data


async def async_setup_entry(hass: HomeAssistant, entry: SwitchManagerConfigEntry) -> bool:
    snmp_settings = get_snmp_connection_settings(entry.data, entry.options)
    host = snmp_settings.get("host")

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
        CONF_POE_CONTROL_LOOPS: entry.options.get(CONF_POE_CONTROL_LOOPS, False),
    }

    env_options = {
        CONF_ENV_ENABLE: entry.options.get(CONF_ENV_ENABLE, False),
        CONF_ENV_MODE: entry.options.get(CONF_ENV_MODE, ENV_MODE_ATTRIBUTES),
        CONF_ENV_POLL_INTERVAL: entry.options.get(CONF_ENV_POLL_INTERVAL, DEFAULT_ENV_POLL_INTERVAL),
    }

    client = SwitchSnmpClient(
        hass,
        host,
        snmp_settings,
        custom_oids=(entry.options.get(CONF_FEATURE_OVERRIDES) or {}).get("device_info") or {},
        bandwidth_options=bandwidth_options,
        poe_options=poe_options,
        env_options=env_options,
        feature_overrides=entry.options.get(CONF_FEATURE_OVERRIDES) or {},
    )
    try:
        await client.async_initialize()
    except SnmpAuthError as exc:
        raise ConfigEntryAuthFailed(
            f"SNMP authentication failed for {host}: {exc}"
        ) from exc
    except SnmpConnectionError as exc:
        raise ConfigEntryNotReady(
            f"Failed to connect to SNMP device at {host}: {exc}"
        ) from exc

    # Apply per-device option for sysUpTime throttling
    client.set_uptime_poll_interval(entry.options.get(CONF_UPTIME_POLL_INTERVAL, DEFAULT_UPTIME_POLL_INTERVAL))

    default_rename_rules = client._database.get("rename_rules", {}).get("rename_rules", [])
    port_rename_rules = _build_port_rename_rules(entry.options, default_rename_rules)

    async def _update_method():
        try:
            data = await client.async_poll()
            # Success: dismiss unreachable notification if it exists
            try:
                from homeassistant.components import persistent_notification
                persistent_notification.async_dismiss(
                    hass,
                    notification_id=f"snmp_switch_offline_{entry.entry_id}"
                )
            except Exception as e:
                _LOGGER.debug("Failed to dismiss persistent notification: %s", e)
            return _postprocess_if_names(data, entry.options, port_rename_rules)
        except SnmpConnectionError as exc:
            # Failure: create unreachable persistent notification with offline illustration
            try:
                from homeassistant.components import persistent_notification
                title = f"SNMP Switch Unreachable ({entry.title})"
                # Embed the offline image served from our registered static route
                message = (
                    f'<img src="/snmp_switch_manager_static/offline.png" width="100%" '
                    f'style="max-width: 400px; border-radius: 8px; margin-bottom: 15px; display: block;" />\n\n'
                    f'The switch at **{host}** is currently unreachable.\n\n'
                    f'**Error:** `{exc}`\n\n'
                    f'Please verify that the device is powered on, connected to the network, and that no firewall is blocking SNMP queries (port {snmp_settings.get("port", 161)}).'
                )
                persistent_notification.async_create(
                    hass,
                    title=title,
                    message=message,
                    notification_id=f"snmp_switch_offline_{entry.entry_id}"
                )
            except Exception as e:
                _LOGGER.debug("Failed to create persistent notification: %s", e)
            raise UpdateFailed(f"Error communicating with SNMP device at {host}: {exc}") from exc

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}-coordinator-{host}",
        update_interval=timedelta(seconds=max(
            MIN_POLL_INTERVAL,
            min(
                MAX_POLL_INTERVAL,
                int(entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL) or DEFAULT_POLL_INTERVAL),
            ),
        )),
        # IMPORTANT: use the client's poll method directly. The client is
        # responsible for handling/guarding poll errors so we don't mark all
        # coordinator-backed entities unavailable.
        update_method=_update_method,
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = SnmpSwitchRuntimeData(client=client, coordinator=coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Clean up duplicate legacy device registry entries if they exist
    try:
        from homeassistant.helpers import device_registry as dr
        device_registry = dr.async_get(hass)
        devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
        if len(devices) > 1:
            _LOGGER.info("Found %d registered devices for config entry %s, starting cleanup", len(devices), entry.entry_id)
            true_device = None
            for device in devices:
                if (DOMAIN, entry.entry_id) in device.identifiers:
                    true_device = device
                    break
            
            if true_device:
                for device in devices:
                    if device.id != true_device.id:
                        _LOGGER.warning("Removing duplicate/legacy device registry entry: %s (ID: %s)", device.name, device.id)
                        device_registry.async_remove_device(device.id)
    except Exception as exc:
        _LOGGER.error("Error during device registry cleanup: %s", exc)

    from .db_updater import async_setup_db_updater
    await async_setup_db_updater(hass, entry)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True

async def _async_update_listener(hass: HomeAssistant, entry: SwitchManagerConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: SwitchManagerConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        from .db_updater import async_unload_db_updater
        async_unload_db_updater(hass, entry)

        runtime: SnmpSwitchRuntimeData | None = getattr(entry, "runtime_data", None)
        if runtime is not None:
            try:
                await runtime.client.async_close()
            except Exception:
                pass
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
        config_entry = hass.config_entries.async_get_entry(entry_id)
        runtime: SnmpSwitchRuntimeData | None = getattr(config_entry, "runtime_data", None) if config_entry else None
        if not runtime:
            return

        client = runtime.client
        # Parse if_index from our unique_id pattern "<entry_id>-if-<index>"
        unique_id = ent.unique_id or ""
        try:
            if_index = int(unique_id.split("-if-")[-1])
        except Exception:
            return

        await client.set_alias(if_index, description)
        await runtime.coordinator.async_request_refresh()

    async def handle_set_system_string(call, oid: str):
        from homeassistant.helpers import device_registry as dr

        device_id = call.data.get("device_id")
        if not device_id:
            return
        if isinstance(device_id, (list, set, tuple)):
            if not device_id:
                return
            device_id = list(device_id)[0]

        dev_reg = dr.async_get(hass)
        device = dev_reg.async_get(device_id)
        if not device:
            return

        entry_id = None
        for entry_id_cand in device.config_entries:
            config_entry = hass.config_entries.async_get_entry(entry_id_cand)
            if config_entry and config_entry.domain == DOMAIN:
                entry_id = entry_id_cand
                break

        if not entry_id:
            return

        config_entry = hass.config_entries.async_get_entry(entry_id)
        runtime: SnmpSwitchRuntimeData | None = getattr(config_entry, "runtime_data", None) if config_entry else None
        if not runtime:
            return

        client = runtime.client
        value = call.data.get("value", "")
        
        target_oid = oid
        if oid == OID_sysName:
            target_oid = client._custom_oid("name") or client._custom_oid("hostname") or OID_sysName
        elif oid == OID_sysContact:
            target_oid = client._custom_oid("contact") or OID_sysContact
        elif oid == OID_sysLocation:
            target_oid = client._custom_oid("location") or OID_sysLocation
            
        await client.set_system_string(target_oid, value)
        await runtime.coordinator.async_request_refresh()

    async def handle_set_system_name(call):
        await handle_set_system_string(call, OID_sysName)

    async def handle_set_system_contact(call):
        await handle_set_system_string(call, OID_sysContact)

    async def handle_set_system_location(call):
        await handle_set_system_string(call, OID_sysLocation)

    async def handle_set_poe_admin(call):
        entity_id = call.data.get("entity_id")
        state = call.data.get("state")

        ent_reg = er.async_get(hass)
        ent = ent_reg.async_get(entity_id)
        if not ent:
            _LOGGER.warning("PoE admin service: Entity %s not found", entity_id)
            return

        entry_id = ent.config_entry_id
        config_entry = hass.config_entries.async_get_entry(entry_id)
        runtime: SnmpSwitchRuntimeData | None = getattr(config_entry, "runtime_data", None) if config_entry else None
        if not runtime:
            return

        client = runtime.client
        unique_id = ent.unique_id or ""
        try:
            if "-poe-" in unique_id:
                if_index = int(unique_id.split("-poe-")[-1])
            elif "-if-" in unique_id:
                if_index = int(unique_id.split("-if-")[-1])
            else:
                _LOGGER.warning("PoE admin service: Entity %s does not have a recognizable ifIndex", entity_id)
                return
        except Exception:
            return

        poe_ports = client.cache.get("poe_ports", {})
        port_info = poe_ports.get(if_index)
        if not port_info:
            _LOGGER.warning("PoE admin service: PoE details not found in cache for ifIndex %s", if_index)
            return

        group_idx = port_info.get("group")
        port_idx = port_info.get("port")
        if group_idx is None or port_idx is None:
            return

        # 1 = auto, 2 = disabled
        val = 1 if (state == "Auto" or state is True) else 2

        ok = await client.set_poe_admin(group_idx, port_idx, val)
        if ok:
            if if_index in client.cache.setdefault("poe_ports", {}):
                client.cache["poe_ports"][if_index]["admin"] = val
            await runtime.coordinator.async_request_refresh()

    async def handle_set_poe_priority(call):
        entity_id = call.data.get("entity_id")
        priority = call.data.get("priority")

        ent_reg = er.async_get(hass)
        ent = ent_reg.async_get(entity_id)
        if not ent:
            _LOGGER.warning("PoE priority service: Entity %s not found", entity_id)
            return

        entry_id = ent.config_entry_id
        config_entry = hass.config_entries.async_get_entry(entry_id)
        runtime: SnmpSwitchRuntimeData | None = getattr(config_entry, "runtime_data", None) if config_entry else None
        if not runtime:
            return

        client = runtime.client
        unique_id = ent.unique_id or ""
        try:
            if "-poe-priority-" in unique_id:
                if_index = int(unique_id.split("-poe-priority-")[-1])
            elif "-poe-" in unique_id:
                if_index = int(unique_id.split("-poe-")[-1])
            elif "-if-" in unique_id:
                if_index = int(unique_id.split("-if-")[-1])
            else:
                _LOGGER.warning("PoE priority service: Entity %s does not have a recognizable ifIndex", entity_id)
                return
        except Exception:
            return

        poe_ports = client.cache.get("poe_ports", {})
        port_info = poe_ports.get(if_index)
        if not port_info:
            _LOGGER.warning("PoE priority service: PoE details not found in cache for ifIndex %s", if_index)
            return

        group_idx = port_info.get("group")
        port_idx = port_info.get("port")
        if group_idx is None or port_idx is None:
            return

        val = 3
        if priority == "Critical":
            val = 1
        elif priority == "High":
            val = 2
        elif priority == "Low":
            current_port_priority = port_info.get("priority")
            if current_port_priority == 4 or any(p.get("priority") == 4 for p in poe_ports.values()):
                val = 4
            else:
                val = 3

        ok = await client.set_poe_priority(group_idx, port_idx, val)
        if ok:
            if if_index in client.cache.setdefault("poe_ports", {}):
                client.cache["poe_ports"][if_index]["priority"] = val
            await runtime.coordinator.async_request_refresh()

    async def handle_set_port_admin_status(call):
        entity_id = call.data.get("entity_id")
        state = call.data.get("state")

        ent_reg = er.async_get(hass)
        ent = ent_reg.async_get(entity_id)
        if not ent:
            _LOGGER.warning("Port admin status service: Entity %s not found", entity_id)
            return

        entry_id = ent.config_entry_id
        config_entry = hass.config_entries.async_get_entry(entry_id)
        runtime: SnmpSwitchRuntimeData | None = getattr(config_entry, "runtime_data", None) if config_entry else None
        if not runtime:
            return

        client = runtime.client
        unique_id = ent.unique_id or ""
        try:
            if "-if-" in unique_id:
                if_index = int(unique_id.split("-if-")[-1])
            else:
                _LOGGER.warning("Port admin status service: Entity %s does not have a recognizable ifIndex", entity_id)
                return
        except Exception:
            return

        # 1 = Up/Enabled, 2 = Down/Disabled
        val = 1 if (state == "Up" or state is True) else 2

        ok = await client.set_admin_status(if_index, val)
        if ok:
            if if_index in client.cache.setdefault("ifTable", {}):
                client.cache["ifTable"][if_index]["admin"] = val
            await runtime.coordinator.async_request_refresh()

    if not hass.services.has_service(DOMAIN, "set_port_description"):
        hass.services.async_register(DOMAIN, "set_port_description", handle_set_alias)

    if not hass.services.has_service(DOMAIN, "set_system_name"):
        hass.services.async_register(DOMAIN, "set_system_name", handle_set_system_name)

    if not hass.services.has_service(DOMAIN, "set_system_contact"):
        hass.services.async_register(DOMAIN, "set_system_contact", handle_set_system_contact)

    if not hass.services.has_service(DOMAIN, "set_system_location"):
        hass.services.async_register(DOMAIN, "set_system_location", handle_set_system_location)

    if not hass.services.has_service(DOMAIN, "set_poe_port_admin"):
        hass.services.async_register(DOMAIN, "set_poe_port_admin", handle_set_poe_admin)

    if not hass.services.has_service(DOMAIN, "set_poe_port_priority"):
        hass.services.async_register(DOMAIN, "set_poe_port_priority", handle_set_poe_priority)

    if not hass.services.has_service(DOMAIN, "set_port_admin_status"):
        hass.services.async_register(DOMAIN, "set_port_admin_status", handle_set_port_admin_status)
