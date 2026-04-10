# Changelog

All notable changes to this project will be documented in this file.

> 📌 See also: [`ROADMAP.md`](./ROADMAP.md) for planned features and release targets.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## \[Unreleased\]

### 🛣️ Roadmap Tracking

* 🔐 **SNMPv3 Support (Secure SNMP)**
  ✅ Completed in **v0.5.0**

### Added

* Created the initial integration

## \[0.5.2\] - 2026-04-10

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
