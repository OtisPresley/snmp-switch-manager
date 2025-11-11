"""
Switch entities for Switch Manager.

Surgical changes only:
- attach "IP address" attribute when available as CIDR
- continue skipping CPU ifIndex 661 (already done in snmp.py)
- DO NOT change your existing naming flow; we simply pass through .name
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.config_entries import ConfigEntry

from .snmp import (
    SwitchSnmpClient,
    IANA_IFTYPE_SOFTWARE_LOOPBACK,
)

DOMAIN = "switch_manager"


@dataclass
class PortEntityDescription:
    index: int
    name: str
    alias: str
    admin: int
    oper: int
    ip_cidr: Optional[str]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = entry.data
    host: str = data["host"]
    port: int = data["port"]
    community: str = data["community"]

    client = await SwitchSnmpClient.async_create(hass, host, port, community)

    # Fetch ports once at setup; your coordinator may also refresh later if you have one
    rows = await client.async_get_port_data()

    entities: List[SwitchPortEntity] = []
    for r in rows:
        desc = PortEntityDescription(
            index=r.index,
            name=r.name,     # keep your existing display names
            alias=r.alias,
            admin=r.admin,
            oper=r.oper,
            ip_cidr=r.ip_cidr,
        )
        entities.append(SwitchPortEntity(desc))

    async_add_entities(entities, update_before_add=False)


class SwitchPortEntity(SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, desc: PortEntityDescription) -> None:
        self._desc = desc
        # Entity id / name – keep as before (use underlying name)
        self._attr_name = desc.name

    @property
    def is_on(self) -> bool:
        # "on" = admin up
        return self._desc.admin == 1

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        attrs: Dict[str, Any] = {
            "Index": self._desc.index,
            "Name": self._desc.name,
            "Admin": self._desc.admin,
            "Oper": self._desc.oper,
        }
        # NEW: add IP in CIDR when present
        if self._desc.ip_cidr:
            attrs["IP address"] = self._desc.ip_cidr
        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        # Not implemented (read-only)
        return

    async def async_turn_off(self, **kwargs: Any) -> None:
        # Not implemented (read-only)
        return
