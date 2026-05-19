from __future__ import annotations

from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)

from .environmental import EnvironmentBaseSensor

# Dell OS6 temperature sensor label mapping (index -> label)
ENV_TEMP_LABELS: dict[int, str] = {
    0: "MAC",
    1: "PHY",
    2: "POE Ctrl 1",
    3: "POE Ctrl 2",
    4: "POE Ctrl 3",
    5: "POE Ctrl 4",
    6: "POE Ctrl 5",
    7: "POE Ctrl 6",
    8: "POE Ctrl 7",
    9: "POE Ctrl 8",
}


def env_temp_label(idx: int) -> str:
    """Return a human-friendly temperature probe label."""
    return ENV_TEMP_LABELS.get(idx, f"Temp {idx}")


class EnvironmentTemperatureSensor(CoordinatorEntity, SensorEntity):
    """Temperature sensor (°C)."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, idx: int, device_info: DeviceInfo, host_label: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._idx = idx
        self._device_info = device_info
        self._host_label = host_label
        self._attr_unique_id = f"{entry.entry_id}-env-temp-{idx}"

    @property
    def device_info(self):
        return self._device_info

    @property
    def name(self) -> str:
        # Expose as numbered sensors; devices label these differently.
        labels = (self.coordinator.data or {}).get("env_temp_labels") or {}
        label = labels.get(self._idx) or env_temp_label(self._idx)
        return f"{self._host_label} {label} Temperature"

    @property
    def native_value(self):
        temps = (self.coordinator.data or {}).get("env_temps_c") or {}
        val = temps.get(self._idx)
        try:
            return int(val) if val is not None else None
        except Exception:
            return None


class EnvironmentUnitTemperatureSensor(EnvironmentBaseSensor):
    """Unit/System temperature for Dell OS6 (show unit temperature)."""

    def __init__(self, coordinator, entry, device_info, host_label):
        super().__init__(coordinator, entry, device_info, host_label)
        self._kind = "environment"
        self._name_prefix = "Environment"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def name(self):
        return f"{self._host_label} System Temperature"

    @property
    def unique_id(self):
        return f"{self._entry.entry_id}_env_system_temp"

    @property
    def native_value(self):
        val = (self.coordinator.data or {}).get("env_unit_temp_c")
        return float(val) if val is not None else None


class EnvironmentUnitTempStateSensor(EnvironmentBaseSensor):
    """Unit/System temperature health state for Dell OS6."""

    # Verified Dell OS6 mapping (user provided)
    _STATE_MAP = {
        1: "GOOD",
        2: "WARNING",
        3: "CRITICAL",
        4: "SHUTDOWN",
        5: "NOT PRESENT",
        6: "NOT FUNCTIONING",
    }

    def __init__(self, coordinator, entry, device_info, host_label):
        super().__init__(coordinator, entry, device_info, host_label)
        self._kind = "environment"
        self._name_prefix = "Environment"
        self._attr_icon = "mdi:thermometer-alert"

    @property
    def name(self):
        # Rename for clarity: tied to System Temperature
        return f"{self._host_label} System Temperature Status"

    @property
    def unique_id(self):
        return f"{self._entry.entry_id}_env_system_temp_state"

    @property
    def native_value(self):
        raw = (self.coordinator.data or {}).get("env_unit_temp_state")
        if raw is None:
            return None
        try:
            raw_i = int(raw)
        except (TypeError, ValueError):
            return None
        return self._STATE_MAP.get(raw_i, str(raw_i))
