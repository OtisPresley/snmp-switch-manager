from __future__ import annotations

DOMAIN = "snmp_switch_manager"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_COMMUNITY = "community" 

DEFAULT_PORT = 161
DEFAULT_POLL_INTERVAL = 10  # seconds

PLATFORMS = ["sensor", "switch"]

# --- Diagnostic OIDs (built-in defaults) ---
# Standard SNMP system OIDs
OID_sysDescr = "1.3.6.1.2.1.1.1.0"
OID_sysUpTime = "1.3.6.1.2.1.1.3.0"
OID_sysName = "1.3.6.1.2.1.1.5.0"

# ENTITY-MIB (used for some vendor firmware/model/manufacturer)
OID_entPhysicalMfgName = "1.3.6.1.2.1.47.1.1.1.1.12"
OID_entPhysicalModelName = "1.3.6.1.2.1.47.1.1.1.1.13"
OID_entPhysicalSoftwareRev = "1.3.6.1.2.1.47.1.1.1.1.10"
OID_entPhysicalSerialNum = "1.3.6.1.2.1.47.1.1.1.1.11"
OID_entPhysicalDescr = "1.3.6.1.2.1.47.1.1.1.1.2"
OID_entPhysicalName = "1.3.6.1.2.1.47.1.1.1.1.7"

# Zyxel specific
OID_entPhysicalMfgName_Zyxel = "1.3.6.1.2.1.47.1.1.1.1.12.67108992"
OID_zyxel_firmware_version = "1.3.6.1.4.1.890.1.15.3.1.6.0"

# MikroTik RouterOS (MIKROTIK-MIB)
OID_mikrotik_software_version = "1.3.6.1.4.1.14988.1.1.7.4.0"
OID_mikrotik_model = "1.3.6.1.4.1.14988.1.1.7.8.0"

# This is entPhysicalSoftwareRev with entPhysicalIndex 67109120
OID_entPhysicalSoftwareRev_CBS350 = "1.3.6.1.2.1.47.1.1.1.1.10.67109120"
OID_hwEntityTemperature = "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.11"

# --- IF-MIB base OIDs ---
OID_ifIndex = "1.3.6.1.2.1.2.2.1.1"
OID_ifDescr = "1.3.6.1.2.1.2.2.1.2"
OID_ifType = "1.3.6.1.2.1.2.2.1.3"
OID_ifMtu = "1.3.6.1.2.1.2.2.1.4"
OID_ifSpeed = "1.3.6.1.2.1.2.2.1.5"
OID_ifPhysAddress = "1.3.6.1.2.1.2.2.1.6"
OID_ifAdminStatus = "1.3.6.1.2.1.2.2.1.7"
OID_ifOperStatus = "1.3.6.1.2.1.2.2.1.8"
OID_ifLastChange = "1.3.6.1.2.1.2.2.1.9"
OID_ifInOctets = "1.3.6.1.2.1.2.2.1.10"
OID_ifInUcastPkts = "1.3.6.1.2.1.2.2.1.11"
OID_ifInNUcastPkts = "1.3.6.1.2.1.2.2.1.12"
OID_ifInDiscards = "1.3.6.1.2.1.2.2.1.13"
OID_ifInErrors = "1.3.6.1.2.1.2.2.1.14"
OID_ifInUnknownProtos = "1.3.6.1.2.1.2.2.1.15"
OID_ifOutOctets = "1.3.6.1.2.1.2.2.1.16"
OID_ifOutUcastPkts = "1.3.6.1.2.1.2.2.1.17"
OID_ifOutNUcastPkts = "1.3.6.1.2.1.2.2.1.18"
OID_ifOutDiscards = "1.3.6.1.2.1.2.2.1.19"
OID_ifOutErrors = "1.3.6.1.2.1.2.2.1.20"
OID_ifOutQLen = "1.3.6.1.2.1.2.2.1.21"
OID_ifSpecific = "1.3.6.1.2.1.2.2.1.22"

# IF-MIB extras
OID_ifAlias = "1.3.6.1.2.1.31.1.1.1.18"
OID_ifName = "1.3.6.1.2.1.31.1.1.1.1"
OID_ifHighSpeed = "1.3.6.1.2.1.31.1.1.1.15"  # Mbps by RFC, but some devices report bps
OID_ifHCInOctets = "1.3.6.1.2.1.31.1.1.1.6"
OID_ifHCOutOctets = "1.3.6.1.2.1.31.1.1.1.10"

# BRIDGE-MIB (PVID / VLAN)
OID_dot1qPvid = "1.3.6.1.2.1.17.7.1.4.5.1.1"

# BRIDGE-MIB (bridge port -> ifIndex mapping)
OID_dot1dBasePortIfIndex = "1.3.6.1.2.1.17.1.4.1.2"

# IP-MIB / legacy (IPv4 address to ifIndex mapping)
OID_ipAdEntAddr = "1.3.6.1.2.1.4.20.1.1"
OID_ipAdEntIfIndex = "1.3.6.1.2.1.4.20.1.2"
OID_ipAdEntNetMask = "1.3.6.1.2.1.4.20.1.3"

# ---------------------------
# Options / device overrides
# ---------------------------

# Per-device custom diagnostic OIDs
CONF_CUSTOM_OIDS = "custom_oids"
CONF_ENABLE_CUSTOM_OIDS = "enable_custom_oids"
CONF_RESET_CUSTOM_OIDS = "reset_custom_oids"

# Device options (overrides)
CONF_UPTIME_POLL_INTERVAL = "uptime_poll_interval"
DEFAULT_UPTIME_POLL_INTERVAL = 300  # seconds
MIN_UPTIME_POLL_INTERVAL = 30  # seconds
MAX_UPTIME_POLL_INTERVAL = 3600  # seconds

CONF_BANDWIDTH_POLL_INTERVAL = "bandwidth_poll_interval"
DEFAULT_BANDWIDTH_POLL_INTERVAL = 30  # seconds
MIN_BANDWIDTH_POLL_INTERVAL = 5  # seconds
MAX_BANDWIDTH_POLL_INTERVAL = 3600  # seconds

# Optional per-feature polling intervals (seconds)
CONF_POE_POLL_INTERVAL = "poe_poll_interval"
DEFAULT_POE_POLL_INTERVAL = 30
MIN_POE_POLL_INTERVAL = 5
MAX_POE_POLL_INTERVAL = 3600

CONF_ENV_POLL_INTERVAL = "env_poll_interval"
DEFAULT_ENV_POLL_INTERVAL = 30
MIN_ENV_POLL_INTERVAL = 5
MAX_ENV_POLL_INTERVAL = 3600

CONF_OVERRIDE_COMMUNITY = "override_community"
CONF_OVERRIDE_PORT = "override_port" 

# Include/exclude rules (simple modes)
CONF_INCLUDE_STARTS_WITH = "include_starts_with"
CONF_INCLUDE_CONTAINS = "include_contains"
CONF_INCLUDE_ENDS_WITH = "include_ends_with"

CONF_EXCLUDE_STARTS_WITH = "exclude_starts_with"
CONF_EXCLUDE_CONTAINS = "exclude_contains"
CONF_EXCLUDE_ENDS_WITH = "exclude_ends_with"

CONF_ICON_RULES = "icon_rules"

# Interface IP display
# Primary option key (v0.4.1-beta.2)
CONF_HIDE_IP_ON_PHYSICAL_INTERFACES = "hide_ip_on_physical_interfaces"

# Compatibility alias (used by some dev builds)
CONF_HIDE_IP_ON_PHYSICAL = "hide_ip_on_physical"

# Bandwidth sensor options (per-device)
CONF_BW_ENABLE = "enable_bandwidth_sensors"
CONF_BW_INCLUDE_STARTS_WITH = "bw_include_starts_with"
CONF_BW_INCLUDE_CONTAINS = "bw_include_contains"
CONF_BW_INCLUDE_ENDS_WITH = "bw_include_ends_with"
CONF_BW_EXCLUDE_STARTS_WITH = "bw_exclude_starts_with"
CONF_BW_EXCLUDE_CONTAINS = "bw_exclude_contains"
CONF_BW_EXCLUDE_ENDS_WITH = "bw_exclude_ends_with"


# Backwards/forwards compatibility aliases (config_flow expects these names)
CONF_BW_ENABLED = CONF_BW_ENABLE
CONF_BW_INCLUDE_RULES = "bw_include_rules"
CONF_BW_EXCLUDE_RULES = "bw_exclude_rules"


# Built-in vendor interface filtering rule toggles (per-device)
CONF_DISABLED_VENDOR_FILTER_RULE_IDS = "disabled_vendor_filter_rule_ids"

# Rule IDs for built-in vendor interface filtering (used for disable/enable)
BUILTIN_VENDOR_FILTER_RULES: list[dict[str, str]] = [
    # Cisco SG
    {"id": "cisco_sg_physical_fa_gi", "label": "Cisco SG: Only create physical Fa*/Gi* interfaces"},
    {"id": "cisco_sg_vlan_admin_or_oper", "label": "Cisco SG: Create VLAN interfaces (oper up or admin down)"},
    {"id": "cisco_sg_other_has_ip", "label": "Cisco SG: Create other interfaces when an IP is configured"},
    # Juniper EX (Junos)
    {"id": "junos_physical_ge", "label": "Junos: Create physical ge-0/0/X interfaces"},
    {"id": "junos_l3_subif_has_ip", "label": "Junos: Create ge-0/0/X.Y subinterfaces with IP (non-.0)"},
    {"id": "junos_vlan_admin_or_oper", "label": "Junos: Create VLAN interfaces (oper up or admin down)"},
    {"id": "junos_other_has_ip", "label": "Junos: Create other interfaces when an IP is configured"},
]

# Port rename rules (regex)
CONF_PORT_RENAME_USER_RULES = "port_rename_user_rules"
CONF_PORT_RENAME_DISABLED_DEFAULT_IDS = "port_rename_disabled_default_ids"

# ---------------------------
# Built-in port rename rules
# (Applied to display name only)
# ---------------------------

DEFAULT_PORT_RENAME_RULES: list[dict[str, str]] = [
    {
        "id": "link_aggregate_to_po",
        "description": "Normalize 'link aggregate N' to 'PoN'",
        "pattern": r"^link\s+aggregate\s+(\d+)$",
        "replace": r"Po\1",
    },
    {
        "id": "port_channel_to_po",
        "description": "Normalize 'Port-channelN' to 'PoN'",
        "pattern": r"^port-?channel\s*(\d+)$",
        "replace": r"Po\1",
    },
    {
        "id": "portchannel_to_po",
        "description": "Normalize 'PortChannelN' to 'PoN'",
        "pattern": r"^portchannel\s*(\d+)$",
        "replace": r"Po\1",
    },
    {
        "id": "loopback_to_lo0",
        "description": "Normalize loopback names to 'Lo0'",
        "pattern": r"^lo\d*(?:\.\d+)?$",
        "replace": r"Lo0",
    },
    {
        "id": "unit_slot_port_10g_to_te",
        "description": "Normalize 'Unit: U Slot: S Port: P 10G' to 'TeU/S/P'",
        "pattern": r"^Unit:\s*(\d+)\s+Slot:\s*(\d+)\s+Port:\s*(\d+)\s+10G$",
        "replace": r"Te\1/\2/\3",
    },
    {
        "id": "unit_slot_port_20g_to_tw",
        "description": "Normalize 'Unit: U Slot: S Port: P 20G' to 'TwU/S/P'",
        "pattern": r"^Unit:\s*(\d+)\s+Slot:\s*(\d+)\s+Port:\s*(\d+)\s+20G$",
        "replace": r"Tw\1/\2/\3",
    },
    {
        "id": "unit_slot_port_1g_to_gi",
        "description": "Normalize 'Unit: U Slot: S Port: P 1G' to 'GiU/S/P'",
        "pattern": r"^Unit:\s*(\d+)\s+Slot:\s*(\d+)\s+Port:\s*(\d+)\s+1G$",
        "replace": r"Gi\1/\2/\3",
    },
    {
        "id": "unit_slot_port_100m_to_fa",
        "description": "Normalize 'Unit: U Slot: S Port: P 100M' to 'FaU/S/P'",
        "pattern": r"^Unit:\s*(\d+)\s+Slot:\s*(\d+)\s+Port:\s*(\d+)\s+100M$",
        "replace": r"Fa\1/\2/\3",
    },
]

# -----------------------------
# v0.4.0+ (planned): history vs attributes mode selectors
# -----------------------------
# Bandwidth collection mode:
# - sensors: create separate sensor entities (history)
# - attributes: add values to port entities as attributes (no history)
CONF_BW_MODE = "bw_mode"
BW_MODE_SENSORS = "sensors"
BW_MODE_ATTRIBUTES = "attributes"

# Environmental sensors enable/mode
CONF_ENV_ENABLE = "env_enabled"
CONF_ENV_MODE = "env_mode"
ENV_MODE_SENSORS = "sensors"
ENV_MODE_ATTRIBUTES = "attributes"

# PoE per-port statistics enable/mode
CONF_POE_ENABLE = "poe_enabled"
CONF_POE_MODE = "poe_mode"
POE_MODE_SENSORS = "sensors"
POE_MODE_ATTRIBUTES = "attributes"
# Bandwidth sensor icon overrides (optional, per type)
CONF_BW_RX_THROUGHPUT_ICON = "bw_rx_throughput_icon"
CONF_BW_TX_THROUGHPUT_ICON = "bw_tx_throughput_icon"
CONF_BW_RX_TOTAL_ICON = "bw_rx_total_icon"
CONF_BW_TX_TOTAL_ICON = "bw_tx_total_icon"
