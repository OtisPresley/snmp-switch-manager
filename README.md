# SNMP Switch Manager: Home Assistant Custom Integration

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-41BDF5?logo=home-assistant&logoColor=white&style=flat)](https://www.home-assistant.io/)
[![HACS Badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://hacs.xyz)
[![HA installs](https://img.shields.io/badge/dynamic/json?url=https://analytics.home-assistant.io/custom_integrations.json&query=$.snmp_switch_manager.total&label=Installs&color=41BDF5)](https://analytics.home-assistant.io/custom_integrations.json)
[![License: MIT](https://raw.githubusercontent.com/otispresley/snmp-switch-manager/main/assets/license-mit.svg)](https://github.com/OtisPresley/snmp-switch-manager/blob/main/LICENSE)
[![hassfest](https://img.shields.io/github/actions/workflow/status/OtisPresley/snmp-switch-manager/hassfest.yaml?branch=main&label=hassfest)](https://github.com/OtisPresley/snmp-switch-manager/actions/workflows/hassfest.yaml)
[![HACS](https://img.shields.io/github/actions/workflow/status/OtisPresley/snmp-switch-manager/hacs.yaml?branch=main&label=HACS)](https://github.com/OtisPresley/snmp-switch-manager/actions/workflows/hacs.yaml)
[![CI](https://img.shields.io/github/actions/workflow/status/OtisPresley/snmp-switch-manager/ci.yaml?branch=main&event=push)](https://github.com/OtisPresley/snmp-switch-manager/actions/workflows/ci.yaml)

SNMP Switch Manager discovers an SNMP-enabled switch and exposes each port to [Home Assistant](https://www.home-assistant.io/) with live status, descriptions, and administrative control. Pair it with the included Lovelace card for a rich dashboard visualisation of your hardware.

---

## Table of Contents

- [Highlights](#highlights)
- [Requirements](#requirements)
- [Installation](#installation)
  - [HACS (recommended)](#hacs-recommended)
  - [Manual install](#manual-install)
- [Documentation](#documentation)
- [Services](#services)
  - [Update a port description](#update-a-port-description)
  - [Toggle administrative state](#toggle-administrative-state)
- [Troubleshooting](#troubleshooting)
- [Support](#support)
- [Changelog](https://github.com/OtisPresley/switch-manager/blob/main/CHANGELOG.md)
- [Roadmap](https://github.com/OtisPresley/switch-manager/blob/main/ROADMAP.md)

---

## Highlights

- 🔍 Automatic discovery of port count, speed, VLAN ID (PVID), description, and operational status via SNMP v2c
- 🔄 Background polling that keeps Home Assistant entities in sync with switch updates
- 🎚️ One `switch` entity per interface for toggling administrative state (up/down)
- 🏷️ Service for updating the interface alias (`ifAlias`) without leaving Home Assistant
- 🖼️ Lovelace card that mirrors the switch layout with colour-coded port status and quick actions
- 📶 Optional per-device bandwidth monitoring (RX / TX throughput & totals)

---

## Requirements

- Home Assistant 2025.11.2 or newer (recommended)
- A switch reachable via SNMP v2c (UDP/161) with read access to interface tables and write access to `ifAlias`
- The SNMP community string that grants the required permissions
- pysnmp 7.x (the integration installs it automatically when needed)

---

## Installation

### HACS (recommended)
You can install this integration directly from HACS:

[![Open your Home Assistant instance and show the repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=OtisPresley&repository=snmp-switch-manager)

After installation, restart Home Assistant and add the integration:

[![Open your Home Assistant instance and add this integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=snmp_switch_manager)

---

#### Manual steps (if you prefer not to use the buttons)
1. In Home Assistant, open **HACS → Integrations**.  
2. Click **Explore & Download Repositories**, search for **SNMP Switch Manager**, then click **Download**.  
3. **Restart Home Assistant**.  
4. Go to **Settings → Devices & Services → Add Integration → SNMP Switch Manager**.  

### Manual install
1. Copy the folder `custom_components/snmp_switch_manager` into your HA `config/custom_components` directory.
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration → SNMP Switch Manager**.

---

## Documentation

Comprehensive documentation for **SNMP Switch Manager** is available
in the GitHub Wiki.

The Wiki includes:
- Installation and configuration guidance
- Attributes vs Sensors explained
- Diagnostics and PoE behavior
- Lovelace card usage and customization
- Supported switches and limitations
- Troubleshooting and FAQ

👉 **Read the full documentation:**  
https://github.com/OtisPresley/snmp-switch-manager/wiki

---

## Services

### Update a port description

Use the `snmp_switch_manager.set_port_description` service to change an interface alias:

```yaml
service: snmp_switch_manager.set_port_description
data:
  entity_id: switch.gi1_0_5
  description: Uplink to router
```

---

### Toggle administrative state

The state of each port entity reflects the interface's administrative status. Turning it **on** sets the port to *up*; turning it **off** sets it to *down*. Entity attributes include both administrative and operational status direct from SNMP. Entity attributes include administrative status, operational status, port speed, VLAN ID (PVID), and IP configuration when available.

---

## Troubleshooting

- **Ports missing:** Ensure the SNMP community string permits reads on the interface tables (`ifDescr`, `ifSpeed`, `ifOperStatus`).
- **Description updates fail:** Confirm the community string has write permission for `ifAlias` (`1.3.6.1.2.1.31.1.1.1.18`).
- **Unexpected speeds:** Some devices report zero or vendor-specific rates for unused interfaces; check the switch UI to confirm raw SNMP data.

---

## Support

If your switch does not display correctly, then the integration will need to have specific support added for it. Please open an issue with an text file attachment with the results of an `snmpwalk` command against your switch with an **RW SNMP v2c community string** and any necessary screenshots. Also describe what is incorrect and what it should look like.

### Switches Working/Supported
- Dell EMC Networking OS6
- Zyxel
- D-Link DGS
- Cisco CBS, SG, 9200CX, 9300X
- Arista
- Juniper EX2200
- Mikrotik RouterOS
- OPNsense Firewall
- DDWRT
- Jt-Com
- Goodtop

### Open an Issue
- Open an issue on the [GitHub tracker](https://github.com/OtisPresley/snmp-switch-manager/issues) if you run into problems or have feature requests.
- Contributions and feedback are welcome!

If you find this integration useful and want to support development, you can:

[![Buy Me a Coffee](https://img.shields.io/badge/Support-Buy%20Me%20a%20Coffee-orange)](https://www.buymeacoffee.com/OtisPresley)
[![Donate via PayPal](https://img.shields.io/badge/Donate-PayPal-blue.svg)](https://paypal.me/OtisPresley)
