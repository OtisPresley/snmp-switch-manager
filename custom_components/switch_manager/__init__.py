from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .snmp import SwitchSnmpClient, ensure_snmp_available, SnmpError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["switch", "sensor"]  # make sure we load sensors too


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Switch Manager entry."""
    await hass.async_add_executor_job(ensure_snmp_available)

    host = entry.data.get("host")
    community = entry.data.get("community")
    port = int(entry.data.get("port", 161))

    # Create a client (tolerant factory handles (hass, host, community, port))
    client = await SwitchSnmpClient.async_create(hass, host, community, port)

    async def _async_update_data() -> Dict[str, Any]:
        """Fetch system + ports and return a single dict the platforms can use."""
        try:
            # Run them in parallel
            system_task = asyncio.create_task(client.async_get_system_info())
            ports_task = asyncio.create_task(client.async_get_port_data())
            system = await system_task
            ports = await ports_task

            # Shape we expect everywhere:
            #   {"system": {...}, "ports": { ifIndex: {index,name,alias,admin,oper,ipv4:[{address,netmask}]}}}
            return {"system": system or {}, "ports": ports or {}}
        except Exception as err:
            raise UpdateFailed(str(err)) from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"Switch Manager {entry.title or host}",
        update_method=_async_update_data,
        update_interval=timedelta(seconds=30),
    )

    # Prime data
    await coordinator.async_config_entry_first_refresh()

    # make the client available to platforms (for set operations)
    coordinator.client = client  # type: ignore[attr-defined]

    # store in a predictable place
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("entries", {})
    hass.data[DOMAIN]["entries"][entry.entry_id] = {"coordinator": coordinator}
    hass.data[DOMAIN]["service_registered"] = True

    # forward to platforms (switch + sensor)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # options reload
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Switch Manager entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        try:
            hass.data[DOMAIN]["entries"].pop(entry.entry_id, None)
            # Cleanup top-level dict if empty
            if not hass.data[DOMAIN]["entries"]:
                hass.data.pop(DOMAIN, None)
        except Exception:  # be tolerant
            pass
    return unload_ok
