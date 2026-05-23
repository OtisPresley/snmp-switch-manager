from __future__ import annotations

import time
import logging
from typing import Any, Dict

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo

from ..const import (
    POE_MODE_ATTRIBUTES,
    BW_MODE_ATTRIBUTES,
)
from ..snmp import SwitchSnmpClient

_LOGGER = logging.getLogger(__name__)


def _format_bps(bps: Any) -> str:
    """Format an integer bits-per-second value into a human-friendly string."""
    try:
        v = int(bps)
    except Exception:
        return "Disconnected"
    if v <= 0:
        return "Disconnected"
    if v >= 1_000_000_000:
        g = v / 1_000_000_000
        return f"{g:g} Gbps"
    if v >= 1_000_000:
        m = v / 1_000_000
        return f"{m:g} Mbps"
    if v >= 1_000:
        k = v / 1_000
        return f"{k:g} Kbps"
    return f"{v} bps"


def _speed_display(row: Any) -> str:
    """Return a human-friendly interface speed string for a row from ifTable."""
    try:
        admin = int(row.get('admin') or 0)
    except Exception:
        admin = 0
    try:
        oper = int(row.get('oper') or 0)
    except Exception:
        oper = 0

    # If admin is up but the link is not operationally up, treat as disconnected
    if admin == 1 and oper != 1:
        return 'Disconnected'

    bps = row.get('speed_bps')
    return _format_bps(bps)


ADMIN_STATE = {1: "Up", 2: "Down", 3: "Testing"}
OPER_STATE = {
    1: "Up",
    2: "Down",
    3: "Testing",
    4: "Unknown",
    5: "Dormant",
    6: "NotPresent",
    7: "LowerLayerDown",
}


class IfAdminSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(
        self,
        coordinator,
        entry_id: str,
        if_index: int,
        raw_name: str,
        display_name: str,
        alias: str,
        hostname: str,
        device_info: DeviceInfo,
        client: SwitchSnmpClient,
        icon_rules: list[dict[str, str]] | None = None,
    ):
        super().__init__(coordinator)
        self._display_name = None  # always defined for HA entity registry add
        self._entry_id = entry_id
        self._if_index = if_index
        self._raw_name = raw_name
        self._display_name = display_name
        self._icon_rules = icon_rules or []
        self._display = display_name
        self._alias = alias
        self._hostname = hostname
        self._client = client
        self._state_override = None
        self._state_override_time = None

        self._attr_unique_id = f"{entry_id}-if-{if_index}"
        # Name includes hostname so entity_id becomes e.g. switch.switch1_gi1_0_1
        self._attr_name = f"{hostname} {display_name}"
        self._attr_device_info = device_info
        
        # Calculate icon once during setup
        self._attr_icon = self._calculate_icon()

    def _calculate_icon(self) -> str:
        """Return an icon from user rules, or a premium dynamic default."""
        name_l = (self._display_name or self._raw_name or "").lower()
        for r in self._icon_rules:
            try:
                match = str(r.get("match") or "").lower()
                value = str(r.get("value") or "").lower()
                icon = str(r.get("icon") or "").strip()
                if not (match and value and icon):
                    continue
                if match == "starts with" and name_l.startswith(value.lower()):
                    return icon
                if match == "contains" and value.lower() in name_l:
                    return icon
                if match == "ends with" and name_l.endswith(value.lower()):
                    return icon
            except Exception:
                continue

        # Dynamic high-quality defaults:
        if name_l.startswith(("vl", "vlan")):
            return "mdi:lan"
        if name_l.startswith(("lo", "loopback")):
            return "mdi:lan-pending"
        if name_l.startswith(("po", "port-channel", "lag")):
            return "mdi:lan-connect"

        # Default for physical ports
        return "mdi:ethernet"

    @property
    def is_on(self) -> bool:
        if self._state_override_time is not None:
            if time.monotonic() - self._state_override_time < 10.0:
                return self._state_override == 1
            else:
                self._state_override_time = None
                self._state_override = None

        data = self.coordinator.data or {}
        row = data.get("ifTable", {}).get(self._if_index, {})
        return row.get("admin") == 1

    async def async_turn_on(self, **kwargs):
        ok = await self._client.set_admin_status(self._if_index, 1)
        if ok:
            self._state_override = 1
            self._state_override_time = time.monotonic()
            self.coordinator.data["ifTable"].setdefault(self._if_index, {})["admin"] = 1
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        ok = await self._client.set_admin_status(self._if_index, 2)
        if ok:
            self._state_override = 2
            self._state_override_time = time.monotonic()
            self.coordinator.data["ifTable"].setdefault(self._if_index, {})["admin"] = 2
            self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        data = self.coordinator.data or {}
        row = data.get("ifTable", {}).get(self._if_index, {})
        
        admin_val = row.get("admin", 0)
        if self._state_override_time is not None:
            if time.monotonic() - self._state_override_time < 10.0:
                admin_val = self._state_override
            else:
                self._state_override_time = None
                self._state_override = None

        attrs: Dict[str, Any] = {
            "Index": self._if_index,
            "Name": self._display,
            # Many switches leave ifAlias blank and place the user-visible port
            # description in ifDescr instead.
            "Alias": row.get("alias") or row.get("descr") or "",
            "Admin": ADMIN_STATE.get(admin_val, "Unknown"),
            "Oper": OPER_STATE.get(row.get("oper", 0), "Unknown"),
            "Speed": _speed_display(row),
        }

        vlan_id = row.get("vlan_id")
        if vlan_id is not None:
            try:
                attrs["VLAN ID"] = int(vlan_id)
            except Exception:
                pass

        # Trunk details
        # NOTE: Access ports often have a single "allowed" VLAN (their PVID). Do not
        # treat that as trunking. Prefer the coordinator's explicit flag, with a safe
        # fallback that only treats the interface as trunk when it carries multiple VLANs
        # and/or explicitly tagged VLANs are present.
        allowed_vlans = row.get("allowed_vlans") or []
        tagged_vlans = row.get("tagged_vlans") or []
        is_trunk = bool(row.get("is_trunk")) or len(allowed_vlans) > 1 or bool(tagged_vlans)
        if is_trunk:
            # Hide redundant VLAN ID on trunk ports
            attrs.pop("VLAN ID", None)

            native_vlan = row.get("native_vlan")
            if native_vlan is not None:
                try:
                    attrs["Native VLAN"] = int(native_vlan)
                except Exception:
                    pass

            if allowed_vlans:
                attrs["Allowed VLANs"] = allowed_vlans

            if tagged_vlans:
                attrs["Tagged VLANs"] = tagged_vlans

            untagged_vlans = row.get("untagged_vlans") or []
            if untagged_vlans:
                attrs["Untagged VLANs"] = untagged_vlans

        port_type = str(row.get("port_type") or "unknown")
        attrs["Port Type"] = port_type

        hide_ip_on_physical = bool(data.get("hide_ip_on_physical", False))

        from . import _ip_for_index
        ip = _ip_for_index(self._if_index, data.get("ip_by_ifindex", {}), data.get("ip_mask_by_ifindex", {}))
        if ip and not (hide_ip_on_physical and port_type == "physical"):
            attrs["IP"] = ip

        # PoE per-port power (optional)
        if (
          data.get("poe_enabled")
            and data.get("poe_mode") == POE_MODE_ATTRIBUTES
        ):
            poe_map = data.get("poe_power_mw") or {}
            mw = poe_map.get(self._if_index)
            if mw is not None:
                 try:
                     # All vendors store mW internally in our coordinator data for precision.
                     # This ensures the UI always displays Watts consistently (mW / 1000).
                     attrs["PoE Power (W)"] = round(float(mw) / 1000.0, 1)
                 except Exception:
                     pass

        # Bandwidth attributes (optional)
        if (
            data.get('bw_enabled')
            and data.get('bw_mode') == BW_MODE_ATTRIBUTES
        ):
            bw_row = (data.get('bandwidth') or {}).get(self._if_index) or {}
            # Throughput (bit/s)
            rx_bps = bw_row.get('rx_bps')
            tx_bps = bw_row.get('tx_bps')
            try:
                if rx_bps is not None:
                    attrs['RX Throughput (bps)'] = int(rx_bps)
                if tx_bps is not None:
                    attrs['TX Throughput (bps)'] = int(tx_bps)
            except Exception:
                pass
            # Totals (bytes)
            rx_oct = bw_row.get('rx_octets')
            tx_oct = bw_row.get('tx_octets')
            try:
                if rx_oct is not None:
                    attrs['RX Total (bytes)'] = int(rx_oct)
                if tx_oct is not None:
                    attrs['TX Total (bytes)'] = int(tx_oct)
            except Exception:
                pass
        return attrs
