from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, PLATFORMS
from .snmp import SwitchSnmpClient

_LOGGER = logging.getLogger(__name__)


class SwitchManagerCoordinator(DataUpdateCoordinator):
    """Fetches system (sensors) and interfaces (switch entities)."""

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
            ports = await self.client.async_get_port_data()  # list[dict]
            system = await self.client.async_get_system_info()  # dict
            return {"ports": ports, "system": system}
        except Exception as exc:
            raise UpdateFailed(str(exc)) from exc


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    host: str = entry.data["host"]
    community: str = entry.data["community"]
    port = entry.data.get("port", 161)

    # tolerant arg order: (port, community) or (community, port)
    client = await SwitchSnmpClient.async_create(hass, host, port, community)

    coordinator = SwitchManagerCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    # Store in both shapes so platforms can always find it
    domain_store = hass.data.setdefault(DOMAIN, {})
    domain_store.setdefault("entries", {})
    domain_store["entries"][entry.entry_id] = {"client": client, "coordinator": coordinator}
    domain_store[entry.entry_id] = domain_store["entries"][entry.entry_id]
    domain_store.setdefault("service_registered", True)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        store = hass.data.get(DOMAIN, {})
        if "entries" in store:
            store["entries"].pop(entry.entry_id, None)
        store.pop(entry.entry_id, None)
    return ok
