from __future__ import annotations

import logging
import time
from typing import Any, Dict

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    CONF_LEGACY_DEVICE_ID,
    CONF_POE_CONTROL_LOOPS,
)
from .snmp import SwitchSnmpClient
from .helpers import format_interface_name

_LOGGER = logging.getLogger(__name__)

# Standard POWER-ETHERNET-MIB priority values:
# 1 = critical
# 2 = high
# 3 = low
PRIORITY_TO_STR = {1: "Critical", 2: "High", 3: "Low", 4: "Low"}
STR_TO_PRIORITY = {"Critical": 1, "High": 2, "Low": 3}


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = entry.runtime_data
    client: SwitchSnmpClient = runtime.client
    coordinator = runtime.coordinator

    poe_control_loops = entry.options.get(CONF_POE_CONTROL_LOOPS, False)
    if not poe_control_loops:
        # Clean up any previously-created PoE select entities if disabled
        ent_reg = er.async_get(hass)
        for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
            if ent.domain != "select":
                continue
            if (ent.unique_id or "").startswith(f"{entry.entry_id}-poe-priority-"):
                ent_reg.async_remove(ent.entity_id)
        return

    entities = []
    poe_ports = client.cache.get("poe_ports", {})
    iftable = client.cache.get("ifTable", {})
    hostname = client.cache.get("sysName") or entry.data.get("name") or client.host

    identifiers = {(DOMAIN, entry.entry_id)}
    legacy_device_id = str(
        entry.data.get(CONF_LEGACY_DEVICE_ID) or entry.options.get(CONF_LEGACY_DEVICE_ID) or ""
    ).strip()
    if legacy_device_id:
        identifiers.add((DOMAIN, legacy_device_id))

    device_info = DeviceInfo(identifiers=identifiers, name=hostname)

    desired_poe_indexes = set()

    for idx, port_info in poe_ports.items():
        group_idx = port_info.get("group")
        port_idx = port_info.get("port")
        if group_idx is None or port_idx is None:
            continue

        row = iftable.get(idx, {})
        raw_name = row.get("display_name") or row.get("name") or row.get("descr") or f"if{idx}"
        
        # Parse display name just like in switch.py
        unit = 1
        slot = 0
        port = None
        try:
            if "/" in raw_name and raw_name[2:3].isdigit():
                parts = raw_name[2:].split("/")
                if len(parts) >= 3:
                    unit = int(parts[0])
                    slot = int(parts[1])
                    port = int(parts[2])
        except Exception:
            pass

        db = client._database.get("interface_classification") if hasattr(client, "_database") else None
        display = format_interface_name(raw_name, unit=unit, slot=slot, port=port, classification_db=db)

        entities.append(
            PoePortPrioritySelect(
                coordinator=coordinator,
                entry_id=entry.entry_id,
                if_index=idx,
                raw_name=raw_name,
                display_name=display,
                group_idx=group_idx,
                port_idx=port_idx,
                device_info=device_info,
                client=client,
                hostname=hostname,
            )
        )
        desired_poe_indexes.add(idx)

    # Clean up obsolete select entities
    ent_reg = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if ent.domain != "select":
            continue
        unique_id = ent.unique_id or ""
        if unique_id.startswith(f"{entry.entry_id}-poe-priority-"):
            try:
                old_idx = int(unique_id.split("-poe-priority-", 1)[1])
            except Exception:
                continue
            if old_idx not in desired_poe_indexes:
                ent_reg.async_remove(ent.entity_id)

    async_add_entities(entities)


class PoePortPrioritySelect(CoordinatorEntity, SelectEntity):
    """Select entity representing PoE Priority allocation status."""

    _attr_options = ["Critical", "High", "Low"]

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

        self._attr_unique_id = f"{entry_id}-poe-priority-{if_index}"
        self._attr_name = f"{hostname} {display_name} PoE Priority"
        self._attr_device_info = device_info
        self._attr_icon = "mdi:power-settings"

    @property
    def current_option(self) -> str | None:
        if self._state_override_time is not None:
            if time.monotonic() - self._state_override_time < 10.0:
                return PRIORITY_TO_STR.get(self._state_override, "Low")
            else:
                self._state_override_time = None
                self._state_override = None

        data = self.coordinator.data or {}
        poe_ports = data.get("poe_ports", {})
        port_data = poe_ports.get(self._if_index, {})
        val = port_data.get("priority", 3)
        return PRIORITY_TO_STR.get(val, "Low")

    async def async_select_option(self, option: str) -> None:
        val = STR_TO_PRIORITY.get(option, 3)
        if option == "Low":
            poe_ports = self._client.cache.get("poe_ports", {})
            current_port_priority = poe_ports.get(self._if_index, {}).get("priority")
            if current_port_priority == 4 or any(p.get("priority") == 4 for p in poe_ports.values()):
                val = 4
        ok = await self._client.set_poe_priority(self._group_idx, self._port_idx, val)
        if ok:
            self._state_override = val
            self._state_override_time = time.monotonic()
            if self._if_index in self.coordinator.data.setdefault("poe_ports", {}):
                self.coordinator.data["poe_ports"][self._if_index]["priority"] = val
            self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        return {
            "ifindex": self._if_index,
            "group": self._group_idx,
            "port": self._port_idx,
        }
