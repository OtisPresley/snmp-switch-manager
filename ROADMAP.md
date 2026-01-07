# 🛣️ Roadmap

> 📌 See also: [`CHANGELOG.md`](./CHANGELOG.md) for implemented features and release history.

This roadmap reflects **active development priorities** and **realistic implementation goals** for **SNMP Switch Manager**.

---

## ✅ Completed  
> 🔗 See related releases in [`CHANGELOG.md`](./CHANGELOG.md)

- ✅ Vendor-specific interface filtering  
  - Juniper EX (ge-0/0/X physical ports, VLAN rules, IP-based logical ports)  
  - Cisco SG (Fa/Gi physical ports, VLAN rules, IP-based logical ports)

- ✅ Hostname-prefixed entity names  
  - `switch.switch1_gi1_0_1`  
  - `sensor.switch1_firmware_revision`

- ✅ Cisco CBS firmware detection via ENTITY-MIB
- ✅ Arista IPv4 normalization fixes

- ✅ Port alias editing & tooltip enhancements

- ✅ Unified port information pop-up across panel and list views  
  - Displays Admin / Oper status, Speed, VLAN ID, and interface index

- ✅ Theme-safe card styling  
  - All colors now derive from Home Assistant theme variables (Light/Dark compatible)

- ✅ Diagnostics panel improvements  
  - Removed hostname prefix from Diagnostics sensor display names  
  - Optional ability to hide the Diagnostics panel entirely (no reserved space)

- ✅ Virtual Interfaces display controls  
  - Optional ability to hide the Virtual Interfaces panel entirely (no reserved space)
 
- ✅ Device Options (per-device configuration)
  - Override SNMP community, port, and friendly name
  - Multi-step options UI with clean navigation
    
- ✅ Interface include / exclude rule engine
  - Starts with / Contains / Ends with matching
  - Include rules can override vendor filtering when needed
  - Exclude rules always take precedence and remove existing entities
    
- ✅ VLAN ID (PVID) reliability improvements
  - Added fallback handling for devices that index VLANs by `ifIndex`

- ✅ Custom switch front-panel visualization  
  - Support for a custom background image in panel view  
  - Adjustable port positioning, offsets, and scaling  
  - Optional per-port coordinate overrides

- ✅ Simplified Lovelace resource loading  
  - Card editor embedded directly in the main card  
  - Only a single dashboard resource URL required
 
- ✅ Device-based Lovelace card configuration
  - Card scoped by Home Assistant Device Registry instead of anchor entities
  - Device selector limited to SNMP Switch Manager devices only

- ✅ Automatic Diagnostics discovery
  - Hostname, Manufacturer, Model, Firmware Revision, and Uptime detected automatically
  - No manual sensor configuration required

- ✅ Reorderable Diagnostics display
  - Diagnostics order configurable directly in the card editor

- ✅ Live port state feedback in UI
  - Port toggle button updates immediately when state changes
  - No need to close/reopen the port popup
 
- ✅ Device Options hardening
  - Confirmed persistence, reload correctness, and safe option removal
  - Removed Friendly Name override to prevent entity naming conflicts
 
- ✅ Configurable port color representation
  - Port colors can represent either **Admin / Oper state** or **link speed**
  - User-selectable via card configuration (`color_mode`)
  - Default behavior remains state-based for backward compatibility
 
- ✅ Configurable Uptime polling interval
  - Per-device control via Device Options
  - User-defined refresh rate for sysUpTime diagnostics
  - Safe bounds enforced (30–3600 seconds)

- ✅ 📶 Bandwidth Sensors
  - Per-device RX / TX throughput sensors
  - Per-device total traffic counters
  - Configurable polling interval
  - Independent include and exclude rules
  - Full Device Options UI
 
- ✅ Bandwidth visualization in the Switch Manager card
  - RX / TX throughput graph shown together per interface
  - Popup-based statistics graph with manual refresh
  - Conditional rendering based on available sensors

- ✅ Optional Physical vs Virtual interface classification
  - If unset, the card uses its built-in defaults

- ✅ 🌡️ Switch Environmentals & CPU / Memory Usage
  - Supports **Attributes mode** (single `Environment` entity with rich attributes)
  - Supports **Sensors mode** (graphable CPU/Memory/System Temp/Fan/PSU sensors)
  - Per-device **Environmental polling interval** (separate from main poll)
  - Creates entities **only when valid SNMP data exists** (no junk/Unknown entities)
  - CPU parsed into **5s / 60s / 300s** values
  - Memory supports **Total / Available (kB)** and **Used (%)**
  - System temperature + status mapping (ALL CAPS)

- ✅ ⚡ Power over Ethernet (PoE) Statistics
  - Supports **Attributes mode** (`Power over Ethernet` entity with budget/used/available/status)
  - Supports **Sensors mode** (graphable PoE budget/used/available + health status)
  - Per-device **PoE polling interval**
  - Creates entities **only when PoE OIDs are supported**
  - PoE health status mapping (ALL CAPS): **HEALTHY / DISABLED / FAULTY**

---

## 📝 Planned

### 🎛️ Simple Mode (Rule Helpers)
**Priority:** 🟡 Medium  
**Target Release:** v0.5.0

- Optional simplified UI for:
  - Port Name Rules
  - Interface Include rules
  - Interface Exclude rules
- Converts user-friendly selections into backend regex rules
- Advanced regex mode remains fully available and unchanged

---

### 🔐 SNMPv3 Support (Secure SNMP)
**Priority:** 🟡 Medium  
**Target Release:** v0.5.0

Add optional support for **SNMPv3** to enable secure, authenticated, and encrypted communication with supported network devices.

#### Planned Capabilities
- 🔐 **SNMPv3 authentication**
  - Username-based access
  - Support for common auth protocols (e.g. SHA / MD5)
- 🔒 **Optional SNMPv3 encryption**
  - Privacy (encryption) protocols where supported by the device
- 🔄 **SNMP version selection per device**
  - SNMPv2c and SNMPv3 configurable independently
  - No global migration requirement

#### Design Goals
- ✅ **Backward compatible**
  - Existing SNMPv2c configurations remain unchanged
- ✅ **Per-device configuration**
  - SNMP version and credentials scoped to the selected device only
- ✅ **Unified polling logic**
  - No changes to entity models, OID handling, or UI behavior
- ✅ **Async-safe implementation**
  - Fully compatible with Home Assistant’s event loop
- ✅ **Secure credential storage**
  - All secrets managed via Home Assistant config entries

#### Notes
- Initial implementation may prioritize **SNMP GET operations**  
  (WALK support may be expanded incrementally)
- Feature is optional and **will not be required** for standard operation
- Implementation scope depends on device compatibility and performance validation

---

## 📦 Backlog (Advanced / Long-Term)
### _Nothing here yet_

