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
- [Configuration](#configuration)
  - [Device Options](#device-options)
    - [Connection & Naming Overrides](#connection--naming-overrides)
    - [Interface Include / Exclude Rules](#interface-include--exclude-rules)
    - [Port Name Rules](#port-name-rules)
    - [Custom Diagnostic SNMP OIDs](#custom-diagnostic-snmp-oids)
- [Lovelace card](#lovelace-card)
  - [HACS (recommended)](#hacs-recommended-1)
  - [Migrating from Manual to HACS Installation](#-migrating-from-manual-to-hacs-installation-important)
  - [Manual installation](#manual-installation)
  - [Configuration](#configuration-1)
  - [Port Color Legend](#-port-color-legend)
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

## Configuration

1. Go to **Settings → Devices & services → Add integration** and search for **SNMP Switch Manager**.
2. Enter the switch hostname/IP address, the SNMP community string, and optionally a non-standard SNMP port.
3. Once the flow completes, Home Assistant adds one `switch` entity per discovered interface. Entities follow the pattern `switch.<hostname>_<interface_name>` (for example: `switch.switch1_gi1_0_1`).

### Device Options

SNMP Switch Manager supports **per-device configuration** via the Home Assistant
Device Options menu.

<table>
  <tr>
    <td align="center">
      <img src="https://raw.githubusercontent.com/otispresley/snmp-switch-manager/main/assets/screenshot5.png" width="250">
    </td>
    <td align="center">
      <img src="https://raw.githubusercontent.com/otispresley/snmp-switch-manager/main/assets/screenshot6.png" width="250">
    </td>
    <td align="center">
      <img src="https://raw.githubusercontent.com/otispresley/snmp-switch-manager/main/assets/screenshot7.png" width="250">
    </td>
  </tr>
  <tr>
    <td align="center">
      <img src="https://raw.githubusercontent.com/otispresley/snmp-switch-manager/main/assets/screenshot8.png" width="250">
    </td>
    <td align="center">
      <img src="https://raw.githubusercontent.com/otispresley/snmp-switch-manager/main/assets/screenshot9.png" width="250">
    </td>
    <td align="center">
      <img src="https://raw.githubusercontent.com/otispresley/snmp-switch-manager/main/assets/screenshot10.png" width="250">
    </td>
  </tr>
</table>

Available options include:

- SNMP connection overrides (community, port)
- Interface Include rules
- Interface Exclude rules
- Port Name (rename) rules
- Custom Diagnostic OIDs
- Uptime polling interval (configurable, default 300 seconds)

The Uptime polling interval controls how often the switch Uptime (sysUpTime)
diagnostic sensor is refreshed. This can be tuned per device to balance
responsiveness versus system load.

All option changes:
- Apply immediately
- Persist across restarts
- Safely remove or restore entities as rules change

Per-device **Device Options** can be configured from the integration options (⚙️ icon).

This allows advanced customization **without deleting and re-adding the device**.

#### Connection & Naming Overrides
- Override **SNMP community string**
- Override **SNMP port**

Overrides apply **only to the selected device** and do not affect other switches.

#### Interface Include / Exclude Rules
Control which interfaces are created as Home Assistant entities using rule-based matching:

- **Include rules**
  - Starts with / Contains / Ends with
  - Can explicitly include interfaces that vendor logic would otherwise exclude
- **Exclude rules**
  - Prevent entity creation and immediately remove existing matching entities
  - Exclude rules always take precedence

Rules are evaluated per device and do not require Home Assistant restarts.

#### Port Name Rules
Customize how interface names are displayed in Home Assistant without affecting the underlying SNMP data.

- **Regex-based rename rules**
  - Match interface names using regular expressions
  - Replace matched names with a normalized or user-friendly format
- **Per-device scope**
  - Rules apply **only to the selected device**
  - Different switches can use different naming conventions
- **Rule order matters**
  - Rules are evaluated top-to-bottom
  - The first matching rule is applied
- **Built-in defaults**
  - Common vendor formats (e.g. Cisco, Dell, generic SNMP) are provided
  - Built-in rules can be individually disabled or re-enabled

Notes:
- Renaming affects **display names only** — entity IDs and SNMP behavior remain unchanged
- Rule changes apply immediately and persist across restarts
- Advanced users can use full regex syntax; a simplified mode is planned for a future release

#### Custom Diagnostic SNMP OIDs
Override how diagnostic sensors are detected for devices with non-standard SNMP implementations:

- Manufacturer
- Model
- Firmware
- Hostname
- Uptime

Notes:
- Overrides apply **only to the selected device**
- Leave fields blank to fall back to automatic detection
- A reset option is available to restore defaults

---

## Lovelace card

### HACS (recommended)

You can install this card directly from HACS:

[![Open your Home Assistant instance and show the repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=OtisPresley&repository=snmp-switch-manager-card)

🚫 **No manual resource configuration is required.**

This card includes its editor automatically, so you do **not** need to add any additional JavaScript resources under  
**Settings → Dashboards → Resources**.

After installation, restart Home Assistant. The card will then be available as:

**Custom: SNMP Switch Manager Card**

---

### 🔁 Migrating from Manual to HACS Installation (Important)

If you previously installed this card manually using resource URLs, follow these steps to safely migrate to the HACS-managed version:

1. 🗑️ **Remove old resources** from  
   **Settings → Dashboards → Resources**
   - Remove:
     ```
     /local/community/snmp-switch-manager-card/snmp-switch-manager-card.js
     ```
     ```
     /local/community/snmp-switch-manager-card/snmp-switch-manager-card-editor.js
     ```

2. 📂 **Delete the old manually installed files** from: `/config/www/community/snmp-switch-manager-card/`
3. ✅ **Install the card via HACS** using the HACS button above.

4. 🔄 **Restart Home Assistant**

Once complete, everything will be fully managed by HACS and you will continue to receive automatic updates.

---

### Manual installation

1. Download the `snmp-switch-manager-card.js` file from the [SNMP Switch Manager Card repository](https://github.com/OtisPresley/snmp-switch-manager-card/tree/main/dist) and place it in Home Assistant here:
`/config/www/community/snmp-switch-manager-card/`

2. Add **only one** JavaScript resource under  
**Settings → Dashboards → Resources**:

   ```yaml
   url: /local/community/snmp-switch-manager-card/snmp-switch-manager-card.js
   type: module
   ```
   ⚠️ Do NOT add a separate editor resource. The editor is embedded in the card.
   
---

### Configuration

1. Place the card on any dashboard and edit via the GUI or in YAML:

   <table>
    <tr>
      <td align="center">
        <img src="https://raw.githubusercontent.com/otispresley/snmp-switch-manager/main/assets/screenshot1.png" width="250">
      </td>
    </tr>
  </table>

   ```yaml
   type: custom:snmp-switch-manager-card
   title: Core Switch
   view: panel
   ports_per_row: 24
   info_position: below
   label_size: 6
   anchor_entity: switch.gi1_0_1
   port_size: 18
   gap: 10
   
   # Optional display controls
   hide_diagnostics: false
   hide_virtual_interfaces: false
   
   # Optional panel background image (panel view only)
   background_image: /local/switches/core-switch.png
   ports_offset_x: 0
   ports_offset_y: 0
   ports_scale: 1
   
   # Optional per-port positioning overrides
   port_positions:
     Gi1/0/1: { x: 120, y: 80 }
     Gi1/0/2: { x: 150, y: 80 }
   ```

   The follows are descriptions of the settings:
   - `title` sets the text displayed at the tip of the card.
   - `view` sets the style that the card uses. `list` lists each port in a tile. `panel` show a representation of the front of a switch.
   - `ports_per_row` sets the number of ports to show in each row on the card when in panel view.
   - `panel width` The total width of the card in pixels when in panel view.
   - `info_position` displays the Diagnostics and Virtual Interfaces either `above` the phisical ports or `below` them.
   - `label_size` determines the font size used for the port labels when in panel view.
   - `anchor_entity` is any entity in your switch so it knows which ports and diagnostics to display.
   - `diagnostics` is a list of sensors you want to display in the diagnostics area.
   - `port_size` determines the size of the port images when in panel view.
   - `gap` determines how far apart the ports are when in panel view.
   - `hide_diagnostics` hides the Diagnostics panel entirely when set to `true`.
   - `hide_virtual_interfaces` hides the Virtual Interfaces panel entirely when set to `true`.
   - `background_image` sets a custom switch image for panel view.
   - `ports_offset_x` and `ports_offset_y` move all ports to align with the background image.
   - `ports_scale` scales all ports uniformly.
   - `port_positions` allows individual ports to be positioned manually.
   - `color_mode` controls how port colors are interpreted:
     - `state` (default): colors reflect Admin / Oper status
     - `speed`: colors reflect negotiated link speed
      
   Clicking a port opens a unified information dialog (used in both panel and list views) showing:

  - Interface name
  - Admin and Oper status
  - Speed
  - VLAN ID
  - Interface index
  
  The port power toggle updates live in the dialog as soon as the port state changes.

  <table>
    <tr>
      <td align="center">
        <img src="https://raw.githubusercontent.com/otispresley/snmp-switch-manager/main/assets/screenshot2.png" width="250">
      </td>
      <td align="center">
        <img src="https://raw.githubusercontent.com/otispresley/snmp-switch-manager/main/assets/screenshot3.png" width="250">
      </td>
      <td align="center">
        <img src="https://raw.githubusercontent.com/otispresley/snmp-switch-manager/main/assets/screenshot4.png" width="250">
      </td>
    </tr>
  </table>

### 🎨 Port Color Legend

Port colors can represent either **port state** or **link speed**, depending on the selected `color_mode`.

#### State Mode (default)
- 🟩 **Green** — Admin: Up · Oper: Up  
- 🟥 **Red** — Admin: Up · Oper: Down  
- 🟧 **Orange** — Admin: Down · Oper: Down  
- ⬜ **Gray** — Admin: Up · Oper: Not Present  

#### Speed Mode
- 🟦 **Blue** — 10 Gbps  
- 🟩 **Green** — 1 Gbps  
- 🟧 **Orange** — 100 Mbps  
- 🟥 **Red** — 10 Mbps  
- ⬜ **Gray** — Unknown or non-standard speed  

#### Example
```yaml
type: custom:snmp-switch-manager-card
device: SWITCH-BONUSCLOSET
color_mode: speed
```

ℹ️ If color_mode is not specified, the card defaults to state-based coloring for full backward compatibility.

---

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

### Open an Issue
- Open an issue on the [GitHub tracker](https://github.com/OtisPresley/snmp-switch-manager/issues) if you run into problems or have feature requests.
- Contributions and feedback are welcome!

If you find this integration useful and want to support development, you can:

[![Buy Me a Coffee](https://img.shields.io/badge/Support-Buy%20Me%20a%20Coffee-orange)](https://www.buymeacoffee.com/OtisPresley)
[![Donate via PayPal](https://img.shields.io/badge/Donate-PayPal-blue.svg)](https://paypal.me/OtisPresley)
