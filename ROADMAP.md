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
- ✅ Default exposure as **per-port attributes**
- ✅ Optional exposure as **dedicated diagnostic sensors**

#### Immediate Capabilities Enabled by This Feature
- 📈 Per-port **historical traffic graphs** (via Home Assistant statistics)
- 🚨 Per-port **bandwidth threshold alerting** via automations
- 📊 **Live throughput display** in the Switch Manager UI

---

## 📦 Backlog (Advanced / Long-Term)

- 🧮 **Nothing here yet**  

---
