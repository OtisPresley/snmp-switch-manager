from __future__ import annotations

from homeassistant.const import EntityCategory, UnitOfPower
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity


class PoEPowerSensor(CoordinatorEntity, SensorEntity):
    """Per-port PoE power draw sensor (W)."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = "W"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, if_index: int, device_info: DeviceInfo, host_label: str):
        super().__init__(coordinator)
        self._entry = entry
        self._if_index = if_index
        self._host_label = host_label
        self._device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}-poe-{if_index}-power"

    @property
    def device_info(self):
        return self._device_info

    def _if_name(self) -> str:
        if_table = self.coordinator.data.get("ifTable", {}) or {}
        row = if_table.get(self._if_index, {}) or {}
        return row.get("name") or row.get("alias") or str(self._if_index)

    @property
    def name(self) -> str:
        return f"{self._if_name()} PoE Power"

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        poe_power_mw = data.get("poe_power_mw", {}) or {}
        mw = poe_power_mw.get(self._if_index)
        if mw is None:
            return 0.0
        try:
            return round(float(mw) / 1000.0, 1)
        except Exception:
            return None


class PoEAggregateSensor(CoordinatorEntity, SensorEntity):
    """PoE aggregate sensor (state = power used W, with attributes)."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:power-plug"

    def __init__(self, coordinator, entry, device_info: DeviceInfo, host_label: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._device_info = device_info
        self._host_label = host_label
        self._attr_unique_id = f"{entry.entry_id}-poe"

    @property
    def device_info(self):
        return self._device_info

    @property
    def name(self) -> str:
        return f"{self._host_label} Power over Ethernet"

    @property
    def native_value(self):
        val = (self.coordinator.data or {}).get("poe_power_used_w")
        try:
            return round(float(val), 1) if val is not None else None
        except Exception:
            return None

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        attrs = {}
        b = data.get("poe_budget_total_w")
        u = data.get("poe_power_used_w")
        a = data.get("poe_power_available_w")
        h = data.get("poe_health_status")
        if b is not None:
            attrs["PoE Budget Total (W)"] = round(float(b), 1)
        if u is not None:
            attrs["PoE Power Used (W)"] = round(float(u), 1)
        if a is not None:
            attrs["PoE Power Available (W)"] = round(float(a), 1)
        if h is not None:
            attrs["PoE Health Status"] = str(h)
        return attrs


class _PoEBase(CoordinatorEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_icon = "mdi:power-plug"

    def __init__(self, coordinator, entry, device_info: DeviceInfo, host_label: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._device_info = device_info
        self._host_label = host_label

    @property
    def device_info(self):
        return self._device_info


class PoEBudgetTotalSensor(_PoEBase):
    def __init__(self, coordinator, entry, device_info, host_label):
        super().__init__(coordinator, entry, device_info, host_label)
        self._attr_unique_id = f"{entry.entry_id}-poe-budget-total"

    @property
    def name(self):
        return f"{self._host_label} PoE Budget Total"

    @property
    def native_value(self):
        val = (self.coordinator.data or {}).get("poe_budget_total_w")
        try:
            return round(float(val), 1) if val is not None else None
        except Exception:
            return None


class PoEPowerUsedSensor(_PoEBase):
    def __init__(self, coordinator, entry, device_info, host_label):
        super().__init__(coordinator, entry, device_info, host_label)
        self._attr_unique_id = f"{entry.entry_id}-poe-power-used"

    @property
    def name(self):
        return f"{self._host_label} PoE Power Used"

    @property
    def native_value(self):
        val = (self.coordinator.data or {}).get("poe_power_used_w")
        try:
            return round(float(val), 1) if val is not None else None
        except Exception:
            return None


class PoEPowerAvailableSensor(_PoEBase):
    def __init__(self, coordinator, entry, device_info, host_label):
        super().__init__(coordinator, entry, device_info, host_label)
        self._attr_unique_id = f"{entry.entry_id}-poe-power-available"

    @property
    def name(self):
        return f"{self._host_label} PoE Power Available"

    @property
    def native_value(self):
        val = (self.coordinator.data or {}).get("poe_power_available_w")
        try:
            return round(float(val), 1) if val is not None else None
        except Exception:
            return None


class PoEHealthStatusSensor(CoordinatorEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:heart-pulse"

    def __init__(self, coordinator, entry, device_info, host_label):
        super().__init__(coordinator)
        self._entry = entry
        self._device_info = device_info
        self._host_label = host_label
        self._attr_unique_id = f"{entry.entry_id}-poe-health"

    @property
    def device_info(self):
        return self._device_info

    @property
    def name(self):
        return f"{self._host_label} PoE Health Status"

    @property
    def native_value(self):
        val = (self.coordinator.data or {}).get("poe_health_status")
        return str(val) if val is not None else None
