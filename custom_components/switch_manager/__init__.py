from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL, PLATFORMS
from .snmp import SwitchSnmpClient, SnmpError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Switch Manager from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    host: str = entry.data["host"]
    port: int = int(entry.data["port"])
    community: str = entry.data["community"]

    client = await SwitchSnmpClient.async_create(hass, host, port, community)

    async def _async_update_data() -> Dict[str, Any]:
        try:
            # --- surgical change: return a *single* dict with both parts ---
            ports = await client.async_get_port_data()
            system = await client.async_get_system_info()
            return {"ports": ports, "system": system}
        except SnmpError as err:
            raise UpdateFailed(str(err)) from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"Switch Manager {host}",
        update_method=_async_update_data,
        update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
