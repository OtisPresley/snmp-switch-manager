from __future__ import annotations

from typing import Any
from homeassistant.const import EntityCategory
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import (
    CONF_BW_RX_THROUGHPUT_ICON,
    CONF_BW_TX_THROUGHPUT_ICON,
    CONF_BW_RX_TOTAL_ICON,
    CONF_BW_TX_TOTAL_ICON,
)


class _BandwidthBase(CoordinatorEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        entry,
        if_index: int,
        direction: str,
        device_info: DeviceInfo,
        host_label: str,
        icon_rules: list[dict[str, str]] | None = None,
    ):
        super().__init__(coordinator)
        self._entry = entry
        self._if_index = int(if_index)
        self._direction = direction  # "rx" or "tx"
        self._device_info = device_info
        self._host_label = host_label

    @property
    def device_info(self):
        return self._device_info

    @property
    def icon(self) -> str | None:
        """Return the entity icon.

        Bandwidth sensors do NOT use interface icon rules. If a bandwidth icon override
        is configured, it is stored in _attr_icon during __init__.
        """
        return getattr(self, "_attr_icon", None)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Restore attributes for the custom card and plugin UI."""
        # This maps the data from the 'ifTable' you fixed in snmp.py (Line 1032)
        iface = self.coordinator.data.get("ifTable", {}).get(self._if_index, {})

        return {
            "if_index": self._if_index,
            "direction": self._direction,
            "speed_mbps": iface.get("speed_mbps"),
            "calculated_speed": iface.get("speed"),
            "status": iface.get("status"),
            "manufacturer": self.coordinator.data.get("manufacturer"),
            "model": self.coordinator.data.get("model"),
        }

    def _if_name(self) -> str:
        row = self.coordinator.data.get("ifTable", {}).get(self._if_index, {}) or {}
        return str(row.get("name") or f"ifIndex {self._if_index}").strip()

    def _bw_row(self) -> dict:
        return (self.coordinator.data.get("bandwidth", {}) or {}).get(self._if_index, {}) or {}


class BandwidthRateSensor(_BandwidthBase):
    _attr_device_class = SensorDeviceClass.DATA_RATE
    _attr_native_unit_of_measurement = "bit/s"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator,
        entry,
        if_index: int,
        direction: str,
        device_info: DeviceInfo,
        host_label: str,
    ):
        super().__init__(coordinator, entry, if_index, direction, device_info, host_label)
        # Bandwidth icon override (configured separately from interface icon rules)
        if direction == "rx":
            ov = (entry.options.get(CONF_BW_RX_THROUGHPUT_ICON) or "").strip()
        else:
            ov = (entry.options.get(CONF_BW_TX_THROUGHPUT_ICON) or "").strip()
        if ov:
            self._attr_icon = ov
        self._attr_unique_id = f"{entry.entry_id}-bw-{self._if_index}-{direction}_bps"

    @property
    def name(self) -> str:
        label = "RX" if self._direction == "rx" else "TX"
        # IMPORTANT: _BandwidthBase uses _attr_has_entity_name = True.
        # Home Assistant will automatically prefix the entity name (and suggested entity_id)
        # with the device name. Therefore, the per-entity name MUST NOT include host/device
        # labels, otherwise the hostname appears twice in the suggested entity_id.
        return f"{self._if_name()} {label} Throughput"

    @property
    def native_value(self):
        row = self._bw_row()
        key = "rx_bps" if self._direction == "rx" else "tx_bps"
        val = row.get(key)
        if val is None:
            return None
        try:
            return int(round(float(val)))
        except Exception:
            return None

    @property
    def extra_state_attributes(self):
        attrs = dict(super().extra_state_attributes)
        attrs["kind"] = "throughput"
        row = self._bw_row()
        if "use_hc" in row:
            attrs["use_hc"] = bool(row.get("use_hc"))
        if "ts" in row:
            try:
                attrs["sample_ts"] = float(row.get("ts"))
            except Exception:
                pass
        return attrs


class BandwidthTotalSensor(_BandwidthBase):
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_native_unit_of_measurement = "B"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self,
        coordinator,
        entry,
        if_index: int,
        direction: str,
        device_info: DeviceInfo,
        host_label: str,
    ):
        super().__init__(coordinator, entry, if_index, direction, device_info, host_label)
        # Bandwidth icon override (configured separately from interface icon rules)
        if direction == "rx":
            ov = (entry.options.get(CONF_BW_RX_TOTAL_ICON) or "").strip()
        else:
            ov = (entry.options.get(CONF_BW_TX_TOTAL_ICON) or "").strip()
        if ov:
            self._attr_icon = ov
        self._attr_unique_id = f"{entry.entry_id}-bw-{self._if_index}-{direction}_bytes_total"

    @property
    def name(self) -> str:
        label = "RX" if self._direction == "rx" else "TX"
        # See BandwidthRateSensor.name() for why we do not include the host label here.
        return f"{self._if_name()} {label} Total"

    @property
    def native_value(self):
        row = self._bw_row()
        key = "rx_octets" if self._direction == "rx" else "tx_octets"
        val = row.get(key)
        if val is None:
            return None
        try:
            return int(val)
        except Exception:
            return None

    @property
    def extra_state_attributes(self):
        attrs = dict(super().extra_state_attributes)
        attrs["kind"] = "total"
        row = self._bw_row()
        if "use_hc" in row:
            attrs["use_hc"] = bool(row.get("use_hc"))
        if "ts" in row:
            try:
                attrs["sample_ts"] = float(row.get("ts"))
            except Exception:
                pass
        return attrs
