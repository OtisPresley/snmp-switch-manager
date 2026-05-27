# Changelog

All notable changes to this project will be documented in this file.

> 📌 See also: [`ROADMAP.md`](./ROADMAP.md) for planned features and release targets.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0-beta.1] - 2026-05-20

This beta release delivers dynamic telemetry scaling overrides, automated background database auto-updating, direct OID overrides, crowdsourced community sharing, and a fully modular options flow with extreme startup performance optimizations.

⚠️ If this release does not work for you, please open an [issue](https://github.com/OtisPresley/snmp-switch-manager/issues) describing the issue and then go back to [v0.5.2](https://github.com/OtisPresley/snmp-switch-manager/releases/tag/v0.5.2) or the previous version you were using before.

### Added

* 🎛️ **100% Modular, Database-Driven Interface Filters:** Migrated all built-in vendor interface filter rules (Cisco SG, Junos, pfSense, CPU pseudo-interfaces) from hardcoded Python code into the dynamic `interface_filters.json` database. A fully vendor-agnostic match engine dynamically interprets these filters based on interface names, state, and IP configurations, enabling seamless community-driven filter contributions and automatic updates without code changes.
* 🔌 **Dynamic Port Classification Schema:** Shifted absolute standard MIB type virtual indicators into `interface_classification.json` under `"virtual_iftypes"`, enabling dynamic customization of hardware port classification rules.
* 🕒 **Scheduled Background Database Auto-Updater:** Automates downloading of system OIDs, filters, and classifications for all **12 database files** from the main repository branch every 6 hours. Performs structural JSON validation and immediately applies updates to running switch/sensor entities within 2 seconds without an HA restart.
* 🔌 **Power over Ethernet (PoE) Control Loops & overrides:** Introduced admin-control toggles for PoE power allocation per physical interface using standard MIB structures. Added full support for custom PoE OID overrides (`Admin state OID` and `Power priority OID`) via the Options Flow forms and database overrides inside `poe.json`.
* 📏 **Dynamic Telemetry Scaling Factors:** Enabled fully custom numeric multipliers (e.g., `0.1` or `1.0`) across all hardware sensors (CPU, Memory, PSU, Fans, PoE, Temp) dynamically from the Home Assistant options flow overrides.
* 🎛️ **Advanced Feature & System OID Overrides:** A brand new, beautifully structured overrides panel under **Device Options**. You can now override custom OIDs for CPU, Memory, Temperature, Fans, PSUs, PoE, and Device Diagnostics (including `Contact`, `Name`, and `Location` OIDs cached inside `device_info.json`) with built-in validation.
* ⚡ **GitHub Community Submissions:** Submit your verified custom OID overrides directly to the public repository from the Home Assistant UI via simple GitHub device authentication to help others.
* 🛠️ **System Mutation & Port Control Services:** Added new administrative control services to manage switch parameters directly from Home Assistant:
  * `set_port_admin_status`: Set standard interface admin status (Up/Down) via target switches.
  * `set_poe_port_admin`: Set PoE port admin status (Auto/Off) on PoE switches.
  * `set_poe_port_priority`: Set PoE power priority allocation (Critical/High/Low) on PoE select entities.
  * `set_system_name`, `set_system_contact`, and `set_system_location`: Modify SNMP system identifiers dynamically, fully integrated with custom OID overrides.
* 🛡️ **Community PR Attestation Pipelines:** Added three Attestation Checkbox confirmations requiring users to verify their filters/tokens are generic, tested, and beneficial to all users before submitting to the repository.
* 📦 **Modular Refactored Settings:** The options flow is now fully split into responsive submenus (Interfaces, Bandwidth, Environmentals, Connection & Name, and Feature Overrides) for an incredibly fast and clean configuration experience.
* 🌐 **Perfect Translation Sync:** Localized all new community filter, classification token options flows, custom PoE overrides, and system OID override settings across **German, Spanish, French, Italian, and Dutch** inside both `strings/` and `translations/` subdirectories.
* 🔌 **Standard MIB-Based Interface Classification:** Integrated parallel polling of standard MIB-II `ifConnectorPresent` (`1.3.6.1.2.1.31.1.1.1.10`) TruthValues to automatically and accurately classify physical (RJ45/SFP) hardware ports vs virtual interfaces (VLANs, Tunnels, Loopbacks, LAGs), with immediate, robust fallback to rule-matching and database classifications when legacy hardware is encountered.

### Fixed

* 🔌 **Standard PoE OIDs:** Corrected a critical typo in standard `POWER-ETHERNET-MIB` OIDs (`OID_pethPsePortAdminEnable`, `OID_pethPsePortActualPower`, `OID_pethPsePortPowerPriority`) which queried with an extra `.1` segment. This was preventing PoE control loops and switches from being successfully discovered and registered on standard switches.

### Improved

* 🚀 **Extreme Startup & Reload Speeds:** Optimized SNMP walks, cached engine bindings, and parallel metadata polling reduce integration loading and reload times by over 80% on high-port switches (such as 24-port and 52-port devices).
* 📦 **Dynamic Database-Driven Naming & Classification:** Migrated static, hardcoded interface naming abbreviations and hardware-port virtual classifications into `interface_classification.json`. Naming formatting, abbreviation lookup, and classification now run 100% modularly via dynamic database configurations, falling back cleanly to static local rules only if the database is unloaded.
* 🎛️ **Device-Targeted Configuration Services:** Refactored new system mutation services to target physical **devices** instead of individual entities, with strict filtering to `snmp_switch_manager` integration instances for a highly intuitive and standard management workflow.
* 🎛️ **Consolidated Device Diagnostics:** Collapsed obsolete individual diagnostic sensors (Firmware, Manufacturer, Hostname, Model) into a single, unified Device Information sensor entity. Expanded metadata tracking to retrieve and display system `sysName`, `sysContact`, and `sysLocation` as rich attributes, significantly reducing Home Assistant entity clutter and keeping dashboards clean.
* 🧩 **100% Dynamic Database-Driven Vendor Engine:** Replaced all hardcoded vendor checks (`_is_h3c`, `_is_jtcom`, `_is_zyxel`) with a dynamic keyword and sysObjectID metadata matching system powered by `vendors.json`. This enables adding support for new vendors and custom-scaling logic dynamically without integration code modifications.
* 📦 **Modular Platform Restructuring:** Modularized switch and sensor platforms (moving entity implementations to `switch_admin.py`, `switch_poe.py`, and `sensor/info.py`), keeping files cohesive, lightweight, and strictly below the 500-line limit.
* 🛡️ **Device Registry Stability:** Restored legacy device identifier mapping to guarantee backwards compatibility and prevent Home Assistant from creating duplicate device entries when connection settings are updated.
* 🛡️ **Stack Robustness:** Resilient environmental and PoE discovery isolated on mixed-hardware stacks.

## [0.5.3-beta.4] - 2026-05-19

### Fixed

* ⚡ **now_mono Scoping Bug:** Eliminated a fatal `UnboundLocalError` inside `async_poll` occurring when Power-over-Ethernet (PoE) polling was disabled.
* 🌡️ **Comware/H3C Environmental Support:** Resolved a severe status mapping bug where normal hardware was reported as `FAILED` inside the Home Assistant GUI.
* 🏷️ **Sequential Index Mapping & Fallback Names:** Added sequential index mapping for Temperature, Fans, and PSU sensors to ensure clean names in the GUI, falling back on `entPhysicalDescr` if `entPhysicalName` returns empty strings.
* 🔋 **Environmental Isolation:** Guaranteed that CPU, Memory, Temperature, Fan, and PSU metrics are completely isolated and only processed when Environmental monitoring is enabled.

## \[0.5.3-beta.3\] - 2026-05-17

### Fixed

* ⚡ **H3C Optimizations:** Refactored sensor discovery to pre-walk physical names and read status tables directly, eliminating slow individual `GET` requests that were causing timeouts and missing sensors.

## \[0.5.3-beta.2\] - 2026-05-15

### Fixed

* 🚧 **H3C Environmentals:** Isolated hardware table discovery routines into distinct exception blocks to prevent unsupported sensors (like Temperature) from aborting the discovery of Fans and PSUs on mixed stacks. Added robust PySNMP byte decoding to prevent trailing null-bytes from breaking text matching.

## \[0.5.3-beta.1\] - 2026-05-15

### Fixed

* 🚧 **H3C Environmentals:** Fixed missing Fan, PSU, and Temperature sensors by switching discovery to `entPhysicalName` (bypassing missing Class tables) and handling label exceptions. Addressed cosmetic memory display issue.

## \[5.2.0\] - 2026-05-15

### Added

* 🚀 **PySNMP v7 Optimizations:** Fixed event-loop blocking issues by aggressively pre-warming PySNMP engine caches and forcing dictionary injection, entirely eliminating Home Assistant `asyncio` blocking `listdir` warnings on startup.
* 🌡️ **H3C Full Environmental Support:** Added full table-walking support for H3C and HP Comware switches, properly discovering and polling CPU, Memory, Temperature, Fans, and Power Supply health.

### Fixed

* 🚧 **Jt-Com / Goodtop Port Speeds:** Restored correct port speed calculation and display formatting for specialty hardware.
* 🚧 **Device Registry Stability:** Fixed a regression causing duplicate switch devices by restoring consistent unique_id anchoring.
* 🚧 **Plugin UI Data:** Restored missing port status and speed attributes required for the custom Lovelace card and plugin webpage.

## \[0.5.1\] - 2026-04-10

Special thanks to [@cerebrate](https://github.com/cerebrate) for significant architectural improvements and performance optimizations.

### Added

* 🚀 **Performance: Bulk SNMP Polling**
  * Replaced slow `GETNEXT` walks with `GETBULK` for much faster data retrieval
  * Automatic fallback to `GETNEXT` for legacy SNMPv1 devices
* ⚡ **Asynchronous Parallelization**
  * All static interface columns (Speed, Type, Alias, Name) are now fetched in parallel
  * Environmental and PoE data collection now utilizes `asyncio.gather` for simultaneous retrieval
* 🔒 **Enhanced SNMP Security & Stability**
  * Explicit detection of SNMP authentication errors with `ConfigEntryAuthFailed` integration
  * Home Assistant will now prompt for re-authentication instead of retrying silently on auth failure
* ⏱️ **Configurable Global Polling Interval**
  * Added `CONF_POLL_INTERVAL` (5s to 300s) to control the main data coordinator refresh rate
* 🛠️ **Modern Home Assistant Architecture**
  * Migrated to `entry.runtime_data` (Standard HA Pattern)
  * Properly handles transport cleanup during integration reloads via `async_close()`

### Improved

* 🧊 **Eliminated Blocking I/O**
  * Expanded MIB preloading to cover all core networking MIBs (`IF`, `ENTITY`, `BRIDGE`, `IP`, etc.)
  * Disabled filesystem-based MIB searching to prevent event-loop stalls
* 🏎️ **Startup Optimization**
  * Moved vendor-specific OID detection (Cisco, Zyxel, MikroTik) to one-time initialization
  * Throttled IPv4 address polling to 5-minute intervals to reduce unnecessary network traffic
  * Removed duplicate coordinator refreshes during platform setup
* 🧹 **Code Quality**
  * Consolidated port renaming logic into the central coordinator
  * Standardized IP address processing by moving `ipaddress` imports to module level

### Fixed

* 🚧 **Cisco CBS350 Firmware Poll:** Fixed a `TypeError` causing silent failures during firmware checks
* 🚧 **Zyxel PoE Statistics:** Corrected alignment for interface-specific PoE metrics
* 🚧 **Resource Leaks:** Fixed unclosed UDP transport handles on integration reload/removal
* 🚧 **Redundant Logic:** Removed duplicated interface name post-processing from switch entities

## \[0.5.1-beta.4\] - 2026-03-16

### Fixed

* 🚧 Support for Zyxel Interface PoE statistics

## \[0.5.1-beta.2\] - 2026-03-15

### Fixed

* 🚧 Support for Zyxel Interface PoE statistics

## \[0.5.1-beta.1\] - 2026-03-15

### Added

* ⚡ Support for Zyxel PoE

## \[0.5.0\] - 2026-01-23

### Added

* 🔐 **SNMPv3 Support**
  * Full support for **SNMP v3** with Username-based authentication, SHA/MD5, and DES
* 🧭 **Official pfSense Support**
  * Recognized as a software platform; correctly parses manufacturer and firmware
* 🎛️ **Simple Mode (Rule Helpers)**
  * Unified, simplified rule dialogs for Includes, Excludes, and Renaming

### Improved

* 🧩 **Options Flow Consistency**
  * Fixed placeholder handling and improved persistence of Device Options

## \[0.4.1\] - 2026-01-22

### Added

* 🧭 **Interface Port Type Classification** (Physical vs Virtual)
* 🎛️ **Interface IP Display Control** (Hide IPs on physical ports)
* 🌡️ **Quidway Temperature Support**
* ⚡ **Per-Port PoE Power Sensors**

## \[0.4.0\] - 2026-01-07

### Added

* 🔀 **Trunk port VLAN visibility** (Allowed/Tagged/Untagged/PVID)
* 🌡️ **Switch Environmentals** (CPU, Memory, Temp, Fans, PSU)
* ⚡ **PoE Statistics** (Budget/Used/Available)
* 📶 **Bandwidth Attributes Mode**

## \[0.3.3\] - 2025-12-25

### Added

* ⏱️ **Configurable Uptime polling interval**
* 🏷️ **Regex-based Port Name Rules**

## \[0.3.2\] - 2025-12-24

### Added

* 🧰 **Device Options panel**
* 🧩 **Per-device interface include/exclude rules**

## \[0.3.1\] - 2025-12-23

### Added

* 🎚️ Support for Mikrotik RouterOS
* ⚡ Port Speed and VLAN ID in attributes

## \[0.3.0\] - 2025-12-07

### Added

* 🎚️ Support for Cisco CBS/SG, Arista, and Juniper EX2200

## \[0.2.0\] - 2025-11-20

### Fixed

* 🚧 Refactored to work with pysnmp 7.1.24

## \[0.1.0\] - 2025-11-13

### Added

* 🔍 Initial release with automatic discovery and Lovelace card support

## \[Unreleased\]

### 🛣️ Roadmap Tracking

* 🔐 **SNMPv3 Support (Secure SNMP)**
  ✅ Completed in **v0.5.0**

### Added

* Created the initial integration
