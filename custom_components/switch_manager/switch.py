from __future__ import annotations

import logging
from typing import List

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .snmp import (
    IANA_IFTYPE_IEEE8023AD_LAG,
    IANA_IFTYPE_SOFTWARE_LOOPBACK,
    SwitchSnmpClient,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up switch entities."""
    client: SwitchSnmpClient = hass.data[DOMAIN][entry.entry_id]["client"]

    # 1) Read ports + IPv4 mapping (CIDR) once up-front
    ports = await client.async_get_ports()
    ipv4_map = await client.async_get_ipv4_map()  # {ifIndex: 'a.b.c.d/len'}

    entities: List[SwitchManagerPort] = []

    for p in ports:
        # (A) Hide default/unconfigured Port-channels/LAGs
        if p.iftype == IANA_IFTYPE_IEEE8023AD_LAG:
            looks_unconfigured = (p.oper == 2) and (not p.alias) and (p.index >= 700)
            if looks_unconfigured:
                continue

        # (B) Friendly name (keep your existing patterns)
        name = p.name
        if p.iftype == IANA_IFTYPE_SOFTWARE_LOOPBACK:
            name = "Lo0"

        # (C) Build entity; attach IPv4 if we have one
        extra_attrs = {
            "Index": p.index,
            "Name": p.name,
            "Alias": p.alias,
            "Admin": p.admin,
            "Oper": p.oper,
        }
        ip_cidr = ipv4_map.get(p.index)
        if ip_cidr:
            extra_attrs["IP address"] = ip_cidr

        entities.append(SwitchManagerPort(entry.entry_id, name, extra_attrs))

    if not entities:
        _LOGGER.warning("No switch ports discovered for %s", entry.entry_id)

    async_add_entities(entities, update_before_add=False)


class SwitchManagerPort(SwitchEntity):
    """Simple on/off wrapper around a port's admin state."""

    _attr_has_entity_name = True

    def __init__(self, entry_id: str, name: str, attrs: dict) -> None:
        self._attr_name = name
        self._attrs = attrs
        self._entry_id = entry_id
        self._state = attrs.get("Admin", 0) == 1

    @property
    def is_on(self) -> bool:
        return self._state

    @property
    def extra_state_attributes(self) -> dict:
        return self._attrs

    @property
    def device_info(self) -> DeviceInfo:
        # Keep using the Device created for the config entry
        return DeviceInfo(identifiers={(DOMAIN, self._entry_id)})

    async def async_turn_on(self, **kwargs):
        # TODO: implement admin up via SNMP set (unchanged here)
        self._state = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        # TODO: implement admin down via SNMP set (unchanged here)
        self._state = False
        self.async_write_ha_state()
