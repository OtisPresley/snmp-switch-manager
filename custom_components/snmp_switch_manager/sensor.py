from __future__ import annotations

import logging
from homeassistant.util import slugify
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass

from .const import DOMAIN, CONF_BW_ENABLE, CONF_BW_INCLUDE_STARTS_WITH, CONF_BW_INCLUDE_CONTAINS, CONF_BW_INCLUDE_ENDS_WITH, CONF_BW_EXCLUDE_STARTS_WITH, CONF_BW_EXCLUDE_CONTAINS, CONF_BW_EXCLUDE_ENDS_WITH
from .snmp import SwitchSnmpClient

_LOGGER = logging.getLogger(__name__)

SENSOR_TYPES = {
    "manufacturer": "Manufacturer",
    "model": "Model",
    "firmware": "Firmware Revision",
    "uptime": "Uptime",
    "hostname": "Hostname",
}

async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    client: SwitchSnmpClient = data["client"]
    coordinator = data["coordinator"]

    # Prefer parsed values placed in cache by snmp.py
    manufacturer = client.cache.get("manufacturer") or "Unknown"
    model = client.cache.get("model") or "Unknown"
    firmware = client.cache.get("firmware") or "Unknown"

    hostname = client.cache.get("sysName")
    host_label = hostname or entry.data.get("name") or client.host
    uptime_ticks = client.cache.get("sysUpTime")

    # Convert sysUpTime (hundredths of seconds) to human string
    def _uptime_human(ticks):
        try:
            t = int(ticks)
            sec = t // 100
            d, r = divmod(sec, 86400)
            h, r = divmod(r, 3600)
            m, s = divmod(r, 60)
            return f"{d}d {h}h {m}m {s}s"
        except Exception:
            return str(ticks) if ticks is not None else "Unknown"

    device_info = DeviceInfo(
        identifiers={(DOMAIN, f"{client.host}:{client.port}:{client.community}")},
        manufacturer=manufacturer if manufacturer != "Unknown" else None,
        model=model if model != "Unknown" else None,
        sw_version=firmware if firmware != "Unknown" else None,
        name=host_label,
    )

    entities = [
        SimpleTextSensor(coordinator, entry, "manufacturer", manufacturer, device_info, host_label),
        SimpleTextSensor(coordinator, entry, "model", model, device_info, host_label),
        SimpleTextSensor(coordinator, entry, "firmware", firmware, device_info, host_label),
        SimpleTextSensor(coordinator, entry, "uptime", _uptime_human(uptime_ticks), device_info, host_label),
        SimpleTextSensor(coordinator, entry, "hostname", hostname or client.host, device_info, host_label),
    ]

    # Bandwidth sensor entities (optional; per-device)
    ent_reg = er.async_get(hass)

    bw_enabled = bool(entry.options.get(CONF_BW_ENABLE, False))
    desired_bw_unique_ids: set[str] = set()
    bw_entities: list[SensorEntity] = []

    if bw_enabled:
        iftable = coordinator.data.get("ifTable", {}) or {}

        # Only create bandwidth sensors for interfaces that are eligible under the integration's
        # built-in vendor interface selection rules.
        #
        # IMPORTANT: Bandwidth rules must be independent from the Interface Include Rules.
        # Interface Include Rules are allowed to *add* interface entities beyond vendor defaults,
        # but bandwidth sensors should not be auto-created for those extra interfaces unless the
        # user explicitly includes them via Bandwidth Sensors/Include Rules.
        #
        # We therefore compute a vendor-eligible ifIndex set here (mirroring switch.py vendor logic,
        # but intentionally NOT honoring interface include rules).
        allowed_if_indexes: set[int] = set()

        ip_index = client.cache.get("ipIndex", {}) or {}
        ip_mask = client.cache.get("ipMask", {}) or {}
        disabled_vendor_filter_ids = set(entry.options.get("disabled_vendor_filter_rule_ids", []) or [])

        manufacturer_l = (client.cache.get("manufacturer") or "").lower()
        sys_descr_l = (client.cache.get("sysDescr") or "").lower()
        is_cisco_sg = manufacturer_l.startswith("sg") and sys_descr_l.startswith("sg")
        is_junos = ("juniper" in manufacturer_l) or ("junos" in sys_descr_l) or ("ex2200" in sys_descr_l)

        def _ip_for_index(if_index: int) -> str | None:
            # Match switch.py behavior: return "<ip>/<maskbits>" if present for this ifIndex
            try:
                for ip, idx in (ip_index or {}).items():
                    if int(idx) == int(if_index):
                        mask = str((ip_mask or {}).get(ip) or "")
                        bits = 0
                        if mask:
                            # Convert dotted quad to mask bits
                            parts = [int(p) for p in mask.split(".") if p.isdigit()]
                            if len(parts) == 4:
                                bits = sum(bin(p).count("1") for p in parts)
                        return f"{ip}/{bits}" if bits else str(ip)
            except Exception:
                return None
            return None

        for idx_i, row in (iftable or {}).items():
            try:
                idx_i = int(idx_i)
            except Exception:
                continue

            raw_name = str(row.get("name") or row.get("descr") or f"if{idx_i}").strip()
            alias = str(row.get("alias") or "")
            if not raw_name:
                continue

            # Skip internal CPU pseudo-interface
            if raw_name.upper() == "CPU":
                continue

            lower = raw_name.lower()
            ip_str = _ip_for_index(idx_i)

            # Mirror switch.py PortChannel gating (avoid pointless Po/Port-Channel entities/sensors)
            is_port_channel = lower.startswith("po") or lower.startswith("port-channel") or lower.startswith("link aggregate")
            if is_port_channel and not (ip_str or alias):
                continue

            admin = row.get("admin")
            oper = row.get("oper")
            has_ip = bool(ip_str)
            include = True  # default for unknown vendors

            if is_cisco_sg:
                enable_physical = "cisco_sg_physical_fa_gi" not in disabled_vendor_filter_ids
                enable_vlan = "cisco_sg_vlan_admin_or_oper" not in disabled_vendor_filter_ids
                enable_has_ip = "cisco_sg_other_has_ip" not in disabled_vendor_filter_ids
                include = False

                if enable_physical and (lower.startswith("fa") or lower.startswith("gi")):
                    include = True
                elif enable_vlan and lower.startswith("vlan"):
                    if oper == 1 or admin == 2:
                        include = True
                elif enable_has_ip and has_ip:
                    include = True

            elif is_junos:
                enable_physical = "junos_physical_ge" not in disabled_vendor_filter_ids
                enable_l3_subif = "junos_l3_subif_has_ip" not in disabled_vendor_filter_ids
                enable_vlan = "junos_vlan_admin_or_oper" not in disabled_vendor_filter_ids
                enable_has_ip = "junos_other_has_ip" not in disabled_vendor_filter_ids
                include = False

                if enable_physical and lower.startswith("ge-") and "." not in raw_name:
                    include = True
                elif enable_l3_subif and lower.startswith("ge-") and "." in raw_name:
                    try:
                        _base, sub = raw_name.split(".", 1)
                        if sub != "0" and has_ip:
                            include = True
                    except Exception:
                        pass
                elif enable_vlan and lower.startswith("vlan"):
                    if oper == 1 or admin == 2:
                        include = True
                elif enable_has_ip and has_ip:
                    include = True

            if include:
                allowed_if_indexes.add(idx_i)

        def _clean_list(key: str) -> list[str]:
            return [str(s).strip().lower() for s in (entry.options.get(key, []) or []) if str(s).strip()]

        include_starts = _clean_list(CONF_BW_INCLUDE_STARTS_WITH)
        include_contains = _clean_list(CONF_BW_INCLUDE_CONTAINS)
        include_ends = _clean_list(CONF_BW_INCLUDE_ENDS_WITH)
        exclude_starts = _clean_list(CONF_BW_EXCLUDE_STARTS_WITH)
        exclude_contains = _clean_list(CONF_BW_EXCLUDE_CONTAINS)
        exclude_ends = _clean_list(CONF_BW_EXCLUDE_ENDS_WITH)

        def _matches_any(name_l: str, starts: list[str], contains: list[str], ends: list[str]) -> bool:
            return (
                any(name_l.startswith(x) for x in starts)
                or any(x in name_l for x in contains)
                or any(name_l.endswith(x) for x in ends)
            )

        selected_indexes: list[int] = []
        for if_index, row in iftable.items():
            try:
                idx_i = int(if_index)
            except Exception:
                continue
            if idx_i not in allowed_if_indexes:
                continue

            raw_name = str(row.get("name") or "").strip()
            if not raw_name:
                continue
            nl = raw_name.lower()
            include_hit = _matches_any(nl, include_starts, include_contains, include_ends)
            exclude_hit = _matches_any(nl, exclude_starts, exclude_contains, exclude_ends)

            if (include_starts or include_contains or include_ends) and not include_hit:
                continue
            if exclude_hit:
                continue

            selected_indexes.append(idx_i)

        for idx_i in selected_indexes:
            base = f"{entry.entry_id}-bw-{idx_i}"
            bw_entities.extend(
                [
                    BandwidthRateSensor(coordinator, entry, idx_i, "rx", device_info, host_label),
                    BandwidthRateSensor(coordinator, entry, idx_i, "tx", device_info, host_label),
                    BandwidthTotalSensor(coordinator, entry, idx_i, "rx", device_info, host_label),
                    BandwidthTotalSensor(coordinator, entry, idx_i, "tx", device_info, host_label),
                ]
            )
            desired_bw_unique_ids.update(
                {
                    f"{base}-rx_bps",
                    f"{base}-tx_bps",
                    f"{base}-rx_bytes_total",
                    f"{base}-tx_bytes_total",
                }
            )

    # Remove stale bandwidth sensor entities (or all if disabled)
    # Also remove legacy entity_ids that were generated without the device prefix
    # so they get recreated with the corrected object_id.
    device_slug = slugify(host_label)
    # Also remove any legacy bandwidth sensors created by earlier versions that may have
    # different unique_id patterns, but still belong to this config entry.
    # We identify them by entity_id naming (no device prefix or double prefix) and the
    # trailing bandwidth suffixes.
    legacy_suffixes = (
        "_rx_throughput",
        "_tx_throughput",
        "_rx_total",
        "_tx_total",
        "_rx_bps",
        "_tx_bps",
        "_rx_bytes_total",
        "_tx_bytes_total",
    )
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if ent.domain != "sensor":
            continue

        uid = ent.unique_id or ""
        eid = ent.entity_id or ""

        # Primary (current) bandwidth sensors are identified by unique_id prefix.
        is_bw_uid = uid.startswith(f"{entry.entry_id}-bw-")

        # Legacy bandwidth sensors may have different unique_id patterns; detect by entity_id suffix.
        is_bw_legacy_eid = eid.endswith(legacy_suffixes)

        if not (is_bw_uid or is_bw_legacy_eid):
            continue

        legacy_bad_name = device_slug and (not eid.startswith(f"sensor.{device_slug}_"))
        legacy_double_prefix = device_slug and eid.startswith(f"sensor.{device_slug}_{device_slug}_")

        # If the entity_id naming is wrong, remove so HA can recreate it with the corrected object_id.
        if legacy_bad_name or legacy_double_prefix:
            ent_reg.async_remove(eid)
            continue

        # If bandwidth sensors are disabled or this interface is no longer selected, remove.
        if is_bw_uid:
            if (not bw_enabled) or (uid not in desired_bw_unique_ids):
                ent_reg.async_remove(eid)
        else:
            # Legacy entities without expected unique_id should be removed when disabled.
            if not bw_enabled:
                ent_reg.async_remove(eid)


    entities.extend(bw_entities)

    async_add_entities(entities)


class SimpleTextSensor(CoordinatorEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, key, value, device_info: DeviceInfo, hostname: str):
        super().__init__(coordinator)
        self._key = key
        self._value = value
        self._hostname = hostname
        self._attr_unique_id = f"{entry.entry_id}-{key}"
        # Include hostname so entity_id becomes e.g. sensor.switch1_firmware_revision
        self._attr_name = f"{hostname} {SENSOR_TYPES[key]}"
        self._attr_device_info = device_info

    @property
    def native_value(self):
        data = self.coordinator.data
        if self._key == "hostname":
            return data.get("sysName") or self._value
        if self._key == "uptime":
            ticks = data.get("sysUpTime")
            try:
                t = int(ticks)
                sec = t // 100
                d, r = divmod(sec, 86400)
                h, r = divmod(r, 3600)
                m, s = divmod(r, 60)
                return f"{d}d {h}h {m}m {s}s"
            except Exception:
                return str(ticks)
        # prefer parsed cache values if present
        if self._key == "manufacturer":
            return data.get("manufacturer") or self._value
        if self._key == "model":
            return data.get("model") or self._value
        if self._key == "firmware":
            return data.get("firmware") or self._value
        return self._value



class _BandwidthBase(CoordinatorEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, if_index: int, direction: str, device_info: DeviceInfo, host_label: str):
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
    def extra_state_attributes(self):
        return {
            "if_index": self._if_index,
            "direction": self._direction,
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

    def __init__(self, coordinator, entry, if_index: int, direction: str, device_info: DeviceInfo, host_label: str):
        super().__init__(coordinator, entry, if_index, direction, device_info, host_label)
        self._attr_unique_id = f"{entry.entry_id}-bw-{self._if_index}-{direction}_bps"

    @property
    def name(self) -> str:
        label = "RX" if self._direction == "rx" else "TX"
        # Include the device label to ensure entity_id uniqueness matches other entities
        # (e.g. sensor.switch_study_gi1_0_1_rx_throughput)
        return f"{self._host_label} {self._if_name()} {label} Throughput"

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

    def __init__(self, coordinator, entry, if_index: int, direction: str, device_info: DeviceInfo, host_label: str):
        super().__init__(coordinator, entry, if_index, direction, device_info, host_label)
        self._attr_unique_id = f"{entry.entry_id}-bw-{self._if_index}-{direction}_bytes_total"

    @property
    def name(self) -> str:
        label = "RX" if self._direction == "rx" else "TX"
        return f"{self._host_label} {self._if_name()} {label} Total"

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
