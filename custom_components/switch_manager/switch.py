from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Dict, List, Optional

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .snmp import SwitchSnmpClient, IANA_IFTYPE_SOFTWARE_LOOPBACK

_LOGGER = logging.getLogger(__name__)


@dataclass
class PortRow:
    index: int
    name: str
    alias: str
    admin: Optional[int]
    oper: Optional[int]
    ips: List  # list[(ip, mask, prefix)]
    iftype: Optional[int]


def _friendly_name_from_descr(descr: str, iftype: Optional[int]) -> str:
    """
    Convert Dell-style 'Unit: 1 Slot: 0 Port: 46 Gigabit - Level' into Gi1/0/46.
    For TenGig stack ports (20G) name them Tw1/0/X.
    VLAN/Loopback names are passed through as-is if they already look like VlXX / Lo0.
    """
    d = (descr or "").strip().lower()

    # Loopback: either explicit ifType or string match
    if iftype == IANA_IFTYPE_SOFTWARE_LOOPBACK or "software loopback" in d or d.startswith("loopback"):
        return "Lo0"

    # If the name already looks like "vlXX" (we propagate "Vl11" etc.)
    if d.startswith("vl"):
        # Recreate with capital V and lowercase l convention
        return "V" + d[1:]

    # Try to parse "Unit: X Slot: Y Port: Z ..." lines
    # We are quite tolerant and only care about numbers + speed class.
    unit = slot = port = None
    speed_class = ""
    parts = d.replace(",", " ").replace("  ", " ").split()
    try:
        for i, tok in enumerate(parts):
            if tok == "unit:" and i + 1 < len(parts):
                unit = int(parts[i + 1])
            elif tok == "slot:" and i + 1 < len(parts):
                slot = int(parts[i + 1])
            elif tok == "port:" and i + 1 < len(parts):
                port = int(parts[i + 1])
            elif tok in ("gigabit", "1gig", "1g"):
                speed_class = "Gi"
            elif tok in ("10g", "10gig", "10gigabit"):
                speed_class = "Te"
            elif tok in ("20g", "20gig", "20gigabit"):
                # Stacking / twinax
                speed_class = "Tw"
    except Exception:
        pass

    if unit is not None and slot is not None and port is not None and speed_class:
        return f"{speed_class}{unit}/{slot}/{port}"

    # Fallback: Title-cased descriptor
    return descr


def _build_port_row(raw: Dict[str, Any]) -> PortRow:
    name = _friendly_name_from_descr(raw.get("descr") or "", raw.get("type"))
    return PortRow(
        index=int(raw.get("index")),
        name=name,
        alias=raw.get("alias") or "",
        admin=raw.get("admin"),
        oper=raw.get("oper"),
        ips=raw.get("ips") or [],
        iftype=raw.get("type"),
    )


def _coordinator_key(entry: ConfigEntry) -> str:
    return f"{entry.entry_id}:coordinator"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    # Coordinator & client were stored during __init__.async_setup_entry
    store = hass.data.get(DOMAIN, {})
    coord = store.get(_coordinator_key(entry))
    client: SwitchSnmpClient = store.get("client")  # populated in __init__.py

    if coord is None or client is None:
        _LOGGER.error(
            "Could not resolve coordinator for entry_id=%s; hass.data keys: %s",
            entry.entry_id,
            list(store.keys()),
        )
        return

    ports_raw: List[Dict[str, Any]] = coord.data.get("ports", [])
    entities: List[SwitchManagerPort] = []

    for pr in ports_raw:
        row = _build_port_row(pr)

        # EXCLUSIONS:
        # - VLANs & Loopback stay
        # - Everything else stays as before (duplicates were already fixed upstream)

        entities.append(SwitchManagerPort(coord, entry, row))

    async_add_entities(entities, True)


class SwitchManagerPort(SwitchEntity):
    _attr_should_poll = False

    def __init__(self, coordinator, entry: ConfigEntry, row: PortRow) -> None:
        self.coordinator = coordinator
        self._entry = entry
        self._row = row
        self._attr_name = row.name
        self._attr_unique_id = f"{entry.entry_id}-if-{row.index}"

    @property
    def is_on(self) -> bool:
        # Admin state ‘1’ is up; anything else consider off
        return (self._row.admin or 0) == 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        # Future: write admin(1) via SNMP set if/when you enable writes
        return

    async def async_turn_off(self, **kwargs: Any) -> None:
        # Future: write admin(2) via SNMP set if/when you enable writes
        return

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        attrs: Dict[str, Any] = {
            "Index": self._row.index,
            "Name": self._row.name,
            "Alias": self._row.alias or "",
            "Admin": self._row.admin,
            "Oper": self._row.oper,
        }

        # IPv4 info (one or more addresses) – expose both ip/mask and CIDR
        # ips is List[(ip, mask, prefix)]
        if self._row.ips:
            # First address for convenience
            ip0, mask0, prefix0 = self._row.ips[0]
            attrs["IP address"] = ip0
            if mask0:
                attrs["Subnet mask"] = mask0
            if prefix0 is not None:
                attrs["CIDR"] = f"{ip0}/{prefix0}"

            # If there are multiple, expose them too (rare on VLANs/Lo)
            if len(self._row.ips) > 1:
                others = []
                for ipi, maski, prefi in self._row.ips[1:]:
                    if prefi is not None:
                        others.append(f"{ipi}/{prefi}")
                    elif maski:
                        others.append(f"{ipi} {maski}")
                    else:
                        others.append(ipi)
                attrs["Additional IPs"] = others

        return attrs

    async def async_update(self) -> None:
        # We read from the coordinator only
        refreshed: List[Dict[str, Any]] = self.coordinator.data.get("ports", [])
        for pr in refreshed:
            if int(pr.get("index")) == self._row.index:
                self._row = _build_port_row(pr)
                break
