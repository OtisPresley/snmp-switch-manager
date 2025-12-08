# Changelog
All notable changes to this project will be documented in this file.

> 📌 See also: [`ROADMAP.md`](./ROADMAP.md) for planned features and release targets.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### 🛣️ Roadmap Tracking

- 📶 **Bandwidth Sensors**  
  Planned for **v0.4.0**  
  🔗 See roadmap: [`#roadmap-bandwidth-sensors`](./ROADMAP.md#roadmap-bandwidth-sensors)

- 🌡️ **Switch Environmentals & CPU / Memory Usage**  
  Planned for **v0.4.0**  
  🔗 See roadmap: [`#roadmap-switch-environmentals`](./ROADMAP.md#roadmap-switch-environmentals)

- ⚡ **Power over Ethernet (PoE) Statistics**  
  Planned for **v0.4.0**  
  🔗 See roadmap: [`#roadmap-poe-statistics`](./ROADMAP.md#roadmap-poe-statistics)

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

## [0.3.1BETA1] - 2025-12-07
### Added
- 🎚️ Support for Mikrotik RouterOS

---

<!-- ROADMAP ANCHOR LINKS -->

<a name="roadmap-bandwidth-sensors"></a>
<a name="roadmap-switch-environmentals"></a>
<a name="roadmap-poe-statistics"></a>
