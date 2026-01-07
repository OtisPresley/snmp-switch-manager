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
    - [Bandwidth Sensors](#bandwidth-sensors)
- [Lovelace card](#lovelace-card)
  - [HACS (recommended)](#hacs-recommended-1)
  - [Migrating from Manual to HACS Installation](#-migrating-from-manual-to-hacs-installation-important)
  - [Manual installation](#manual-installation)
  - [Configuration](#configuration-1)
  - [Drag-and-Drop Port Calibration (Panel View)](#-drag-and-drop-port-calibration-panel-view)
  - [Bandwidth Monitoring & History Graphs](#-bandwidth-monitoring--history-graphs)
  - [Performance Notes](#-performance-notes)
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
  <tr>
    <td align="center">
      <img src="https://raw.githubusercontent.com/otispresley/snmp-switch-manager/main/assets/screenshot11.png" width="250">
    </td>
    <td align="center">
      <img src="https://raw.githubusercontent.com/otispresley/snmp-switch-manager/main/assets/screenshot12.png" width="250">
    </td>
  </tr>
</table>

Available options include:

- SNMP connection overrides (community, port)
  - Uptime polling interval (configurable, default 300 seconds)
- Interface Include rules
- Interface Exclude rules
- Port Name (rename) rules
- Custom Diagnostic OIDs
- Bandwidth Sensors

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

ℹ️ Interface Include / Exclude rules affect **entity creation only**.
They do **not** control Bandwidth Sensors.

Bandwidth Sensors use their own independent rule set.

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

#### Bandwidth Sensors
Enable optional per-device bandwidth monitoring using SNMP counters. Bandwidth monitoring supports **Sensors** and **Attributes** modes:
- **Sensors mode:** per-port RX/TX bandwidth sensors
- **Attributes mode:** bandwidth values exposed as attributes on each port entity

- RX / TX throughput sensors (bits per second)
- Total RX / TX traffic sensors
- Configurable polling interval
- Independent include and exclude rules

Notes:
- Bandwidth rules are **completely independent** from Interface Include / Exclude rules
- Exclude rules always take precedence
- Rule changes apply immediately and persist across restarts
- Sensors are created only for interfaces matching the rules
- Bandwidth values remain raw numeric values (bits per second / bytes) to ensure accuracy and consistency with switch CLIs

#### Attributes vs Sensors Modes

Several SNMP Switch Manager features support **two operating modes**: **Attributes mode** and **Sensors mode**.  
Mode selection is configured **per device** via **Device Options** and applies immediately without restarting Home Assistant.
Attributes contain no history in Home Assistant where Sensors do. If you want to create graphs or historical data, use Sensors.

##### Sensors Mode
In **Sensors mode**, individual Home Assistant `sensor` entities are created for each supported metric.

**Best for:**
- History graphs
- Long-term statistics
- Automations based on numeric thresholds

**Characteristics:**
- One sensor per metric (and per instance, where applicable)
- Native numeric values suitable for charts and statistics
- Higher entity count

##### Attributes Mode
In **Attributes mode**, metrics are exposed as **attributes on a single parent sensor** instead of individual sensor entities.

**Best for:**
- Cleaner entity lists
- Dashboards and UI display
- Reduced database and recorder load

**Characteristics:**
- No per-metric sensors are created
- Values appear as attributes on a single sensor
- Attributes update on the same polling interval as Sensors mode
- Attributes are not recorded individually by Home Assistant

#### Environment Monitoring

Environment monitoring includes system health and operational metrics such as:
- CPU utilization
- Memory usage
- System / chassis temperature
- Fan speed and status
- Power supply (PSU) status

##### Environment — Sensors Mode
- Individual sensors are created for each supported metric
- Examples include CPU utilization (5s / 60s / 300s), memory usage, system temperature, fan RPM, and PSU status

##### Environment — Attributes Mode
- A single sensor named **Environment** is created
- All supported environment values are exposed as attributes on that sensor

> Environment sensors and attributes are created **only when valid SNMP data is reported** by the device.

#### Power over Ethernet (PoE)

PoE monitoring reports switch-wide power usage and health using standard SNMP PoE MIBs where available.

##### Metrics
- PoE budget total (W)
- PoE power used (W)
- PoE power available (W)
- PoE health status (`HEALTHY`, `DISABLED`, `FAULTY`)

##### PoE — Sensors Mode
- Individual sensors are created for each PoE metric

##### PoE — Attributes Mode
- A single sensor named **Power over Ethernet** is created
- All PoE metrics are exposed as attributes

> PoE entities are created only when the device reports valid PoE data.

#### Upgrade Notes (v0.4.0)

Users upgrading from **v0.3.x** should note:
- New Attributes vs Sensors modes are available for Environment, PoE, and Bandwidth
- Switching modes automatically cleans up obsolete entities
- No manual entity removal is required
- Existing device and vendor support is preserved

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

1. Download the `snmp-switch-manager-card.js` file and place it in Home Assistant here:
`/config/www/community/snmp-switch-manager-card/`

2. Add **only one** JavaScript resource under  
**Settings → Dashboards → Resources**:

   ```yaml
   url: /local/community/snmp-switch-manager-card/snmp-switch-manager-card.js
   type: module
   ```
   ⚠️ Do NOT add a separate editor resource. The editor is embedded in the card.
   
---

## Configuration

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
    title: ""
    view: panel
    color_mode: state
    ports_per_row: 24
    panel_width: 940
    gap: 10
    show_labels: false
    label_size: 6
    info_position: below
    hide_diagnostics: false
    hide_virtual_interfaces: false
    calibration_mode: false
    device: switch_study
    background_image: /local/images/N1108P-ON_front_black.png
    port_positions:
      Gi1/0/1:
        x: 386.4295959472656
        "y": 24.34100341796875
      Gi1/0/2:
        x: 386.4295959472656
        "y": 55.947601318359375
      Gi1/0/3:
        x: 422.4835205078125
        "y": 24.34100341796875
      Gi1/0/4:
        x: 422.4835205078125
        "y": 55.947601318359375
      Gi1/0/5:
        x: 458.5374450683594
        "y": 24.34100341796875
      Gi1/0/6:
        x: 458.5374450683594
        "y": 55.947601318359375
      Gi1/0/7:
        x: 494.59136962890625
        "y": 24.34100341796875
      Gi1/0/8:
        x: 494.59136962890625
        "y": 55.947601318359375
      Gi1/0/10:
        x: 543.7317199707031
        "y": 55.947601318359375
      Gi1/0/9:
        x: 543.7317199707031
        "y": 24.34100341796875
      Gi1/0/11:
        x: 591.5968017578125
        "y": 20.962440490722656
      Gi1/0/12:
        x: 591.5968017578125
        "y": 59.34493637084961
    state_colors:
      up_up: "#118d3c"
      up_down: "#9c3030"
      down_down: "#9d6606"
    port_scale: 1.2
    label_bg_color: "#050505"
    label_numbers_only: false
    virtual_overrides: []
    show_uplinks_separately: false
    uplink_ports:
      - Gi1/0/9
      - Gi1/0/10
      - Gi1/0/11
      - Gi1/0/12
    speed_click_opens_graph: false
    hide_ports: []
   ```
  
  ### Configuration Options
  The following are descriptions of the settings:
  
  #### Core
  - `title` — Card title text.
  - `view` — `panel` (switch face) or `list` (rows/tiles).
  - `device` — **Preferred** device selector (Device Registry entry id/slug used by the card).
  - `device_name` — **Legacy** device selector (kept for compatibility; prefer `device`).
  - `color_mode` — `state` (default) or `speed`.
  
  #### Panel layout (panel view)
  - `ports_per_row` — Number of ports per row.
  - `panel_width` — Panel width in pixels.
  - `port_size` — Port icon size.
  - `gap` — Spacing between ports.
  - `ports_scale` — Uniform scaling factor for ports.
  - `port_scale` — **Alias** for `ports_scale` (compatibility).
  - `background_image` — Background image URL (panel view).
  - `port_positions` — Per-port `{x,y}` overrides (often generated by Layout Editor).
  - `calibration_mode` — Enables the Layout Editor (panel view).
  
  #### Labels (panel view)
  - `show_labels` — Show/hide labels under ports.
  - `label_size` — Label font size.
  - `label_numbers_only` — Show only the numeric portion of labels.
  - `label_color` — Override label text color.
  - `label_bg_color` — Override label background color (panel view only).
  
  #### Sections & visibility
  - `info_position` — `above` or `below` (Diagnostics/Virtual Interfaces relative to ports).
  - `hide_diagnostics` — Hide diagnostics panel.
  - `hide_virtual_interfaces` — Hide virtual interfaces panel.
  - `hide_ports` — Hide specific ports (list or YAML array of port names).
  
  #### Diagnostics
  - `diagnostics_order` — Order of discovered diagnostics (e.g., hostname, manufacturer…).
  - `diagnostics_enabled` — Enable/disable individual diagnostics by key.
  - `diagnostics` — **Legacy** manual sensor list (compatibility; discovery is preferred).
  
  #### Physical vs virtual classification
  - `physical_prefixes` — Comma-separated prefixes treated as Physical.
  - `physical_regex` — Optional regex override (takes precedence).
  - `virtual_overrides` — Explicit list of interfaces to treat as virtual.
  
  #### Uplinks (layout behavior only)
  - `show_uplinks_separately` — Enables uplink handling **in Layout Editor only**.
  - `uplink_ports` — List of uplink ports (used by Layout Editor / Smart Assist).
  
  #### Speed-mode click behavior
  - `speed_click_opens_graph` — When `color_mode: speed` and bandwidth sensors exist, clicking a port opens the bandwidth graph first.
  
  #### Color overrides
  - `state_colors` — Override colors used in state mode (e.g., `up_up`, `up_down`, `down_down`, etc.).
  - `speed_colors` — Override colors used in speed mode (keys like `10 Mbps`, `100 Mbps`, `Unknown`, etc.).

      
   Clicking a port opens a unified information dialog (used in both panel and list views) showing:

  - Interface name
  - Admin and Oper status
  - RX and TX throughput and cumulative
  - Speed
  - VLAN ID / Trunk information
  - Interface index
  - Turn on/off button
  - Graph button
  
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
    <tr>
      <td align="center">
        <img src="https://raw.githubusercontent.com/otispresley/snmp-switch-manager/main/assets/screenshot13.png" width="250">
      </td>
      <td align="center">
        <img src="https://raw.githubusercontent.com/otispresley/snmp-switch-manager/main/assets/screenshot14.png" width="250">
      </td>
      <td align="center">
        <img src="https://raw.githubusercontent.com/otispresley/snmp-switch-manager/main/assets/screenshot15.png" width="250">
      </td>
    </tr>
  </table>

**Example using vertical stack card showing the switch ports duplicated with the first row showing port state colors and the second row showing port speed colors.** Thanks to [@larieu](https://github.com/larieu) for contributing this.
 <table>
    <tr>
      <td align="center">
        <img src="https://raw.githubusercontent.com/otispresley/snmp-switch-manager/main/assets/screenshot16.png" width="250">
      </td>
    </tr>
  </table>

**24 port switch:**
```yaml
  type: vertical-stack
  cards:
    - type: custom:snmp-switch-manager-card
      title: ""
      view: panel
      color_mode: state
      ports_per_row: 24
      panel_width: 1480
      port_size: 36
      gap: 10
      show_labels: false
      label_size: 8
      info_position: below
      hide_diagnostics: true
      hide_virtual_interfaces: true
      calibration_mode: false
      device: gs1900_24ep
      ports_scale: 1.5
    - type: custom:snmp-switch-manager-card
      title: ""
      view: panel
      color_mode: speed
      ports_per_row: 24
      panel_width: 1480
      port_size: 36
      gap: 10
      show_labels: true
      label_size: 24
      info_position: below
      hide_diagnostics: false
      hide_virtual_interfaces: true
      calibration_mode: false
      device: gs1900_24ep
      ports_scale: 1.5
  title: SNMP Switch 24
  grid_options:
    columns: 24
    rows: auto
```

**8 port switch:**
```yaml
  type: vertical-stack
  cards:
    - type: custom:snmp-switch-manager-card
      title: ""
      view: panel
      color_mode: state
      ports_per_row: 8
      panel_width: 740
      port_size: 36
      gap: 10
      show_labels: false
      label_size: 8
      info_position: below
      hide_diagnostics: true
      hide_virtual_interfaces: true
      calibration_mode: false
      device: gs1900_8hp_01
      ports_scale: 1.5
    - type: custom:snmp-switch-manager-card
      title: ""
      view: panel
      color_mode: speed
      ports_per_row: 8
      panel_width: 740
      port_size: 36
      gap: 10
      show_labels: true
      label_size: 24
      info_position: below
      hide_diagnostics: false
      hide_virtual_interfaces: true
      calibration_mode: false
      device: gs1900_8hp_01
      ports_scale: 1.5
title: SNMP Switch 08 - 01
```

---

## 🧩 Layout Editor (Panel View)

The SNMP Switch Manager Card includes a built-in **Layout Editor** designed to make aligning ports with real switch faceplates fast and intuitive.

### What it does
- Enables **visual drag-and-drop positioning** of ports
- Supports precise alignment over custom background images
- Eliminates trial-and-error placement using raw coordinates

### How to use
1. Enable **Layout Editor** in the card editor
2. Use the on-card tools to:
   - Move ports
   - Adjust scale and offsets
   - Define port grouping and order
3. When finished, click the **close (✕) button** on the card to exit Layout Editor instantly
4. Save the card configuration to persist changes

> ℹ️ Layout Editor controls only affect layout behavior and do not change port data or device state.

### Generated configuration
The Layout Editor produces standard configuration values such as:

```yaml
ports_scale: 1
port_positions:
  Gi1/0/1: { x: 120, y: 80 }
  Gi1/0/2: { x: 150, y: 80 }
```

### ❌ What was removed (and should NOT appear anywhere)
The following options are **no longer used** and should not be documented:

- `ports_offset_x`
- `ports_offset_y`

Alignment and positioning are now handled entirely through:
- `ports_scale`
- `port_positions`
- Layout Editor interactions

This keeps the configuration simpler and avoids confusion or save-time validation issues.

---

## 🔍 Sanity check (we’re good)
- CHANGELOG entry **does not mention** these fields ✅
- Layout Editor description remains accurate ✅
- No backward-compat confusion introduced ✅

If you want, next we can:
- Do a **final README consistency sweep** (only what exists in the editor)
- Or prepare a **clean migration note** for users upgrading from ≤0.3.4

You’re in great shape for **v0.3.5-beta.1** 🚀

## 📈 Bandwidth Monitoring & History Graphs

When **Bandwidth Sensors** are enabled in the **SNMP Switch Manager integration**, the Switch Manager card automatically enhances the port popup with real-time throughput data and historical graphs.

### What’s included
- **RX and TX throughput values** displayed directly in the port popup
- 📊 **History graph button** per interface
- RX and TX plotted together in a single statistics graph
- Uses Home Assistant’s native **Statistics Graph** card

### Popup behavior
- The bandwidth graph opens in a **modal popup**
- Includes a **manual refresh button**
- Prevents constant redraws and unnecessary re-renders
- Popup remains visible until explicitly closed by the user

### Conditional display
The bandwidth section is shown **only when all conditions are met**:
- Bandwidth Sensors are enabled for the device
- The interface has valid RX and TX sensor entities
- Sensor values are numeric and available

Interfaces without bandwidth sensors remain unchanged and do not show empty fields or inactive controls.

> ℹ️ No additional card configuration is required.  
> The card automatically detects and uses the bandwidth sensors created by the integration.

---

## ❓ Contextual Help

Most editor options include a **help icon** providing detailed explanations and usage guidance.
These hints adapt based on the current view and enabled features, helping keep the interface clean while still offering advanced control when needed.

---

## 🧠 Performance Notes

- The history graph does **not auto-refresh** continuously
- A manual refresh button is provided to:
  - Improve dashboard performance
  - Avoid flickering or unpredictable redraw behavior
- This mirrors the behavior of a standalone Statistics Graph card while keeping the UI lightweight

---

## 🎨 Port Color Legend

  Port colors can represent either **port state** or **link speed**, depending on the selected `color_mode`. The colors represented are the default. You can set your own custom colors in the card configuration.
  
  ### State Mode (default)
  - 🟩 **Green** — Admin: Up · Oper: Up  
  - 🟥 **Red** — Admin: Up · Oper: Down  
  - 🟧 **Orange** — Admin: Down · Oper: Down  
  - ⬜ **Gray** — Admin: Up · Oper: Not Present  
  
  ### Speed Mode

  When `color_mode: speed` is enabled, port colors represent the negotiated link speed:
  
  - <img src="https://singlecolorimage.com/get/9ca3af/18x18" width="18" height="18" style="vertical-align:middle" /> **Gray** — 10 Mbps
  - <img src="https://singlecolorimage.com/get/f59e0b/18x18" width="18" height="18" style="vertical-align:middle" /> **Orange** — 100 Mbps
  - <img src="https://singlecolorimage.com/get/22c55e/18x18" width="18" height="18" style="vertical-align:middle" /> **Green** — 1 Gbps
  - <img src="https://singlecolorimage.com/get/14b8a6/18x18" width="18" height="18" style="vertical-align:middle" /> **Teal** — 2.5 Gbps
  - <img src="https://singlecolorimage.com/get/0ea5e9/18x18" width="18" height="18" style="vertical-align:middle" /> **Cyan** — 5 Gbps
  - <img src="https://singlecolorimage.com/get/3b82f6/18x18" width="18" height="18" style="vertical-align:middle" /> **Blue** — 10 Gbps
  - <img src="https://singlecolorimage.com/get/6366f1/18x18" width="18" height="18" style="vertical-align:middle" /> **Indigo** — 20 Gbps
  - <img src="https://singlecolorimage.com/get/8b5cf6/18x18" width="18" height="18" style="vertical-align:middle" /> **Violet** — 25 Gbps
  - <img src="https://singlecolorimage.com/get/a855f7/18x18" width="18" height="18" style="vertical-align:middle" /> **Purple** — 40 Gbps
  - <img src="https://singlecolorimage.com/get/d946ef/18x18" width="18" height="18" style="vertical-align:middle" /> **Fuchsia** — 50 Gbps
  - <img src="https://singlecolorimage.com/get/ec4899/18x18" width="18" height="18" style="vertical-align:middle" /> **Pink** — 100 Gbps
  - <img src="https://singlecolorimage.com/get/ef4444/18x18" width="18" height="18" style="vertical-align:middle" /> **Red** — Unknown or unsupported speed

  > ℹ️ Speed values are automatically parsed from SNMP attributes and normalized.
  > The card supports both numeric (e.g. `2500`, `100000`) and textual
  > representations (e.g. `2.5G`, `25Gbps`, `100G`).

  ### Example
  ```yaml
  type: custom:snmp-switch-manager-card
  device: SWITCH-BONUSCLOSET
  color_mode: speed
  ```
  
  > ℹ️ If color_mode is not specified, the card defaults to state-based coloring for full backward compatibility.

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
