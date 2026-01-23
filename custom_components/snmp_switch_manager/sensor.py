from __future__ import annotations

import logging
from homeassistant.util import slugify
from homeassistant.const import (
    EntityCategory,
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass

from .const import (
    DOMAIN,
    CONF_COMMUNITY,
    CONF_LEGACY_DEVICE_ID,
    CONF_SNMP_VERSION,
    SNMP_VERSION_V3,
    CONF_ICON_RULES,
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
    CONF_ENV_POLL_INTERVAL,
    ENV_MODE_ATTRIBUTES,
    ENV_MODE_SENSORS,
    DEFAULT_ENV_POLL_INTERVAL,
    CONF_BW_RX_THROUGHPUT_ICON,
    CONF_BW_TX_THROUGHPUT_ICON,
    CONF_BW_RX_TOTAL_ICON,
    CONF_BW_TX_TOTAL_ICON,
)
from .snmp import SwitchSnmpClient

_LOGGER = logging.getLogger(__name__)
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

# Reasonable defaults for Dell N-Series (and harmless for others).
DEFAULT_ENV_TEMP_COUNT = 10
DEFAULT_ENV_FAN_COUNT = 2
DEFAULT_ENV_PSU_COUNT = 2


def env_temp_label(idx: int) -> str:
    """Return a human-friendly temperature probe label."""
    return ENV_TEMP_LABELS.get(idx, f"Temp {idx}")

SENSOR_TYPES = {
    "manufacturer": "Manufacturer",
    "model": "Model",
    "firmware": "Firmware Revision",
    "uptime": "Uptime",
    "hostname": "Hostname",
}


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
        self._kind = 'environment'
        self._name_prefix = 'Environment'

    @property
    def device_info(self) -> DeviceInfo:
        return self._device_info

async def async_setup_entry(hass, entry, async_add_entities):
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client: SwitchSnmpClient = entry_data["client"]
    coordinator = entry_data["coordinator"]

    # Ensure coordinator has initial data so we can create only supported sensors
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        pass

    coord_data = coordinator.data or {}

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

    # Device identifiers must be stable.
    #
    # Historically, SNMP Switch Manager used a v2c-only identifier that included
    # host:port:community. When SNMPv3 was added, switching to entry.entry_id
    # alone caused Home Assistant to create duplicate Devices on existing installs
    # (because the identifiers no longer matched the existing Device).
    #
    # To preserve backwards compatibility (and allow HA to automatically re-associate
    # entities to the original Device), include the legacy identifier for v2c entries.
    # For v3 entries, do not include any secrets.
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
        SimpleTextSensor(coordinator, entry, "uptime", _uptime_human(uptime_ticks), device_info, host_label),
        SimpleTextSensor(coordinator, entry, "hostname", hostname or client.host, device_info, host_label),
    ]

    # Bandwidth sensor entities (optional; per-device)
    ent_reg = er.async_get(hass)

    bw_enabled = bool(entry.options.get(CONF_BW_ENABLE, False))
    bw_mode = entry.options.get(CONF_BW_MODE, BW_MODE_SENSORS)
    bw_mode = str(bw_mode).strip().lower()
    if bw_mode not in (BW_MODE_SENSORS, BW_MODE_ATTRIBUTES):
        bw_mode = BW_MODE_SENSORS
    # BW_MODE_ATTRIBUTES means: no per-interface bandwidth sensors; bandwidth is exposed as attributes on port entities.
    bw_entities_enabled = bool(bw_enabled) and (bw_mode == BW_MODE_SENSORS)
    desired_bw_unique_ids: set[str] = set()
    bw_entities: list[SensorEntity] = []

    if bw_entities_enabled:
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
            if (not bw_entities_enabled) or (uid not in desired_bw_unique_ids):
                ent_reg.async_remove(eid)
        else:
            # Legacy entities without expected unique_id should be removed when disabled.
            if not bw_entities_enabled:
                ent_reg.async_remove(eid)


    entities.extend(bw_entities)

    # Environmental sensors (optional)
    #
    # ENV_MODE_ATTRIBUTES -> create a single "Environment" sensor (with everything as attributes)
    # ENV_MODE_SENSORS    -> do NOT create the "Environment" sensor; create per-metric sensors instead
    env_enabled = entry.options.get(CONF_ENV_ENABLE, False)
    env_mode = entry.options.get(CONF_ENV_MODE, ENV_MODE_ATTRIBUTES)

    env_power_uid = f"{entry.entry_id}-env-power"
    env_system_power_uid = f"{entry.entry_id}-env-system-power"

    # Legacy unique_id formats existed before the "<entry_id>-env-*" convention.
    # When switching modes, remove both formats so we don't leave orphan sensors behind.
    env_uid_prefixes = (
        f"{entry.entry_id}-env-",
        f"{entry.entry_id}_env_",
    )
    legacy_env_power_uids = {
        f"{entry.entry_id}_env_power",
        f"{entry.entry_id}_env-power",
    }

    # Remove any env entities that should not exist for the selected mode.
    ent_reg = er.async_get(hass)
    for entity_entry in list(er.async_entries_for_config_entry(ent_reg, entry.entry_id)):
        if entity_entry.domain != "sensor" or not entity_entry.unique_id:
            continue

        uid = entity_entry.unique_id
        is_env_uid = uid.startswith(env_uid_prefixes)

        # Remove all env entities if env is disabled.
        if not env_enabled and is_env_uid:
            ent_reg.async_remove(entity_entry.entity_id)
            continue

        if not env_enabled:
            continue

        # Attributes mode keeps only the single Environment sensor.
        if env_mode == ENV_MODE_ATTRIBUTES and is_env_uid:
            # Keep only the current env-power unique_id; remove legacy ones so HA recreates cleanly.
            if uid != env_power_uid:
                ent_reg.async_remove(entity_entry.entity_id)
            continue

        # Sensors mode keeps only per-metric sensors (no Environment sensor).
        if env_mode == ENV_MODE_SENSORS and (uid == env_power_uid or uid in legacy_env_power_uids):
            ent_reg.async_remove(entity_entry.entity_id)

    # Create the correct entities for the selected mode.
    if env_enabled and env_mode == ENV_MODE_ATTRIBUTES:
        entities.append(EnvironmentPowerSensor(coordinator, entry, device_info, host_label))
    elif env_enabled and env_mode == ENV_MODE_SENSORS:
        entities.append(EnvironmentSystemPowerSensor(coordinator, entry, device_info, host_label))        # CPU (Dell OS6 provides 5/60/300 second averages) + Memory sensors
        # Create only if backing values exist in coordinator.data.
        if (coord_data.get("env_cpu_5s") is not None):
            entities.append(EnvironmentCpuUtilSensor(coordinator, entry, device_info, host_label, "5s"))
        if (coord_data.get("env_cpu_60s") is not None):
            entities.append(EnvironmentCpuUtilSensor(coordinator, entry, device_info, host_label, "60s"))
        if (coord_data.get("env_cpu_300s") is not None):
            entities.append(EnvironmentCpuUtilSensor(coordinator, entry, device_info, host_label, "300s"))

        if (coord_data.get("env_mem_available_kb") is not None) or (coord_data.get("env_mem_free_kb") is not None):
            entities.append(EnvironmentMemoryValueSensor(coordinator, entry, device_info, host_label, "available"))
        if (coord_data.get("env_mem_total_kb") is not None):
            entities.append(EnvironmentMemoryValueSensor(coordinator, entry, device_info, host_label, "total"))
        if (coord_data.get("env_mem_total_kb") is not None) and ((coord_data.get("env_mem_available_kb") is not None) or (coord_data.get("env_mem_free_kb") is not None)):
            entities.append(EnvironmentMemoryUsedPercentSensor(coordinator, entry, device_info, host_label))

        # Fans
        fan_rpm = coord_data.get("env_fans_rpm") or {}
        fan_status = coord_data.get("env_fans_status") or {}
        fan_indices = sorted({int(i) for i in list(fan_rpm.keys()) + list(fan_status.keys())})
        for idx in fan_indices:
            entities.append(EnvironmentFanRpmSensor(coordinator, entry, idx, device_info, host_label))
            entities.append(EnvironmentFanStatusSensor(coordinator, entry, device_info, host_label, idx))

        # PSUs
        psu_status = coord_data.get("env_psu_status") or {}
        psu_indices = sorted({int(i) for i in psu_status.keys()})
        for idx in psu_indices:
            entities.append(EnvironmentPsuStatusSensor(coordinator, entry, device_info, host_label, idx))

        # Temperatures (probe labels are position-based on Dell N-Series)
        temps_c = coord_data.get("env_temps_c") or {}
        try:
            temp_indices = sorted({int(i) for i in temps_c.keys()})
        except Exception:
            temp_indices = []
        for idx in temp_indices:
            # EnvironmentTemperatureSensor signature is (coordinator, entry, idx, device_info, host_label)
            # Keep idx as an int; passing device_info (dict) here breaks label lookups
            # and name formatting ("unhashable type: 'dict'" / dict+int TypeError).
            entities.append(EnvironmentTemperatureSensor(coordinator, entry, idx, device_info, host_label))

        # Unit/System temperature + status (Dell OS6). Create only if backing values exist.
        if coord_data.get("env_unit_temp_c") is not None:
            entities.append(EnvironmentUnitTemperatureSensor(coordinator, entry, device_info, host_label))
        if coord_data.get("env_unit_temp_state") is not None:
            entities.append(EnvironmentUnitTempStateSensor(coordinator, entry, device_info, host_label))
    # PoE sensors (optional)
    # Implemented below



    # --- Cleanup unsupported Environment sensors in Sensors mode ---
    # If a device does not expose a given env table (fans/psu/temps), we do not create those entities.
    # Remove any previously-registered env entities that are no longer desired so they don't linger as UNAVAILABLE.
    if env_enabled and env_mode == ENV_MODE_SENSORS:
        try:
            desired_env_uids = {e.unique_id for e in entities if getattr(e, 'unique_id', None)}
            for entity_entry in list(er.async_entries_for_config_entry(ent_reg, entry.entry_id)):
                if entity_entry.domain != 'sensor' or not entity_entry.unique_id:
                    continue
                uid = entity_entry.unique_id
                is_env_uid = uid.startswith(env_uid_prefixes)
                if is_env_uid and uid not in desired_env_uids:
                    ent_reg.async_remove(entity_entry.entity_id)
        except Exception:
            pass

    # --- PoE sensors (optional) ---
    poe_enabled_opt = entry.options.get(CONF_POE_ENABLE, False)
    poe_mode_opt = entry.options.get(CONF_POE_MODE, POE_MODE_ATTRIBUTES)
    poe_per_port_opt = entry.options.get(CONF_POE_PER_PORT_POWER, False)

    poe_uid_prefixes = (
        f"{entry.entry_id}-poe-",
        f"{entry.entry_id}_poe_",
    )
    poe_aggregate_uid = f"{entry.entry_id}-poe"

    poe_budget_w = (coord_data.get('poe_budget_total_w'))
    poe_used_w = (coord_data.get('poe_power_used_w'))
    poe_avail_w = (coord_data.get('poe_power_available_w'))
    poe_health = (coord_data.get('poe_health_status'))
    poe_power_mw = (coord_data.get('poe_power_mw') or {})
    poe_supported = any(v is not None for v in (poe_budget_w, poe_used_w, poe_avail_w, poe_health)) or bool(poe_power_mw)

    # Remove PoE entities when disabled or unsupported
    if (not poe_enabled_opt) or (not poe_supported):
        for entity_entry in list(er.async_entries_for_config_entry(ent_reg, entry.entry_id)):
            if entity_entry.domain != 'sensor' or not entity_entry.unique_id:
                continue
            uid = entity_entry.unique_id
            if uid.startswith(poe_uid_prefixes) or uid == poe_aggregate_uid:
                ent_reg.async_remove(entity_entry.entity_id)
    else:
        if poe_mode_opt == POE_MODE_ATTRIBUTES:
            entities.append(PoEAggregateSensor(coordinator, entry, device_info, host_label))
        elif poe_mode_opt == POE_MODE_SENSORS:
            # Create only sensors that have valid backing values.
            if poe_budget_w is not None:
                entities.append(PoEBudgetTotalSensor(coordinator, entry, device_info, host_label))
            if poe_used_w is not None:
                entities.append(PoEPowerUsedSensor(coordinator, entry, device_info, host_label))
            if poe_avail_w is not None:
                entities.append(PoEPowerAvailableSensor(coordinator, entry, device_info, host_label))
            if poe_health is not None:
                entities.append(PoEHealthStatusSensor(coordinator, entry, device_info, host_label))
            if poe_per_port_opt:
                if_table = (coordinator.data.get('ifTable') or {})
                for if_idx, row in (if_table or {}).items():
                    try:
                        if_idx_i = int(if_idx)
                    except Exception:
                        continue
                    port_type = str((row or {}).get('port_type') or '').lower()
                    if port_type != 'physical':
                        continue
                    if if_idx_i not in poe_power_mw:
                        continue
                    entities.append(PoEPowerSensor(coordinator, entry, if_idx_i, device_info, host_label))

        # Cleanup any PoE entities not desired for the current mode
        try:
            desired_poe_uids = {e.unique_id for e in entities if getattr(e, 'unique_id', None) and (str(e.unique_id).startswith(f"{entry.entry_id}-poe") or str(e.unique_id).startswith(f"{entry.entry_id}_poe"))}
            desired_poe_uids.add(poe_aggregate_uid) if poe_mode_opt == POE_MODE_ATTRIBUTES else None
            for entity_entry in list(er.async_entries_for_config_entry(ent_reg, entry.entry_id)):
                if entity_entry.domain != 'sensor' or not entity_entry.unique_id:
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
        if direction == 'rx':
            ov = (entry.options.get(CONF_BW_RX_THROUGHPUT_ICON) or '').strip()
        else:
            ov = (entry.options.get(CONF_BW_TX_THROUGHPUT_ICON) or '').strip()
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
        #
        # Example desired entity_id:
        #   sensor.gs1900_24ep_01_gigabitethernet1_rx_throughput
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
        if direction == 'rx':
            ov = (entry.options.get(CONF_BW_RX_TOTAL_ICON) or '').strip()
        else:
            ov = (entry.options.get(CONF_BW_TX_TOTAL_ICON) or '').strip()
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
        total_mw = (data.get("env_power_mw_total") or 0.0)
        try:
            return round(float(total_mw) / 1000.0, 1)
        except Exception:
            return None


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
        data = (self.coordinator.data or {})
        val = data.get(self._key)
        if val is None and self._key == "env_mem_available_kb":
            val = data.get("env_mem_free_kb")
        try:
            return round(float(val), 1) if val is not None else None
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
        data = (self.coordinator.data or {})
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
            return float(mw) / 1000.0
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
        val = (self.coordinator.data or {}).get('poe_power_used_w')
        try:
            return round(float(val), 1) if val is not None else None
        except Exception:
            return None

    @property
    def extra_state_attributes(self):
        data = (self.coordinator.data or {})
        attrs = {}
        b = data.get('poe_budget_total_w')
        u = data.get('poe_power_used_w')
        a = data.get('poe_power_available_w')
        h = data.get('poe_health_status')
        if b is not None:
            attrs['PoE Budget Total (W)'] = round(float(b), 1)
        if u is not None:
            attrs['PoE Power Used (W)'] = round(float(u), 1)
        if a is not None:
            attrs['PoE Power Available (W)'] = round(float(a), 1)
        if h is not None:
            attrs['PoE Health Status'] = str(h)
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
        val = (self.coordinator.data or {}).get('poe_budget_total_w')
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
        val = (self.coordinator.data or {}).get('poe_power_used_w')
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
        val = (self.coordinator.data or {}).get('poe_power_available_w')
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
        val = (self.coordinator.data or {}).get('poe_health_status')
        return str(val) if val is not None else None
