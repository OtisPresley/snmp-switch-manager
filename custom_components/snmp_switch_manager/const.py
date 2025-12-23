from __future__ import annotations

DOMAIN = "snmp_switch_manager"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_COMMUNITY = "community"
CONF_NAME = "name"
CONF_CUSTOM_OIDS = "custom_oids"
CONF_ENABLE_CUSTOM_OIDS = "enable_custom_oids"
CONF_RESET_CUSTOM_OIDS = "reset_custom_oids"

DEFAULT_PORT = 161
DEFAULT_POLL_INTERVAL = 10  # seconds

PLATFORMS = ["sensor", "switch"]

# OIDs
OID_sysDescr = "1.3.6.1.2.1.1.1.0"
OID_sysName = "1.3.6.1.2.1.1.5.0"
OID_sysUpTime = "1.3.6.1.2.1.1.3.0"

# IF-MIB
OID_ifIndex = "1.3.6.1.2.1.2.2.1.1"         # table
OID_ifDescr = "1.3.6.1.2.1.2.2.1.2"         # table
OID_ifType = "1.3.6.1.2.1.2.2.1.3"          # table
OID_ifAdminStatus = "1.3.6.1.2.1.2.2.1.7"   # table
OID_ifOperStatus = "1.3.6.1.2.1.2.2.1.8"    # table
OID_ifName = "1.3.6.1.2.1.31.1.1.1.1"       # table (ifXTable)
OID_ifAlias = "1.3.6.1.2.1.31.1.1.1.18"     # table (RW)

# IF-MIB (interface speeds)
OID_ifSpeed = "1.3.6.1.2.1.2.2.1.5"         # table (bps)
OID_ifHighSpeed = "1.3.6.1.2.1.31.1.1.1.15" # table (Mbps)

# BRIDGE-MIB / Q-BRIDGE-MIB (VLAN/PVID)
# dot1dBasePortIfIndex maps bridge port number <-> ifIndex
OID_dot1dBasePortIfIndex = "1.3.6.1.2.1.17.1.4.1.2"  # table
# dot1qPvid yields the PVID (untagged VLAN) per bridge port
OID_dot1qPvid = "1.3.6.1.2.1.17.7.1.4.5.1.1"         # table

# IP-MIB (legacy IPv4 table)
OID_ipAdEntAddr = "1.3.6.1.2.1.4.20.1.1"
OID_ipAdEntIfIndex = "1.3.6.1.2.1.4.20.1.2"
OID_ipAdEntNetMask = "1.3.6.1.2.1.4.20.1.3"

# ENTITY-MIB — model name column (walk and pick a base-chassis entry)
OID_entPhysicalModelName = "1.3.6.1.2.1.47.1.1.1.1.13"

# ENTITY-MIB — CBS350 base-chassis software revision (see Cisco CBS350 SNMP OIDs doc)
# This is entPhysicalSoftwareRev with entPhysicalIndex 67109120
OID_entPhysicalSoftwareRev_CBS350 = "1.3.6.1.2.1.47.1.1.1.1.10.67109120"

# MikroTik RouterOS (MIKROTIK-MIB .1.3.6.1.4.1.14988.1.1.7)
# routerBoardInfoSoftwareVersion: "7.20.6"
OID_mikrotik_software_version = "1.3.6.1.4.1.14988.1.1.7.4.0"
# routerBoardInfoModel: "CRS305-1G-4S+"
OID_mikrotik_model = "1.3.6.1.4.1.14988.1.1.7.8.0"

# Zyxel (vendor-specific)
# Manufacturer via ENTITY-MIB entPhysicalMfgName for base chassis
OID_entPhysicalMfgName_Zyxel = "1.3.6.1.2.1.47.1.1.1.1.12.67108992"
# Firmware version via Zyxel enterprise OID
OID_zyxel_firmware_version = "1.3.6.1.4.1.890.1.15.3.1.6.0"
