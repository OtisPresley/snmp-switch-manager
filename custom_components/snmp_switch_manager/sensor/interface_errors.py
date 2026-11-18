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

_METRIC_META: dict[str, tuple[str, str, str, str]] = {
    "rx_errors": ("RX Errors", "errors", CONF_IF_ERRORS_RX_ICON, "mdi:alert-circle-outline"),
    "tx_errors": ("TX Errors", "errors", CONF_IF_ERRORS_TX_ICON, "mdi:alert-circle-outline"),
    "rx_discards": ("RX Discards", "packets", CONF_IF_ERRORS_RX_DISCARDS_ICON, "mdi:package-variant-closed-remove"),
    "tx_discards": ("TX Discards", "packets", CONF_IF_ERRORS_TX_DISCARDS_ICON, "mdi:package-variant-closed-remove"),
}


class InterfaceErrorSensor(CoordinatorEntity, SensorEntity):
    """Cumulative per-interface error or discard counter sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
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
        super().__init__(coordinator)
        self._entry = entry
        self._if_index = int(if_index)
        self._metric = metric
        self._device_info = device_info
        self._host_label = host_label

        label, unit, icon_opt_key, default_icon = _METRIC_META[metric]
        self._label = label
        self._attr_native_unit_of_measurement = unit
        ov = (entry.options.get(icon_opt_key) or "").strip()
        self._attr_icon = ov or default_icon
        self._attr_unique_id = f"{entry.entry_id}-iferr-{self._if_index}-{metric}"

    @property
    def device_info(self) -> DeviceInfo:
        return self._device_info

    @property
    def name(self) -> str:
        row = (self.coordinator.data.get("ifTable", {}) or {}).get(self._if_index, {}) or {}
        if_name = str(row.get("name") or f"ifIndex {self._if_index}").strip()
        return f"{if_name} {self._label}"

    @property
    def native_value(self) -> int | None:
        row = (self.coordinator.data.get("interface_errors", {}) or {}).get(self._if_index, {}) or {}
        val = row.get(self._metric)
        if val is None:
            return None
        try:
            return int(val)
        except Exception:
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        iface = (self.coordinator.data.get("ifTable", {}) or {}).get(self._if_index, {}) or {}
        row = (self.coordinator.data.get("interface_errors", {}) or {}).get(self._if_index, {}) or {}
        attrs: dict[str, Any] = {
            "if_index": self._if_index,
            "metric": self._metric,
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
