from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, PLATFORMS
from .snmp import SwitchSnmpClient, SnmpError

_LOGGER = logging.getLogger(__name__)


class SwitchManagerCoordinator(DataUpdateCoordinator):
    """Coordinator that fetches switch system/port state."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: SwitchSnmpClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"Switch Manager {entry.title}",
            update_interval=timedelta(seconds=30),
        )
        self.client = client
        self.entry = entry

    async def _async_update_data(self):
        try:
            # Keep keys stable: sensors expect "system"; switch entities expect "ports"
            ports = await self.client.async_get_port_data()
            system = await self.client.async_get_system_info()
            return {"ports": ports, "system": system}
        except Exception as exc:
            raise UpdateFailed(str(exc)) from exc


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Switch Manager from a config entry."""
    host = entry.data["host"]
    community = entry.data["community"]
    port = entry.data.get("port", 161)

    # Create client (tolerates arg order)
    client = await SwitchSnmpClient.async_create(hass, host, port, community)

    coordinator = SwitchManagerCoordinator(hass, entry, client)
    # Make sure we have data before platforms read coordinator.data
    await coordinator.async_config_entry_first_refresh()

    # Robust storage so both old/new platform codepaths work
    domain_store = hass.data.setdefault(DOMAIN, {})
    # Primary map used by some versions
    domain_store.setdefault("entries", {})
    domain_store["entries"][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }
    # Back-compat direct access used by other versions
    domain_store[entry.entry_id] = domain_store["entries"][entry.entry_id]

    # Mark that we registered services once
    domain_store.setdefault("service_registered", True)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        store = hass.data.get(DOMAIN, {})
        # Remove both storage shapes
        if "entries" in store:
            store["entries"].pop(entry.entry_id, None)
        store.pop(entry.entry_id, None)
    return unloaded
