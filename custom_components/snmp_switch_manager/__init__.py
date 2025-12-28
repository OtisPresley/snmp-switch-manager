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
    CONF_BW_INCLUDE_STARTS_WITH,
    CONF_BW_INCLUDE_CONTAINS,
    CONF_BW_INCLUDE_ENDS_WITH,
    CONF_BW_EXCLUDE_STARTS_WITH,
    CONF_BW_EXCLUDE_CONTAINS,
    CONF_BW_EXCLUDE_ENDS_WITH,
)
from .snmp import SwitchSnmpClient

_LOGGER = logging.getLogger(__name__)

# Use standard aliasing compatible with Python <3.12
SwitchManagerConfigEntry = ConfigEntry

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True

async def async_setup_entry(hass: HomeAssistant, entry: SwitchManagerConfigEntry) -> bool:
    host = entry.data.get("host")
    port = entry.data.get("port")
    community = entry.data.get("community")

    client = SwitchSnmpClient(hass, host, community, port, custom_oids=entry.options.get(CONF_CUSTOM_OIDS) or {}, bandwidth_options={
        CONF_BW_ENABLE: entry.options.get(CONF_BW_ENABLE, False),
        CONF_BW_INCLUDE_STARTS_WITH: entry.options.get(CONF_BW_INCLUDE_STARTS_WITH, []) or [],
        CONF_BW_INCLUDE_CONTAINS: entry.options.get(CONF_BW_INCLUDE_CONTAINS, []) or [],
        CONF_BW_INCLUDE_ENDS_WITH: entry.options.get(CONF_BW_INCLUDE_ENDS_WITH, []) or [],
        CONF_BW_EXCLUDE_STARTS_WITH: entry.options.get(CONF_BW_EXCLUDE_STARTS_WITH, []) or [],
        CONF_BW_EXCLUDE_CONTAINS: entry.options.get(CONF_BW_EXCLUDE_CONTAINS, []) or [],
        CONF_BW_EXCLUDE_ENDS_WITH: entry.options.get(CONF_BW_EXCLUDE_ENDS_WITH, []) or [],
        CONF_BANDWIDTH_POLL_INTERVAL: entry.options.get(CONF_BANDWIDTH_POLL_INTERVAL, DEFAULT_BANDWIDTH_POLL_INTERVAL),
    })
    await client.async_initialize()

    # Apply per-device option for sysUpTime throttling
    client.set_uptime_poll_interval(entry.options.get(CONF_UPTIME_POLL_INTERVAL, DEFAULT_UPTIME_POLL_INTERVAL))

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}-coordinator-{host}",
        update_interval=timedelta(seconds=DEFAULT_POLL_INTERVAL),
        update_method=client.async_poll,
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
