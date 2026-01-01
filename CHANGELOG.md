# Changelog
All notable changes to this project will be documented in this file.

> 📌 See also: [`ROADMAP.md`](./ROADMAP.md) for planned features and release targets.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### 🛣️ Roadmap Tracking

- 🌡️ **Switch Environmentals & CPU / Memory Usage**  
  Planned for **v0.4.0**  
  🔗 See roadmap: [`#roadmap-switch-environmentals`](./ROADMAP.md#roadmap-switch-environmentals)

- ⚡ **Power over Ethernet (PoE) Statistics**  
  Planned for **v0.4.0**  
  🔗 See roadmap: [`#roadmap-poe-statistics`](./ROADMAP.md#roadmap-poe-statistics)

### Added
- Created the initial integration

---

## [0.1.0] - 2025-11-13
### Added
- 🔍 Automatic discovery of port count, speed, description, and operational status via SNMP v2c
- 🔄 Background polling that keeps Home Assistant entities in sync with switch updates
- 🎚️ One `switch` entity per interface for toggling administrative state (up/down)
- 🏷️ Service for updating the interface alias (`ifAlias`) without leaving Home Assistant
- 🖼️ Lovelace card that mirrors the switch layout with colour-coded port status and quick actions

---

## [0.2.0] - 2025-11-20
### Fixed
- 🚧 Refactored to work with pysnmp 7.1.24 to work with HA Core 7.1.24

---

## [0.3.0RC1] - 2025-11-21
### Added
- 🎚️ Support for Cisco CBS250
- 🏷️ Updated README

---

## [0.3.0RC2] - 2025-12-02
### Added
- 🎚️ Support for Cisco CBS250
- 🎚️ Support for Cisco CBS250 firmware sensor
- 🎚️ Initial support for Arista
- 🏷️ Updated README
### Fixed
- 🚧 Fixed issue causing inability to operate the port switches

---

## [0.3.0] - 2025-12-07
### Added
- 🎚️ Support for Cisco CBS and SG
- 🎚️ Support for Cisco CBS250 firmware sensor
- 🎚️ Initial support for Arista
- 🎚️ Support for Juniper EX2200
- 🏷️ Updated README
### Fixed
- 🚧 Fixed issue causing inability to operate the port switches
- 🚧 Fixed naming of switch and sensor entities to include the switch name (must delete switch and readd it)

---

## [0.3.1-beta.1] - 2025-12-07
### Added
- 🎚️ Support for Mikrotik RouterOS

---

## [0.3.1] - 2025-12-23
### Added
- 🎚️ Support for Mikrotik RouterOS
- ⚡ Port Speed in the interface attributes
- 🏷️ VLAN ID in the interface attributes (PVID / untagged VLAN)
- 🧩 Per-device custom SNMP OID overrides for diagnostic sensors (with reset to defaults)
- 🏷️ Updated README

### Fixed
- 🚧 Thanks to [@cerebrate](https://github.com/cerebrate) for Cisco SG-Series interface filtering improvements
- 🚧 Diagnostic sensors now refresh correctly without requiring an integration restart
- 🚧 Corrected Manufacturer and Firmware OIDs for Zyxel devices

---

## [0.3.2] - 2025-12-24
### Added
- 🧰 **Device Options** panel replacing Custom SNMP OIDs
  - Per-device overrides for SNMP community, port, and friendly name
- 🧩 **Per-device interface include rules**
  - Starts with / Contains / Ends with matching
  - Can explicitly include interfaces otherwise excluded by vendor logic
- 🚫 **Per-device interface exclude rules**
  - Prevent entity creation and remove existing matching entities
  - Exclude rules always take precedence
- 🧭 **Multi-step rule manager UI**
  - Clean, menu-driven Options flow
  - Dedicated sub-forms for include rules, exclude rules, and custom diagnostic OIDs
- 🏷️ **VLAN ID (PVID) attribute reliability improvements**
  - Added fallback handling for devices that index PVIDs by `ifIndex`

---

## [0.3.3] - 2025-12-25
### Added
- ⏱️ **Configurable Uptime polling interval**
  - Default uptime refresh reduced to **5 minutes** to avoid excessive updates
- 🧰 **Stabilized Device Options framework**
  - Confirmed persistence and correct reload behavior for all option changes
  - Options now reliably apply without requiring multiple manual reloads
- 🏷️ **Port Name Rules**
  - Regex-based renaming verified working end-to-end
  - Fixed rule application order and duplicate-prefix issues (e.g. `GigEgE`)

### Improved
- 🧩 **Interface Include / Exclude rule engine**
  - Rule changes now correctly:
    - Apply immediately
    - Persist across restarts
    - Remove or restore entities as expected
  - Exclude rules properly remove existing entities (not just block creation)
- 🔄 **Integration reload behavior**
  - Reduced reload time on large switches
  - Eliminated spurious “Unknown error” during option changes

### Fixed
- 🚧 Uptime sensor updating too frequently
- 🚧 Option removal not persisting after UI close or reload
- 🚧 Device Options menus not applying changes properly

### Removed
- 🗑️ **Friendly Name override**
  - Removed from Add Entry flow and Device Options
  - Entity naming now relies solely on device hostname and interface name

---

## [0.3.5] - 2025-12-25
### Fixed
- 🚧 Custom Diagnostic OIDs not applying properly

---

## [0.3.6] - 2025-12-27
### Added
- ⏱️ **Per-device configurable Uptime polling interval**
  - Exposed via **Device Options**
  - Controls refresh rate of the Uptime (sysUpTime) diagnostic sensor
  - Default: **300 seconds (5 minutes)**
  - Configurable range: **30–3600 seconds**
  - Applies immediately without restart
- 📶 **Bandwidth Sensors (RX / TX throughput & total traffic)**
  - Optional per-device bandwidth sensors
  - RX/TX rate sensors (bits per second)
  - Total RX/TX byte counters
  - Per-device enable / disable
  - Per-device polling interval
  - Independent include and exclude rules
- 🧰 **Bandwidth Sensor rule engine**
  - Include rules: Starts with / Contains / Ends with
  - Exclude rules always take precedence
  - Rules apply immediately and persist across restarts
  - Bandwidth rules are fully isolated from Interface Include / Exclude rules
- 🧭 **Expanded Device Options menu**
  - Dedicated Bandwidth Sensors sub-menu
  - Independent configuration from interface discovery rules

### Improved
- 🔄 Device Options flow stability
  - All option dialogs now return cleanly to the parent menu

### Fixed
- 🚧 Bandwidth polling interval validation and persistence
- 🚧 Incorrect interface speed on some devices that report in bps

---

## [0.3.7-beta.1] - 2025-12-28
### Fixed
- 🚧 VLAN ID not displaying in port attributes

---

## [0.3.7-beta.2] - 2025-12-28
### Fixed
- 🚧 VLAN ID not displaying in port attributes
- 🚧 Issues reporting speed with very large values

---

## [0.3.7-beta.3] - 2025-12-28
### Fixed
- 🚧 VLAN ID not displaying in port attributes
- 🚧 Issues reporting speed with very large values
- 🚧 Restored Cisco SG-specific rules impacting which interfaces get created and how they are named

---

## 0.3.7-beta.4
### ✨ Added
- 🔀 **Trunk port VLAN visibility** using standard IEEE 802.1Q SNMP MIBs when available:
  - 🏷️ Native VLAN (PVID)
  - 📋 Allowed VLAN list
  - 🧵 Tagged VLAN list
  - 🚫 Untagged VLAN list
  - 🔗 Trunk detection flag
- 🧠 **Automatic fallback to static VLAN membership tables** for platforms that do
  not expose current VLAN membership tables

### Fixed
- 🚧 VLAN ID not displaying in port attributes
- 🚧 Issues reporting speed with very large values
- 🚧 Restored Cisco SG-specific rules impacting which interfaces get created and how they are named
- 🎯 Corrected **PVID (native VLAN) detection** for switches that expose PVID via `dot1qPvid` (including ZyXEL and similar platforms)
- 🌐 Improved **per-port IP address detection** to avoid displaying invalid or non-routable addresses (e.g. loopback addresses on physical ports)

<!-- ROADMAP ANCHOR LINKS -->

<a name="roadmap-bandwidth-sensors"></a>
<a name="roadmap-switch-environmentals"></a>
<a name="roadmap-poe-statistics"></a>
