from __future__ import annotations

from typing import Any
from homeassistant.const import EntityCategory, UnitOfPower
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)

# Reasonable defaults for Dell N-Series (and harmless for others).
DEFAULT_ENV_TEMP_COUNT = 10
DEFAULT_ENV_FAN_COUNT = 2
DEFAULT_ENV_PSU_COUNT = 2


class EnvironmentBaseSensor(CoordinatorEntity, SensorEntity):
    """Shared base for Environment sensors.

    Prevents HA startup NameError when environment sensor subclasses rely on a
    common base class.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, device_info: DeviceInfo, host_label: str):
        super().__init__(coordinator)
        self._entry = entry
        self._device_info = device_info
        self._host_label = host_label
        # subclasses may override
        self._kind = "environment"
        self._name_prefix = "Environment"

    @property
    def device_info(self) -> DeviceInfo:
        return self._device_info


class EnvironmentPowerSensor(CoordinatorEntity, SensorEntity):
    """Device-level environmental power sensor (W) derived from private MIB."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT

    # Use native_unit_of_measurement so HA validates correctly for POWER device_class.
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, device_info: DeviceInfo, host_label: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._device_info = device_info
        self._host_label = host_label
        self._attr_unique_id = f"{entry.entry_id}-env-power"

    @property
    def device_info(self):
        return self._device_info

    @property
    def name(self) -> str:
        return f"{self._host_label} Environment"

    @property
    def native_value(self):
        # Coordinator stores refreshed SNMP values in coordinator.data
        data = self.coordinator.data or {}
        total_mw = data.get("env_power_mw_total")
        if total_mw is None:
            return None
        try:
            return round(float(total_mw) / 1000.0, 1)
        except Exception:
            return None

    @property
    def extra_state_attributes(self):
        """High-level environment attributes (no raw/debug fields)."""
        data = self.coordinator.data or {}
        attrs: dict[str, object] = {}

        # CPU (Dell OS6 provides 5/60/300 second averages)
        for label, key in (
            ("CPU 5s (%)", "env_cpu_5s"),
            ("CPU 60s (%)", "env_cpu_60s"),
            ("CPU 300s (%)", "env_cpu_300s"),
        ):
            v = data.get(key)
            if v is not None:
                attrs[label] = v

        # Memory (kB) + computed usage %
        total_kb = data.get("env_mem_total_kb")
        free_kb = data.get("env_mem_available_kb")
        if free_kb is None:
            free_kb = data.get("env_mem_free_kb")
        if total_kb is not None:
            attrs["Memory Total (kB)"] = total_kb
        if free_kb is not None:
            # Dell OS6 OID is "Memory Available" (in kB)
            attrs["Memory Available (kB)"] = free_kb
        try:
            if total_kb is not None and free_kb is not None and float(total_kb) > 0:
                used_pct = ((float(total_kb) - float(free_kb)) / float(total_kb)) * 100.0
                attrs["Memory Used (%)"] = round(max(0.0, min(100.0, used_pct)), 1)
        except Exception:
            pass

        # System/Chassis temperature (Dell OS6 unit temperature table)
        unit_temp_c = data.get("env_unit_temp_c")
        if unit_temp_c is not None:
            attrs["System Temperature (°C)"] = unit_temp_c

        unit_state = data.get("env_unit_temp_state")
        if unit_state is not None:
            # Mapping verified by user
            state_map = {
                1: "GOOD",
                2: "WARNING",
                3: "CRITICAL",
                4: "SHUTDOWN",
                5: "NOT PRESENT",
                6: "NOT FUNCTIONING",
            }
            try:
                unit_state_i = int(unit_state)
            except Exception:
                unit_state_i = None
            if unit_state_i is not None:
                attrs["System Temperature Status"] = state_map.get(unit_state_i, str(unit_state_i))

        # Fans / PSUs / Temperatures
        # NOTE: Always read refreshed values from coordinator.data
        fans_rpm = data.get("env_fans_rpm") or {}
        for idx, rpm in sorted(fans_rpm.items(), key=lambda x: int(x[0])):
            attrs[f"Fan {idx} (RPM)"] = rpm

        fans_status = data.get("env_fans_status") or {}
        for idx, st in sorted(fans_status.items(), key=lambda x: int(x[0])):
            attrs[f"Fan {idx} Status"] = "OK" if int(st) == 2 else st

        psu_status = data.get("env_psu_status") or {}
        for idx, st in sorted(psu_status.items(), key=lambda x: int(x[0])):
            try:
                st_i = int(st)
            except Exception:
                continue
            # Some Dell variants use 1 for OK, others use 2.
            psu_map = {
                1: "OK",
                2: "OK",
                3: "FAILED",
                4: "SHUTDOWN",
                5: "NOT PRESENT",
                6: "NOT FUNCTIONING",
            }
            attrs[f"PSU {idx} Status"] = psu_map.get(st_i, str(st_i))

        temps_c = data.get("env_temps_c") or {}
        from .temperature import env_temp_label
        for idx, temp in sorted(temps_c.items(), key=lambda x: int(x[0])):
            label = env_temp_label(int(idx))
            attrs[f"{label} (°C)"] = temp

        return attrs


class EnvironmentSystemPowerSensor(CoordinatorEntity, SensorEntity):
    """Device-level system power sensor (W). Used when Environment mode is Sensors."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    # Use native_unit_of_measurement so HA validates correctly for POWER device_class.
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, device_info: DeviceInfo, host_label: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._device_info = device_info
        self._host_label = host_label
        self._attr_unique_id = f"{entry.entry_id}-env-system-power"

    @property
    def device_info(self):
        return self._device_info

    @property
    def name(self) -> str:
        return f"{self._host_label} System (W)"

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        total_mw = data.get("env_power_mw_total") or 0.0
        try:
            return round(float(total_mw) / 1000.0, 1)
        except Exception:
            return None


class EnvironmentFanRpmSensor(CoordinatorEntity, SensorEntity):
    """Fan speed sensor (RPM)."""

    _attr_native_unit_of_measurement = "RPM"
    _attr_icon = "mdi:speedometer"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, idx: int, device_info: DeviceInfo, host_label: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._idx = idx
        self._device_info = device_info
        self._host_label = host_label
        self._attr_unique_id = f"{entry.entry_id}-env-fan-{idx}-rpm"

    @property
    def device_info(self):
        return self._device_info

    @property
    def name(self) -> str:
        return f"{self._host_label} Fan {self._idx + 1} Speed"

    @property
    def native_value(self):
        fans = (self.coordinator.data or {}).get("env_fans_rpm") or {}
        val = fans.get(self._idx)
        try:
            return int(val) if val is not None else None
        except Exception:
            return None


class EnvironmentOkStatusSensor(CoordinatorEntity, SensorEntity):
    """Simple OK/Not OK status sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator,
        entry,
        kind: str,
        idx: int,
        source_key: str,
        name_prefix: str,
        device_info: DeviceInfo,
        host_label: str,
        label: str | None = None,
        icon: str | None = None,
        **_: Any,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._kind = kind
        self._idx = idx
        self._source_key = source_key
        self._name_prefix = name_prefix
        self._device_info = device_info
        self._host_label = host_label
        self._label = label
        self._icon = icon
        self._attr_unique_id = f"{entry.entry_id}-env-{kind}-{idx}-status"

    @property
    def device_info(self):
        return self._device_info

    @property
    def name(self) -> str:
        if getattr(self, "_label", None):
            return f"{self._host_label} {self._label}"
        return f"{self._host_label} {self._name_prefix} {self._idx + 1} Status"

    @property
    def icon(self) -> str | None:
        return getattr(self, "_icon", None)

    @property
    def native_value(self):
        d = (self.coordinator.data or {}).get(self._source_key) or {}
        val = d.get(self._idx)
        if val is None:
            return None
        try:
            return "OK" if int(val) == 2 else "NOT OK"
        except Exception:
            return None


class EnvironmentFanStatusSensor(EnvironmentOkStatusSensor):
    """Fan status sensor (2 == OK)."""

    def __init__(self, coordinator, entry, device_info: DeviceInfo, host_label: str, idx: int) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            kind="fan",
            name_prefix="Fan",
            device_info=device_info,
            host_label=host_label,
            source_key="env_fans_status",
            idx=idx,
            label=f"Fan {idx + 1} Status",
            icon="mdi:fan",
        )


class EnvironmentPsuStatusSensor(EnvironmentOkStatusSensor):
    """PSU status sensor (2 == OK)."""

    def __init__(self, coordinator, entry, device_info: DeviceInfo, host_label: str, idx: int) -> None:
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            kind="psu",
            name_prefix="PSU",
            device_info=device_info,
            host_label=host_label,
            source_key="env_psu_status",
            idx=idx,
            label=f"PSU {idx + 1} Status",
            icon="mdi:power-plug",
        )

    @property
    def native_value(self):
        d = (self.coordinator.data or {}).get(self._source_key) or {}
        val = d.get(self._idx)
        if val is None:
            return None
        try:
            st_i = int(val)
        except Exception:
            return None
        psu_map = {
            1: "OK",
            2: "OK",
            3: "FAILED",
            4: "SHUTDOWN",
            5: "NOT PRESENT",
            6: "NOT FUNCTIONING",
        }
        return psu_map.get(st_i, str(st_i))
