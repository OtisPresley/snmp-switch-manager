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

---

## 📝 Planned

### 📶 Bandwidth Sensors  
**Priority:** 🔴 High  
**Target Release:** v0.4.0  
**Tracking:** [`#roadmap-bandwidth-sensors`](./CHANGELOG.md#roadmap-bandwidth-sensors)

Add real-time and cumulative traffic visibility for every network interface.

#### Planned Capabilities
- ⬆️ **Total Transmit (TX) Bandwidth**  
  - Cumulative bytes sent per interface  
- ⬇️ **Total Receive (RX) Bandwidth**  
  - Cumulative bytes received per interface  
- ⚡ **Live Throughput (bps)**  
  - Real-time transmit and receive speeds in bits per second  

#### Design Goals
- ✅ Works across **all supported platforms**
  - Cisco SG / CBS  
  - Arista  
  - Juniper (EX series)  
  - OPNsense / pfSense  
- ✅ Uses **high-capacity 64-bit counters** where available (`ifHCInOctets`, `ifHCOutOctets`)
- ✅ **Automatic 32-bit counter wrap detection & correction**
- ✅ **Efficient polling** via the existing coordinator (no per-entity SNMP sessions)
- ✅ **Minimal Home Assistant performance impact**
- ✅ Default exposure as **dedicated diagnostic sensors**

---

### 🌡️ Switch Environmentals & CPU / Memory Usage  
**Priority:** 🔴 High  
**Target Release:** v0.4.0  
**Tracking:** [`#roadmap-switch-environmentals`](./CHANGELOG.md#roadmap-switch-environmentals)

Add environmental monitoring and system performance telemetry for supported switches and routers.

#### Planned Capabilities
- 🌡️ **Temperature Monitoring**  
  - CPU, PSU, and chassis temperature sensors (when available via SNMP)  
- 🧠 **CPU Utilization**  
  - Current system CPU usage percentage  
- 💾 **Memory Utilization**  
  - Current system memory usage percentage  

#### Design Goals
- ✅ Works across **all supported platforms**
  - Cisco SG / CBS  
  - Arista  
  - Juniper (EX series)  
  - OPNsense / pfSense  
- ✅ Uses **standard SNMP environmental and performance OIDs**
- ✅ **Automatic unit handling**
  - Celsius ↔ Fahrenheit conversion where applicable  
- ✅ **Efficient polling** via the existing coordinator
- ✅ **Minimal Home Assistant performance impact**
- ✅ Default exposure as **dedicated sensor entities**

#### Immediate Capabilities Enabled by This Feature
- 📈 **Historical temperature and utilization graphs** (via Home Assistant statistics)
- 🚨 **Temperature & performance alerting** via automations
- 📊 **Live environmental and system load display** in the Switch Manager UI

---

### ⚡ Power over Ethernet (PoE) Statistics  
**Priority:** 🔴 High  
**Target Release:** v0.4.0  
**Tracking:** [`#roadmap-poe-statistics`](./CHANGELOG.md#roadmap-poe-statistics)

Add real-time **PoE power usage, status, and budget monitoring** for supported PoE-capable switches.

#### Planned Capabilities
- ⚡ **Per-Port Power Usage (Watts)**  
  - Real-time PoE draw per interface  
- 🔌 **Per-Port PoE Status**  
  - Enabled / Disabled / Fault state  
- 🧮 **Total PoE Budget Usage**  
  - Overall switch PoE utilization percentage  
- 📊 **Available vs Used Power Budget**  
  - Remaining PoE headroom for new devices  

#### Design Goals
- ✅ Uses **standard and vendor-specific PoE SNMP OIDs**
  - Cisco  
  - Arista  
  - Juniper  
  - MikroTik (where supported)  
- ✅ **Automatic unit normalization** (W, mW, percentage)
- ✅ **Efficient polling** via the existing coordinator
- ✅ **Minimal Home Assistant performance impact**
- ✅ Default exposure as:
  - 📎 **Attributes on port switch entities**, and/or  
  - ⚙️ **Dedicated diagnostic sensor entities**

#### Immediate Capabilities Enabled by This Feature
- 🚨 **PoE overload and fault alerting**
- 📈 **Historical PoE power usage graphs**
- 🔍 **Fast detection of non-responsive powered devices**
- 📊 **Live PoE power display** in the Switch Manager UI

---

## 📦 Backlog (Advanced / Long-Term)

- 🧮 **Nothing here yet**
