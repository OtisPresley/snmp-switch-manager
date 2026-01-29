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

- 🔍 Automatic discovery of port count, speed, VLAN ID (PVID), description, and operational status via SNMP (v2c or v3)
- 🔄 Background polling that keeps Home Assistant entities and attributes in sync with live switch data
- 🎚️ One `switch` entity per interface for toggling administrative state (up/down)
- 🏷️ Service for updating the interface alias (`ifAlias`) directly from Home Assistant
- 🖼️ Lovelace card that mirrors the physical switch layout with colour-coded port status and quick actions
- 📶 Optional per-port bandwidth monitoring (RX / TX throughput & totals) with support for attributes or dedicated sensors
- 🌡️ **Environment monitoring** (CPU, memory, system/chassis temperature) with support for attributes or dedicated sensors
- ⚡ **Power over Ethernet (PoE) monitoring** (used and remaining power budget) with support for attributes or dedicated sensors

---

## Requirements

- Home Assistant 2025.11.2 or newer (recommended)
- A switch (or SNMP-enabled network device) reachable via SNMP (UDP/161)
- SNMP credentials with **read access** to interface tables
- **Write access is optional** but required for:
  - Updating `ifAlias` (port description)
  - Toggling administrative state (if supported by the device)
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

SNMP Switch Manager provides Home Assistant services for advanced
use cases, such as interacting with or refreshing switch-related data.

These services are optional and are typically used by:
- Advanced users
- Automations
- Scripts

Most users will not need to use services directly.

👉 **See the GitHub Wiki for full usage guidance and examples:**
https://github.com/OtisPresley/snmp-switch-manager/wiki

### Example: Update a port description

Use the `snmp_switch_manager.set_port_description` service to change an interface alias:

```yaml
service: snmp_switch_manager.set_port_description
data:
  entity_id: switch_switch_study_gi1_0_5
  description: Uplink to router
```

---

### Toggle administrative state

The state of each port entity reflects the interface's administrative status. Turning it **on** sets the port to *up*; turning it **off** sets it to *down*. Entity attributes include both administrative and operational status direct from SNMP. Entity attributes include administrative status, operational status, port speed, VLAN ID (PVID), and IP configuration when available.

---

## Troubleshooting

### ⚠️ Startup Warning Messages (pysnmp)

During Home Assistant startup, you may see one or two warning messages similar to:
```
Detected blocking call to listdir/open inside the event loop by custom integration 'snmp_switch_manager'
```

#### What this means
These warnings originate from **pysnmp**, the upstream SNMP library used by this integration.  
On first use, pysnmp lazily loads a small number of internal MIB files from disk, which Home Assistant flags as a potential blocking operation.

#### Impact
- ✔️ **No functional impact**
- ✔️ **No data loss**
- ✔️ **No performance degradation during normal operation**
- ✔️ Typically occurs **only once at startup**

The integration continues to operate asynchronously and efficiently after initialization.

#### Why this is not suppressed
Suppressing these warnings would require moving all SNMP operations into background threads, which significantly increases startup time and slows down option changes on large switches. To preserve performance and responsiveness, the integration intentionally keeps the fast async execution path.

#### Summary
If you see these warnings:
- They are **expected**
- They are **safe to ignore**
- No action is required

This behavior is tracked upstream in pysnmp and Home Assistant.

### Common Issues

- **Ports missing:** Ensure your SNMP credentials permit reads on the interface tables (`ifDescr`, `ifSpeed`, `ifOperStatus`).
- **Description updates fail:** Confirm your SNMP credentials have write permission for `ifAlias` (`1.3.6.1.2.1.31.1.1.1.18`).
- **Unexpected speeds:** Some devices report zero or vendor-specific rates for unused interfaces; check the device UI to confirm raw SNMP data.

---

## Support

If your switch does not display correctly, then the integration may need device-specific support added for it.

Please open an issue with:
- A text file attachment containing `snmpwalk` output against your device (SNMP v2c **or** SNMP v3)
- Any necessary screenshots
- A description of what is incorrect and what it should look like

> Tip: If you want port descriptions and administrative toggles to work, your SNMP credentials must allow writes to the required OIDs (device-dependent).

### Supported Switches
👉 **Read the full documentation:**  
https://github.com/OtisPresley/snmp-switch-manager/wiki

### Open an Issue
- Open an issue on the [GitHub tracker](https://github.com/OtisPresley/snmp-switch-manager/issues) if you run into problems or have feature requests.
- Contributions and feedback are welcome!

If you find this integration useful and want to support development, you can:

[![Buy Me a Coffee](https://img.shields.io/badge/Support-Buy%20Me%20a%20Coffee-orange)](https://www.buymeacoffee.com/OtisPresley)
[![Donate via PayPal](https://img.shields.io/badge/Donate-PayPal-blue.svg)](https://paypal.me/OtisPresley)
