# SNMP Switch Manager: Home Assistant Custom Integration

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-41BDF5?logo=home-assistant&logoColor=white&style=flat)](https://www.home-assistant.io/)
[![HACS Badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://hacs.xyz)
[![HA installs](https://img.shields.io/badge/dynamic/json?url=https://analytics.home-assistant.io/custom_integrations.json&query=$.snmp_switch_manager.total&label=Installs&color=41BDF5)](https://analytics.home-assistant.io/custom_integrations.json)
[![License: MIT](https://raw.githubusercontent.com/otispresley/snmp-switch-manager/main/assets/license-mit.svg)](https://github.com/OtisPresley/snmp-switch-manager/blob/main/LICENSE)
[![hassfest](https://img.shields.io/github/actions/workflow/status/OtisPresley/snmp-switch-manager/hassfest.yaml?branch=main&label=hassfest)](https://github.com/OtisPresley/snmp-switch-manager/actions/workflows/hassfest.yaml)
[![HACS](https://img.shields.io/github/actions/workflow/status/OtisPresley/snmp-switch-manager/hacs.yaml?branch=main&label=HACS)](https://github.com/OtisPresley/snmp-switch-manager/actions/workflows/hacs.yaml)
[![CI](https://img.shields.io/github/actions/workflow/status/OtisPresley/snmp-switch-manager/ci.yaml?branch=main&event=push)](https://github.com/OtisPresley/snmp-switch-manager/actions/workflows/ci.yaml)

SNMP Switch Manager discovers and monitors SNMP-enabled managed switches and network devices, exposing each port to **Home Assistant** with live administrative control, operational status, descriptions, VLAN identification, and active power management. 

---

## 📖 Table of Contents

- [✨ Core Highlights](#-core-highlights)
- [🛠️ Requirements](#️-requirements)
- [📦 Installation](#-installation)
  - [HACS (Recommended)](#hacs-recommended)
  - [Manual Install](#manual-install)
- [📘 Documentation](#-documentation)
- [⚡ Active Port & PoE Control](#-active-port--poe-control)
- [🏷️ Services](#️-services)
- [🔧 Troubleshooting & Support](#-troubleshooting--support)
- [🛣️ Roadmap & Changelog](#️-roadmap--changelog)

---

## ✨ Core Highlights

- 🎛️ **Active Port Control**: Direct administrative state management (Up/Down) via native Home Assistant `switch` entities.
- 🔌 **Graceful Offline & Connection Handling**: Displays a clear "Setup failed: will retry" status if unreachable at startup, marks entities as `Unavailable` at runtime, and automatically issues self-healing persistent notifications with custom offline imagery to simplify troubleshooting.
- ⚡ **Power over Ethernet (PoE)**: Switch-level budgets (total, used, remaining power) and per-port PoE power monitoring and toggles (reboot or disable PoE devices directly from HA!).
- 🔑 **Robust SNMP v3 Support**: Secure connections with full SHA/MD5 authentication and CBC-DES privacy encryption. Seamlessly transition between SNMP v2c and v3 without losing your Home Assistant device and entity registry.
- 🔄 **Dynamic OID Database**: Automatically pulls updated vendor definitions (CPU, Memory, Fans, PSUs, Temperature, Power, PoE) from the community database in the background every 6 hours—applying updates instantly without requiring a Home Assistant restart.
- 🚀 **GitHub PR Integration**: Enter custom OIDs, interface filters, or port classification rules in the Options flow and easily submit them as a Pull Request back to the community repository using a secure **GitHub Device Flow** (`github.com/login/device`) built directly into the UI!
- 📶 **Advanced Bandwidth Monitoring**: Real-time throughput (bits per second) and total traffic (bytes) for RX/TX with custom include/exclude rules to prevent entity registry bloat.
- 🌡️ **Comprehensive Hardware Health**: Tracks chassis temperature, CPU load, memory utilization, fan speeds, power supply status, and chassis power draw.
- 🧠 **Attributes Mode vs. Sensors Mode**: Choose between a lightweight, attributes-rich setup (highly recommended for the Lovelace card) or standalone sensors for every metric (ideal for history graphs and automation).
- 🏷️ **Dynamic Port Renaming & Filters**: Built-in and user-defined regular expression rules to cleanly format port names (e.g., `Gi1/0/5` to `Gi-5`) and automatically filter out virtual or irrelevant interfaces.
- 🏎️ **Ultra-Optimized Asynchronous Polling**: Built on PySNMP 7.x, fully compliant with Home Assistant's event loop with zero blocking I/O calls.

---

> 📸 **[Screenshot Placeholder]**: *Interactive Lovelace Card showing physical port grids, color-coded status, PoE consumption bars, and active port toggles.*

---

## 🛠️ Requirements

- **Home Assistant**: version 2025.11.2 or newer (recommended).
- **Network Access**: Port UDP/161 reachable on the switch from your Home Assistant host.
- **SNMP Credentials**:
  - **Read Access**: Required to poll port metrics, status, speed, VLANs, and health diagnostics.
  - **Write Access**: Required for active control features (toggling port admin state, toggling PoE power, or writing new port descriptions/aliases).
- **pysnmp 7.x**: Automatically installed by the integration when needed.

---

## 📦 Installation

### HACS (Recommended)

1. Open your Home Assistant instance and navigate to **HACS → Integrations**.
2. Click the three dots in the top-right corner, select **Custom Repositories**, and add:
   `https://github.com/OtisPresley/snmp-switch-manager` (Category: **Integration**).
3. Search for **SNMP Switch Manager** and click **Download**.
4. **Restart Home Assistant**.
5. Go to **Settings → Devices & Services → Add Integration** and search for **SNMP Switch Manager**.

---

### Manual Install

1. Copy the contents of `custom_components/snmp_switch_manager` into your Home Assistant installation folder under `/config/custom_components/snmp_switch_manager`.
2. **Restart Home Assistant**.
3. Go to **Settings → Devices & Services → Add Integration** and select **SNMP Switch Manager**.

---

## 📘 Documentation

Comprehensive, step-by-step guides are hosted in the **[GitHub Wiki](https://github.com/OtisPresley/snmp-switch-manager/wiki)**:

- 📦 **[Installation & Prerequisites](https://github.com/OtisPresley/snmp-switch-manager/wiki/Installation)** – Switch setup, write access permissions, and HACS discovery.
- ⚙️ **[Integration Configuration](https://github.com/OtisPresley/snmp-switch-manager/wiki/Integration-Configuration)** – Walkthrough of the multi-step options menus, SNMP v3, Bandwidth rules, port classification, and custom overrides.
- 🌡️ **[Diagnostics & Health Metrics](https://github.com/OtisPresley/snmp-switch-manager/wiki/Diagnostics)** – Explaining environment, PoE budget data, and custom OIDs.
- 🖧 **[Supported Switch Matrix](https://github.com/OtisPresley/snmp-switch-manager/wiki/Supported-Switches)** – Known working devices (Cisco, Dell, Juniper, MikroTik, Zyxel, pfSense, and more) and limitations.
- 🛠️ **[Troubleshooting & FAQ](https://github.com/OtisPresley/snmp-switch-manager/wiki/Troubleshooting)** – Resolving SNMP v3 auth errors, missing OIDs, and optimizing bandwidth polling.

---

## ⚡ Active Port & PoE Control

With **SNMP write permissions** enabled on your switch, SNMP Switch Manager provides deep interactive control directly within Home Assistant:

1. **Port Administrative Toggle**: Each physical port is exposed as a native `switch` entity. Turning the switch **Off** sends an SNMP write command to administrative-down the physical port. Turning it **On** administratively enables the port.
2. **PoE Port Power Control**: When PoE is enabled on your switch and per-port controls are active, you can toggle the PoE power output of a specific port. This is perfect for power-cycling hung IP cameras, access points, or VoIP phones without disabling physical port links.
3. **Port Description Synchronization**: Updating a port description using the integration's service writes the new description back to the switch's `ifAlias` table permanently.

---

## 🏷️ Services

With Read-Write permissions enabled, the following services are available to manage and configure your switch directly from Home Assistant:

### 🔌 Port Management Services

#### Service: `snmp_switch_manager.set_port_admin_status`
Enable or disable a standard switch port (set link admin status to Up/Down).
```yaml
service: snmp_switch_manager.set_port_admin_status
data:
  entity_id: switch.switch_study_gi1_0_5
  state: "Down" # "Up" or "Down"
```

#### Service: `snmp_switch_manager.set_port_description`
Updates the interface alias (`ifAlias`) directly on the switch hardware and immediately syncs the name back to Home Assistant.
```yaml
service: snmp_switch_manager.set_port_description
data:
  entity_id: switch.switch_study_gi1_0_5
  description: "Uplink to Core Router"
```

### ⚡ Power over Ethernet (PoE) Services

#### Service: `snmp_switch_manager.set_poe_port_admin`
Enable or disable PoE on a specific port without changing the physical link admin status.
```yaml
service: snmp_switch_manager.set_poe_port_admin
data:
  entity_id: switch.switch_study_gi1_0_5_poe
  state: "Off" # "Auto" or "Off"
```

#### Service: `snmp_switch_manager.set_poe_port_priority`
Set the PoE power priority allocation level (Critical, High, Low) on a specific port priority select entity.
```yaml
service: snmp_switch_manager.set_poe_port_priority
data:
  entity_id: select.switch_study_gi1_0_5_poe_priority
  priority: "Critical" # "Critical", "High", or "Low"
```

### ⚙️ System Mutation Services

These services target the switch device configuration instead of individual port entities:

#### Service: `snmp_switch_manager.set_system_name`
Updates the switch's SNMP system name (`sysName`).
```yaml
service: snmp_switch_manager.set_system_name
data:
  device_id: "f83a45c3de722784b2abce8e001" # Target Device ID in Home Assistant
  value: "CoreSwitch-01"
```

#### Service: `snmp_switch_manager.set_system_contact`
Updates the switch's SNMP system contact (`sysContact`).
```yaml
service: snmp_switch_manager.set_system_contact
data:
  device_id: "f83a45c3de722784b2abce8e001"
  value: "admin@example.com"
```

#### Service: `snmp_switch_manager.set_system_location`
Updates the switch's SNMP system location (`sysLocation`).
```yaml
service: snmp_switch_manager.set_system_location
data:
  device_id: "f83a45c3de722784b2abce8e001"
  value: "Server Rack A"
```

---

## 🔧 Troubleshooting & Support

### Common Issues Quick Guide

- **Ports show up as Missing**: Check your SNMP credentials and ensure they permit reading the interface tables (`ifDescr`, `ifSpeed`, `ifOperStatus`). Verify that your interface inclusion/exclusion patterns are not filtering the ports.
- **Port Administrative Toggle / Description Updates Fail**: Your SNMP community string or v3 user does not have **write permissions** (`read-write`) on the switch.
- **Speeds are incorrect or non-standard**: Some switches report non-standard values (e.g. 10Gbps as 1Gbps or 0). You can easily define Custom Name or OID overrides in the integration options.

### Reporting Issues & Contributing

If your switch does not display hardware diagnostics (CPU, Memory, Fan, or PoE budgets) correctly, please consider defining OID overrides in the **Device Options** menu and sharing them directly back to the community via the built-in **GitHub Device Flow**!

To report bugs, request features, or ask questions, please visit the **[GitHub Issues page](https://github.com/OtisPresley/snmp-switch-manager/issues)**.

---

## 🛣️ Roadmap & Changelog

- Check the **[Roadmap](https://github.com/OtisPresley/snmp-switch-manager/blob/main/ROADMAP.md)** for planned features and architecture updates.
- Check the **[Changelog](https://github.com/OtisPresley/snmp-switch-manager/blob/main/CHANGELOG.md)** for detailed release notes.

---

If you find this integration useful and want to support its ongoing development:

[![Buy Me a Coffee](https://img.shields.io/badge/Support-Buy%20Me%20a%20Coffee-orange)](https://www.buymeacoffee.com/OtisPresley)
[![Donate via PayPal](https://img.shields.io/badge/Donate-PayPal-blue.svg)](https://paypal.me/OtisPresley)
