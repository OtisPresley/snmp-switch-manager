# Changelog
All notable changes to this project will be documented in this file.

> 📌 See also: [`ROADMAP.md`](./ROADMAP.md) for planned features and release targets.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### 🛣️ Roadmap Tracking

- 🔐 **SNMPv3 Support (Secure SNMP)**
  Planned for **v0.5.0**  
  🔗 See roadmap: [`#roadmap-poe-statistics`](./ROADMAP.md#roadmap-snmpv3-support)

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
### Added
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

---

## [0.4.0] - 2026-01-07
### Added
- 🔀 **Trunk port VLAN visibility** using standard IEEE 802.1Q SNMP MIBs when available:
  - 🏷️ Native VLAN (PVID)
  - 📋 Allowed VLAN list
  - 🧵 Tagged VLAN list
  - 🚫 Untagged VLAN list
  - 🔗 Trunk detection flag
- 🧠 **Automatic fallback to static VLAN membership tables** for platforms that do
  not expose current VLAN membership tables
- 🌡️ **Switch Environmentals & CPU / Memory Usage**
  - Supports **Attributes** and **Sensors** modes
  - CPU 5s/60s/300s, Memory Total/Available/Used, System Temperature + Status
  - Fan + PSU telemetry (when supported)
  - Separate per-device **Environmental polling interval**
- ⚡ **Power over Ethernet (PoE) Statistics**
  - Supports **Attributes** and **Sensors** modes
  - PoE Budget Total / Power Used / Power Available (all in **W**)
  - PoE Health Status mapping: **HEALTHY / DISABLED / FAULTY**
  - Separate per-device **PoE polling interval**
- 📶 **Bandwidth mode: Attributes vs Sensors**
  - When set to **Attributes**, bandwidth stats are exposed as attributes on the corresponding port entities
  - When set to **Sensors**, existing bandwidth sensors remain available

### Improved
- Entity creation now avoids generating environmental/PoE entities when SNMP data is unsupported or invalid
- Environmental and PoE status strings normalized to ALL CAPS for consistency

### Fixed
- 🚧 VLAN ID not displaying in port attributes
- 🚧 Issues reporting speed with very large values
- 🚧 Restored Cisco SG-specific rules impacting which interfaces get created and how they are named
- 🎯 Corrected **PVID (native VLAN) detection** for switches that expose PVID via `dot1qPvid` (including ZyXEL and similar platforms)
- 🌐 Improved **per-port IP address detection** to avoid displaying invalid or non-routable addresses (e.g. loopback addresses on physical ports)
- 🚧 Fixed IP misalignment for some switches, including ZyXEL

---

## [0.4.1-beta.1] - 2026-01-08
### Fixed
- 🏷️ **Port Name Rules regression introduced in v0.4.0**
  - Restored correct application of **Port Name Rules** across all integration consumers:
    - Switch entities
    - Sensors
    - Bandwidth attributes
    - Lovelace card data
  - Rules are now applied consistently to interface data at the coordinator level
- 🧩 **Multiple rename rules**
  - All matching Port Name Rules are now applied **in order**, rather than stopping after the first match
- ␣ **Trailing space handling in rename rules**
  - Preserve intentional trailing spaces in replacement values (e.g. `"10G "` → `"10G 12"`)
- 🔁 **Switch interface entity creation**
  - Fixed an issue where interface switch entities could fail to be created under certain conditions

### Notes
- This is a **beta hotfix** intended to address regressions affecting interface naming and visibility introduced in **v0.4.0**
- No schema changes; existing Port Name Rules and Device Options are preserved

---

## [0.4.1-beta.2] - 2026-01-09
### Added
- 🧭 **Interface Port Type classification**
  - Interfaces are now classified as:
    - `physical`
    - `virtual`
    - `unknown`
  - Port Type is always exposed as an interface attribute
  - Classification is derived from SNMP data (ifType, bridge participation, and vendor-safe heuristics)
- 🎛️ **Hide IP field on Physical Interfaces**
  - New per-device option under:
    **Device Options → Interface Management → Interface IP Display**
  - When enabled:
    - IP addresses are hidden on interfaces classified as **physical**
    - IPs remain visible on **virtual / logical** interfaces (e.g. VLAN, management, SVI)
  - Prevents management or SVI IPs from appearing on physical port tiles for switches that expose them this way (e.g. Zyxel)
- 🌍 **Additional UI translations**
  - Added commonly used language translations for the new options and labels:
    - German (`de`)
    - French (`fr`)
    - Spanish (`es`)
    - Italian (`it`)
    - Dutch (`nl`)

### Fixed
- 🚧 Various code updates

### Notes
- This beta introduces **display-only behavior changes**; no existing entities are renamed or removed
- The new IP visibility toggle is **disabled by default** to preserve existing behavior
- Port Type classification is designed to be conservative and vendor-safe

---

## [0.4.1-beta.3] - 2026-01-09
### Fixed
- 🚧 Interface naming regression

---

## [0.4.1-beta.4] - 2026-01-09
### Fixed
- 🚧 Bandwidth sensor naming

---

## [0.4.1-beta.5] - 2026-01-12
### Fixed
- 🎛️ **Restored “Hide IP field on Physical Interfaces”**
  - Option returned to **Device Options → Interface Management → Interface IP Display**
  - Corrected option handling to persist and apply reliably
  - Maintains backward compatibility with existing installations
- 🏷️ **Custom Interface Name Rules – Edit dialog parity**
  - Edit Rule dialog now fully matches Add Rule behavior
  - Replacement values correctly preserve spaces
  - Rule descriptions are retained when editing
- 🌍 **Translation reliability improvements**
  - Verified config flow and options flow translations across supported languages
  - Ensured consistency and fallback safety for non-English users

### Notes
- No existing entities are renamed or removed
- No switch-specific logic or vendor support was altered

---

## [0.4.1-beta.6] - 2026-01-17
### Fixed
- 🚧 Bug causing discovery of certain platforms to fail
- 🚧 Fixed precendence of fields used for Description and Name
- 🚧 Switches with interfaces starting with "Port" are now classified as `physical` for **Port Type**

---

## [0.4.1-beta.7] - 2026-01-20
### Added
- 🌡️ Support for Quidway temperature
  
### Fixed
- 🚧 Fixed issue causing interfaces starting with Port to be skipped

---

## [0.4.1-beta.8] - 2026-01-21
### Fixed
- 🚧 Skip creating temperature sensors that have a value of 0 or an invalid value
- 🚧 Try to determine which temperature sensor it is and name it accordingly

---

## [0.4.1] - 2026-01-22
### Added
- 🧭 **Interface Port Type Classification**
  - Interfaces are classified as:
    - `physical`
    - `virtual`
    - `unknown`
  - Port Type is always exposed as an interface attribute
  - Classification is derived from SNMP data (`ifType`, bridge membership, and vendor-safe heuristics)
- 🎛️ **Interface IP Display Control**
  - New per-device option:
    **Device Options → Interface Management → Interface IP Display**
  - Allows hiding IP addresses on **physical** interfaces while preserving them on
    logical interfaces (VLANs, SVIs, management)
  - Disabled by default to preserve existing behavior
- 🌡️ **Expanded Environmental Sensor Support**
  - Added support for **Quidway temperature sensors**
  - Automatic filtering of invalid or zero-value temperature sensors
  - Improved temperature sensor naming to better reflect sensor purpose
- ⚡ **Per-Port PoE Power Sensors (Sensors Mode)**
  - New optional toggle under **Environmental & PoE Options**
  - When enabled and PoE is set to **Sensors** mode:
    - Creates a PoE Power (W) sensor per PoE-capable physical port
    - Sensors exist even when draw is 0 W, enabling seamless activation later
    - Non-PoE-capable ports (e.g. Te interfaces) are excluded
  - Disabled by default to avoid unexpected entity creation
- 🌍 **Expanded UI Translations**
  - Added and verified translations for:
    - German (`de`)
    - French (`fr`)
    - Spanish (`es`)
    - Italian (`it`)
    - Dutch (`nl`)

### Improved
- 🧩 **Port Name Rules Engine**
  - All matching rename rules now apply **in order**
  - Trailing spaces in replacement values are preserved
  - Rules are applied consistently at the coordinator level across:
    - Interface entities
    - Bandwidth sensors
    - Environmental sensors
    - Lovelace card data
- 🔄 **Options Flow Reliability**
  - Improved persistence and reload behavior across all Device Options dialogs
  - Reduced need for repeated reloads after option changes
- 🌡️ **Environmental & PoE Data Validation**
  - Sensors and attributes are no longer created when SNMP data is missing, invalid, or unsupported
  - Status strings normalized for consistency

### Fixed
- 🚧 Multiple regressions introduced in **v0.4.0**, including:
  - Interface and bandwidth sensor naming duplication
  - Port Name Rules not applying uniformly
  - Interfaces starting with `"Port"` being incorrectly skipped
- 🚧 Bandwidth sensor naming inconsistencies
- 🚧 IP address misalignment on physical ports for certain platforms (e.g. Zyxel)
- 🚧 Discovery failures on specific platforms
- 🚧 Interface description/name precedence issues
- 🚧 Temperature sensors incorrectly created with invalid values

### Notes
- This release **does not rename or remove any existing entities**
- All changes are backward-compatible
- New features are **opt-in** via Device Options

---

## [0.5.0] - 2026-01-23
### Added
- 🔐 **SNMPv3 Support**
  - Full support for **SNMP v3** with:
    - Username-based authentication
    - Authentication protocols: **HMAC-SHA / HMAC-MD5**
    - Privacy support using **DES**
  - Configurable via:
    **Device Options → Connection & Name**
  - Seamless switching between **SNMP v2c ↔ SNMP v3** without recreating devices or entities
- 🧭 **Official pfSense Support**
  - Recognized as a **software platform** rather than a hardware switch
  - Correctly parsed and exposed:
    - Manufacturer: **pfSense**
    - Model: **FreeBSD (cleaned, architecture removed)**
    - Firmware: **pfSense version**
    - Hostname: Fully-qualified system hostname
  - No impact to existing switch support or vendor logic
- 🎛️ **Simple Mode (Rule Helpers) – Completed**
  - Unified, simplified rule dialogs for:
    - Interface Include Rules
    - Interface Exclude Rules
    - Interface Rename Rules
    - Bandwidth Sensor Include / Exclude Rules
  - All rule types now use the **same consistent dialog structure**
  - Existing rules are always displayed at the top of each dialog
  - Advanced regex behavior remains fully supported behind the scenes

### Improved
- 🧩 **Options Flow Consistency & Reliability**
  - All Device Options dialogs now:
    - Correctly show current values and rules
    - Avoid unnecessary reloads when submitting with no changes
    - Apply changes deterministically and predictably
  - Fixed placeholder handling in rule dialogs to prevent translation errors
- 🧭 **Connection & Name UX Clarifications**
  - Clear visual grouping of:
    - **SNMP v2c settings**
    - **SNMP v3 settings**
  - Explicit guidance that:
    - All fields are always visible
    - Only the selected SNMP version determines which fields are used
  - Reduces confusion caused by Home Assistant’s static form limitations

### Notes
- This release introduces **no breaking changes**
- No existing entities are renamed or removed
- All changes are backward-compatible
- New functionality is opt-in via **Device Options**

<!-- ROADMAP ANCHOR LINKS -->

<a name="roadmap-simple-mode"></a>
<a name="roadmap-snmpv3-support"></a>
