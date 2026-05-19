from __future__ import annotations

from homeassistant.const import EntityCategory, PERCENTAGE
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)


class EnvironmentCpuUtilSensor(CoordinatorEntity, SensorEntity):
    """CPU utilization sensor (percent)."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:cpu-64-bit"

    def __init__(
        self,
        coordinator,
        entry,
        device_info: DeviceInfo,
        host_label: str,
        window: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._device_info = device_info
        self._host_label = host_label
        self._window = window

        # window is one of: 5s / 60s / 300s
        win_norm = str(window).lower().replace("sec", "s").replace(" ", "")
        if win_norm not in {"5s", "60s", "300s"}:
            win_norm = "300s"
        self._win_norm = win_norm
        self._attr_unique_id = f"{entry.entry_id}-env-cpu-{win_norm.replace('s','')}"

    @property
    def device_info(self):
        return self._device_info

    @property
    def name(self) -> str:
        return f"{self._host_label} CPU ({self._win_norm})"

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        raw = data.get("env_cpu_raw")
        return {"raw": raw} if raw is not None else {}

    @property
    def native_value(self):
        key = {
            "5s": "env_cpu_5s",
            "60s": "env_cpu_60s",
            "300s": "env_cpu_300s",
        }[self._win_norm]
        val = (self.coordinator.data or {}).get(key)
        try:
            return round(float(val), 1) if val is not None else None
        except Exception:
            return None


class EnvironmentMemorySensor(CoordinatorEntity, SensorEntity):
    """Memory metric sensor (kB or percent)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:memory"

    def __init__(
        self,
        coordinator,
        entry,
        key: str,
        name_suffix: str,
        unit: str | None,
        device_info: DeviceInfo,
        host_label: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._key = key
        self._name_suffix = name_suffix
        self._device_info = device_info
        self._host_label = host_label
        self._attr_unique_id = f"{entry.entry_id}-env-mem-{key}"
        if unit:
            self._attr_native_unit_of_measurement = unit

    @property
    def device_info(self):
        return self._device_info

    @property
    def name(self) -> str:
        return f"{self._host_label} {self._name_suffix}"

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        val = data.get(self._key)
        if val is None and self._key == "env_mem_available_kb":
            val = data.get("env_mem_free_kb")
        try:
            return round(float(val), 1) if val is not None else None
        except Exception:
            return None


class EnvironmentMemoryValueSensor(CoordinatorEntity, SensorEntity):
    """Memory value sensor (kB)."""

    _attr_native_unit_of_measurement = "kB"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, device_info: DeviceInfo, host_label: str, kind: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._device_info = device_info
        self._host_label = host_label
        self._kind = kind  # "available" | "total"

        if kind == "total":
            self._key = "env_mem_total_kb"
            self._label = "Memory Total"
            suffix = "total"
        else:
            self._key = "env_mem_available_kb"
            self._label = "Memory Available"
            suffix = "available"

        self._attr_unique_id = f"{entry.entry_id}-env-mem-{suffix}"

    @property
    def device_info(self):
        return self._device_info

    @property
    def name(self) -> str:
        return f"{self._host_label} {self._label}"

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        val = data.get(self._key)
        # Backward compatibility: older builds used env_mem_free_kb for available memory.
        if val is None and self._key == "env_mem_available_kb":
            val = data.get("env_mem_free_kb")
        try:
            return int(val) if val is not None else None
        except Exception:
            return None


class EnvironmentMemoryUsedPercentSensor(CoordinatorEntity, SensorEntity):
    """Memory used percentage based on total and available."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, device_info: DeviceInfo, host_label: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._device_info = device_info
        self._host_label = host_label
        self._attr_unique_id = f"{entry.entry_id}-env-mem-used-pct"

    @property
    def device_info(self):
        return self._device_info

    @property
    def name(self) -> str:
        return f"{self._host_label} Memory Used"

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        total = data.get("env_mem_total_kb")
        # Stored as available/free kB in coordinator.data
        avail = data.get("env_mem_available_kb")
        if avail is None:
            avail = data.get("env_mem_free_kb")
        try:
            total_i = float(total) if total is not None else None
            avail_i = float(avail) if avail is not None else None
            if not total_i or avail_i is None:
                return None
            used_pct = max(0.0, min(100.0, ((total_i - avail_i) / total_i) * 100.0))
            return round(used_pct, 1)
        except Exception:
            return None
