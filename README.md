# Switch Manager for Home Assistant

<p align="center">
  <a href="https://hacs.xyz/">
    <img src="https://img.shields.io/badge/HACS-Custom-41BDF5?style=flat-square&logo=homeassistant" alt="HACS Custom" />
  </a>
  <a href="https://github.com/OtisPresley/switch-manager/actions/workflows/ci.yaml">
    <img src="https://img.shields.io/github/actions/workflow/status/OtisPresley/switch-manager/ci.yaml?branch=main&label=CI&style=flat-square&logo=github" alt="Continuous integration" />
  </a>
  <a href="https://github.com/OtisPresley/switch-manager/actions/workflows/hassfest.yaml">
    <img src="https://img.shields.io/github/actions/workflow/status/OtisPresley/switch-manager/hassfest.yaml?branch=main&label=hassfest&style=flat-square&logo=homeassistant" alt="Validate with hassfest" />
  </a>
  <a href="https://github.com/OtisPresley/switch-manager/actions/workflows/hacs.yaml">
    <img src="https://img.shields.io/github/actions/workflow/status/OtisPresley/switch-manager/hacs.yaml?branch=main&label=HACS&style=flat-square&logo=homeassistant" alt="Validate with HACS" />
  </a>
  <a href="https://github.com/OtisPresley/switch-manager/releases">
    <img src="https://img.shields.io/github/v/release/OtisPresley/switch-manager?style=flat-square&logo=github" alt="Latest release" />
  </a>
  <a href="https://github.com/OtisPresley/switch-manager/releases">
    <img src="https://img.shields.io/github/downloads/OtisPresley/switch-manager/total?style=flat-square&logo=github" alt="GitHub downloads" />
  </a>
  <a href="https://github.com/OtisPresley/switch-manager/issues">
    <img src="https://img.shields.io/github/issues/OtisPresley/switch-manager?style=flat-square&logo=github" alt="GitHub issues" />
  </a>
  <a href="https://github.com/OtisPresley/switch-manager/blob/main/LICENSE">
    <img src="https://img.shields.io/github/license/OtisPresley/switch-manager?style=flat-square" alt="License" />
  </a>
</p>

Switch Manager discovers an SNMP-enabled switch and exposes each port to Home Assistant with live status, descriptions, and administrative control. Pair it with the included Lovelace card for a rich dashboard visualisation of your hardware.

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Lovelace card](#lovelace-card)
- [Services](#services)
- [Troubleshooting](#troubleshooting)
- [Support](#support)

## Features

- 🔍 Automatic discovery of port count, speed, description, and operational status via SNMP v2c
- 🔄 Background polling that keeps Home Assistant entities in sync with switch updates
- 🎚️ One `switch` entity per interface for toggling administrative state (up/down)
- 🏷️ Service for updating the interface alias (`ifAlias`) without leaving Home Assistant
- 🖼️ Lovelace card that mirrors the switch layout with colour-coded port status and quick actions
- 🧭 Automatic population of device metadata (name, firmware, manufacturer) from core SNMP system OIDs

## Requirements

- Home Assistant 2023.12 or newer (recommended)
- A switch reachable via SNMP v2c (UDP/161) with read access to interface tables and write access to `ifAlias`
- The SNMP community string that grants the required permissions
- pysnmp 4.x (installed automatically when adding the integration through HACS)

## Installation

### Install through HACS (recommended)

1. In Home Assistant, open **HACS → Integrations → ⋮ → Custom repositories** and add `https://github.com/OtisPresley/switch-manager` as an Integration repository.
2. Search HACS for **Switch Manager** and click **Download**.
3. Restart Home Assistant when prompted.

### Manual installation

1. Download the latest release ZIP from the [GitHub releases page](https://github.com/OtisPresley/switch-manager/releases).
2. Copy `custom_components/switch_manager` into your Home Assistant `custom_components` directory.
3. Copy `www/community/switch-manager-card` into `www/community` (create the path if necessary).
4. Restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & services → Add integration** and search for **Switch Manager**.
2. Enter the switch hostname/IP address, the SNMP community string, and optionally a friendly name or non-standard SNMP port.
3. Once the flow completes, Home Assistant adds one `switch` entity per discovered interface. Entities follow the pattern `switch.<device_name>_port_<index>`.

## Lovelace card

1. Add the card JavaScript as a resource under **Settings → Dashboards → Resources**:

   ```yaml
   url: /hacsfiles/switch-manager-card/switch-manager-card.js
   type: module
   ```

2. Place the card on any dashboard:

   ```yaml
   type: custom:switch-manager-card
   title: Core Switch
   entities:
     - switch.core_switch_port_1
     - switch.core_switch_port_2
     - switch.core_switch_port_3
   ```

   Clicking a port opens a dialog with quick actions to toggle the port or edit its description.

### Overlay a custom switch image

Export the layout of your switch (for example, from Visio) as an image that lives under `/config/www`. The card can place colour-coded markers on top of that image by switching to the `image` layout and providing coordinates for every port:

```yaml
type: custom:switch-manager-card
title: Bonus Closet Switch
image: /local/images/bonus-closet-switch.png
layout: image
marker_size: 28  # optional, defaults to 26px
ports:
  - entity: switch.bonus_closet_port_1
    label: 1
    x: 12.5   # percentage from the left edge
    y: 62     # percentage from the top edge
  - entity: switch.bonus_closet_port_2
    label: 2
    x: 23
    y: 62
  # ...repeat for each port you want to place on the image
```

Markers adopt the port’s administrative status—green for enabled, red for disabled, amber for unknown—and clicking them opens the same management dialog shown in the grid layout.

## Services

### Update a port description

Use the `switch_manager.set_port_description` service to change an interface alias:

```yaml
service: switch_manager.set_port_description
data:
  entity_id: switch.core_switch_port_5
  description: Uplink to router
```

### Toggle administrative state

The state of each port entity reflects the interface's administrative status. Turning it **on** sets the port to *up*; turning it **off** sets it to *down*. Entity attributes include both administrative and operational status direct from SNMP.

## Troubleshooting

- **Ports missing:** Ensure the SNMP community string permits reads on the interface tables (`ifDescr`, `ifSpeed`, `ifOperStatus`).
- **Description updates fail:** Confirm the community string has write permission for `ifAlias` (`1.3.6.1.2.1.31.1.1.1.18`).
- **Unexpected speeds:** Some devices report zero or vendor-specific rates for unused interfaces; check the switch UI to confirm raw SNMP data.

## Support

Need help or have a feature request? Open an issue on the [GitHub tracker](https://github.com/OtisPresley/switch-manager/issues) and we’ll take a look.

<p align="center">
  <a href="https://ko-fi.com/otispresley">
    <img src="https://img.shields.io/badge/Ko--fi-Support%20the%20project-FF5E5B?style=flat-square&logo=ko-fi" alt="Ko-fi" />
  </a>
  <a href="https://paypal.me/OtisPresley">
    <img src="https://img.shields.io/badge/PayPal-Donate-00457C?style=flat-square&logo=paypal" alt="PayPal" />
  </a>
</p>
