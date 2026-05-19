from __future__ import annotations

import logging
from homeassistant.util import slugify
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import SensorEntity

from ..const import (
    DOMAIN,
    CONF_LEGACY_DEVICE_ID,
    CONF_BW_ENABLE,
    CONF_BW_MODE,
    BW_MODE_SENSORS,
    BW_MODE_ATTRIBUTES,
    CONF_BW_INCLUDE_STARTS_WITH,
    CONF_BW_INCLUDE_CONTAINS,
    CONF_BW_INCLUDE_ENDS_WITH,
    CONF_BW_EXCLUDE_STARTS_WITH,
    CONF_BW_EXCLUDE_CONTAINS,
    CONF_BW_EXCLUDE_ENDS_WITH,
    CONF_POE_ENABLE,
    CONF_POE_MODE,
    CONF_POE_PER_PORT_POWER,
    POE_MODE_ATTRIBUTES,
    POE_MODE_SENSORS,
    CONF_ENV_ENABLE,
    CONF_ENV_MODE,
    ENV_MODE_ATTRIBUTES,
    ENV_MODE_SENSORS,
)
from ..snmp import SwitchSnmpClient
from ..helpers import check_vendor_interface_rules, uptime_human

from .bandwidth import BandwidthRateSensor, BandwidthTotalSensor
from .environmental import (
    EnvironmentPowerSensor,
    EnvironmentSystemPowerSensor,
    EnvironmentFanRpmSensor,
    EnvironmentFanStatusSensor,
    EnvironmentPsuStatusSensor,
)
from .cpu_memory import (
    EnvironmentCpuUtilSensor,
    EnvironmentMemoryValueSensor,
    EnvironmentMemoryUsedPercentSensor,
)
from .temperature import (
    EnvironmentTemperatureSensor,
    EnvironmentUnitTemperatureSensor,
    EnvironmentUnitTempStateSensor,
)
from .poe import (
    PoEPowerSensor,
    PoEAggregateSensor,
    PoEBudgetTotalSensor,
    PoEPowerUsedSensor,
    PoEPowerAvailableSensor,
    PoEHealthStatusSensor,
)

_LOGGER = logging.getLogger(__name__)

SENSOR_TYPES = {
    "manufacturer": "Manufacturer",
    "model": "Model",
    "firmware": "Firmware Revision",
    "uptime": "Uptime",
    "hostname": "Hostname",
}


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = entry.runtime_data
    client: SwitchSnmpClient = runtime.client
    coordinator = runtime.coordinator

    coord_data = coordinator.data or {}

    # Prefer parsed values placed in cache by snmp.py
    manufacturer = client.cache.get("manufacturer") or "Unknown"
    model = client.cache.get("model") or "Unknown"
    firmware = client.cache.get("firmware") or "Unknown"

    hostname = client.cache.get("sysName")
    host_label = hostname or entry.data.get("name") or client.host
    uptime_ticks = client.cache.get("sysUpTime")

    # Device identifiers must be stable.
    identifiers = {(DOMAIN, entry.entry_id)}
    legacy_device_id = str(
        entry.data.get(CONF_LEGACY_DEVICE_ID) or entry.options.get(CONF_LEGACY_DEVICE_ID) or ""
    ).strip()
    if legacy_device_id:
        identifiers.add((DOMAIN, legacy_device_id))

    device_info = DeviceInfo(
        identifiers=identifiers,
        manufacturer=manufacturer if manufacturer != "Unknown" else None,
        model=model if model != "Unknown" else None,
        sw_version=firmware if firmware != "Unknown" else None,
        name=host_label,
    )

    entities = [
        SimpleTextSensor(coordinator, entry, "manufacturer", manufacturer, device_info, host_label),
        SimpleTextSensor(coordinator, entry, "model", model, device_info, host_label),
        SimpleTextSensor(coordinator, entry, "firmware", firmware, device_info, host_label),
        SimpleTextSensor(coordinator, entry, "uptime", uptime_human(uptime_ticks), device_info, host_label),
        SimpleTextSensor(coordinator, entry, "hostname", hostname or client.host, device_info, host_label),
    ]

    # Bandwidth sensor entities (optional; per-device)
    ent_reg = er.async_get(hass)

    bw_enabled = bool(entry.options.get(CONF_BW_ENABLE, False))
    bw_mode = entry.options.get(CONF_BW_MODE, BW_MODE_SENSORS)
    bw_mode = str(bw_mode).strip().lower()
    if bw_mode not in (BW_MODE_SENSORS, BW_MODE_ATTRIBUTES):
        bw_mode = BW_MODE_SENSORS
    bw_entities_enabled = bool(bw_enabled) and (bw_mode == BW_MODE_SENSORS)
    desired_bw_unique_ids: set[str] = set()
    bw_entities: list[SensorEntity] = []

    if bw_entities_enabled:
        iftable = coordinator.data.get("ifTable", {}) or {}
        allowed_if_indexes: set[int] = set()

        ip_index = client.cache.get("ipIndex", {}) or {}
        ip_mask = client.cache.get("ipMask", {}) or {}
        disabled_vendor_filter_ids = set(entry.options.get("disabled_vendor_filter_rule_ids", []) or [])

        manufacturer_l = (client.cache.get("manufacturer") or "").lower()
        sys_descr_l = (client.cache.get("sysDescr") or "").lower()
        is_cisco_sg = manufacturer_l.startswith("sg") and sys_descr_l.startswith("sg")
        is_junos = ("juniper" in manufacturer_l) or ("junos" in sys_descr_l) or ("ex2200" in sys_descr_l)

        ip_by_ifindex = {}
        for ip, idx in ip_index.items():
            try:
                ip_by_ifindex[int(idx)] = ip
            except Exception:
                pass

        def _ip_for_index(if_index: int) -> str | None:
            ip = ip_by_ifindex.get(int(if_index))
            if not ip:
                return None
            mask = str(ip_mask.get(ip) or "")
            if mask:
                try:
                    parts = [int(p) for p in mask.split(".") if p.isdigit()]
                    if len(parts) == 4:
                        bits = sum(bin(p).count("1") for p in parts)
                        return f"{ip}/{bits}"
                except Exception:
                    pass
            return str(ip)

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

            is_port_channel = lower.startswith("po") or lower.startswith("port-channel") or lower.startswith("link aggregate")
            if is_port_channel and not (ip_str or alias):
                continue

            admin = row.get("admin")
            oper = row.get("oper")
            has_ip = bool(ip_str)

            include, _ = check_vendor_interface_rules(
                normalized_name=lower,
                raw_name=raw_name,
                admin=admin,
                oper=oper,
                has_ip=has_ip,
                is_cisco_sg=is_cisco_sg,
                is_junos=is_junos,
                disabled_vendor_filter_ids=disabled_vendor_filter_ids,
            )

            if include:
                allowed_if_indexes.add(idx_i)

        def _clean_list(key: str) -> tuple[str, ...]:
            return tuple(str(s).strip().lower() for s in (entry.options.get(key, []) or []) if str(s).strip())

        include_starts = _clean_list(CONF_BW_INCLUDE_STARTS_WITH)
        include_contains = _clean_list(CONF_BW_INCLUDE_CONTAINS)
        include_ends = _clean_list(CONF_BW_INCLUDE_ENDS_WITH)
        exclude_starts = _clean_list(CONF_BW_EXCLUDE_STARTS_WITH)
        exclude_contains = _clean_list(CONF_BW_EXCLUDE_CONTAINS)
        exclude_ends = _clean_list(CONF_BW_EXCLUDE_ENDS_WITH)

        def _matches_any(name_l: str, starts: tuple[str, ...], contains: tuple[str, ...], ends: tuple[str, ...]) -> bool:
            if starts and name_l.startswith(starts):
                return True
            if ends and name_l.endswith(ends):
                return True
            if contains:
                for x in contains:
                    if x in name_l:
                        return True
            return False

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

    device_slug = slugify(host_label)
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

        is_bw_uid = uid.startswith(f"{entry.entry_id}-bw-")
        is_bw_legacy_eid = eid.endswith(legacy_suffixes)

        if not (is_bw_uid or is_bw_legacy_eid):
            continue

        legacy_bad_name = device_slug and (not eid.startswith(f"sensor.{device_slug}_"))
        legacy_double_prefix = device_slug and eid.startswith(f"sensor.{device_slug}_{device_slug}_")

        if legacy_bad_name or legacy_double_prefix:
            ent_reg.async_remove(eid)
            continue

        if is_bw_uid:
            if (not bw_entities_enabled) or (uid not in desired_bw_unique_ids):
                ent_reg.async_remove(eid)
        else:
            if not bw_entities_enabled:
                ent_reg.async_remove(eid)

    entities.extend(bw_entities)

    # Environmental sensors (optional)
    env_enabled = entry.options.get(CONF_ENV_ENABLE, False)
    env_mode = entry.options.get(CONF_ENV_MODE, ENV_MODE_ATTRIBUTES)

    env_power_uid = f"{entry.entry_id}-env-power"
    env_uid_prefixes = (
        f"{entry.entry_id}-env-",
        f"{entry.entry_id}_env_",
    )
    legacy_env_power_uids = {
        f"{entry.entry_id}_env_power",
        f"{entry.entry_id}_env-power",
    }

    ent_reg = er.async_get(hass)
    for entity_entry in list(er.async_entries_for_config_entry(ent_reg, entry.entry_id)):
        if entity_entry.domain != "sensor" or not entity_entry.unique_id:
            continue

        uid = entity_entry.unique_id
        is_env_uid = uid.startswith(env_uid_prefixes)

        if not env_enabled and is_env_uid:
            ent_reg.async_remove(entity_entry.entity_id)
            continue

        if not env_enabled:
            continue

        if env_mode == ENV_MODE_ATTRIBUTES and is_env_uid:
            if uid != env_power_uid:
                ent_reg.async_remove(entity_entry.entity_id)
            continue

        if env_mode == ENV_MODE_SENSORS and (uid == env_power_uid or uid in legacy_env_power_uids):
            ent_reg.async_remove(entity_entry.entity_id)

    if env_enabled and env_mode == ENV_MODE_ATTRIBUTES:
        entities.append(EnvironmentPowerSensor(coordinator, entry, device_info, host_label))
    elif env_enabled and env_mode == ENV_MODE_SENSORS:
        entities.append(EnvironmentSystemPowerSensor(coordinator, entry, device_info, host_label))
        if coord_data.get("env_cpu_5s") is not None:
            entities.append(EnvironmentCpuUtilSensor(coordinator, entry, device_info, host_label, "5s"))
        if coord_data.get("env_cpu_60s") is not None:
            entities.append(EnvironmentCpuUtilSensor(coordinator, entry, device_info, host_label, "60s"))
        if coord_data.get("env_cpu_300s") is not None:
            entities.append(EnvironmentCpuUtilSensor(coordinator, entry, device_info, host_label, "300s"))

        if (coord_data.get("env_mem_available_kb") is not None) or (coord_data.get("env_mem_free_kb") is not None):
            entities.append(EnvironmentMemoryValueSensor(coordinator, entry, device_info, host_label, "available"))
        if coord_data.get("env_mem_total_kb") is not None:
            entities.append(EnvironmentMemoryValueSensor(coordinator, entry, device_info, host_label, "total"))
        if (coord_data.get("env_mem_total_kb") is not None) and (
            (coord_data.get("env_mem_available_kb") is not None) or (coord_data.get("env_mem_free_kb") is not None)
        ):
            entities.append(EnvironmentMemoryUsedPercentSensor(coordinator, entry, device_info, host_label))

        fan_rpm = coord_data.get("env_fans_rpm") or {}
        fan_status = coord_data.get("env_fans_status") or {}
        fan_indices = sorted({int(i) for i in list(fan_rpm.keys()) + list(fan_status.keys())})
        for idx in fan_indices:
            entities.append(EnvironmentFanRpmSensor(coordinator, entry, idx, device_info, host_label))
            entities.append(EnvironmentFanStatusSensor(coordinator, entry, device_info, host_label, idx))

        psu_status = coord_data.get("env_psu_status") or {}
        psu_indices = sorted({int(i) for i in psu_status.keys()})
        for idx in psu_indices:
            entities.append(EnvironmentPsuStatusSensor(coordinator, entry, device_info, host_label, idx))

        temps_c = coord_data.get("env_temps_c") or {}
        try:
            temp_indexes = sorted({int(i) for i in temps_c.keys()})
        except Exception:
            temp_indexes = []
        for idx in temp_indexes:
            entities.append(EnvironmentTemperatureSensor(coordinator, entry, idx, device_info, host_label))

        if coord_data.get("env_unit_temp_c") is not None:
            entities.append(EnvironmentUnitTemperatureSensor(coordinator, entry, device_info, host_label))
        if coord_data.get("env_unit_temp_state") is not None:
            entities.append(EnvironmentUnitTempStateSensor(coordinator, entry, device_info, host_label))

    if env_enabled and env_mode == ENV_MODE_SENSORS:
        try:
            desired_env_uids = {e.unique_id for e in entities if getattr(e, "unique_id", None)}
            for entity_entry in list(er.async_entries_for_config_entry(ent_reg, entry.entry_id)):
                if entity_entry.domain != "sensor" or not entity_entry.unique_id:
                    continue
                uid = entity_entry.unique_id
                is_env_uid = uid.startswith(env_uid_prefixes)
                if is_env_uid and uid not in desired_env_uids:
                    ent_reg.async_remove(entity_entry.entity_id)
        except Exception:
            pass

    # PoE sensors (optional)
    poe_enabled_opt = entry.options.get(CONF_POE_ENABLE, False)
    poe_mode_opt = entry.options.get(CONF_POE_MODE, POE_MODE_ATTRIBUTES)
    poe_per_port_opt = entry.options.get(CONF_POE_PER_PORT_POWER, False)

    poe_uid_prefixes = (
        f"{entry.entry_id}-poe-",
        f"{entry.entry_id}_poe_",
    )
    poe_aggregate_uid = f"{entry.entry_id}-poe"

    poe_budget_w = coord_data.get("poe_budget_total_w")
    poe_used_w = coord_data.get("poe_power_used_w")
    poe_avail_w = coord_data.get("poe_power_available_w")
    poe_health = coord_data.get("poe_health_status")
    poe_power_mw = coord_data.get("poe_power_mw") or {}
    poe_supported = any(v is not None for v in (poe_budget_w, poe_used_w, poe_avail_w, poe_health)) or bool(poe_power_mw)

    if (not poe_enabled_opt) or (not poe_supported):
        for entity_entry in list(er.async_entries_for_config_entry(ent_reg, entry.entry_id)):
            if entity_entry.domain != "sensor" or not entity_entry.unique_id:
                continue
            uid = entity_entry.unique_id
            if uid.startswith(poe_uid_prefixes) or uid == poe_aggregate_uid:
                ent_reg.async_remove(entity_entry.entity_id)
    else:
        if poe_mode_opt == POE_MODE_ATTRIBUTES:
            entities.append(PoEAggregateSensor(coordinator, entry, device_info, host_label))
        elif poe_mode_opt == POE_MODE_SENSORS:
            if poe_budget_w is not None:
                entities.append(PoEBudgetTotalSensor(coordinator, entry, device_info, host_label))
            if poe_used_w is not None:
                entities.append(PoEPowerUsedSensor(coordinator, entry, device_info, host_label))
            if poe_avail_w is not None:
                entities.append(PoEPowerAvailableSensor(coordinator, entry, device_info, host_label))
            if poe_health is not None:
                entities.append(PoEHealthStatusSensor(coordinator, entry, device_info, host_label))
            if poe_per_port_opt:
                if_table = coordinator.data.get("ifTable") or {}
                for if_idx, row in (if_table or {}).items():
                    try:
                        if_idx_i = int(if_idx)
                    except Exception:
                        continue
                    port_type = str((row or {}).get("port_type") or "").lower()
                    if port_type != "physical":
                        continue
                    if if_idx_i not in poe_power_mw:
                        continue
                    entities.append(PoEPowerSensor(coordinator, entry, if_idx_i, device_info, host_label))

        try:
            desired_poe_uids = {
                e.unique_id
                for e in entities
                if getattr(e, "unique_id", None)
                and (
                    str(e.unique_id).startswith(f"{entry.entry_id}-poe")
                    or str(e.unique_id).startswith(f"{entry.entry_id}_poe")
                )
            }
            if poe_mode_opt == POE_MODE_ATTRIBUTES:
                desired_poe_uids.add(poe_aggregate_uid)
            for entity_entry in list(er.async_entries_for_config_entry(ent_reg, entry.entry_id)):
                if entity_entry.domain != "sensor" or not entity_entry.unique_id:
                    continue
                uid = entity_entry.unique_id
                if (uid.startswith(poe_uid_prefixes) or uid == poe_aggregate_uid) and (uid not in desired_poe_uids):
                    ent_reg.async_remove(entity_entry.entity_id)
        except Exception:
            pass

    async_add_entities(entities)


class SimpleTextSensor(CoordinatorEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, key, value, device_info: DeviceInfo, hostname: str):
        super().__init__(coordinator)
        self._key = key
        self._value = value
        self._hostname = hostname
        self._attr_unique_id = f"{entry.entry_id}-{key}"
        self._attr_name = f"{hostname} {SENSOR_TYPES[key]}"
        self._attr_device_info = device_info

    @property
    def native_value(self):
        data = self.coordinator.data
        if self._key == "uptime":
            return uptime_human(data.get("sysUpTime"))
        return data.get("sysName" if self._key == "hostname" else self._key) or self._value
