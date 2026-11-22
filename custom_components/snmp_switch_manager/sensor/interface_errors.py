"""Interface error and discard counter sensors."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import (
    CONF_IF_ERRORS_RX_DISCARDS_ICON,
    CONF_IF_ERRORS_RX_ICON,
    CONF_IF_ERRORS_TX_DISCARDS_ICON,
    CONF_IF_ERRORS_TX_ICON,
)

# metric -> (label, total_unit, rate_unit, icon_opt_key, default_icon)
_METRIC_META: dict[str, tuple[str, str, str, str, str]] = {
    "rx_errors": ("RX Errors", "errors", "errors/s", CONF_IF_ERRORS_RX_ICON, "mdi:alert-circle-outline"),
    "tx_errors": ("TX Errors", "errors", "errors/s", CONF_IF_ERRORS_TX_ICON, "mdi:alert-circle-outline"),
    "rx_discards": ("RX Discards", "packets", "packets/s", CONF_IF_ERRORS_RX_DISCARDS_ICON, "mdi:package-variant-closed-remove"),
    "tx_discards": ("TX Discards", "packets", "packets/s", CONF_IF_ERRORS_TX_DISCARDS_ICON, "mdi:package-variant-closed-remove"),
}


class _InterfaceErrorBase(CoordinatorEntity, SensorEntity):
    """Shared base for per-interface error/discard total and rate sensors."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        entry,
        if_index: int,
        metric: str,
        device_info: DeviceInfo,
        host_label: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._if_index = int(if_index)
        self._metric = metric
        self._device_info = device_info
        self._host_label = host_label

        label, _total_unit, _rate_unit, icon_opt_key, default_icon = _METRIC_META[metric]
        self._label = label
        ov = (entry.options.get(icon_opt_key) or "").strip()
        self._attr_icon = ov or default_icon

    @property
    def device_info(self) -> DeviceInfo:
        return self._device_info

    def _if_name(self) -> str:
        row = (self.coordinator.data.get("ifTable", {}) or {}).get(self._if_index, {}) or {}
        return str(row.get("name") or f"ifIndex {self._if_index}").strip()

    def _err_row(self) -> dict[str, Any]:
        return (self.coordinator.data.get("interface_errors", {}) or {}).get(self._if_index, {}) or {}

    def _base_attributes(self, kind: str) -> dict[str, Any]:
        iface = (self.coordinator.data.get("ifTable", {}) or {}).get(self._if_index, {}) or {}
        row = self._err_row()
        attrs: dict[str, Any] = {
            "if_index": self._if_index,
            "metric": self._metric,
            "kind": kind,
            "status": iface.get("status"),
            "manufacturer": self.coordinator.data.get("manufacturer"),
            "model": self.coordinator.data.get("model"),
        }
        if "ts" in row:
            try:
                attrs["sample_ts"] = float(row["ts"])
            except Exception:
                pass
        return attrs


class InterfaceErrorSensor(_InterfaceErrorBase):
    """Cumulative per-interface error or discard counter sensor."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self,
        coordinator,
        entry,
        if_index: int,
        metric: str,
        device_info: DeviceInfo,
        host_label: str,
    ) -> None:
        super().__init__(coordinator, entry, if_index, metric, device_info, host_label)
        self._attr_native_unit_of_measurement = _METRIC_META[metric][1]
        self._attr_unique_id = f"{entry.entry_id}-iferr-{self._if_index}-{metric}"

    @property
    def name(self) -> str:
        return f"{self._if_name()} {self._label}"

    @property
    def native_value(self) -> int | None:
        val = self._err_row().get(self._metric)
        if val is None:
            return None
        try:
            return int(val)
        except Exception:
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._base_attributes("total")


class InterfaceErrorRateSensor(_InterfaceErrorBase):
    """Per-interface error or discard rate sensor (diff since previous poll / dt)."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator,
        entry,
        if_index: int,
        metric: str,
        device_info: DeviceInfo,
        host_label: str,
    ) -> None:
        super().__init__(coordinator, entry, if_index, metric, device_info, host_label)
        self._attr_native_unit_of_measurement = _METRIC_META[metric][2]
        self._attr_unique_id = f"{entry.entry_id}-iferr-{self._if_index}-{metric}_rate"

    @property
    def name(self) -> str:
        return f"{self._if_name()} {self._label} Rate"

    @property
    def native_value(self) -> float | None:
        val = self._err_row().get(f"{self._metric}_rate")
        if val is None:
            return None
        try:
            return round(float(val), 3)
        except Exception:
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = self._base_attributes("rate")
        delta = self._err_row().get(f"{self._metric}_delta")
        if delta is not None:
            try:
                attrs["delta"] = int(delta)
            except Exception:
                pass
        return attrs
