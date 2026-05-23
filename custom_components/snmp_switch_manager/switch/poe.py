from __future__ import annotations

import time
from typing import Any, Dict

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo

from ..snmp import SwitchSnmpClient


class PoePortSwitch(CoordinatorEntity, SwitchEntity):
    """Switch entity representing PoE Admin Enable status."""

    def __init__(
        self,
        coordinator,
        entry_id: str,
        if_index: int,
        raw_name: str,
        display_name: str,
        group_idx: int,
        port_idx: int,
        device_info: DeviceInfo,
        client: SwitchSnmpClient,
        hostname: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._if_index = if_index
        self._raw_name = raw_name
        self._display_name = display_name
        self._group_idx = group_idx
        self._port_idx = port_idx
        self._client = client
        self._state_override = None
        self._state_override_time = None

        self._attr_unique_id = f"{entry_id}-poe-{if_index}"
        self._attr_name = f"{hostname} {display_name} PoE"
        self._attr_device_info = device_info
        self._attr_icon = "mdi:ethernet"

    @property
    def is_on(self) -> bool:
        if self._state_override_time is not None:
            if time.monotonic() - self._state_override_time < 10.0:
                return self._state_override == 1
            else:
                self._state_override_time = None
                self._state_override = None

        data = self.coordinator.data or {}
        poe_ports = data.get("poe_ports", {})
        port_data = poe_ports.get(self._if_index, {})
        return port_data.get("admin") == 1

    async def async_turn_on(self, **kwargs):
        ok = await self._client.set_poe_admin(self._group_idx, self._port_idx, 1)
        if ok:
            self._state_override = 1
            self._state_override_time = time.monotonic()
            if self._if_index in self.coordinator.data.setdefault("poe_ports", {}):
                self.coordinator.data["poe_ports"][self._if_index]["admin"] = 1
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        ok = await self._client.set_poe_admin(self._group_idx, self._port_idx, 2)
        if ok:
            self._state_override = 2
            self._state_override_time = time.monotonic()
            if self._if_index in self.coordinator.data.setdefault("poe_ports", {}):
                self.coordinator.data["poe_ports"][self._if_index]["admin"] = 2
            self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        data = self.coordinator.data or {}
        poe_ports = data.get("poe_ports", {})
        port_data = poe_ports.get(self._if_index, {})
        admin_val = port_data.get("admin", 2)
        if self._state_override_time is not None:
            if time.monotonic() - self._state_override_time < 10.0:
                admin_val = self._state_override
            else:
                self._state_override_time = None
                self._state_override = None

        attrs = {
            "ifindex": self._if_index,
            "group": self._group_idx,
            "port": self._port_idx,
            "admin": "Auto/Enabled" if admin_val == 1 else "Disabled",
        }
        return attrs
