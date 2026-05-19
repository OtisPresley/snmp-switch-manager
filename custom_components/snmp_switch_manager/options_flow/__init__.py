from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant import config_entries
import homeassistant.helpers.config_validation as cv
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ..const import (
    CONF_FEATURE_OVERRIDES,
    CONF_OVERRIDE_COMMUNITY,
    CONF_OVERRIDE_PORT,
    CONF_UPTIME_POLL_INTERVAL,
    DEFAULT_UPTIME_POLL_INTERVAL,
    MIN_UPTIME_POLL_INTERVAL,
    MAX_UPTIME_POLL_INTERVAL,
    CONF_SNMP_VERSION,
    SNMP_VERSION_V2C,
    SNMP_VERSION_V3,
    CONF_SNMPV3_USERNAME,
    CONF_SNMPV3_AUTH_PROTOCOL,
    CONF_SNMPV3_AUTH_PASSWORD,
    CONF_SNMPV3_PRIV_PROTOCOL,
    CONF_SNMPV3_PRIV_PASSWORD,
    SNMPV3_AUTH_NONE,
    SNMPV3_AUTH_SHA,
    SNMPV3_AUTH_MD5,
    SNMPV3_PRIV_NONE,
    SNMPV3_PRIV_DES,
)
from ..config_flow import load_database

from .interfaces import InterfacesOptionsMixin
from .naming import InterfacesNamingMixin
from .icons import InterfacesIconsMixin
from .bandwidth import BandwidthOptionsMixin
from .overrides_basic import OverridesBasicMixin
from .overrides_hardware import OverridesHardwareMixin
from .overrides_power import OverridesPowerMixin
from .overrides_env import OverridesEnvMixin

_LOGGER = logging.getLogger(__name__)


class OptionsFlowHandler(
    InterfacesOptionsMixin,
    InterfacesNamingMixin,
    InterfacesIconsMixin,
    BandwidthOptionsMixin,
    OverridesBasicMixin,
    OverridesHardwareMixin,
    OverridesPowerMixin,
    OverridesEnvMixin,
    config_entries.OptionsFlow,
):
    """Main Options Flow Handler composing all modular submenus and settings."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry
        self._options: dict = dict(config_entry.options)
        self._database = None

    def _get_database(self) -> dict:
        """Lazy-load and cache database JSON files to avoid repetitive parsing."""
        if self._database is None:
            _LOGGER.warning("Synchronous database load in options flow - pre-loading should occur in async_step_init")
            self._database = load_database()
        return self._database

    def _get_device_vendor(self) -> str:
        """Resolve the active vendor name for the device."""
        if hasattr(self._entry, "runtime_data") and self._entry.runtime_data:
            client = getattr(self._entry.runtime_data, "client", None)
            if client and client.cache.get("vendor"):
                return client.cache.get("vendor")
        overrides = self._options.get(CONF_FEATURE_OVERRIDES, {})
        for feature, data in overrides.items():
            if data and data.get("vendor"):
                return data.get("vendor")
        db = self._get_database()
        db_vendors = db.get("vendors", {}).get("vendors", [])
        if db_vendors:
            return db_vendors[0]["name"]
        return "Standard"

    def _apply_options(self) -> None:
        """Persist options immediately (only if changed)."""
        old = dict(self._entry.options)
        new = dict(self._options)
        if old == new:
            return

        self.hass.config_entries.async_update_entry(self._entry, options=new)
        self.hass.async_create_task(self.hass.config_entries.async_reload(self._entry.entry_id))

    def _get_override_defaults(self, feature: str) -> dict:
        """Resolve pre-populated defaults from existing overrides or database."""
        db = self._get_database()
        overrides = self._options.get(CONF_FEATURE_OVERRIDES, {}) or {}
        existing = overrides.get(feature, {})
        
        db_items = db.get(feature, {}).get(feature, [])
        first_db = db_items[0] if db_items else {}
        
        defaults = {}
        defaults["vendor"] = existing.get("vendor", first_db.get("vendors", [""])[0] if first_db.get("vendors") else "")
        defaults["method"] = existing.get("method", first_db.get("method", "get"))
        
        if feature == "cpu":
            defaults["oid"] = existing.get("oid", first_db.get("oid", ""))
            defaults["scale"] = existing.get("scale", first_db.get("scale", 1.0))
            defaults["unit"] = existing.get("unit", first_db.get("unit", "%"))
            defaults["description"] = existing.get("description", first_db.get("description", ""))
        elif feature == "memory":
            defaults["type"] = existing.get("type", first_db.get("type", "free_total"))
            defaults["oid"] = existing.get("oid", first_db.get("oid", ""))
            defaults["oid_free"] = existing.get("oid_free", first_db.get("oid_free", ""))
            defaults["oid_total"] = existing.get("oid_total", first_db.get("oid_total", ""))
        elif feature == "fans":
            defaults["oid_rpm"] = existing.get("oid_rpm", first_db.get("oid_rpm", ""))
            defaults["oid_status"] = existing.get("oid_status", first_db.get("oid_status", ""))
        elif feature == "psu":
            defaults["oid_status"] = existing.get("oid_status", first_db.get("oid_status", ""))
            defaults["oid_label"] = existing.get("oid_label", first_db.get("oid_label", ""))
            defaults["filter"] = existing.get("filter", first_db.get("filter", ""))
        elif feature == "temperature":
            defaults["oid"] = existing.get("oid", first_db.get("oid", ""))
            defaults["oid_state"] = existing.get("oid_state", first_db.get("oid_state", ""))
            defaults["oid_label"] = existing.get("oid_label", first_db.get("oid_label", ""))
        elif feature == "power":
            defaults["oid"] = existing.get("oid", first_db.get("oid", ""))
            defaults["description"] = existing.get("description", first_db.get("description", ""))
        elif feature == "poe":
            defaults["oid_budget"] = existing.get("oid_budget", first_db.get("oid_budget", ""))
            defaults["oid_used"] = existing.get("oid_used", first_db.get("oid_used", ""))
            defaults["oid_port_power"] = existing.get("oid_port_power", first_db.get("oid_port_power", ""))
            defaults["description"] = existing.get("description", first_db.get("description", ""))
            
        return defaults

    def _get_existing_entries_html(self, feature: str) -> str:
        """Format a clean, scrollable HTML table of existing OIDs, vendors, and descriptions."""
        db = self._get_database()
        
        db_key = "device_info" if feature == "device_info" else feature
        db_items = db.get(db_key, {}).get(db_key, [])
        if not db_items:
            return "<p>No existing database entries found.</p>"

        html_lines = [
            '<div style="max-height: 180px; overflow-y: auto; border: 1px solid var(--divider-color, #e0e0e0); border-radius: 8px; margin: 8px 0 16px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">'
            '<table style="width: 100%; border-collapse: collapse; text-align: left; font-family: var(--paper-font-body1_-_font-family, sans-serif); font-size: 13px;">'
            '<thead>'
            '<tr style="background-color: var(--table-header-background-color, var(--card-background-color, #fafafa)); border-bottom: 2px solid var(--divider-color, #e0e0e0); color: var(--secondary-text-color, #727272);">'
            '<th style="padding: 10px 12px; font-weight: 600;">Vendor</th>'
            '<th style="padding: 10px 12px; font-weight: 600;">OID(s)</th>'
            '<th style="padding: 10px 12px; font-weight: 600;">Description</th>'
            '</tr>'
            '</thead>'
            '<tbody>'
        ]

        for idx, item in enumerate(db_items):
            vendors = ", ".join(item.get("vendors", []))
            desc = item.get("description", "")
            
            if feature == "memory":
                m_type = item.get("type", "free_total")
                if m_type == "percentage":
                    oids = f"<code>{item.get('oid')}</code> (Percentage)"
                else:
                    oids = f"Free: <code>{item.get('oid_free')}</code><br>Total: <code>{item.get('oid_total')}</code>"
            elif feature == "fans":
                rpm = item.get("oid_rpm")
                status = item.get("oid_status")
                parts = []
                if rpm:
                    parts.append(f"RPM: <code>{rpm}</code>")
                if status:
                    parts.append(f"Status: <code>{status}</code>")
                oids = "<br>".join(parts)
            elif feature == "psu":
                oids = f"Status: <code>{item.get('oid_status')}</code>"
                if item.get("oid_label"):
                    oids += f"<br>Label: <code>{item.get('oid_label')}</code>"
            elif feature == "temperature":
                oids = f"Temp: <code>{item.get('oid')}</code>"
                if item.get("oid_state"):
                    oids += f"<br>State: <code>{item.get('oid_state')}</code>"
                if item.get("oid_label"):
                    oids += f"<br>Label: <code>{item.get('oid_label')}</code>"
            elif feature == "poe":
                parts = []
                if item.get("oid_budget"):
                    parts.append(f"Budget: <code>{item.get('oid_budget')}</code>")
                if item.get("oid_used"):
                    parts.append(f"Used: <code>{item.get('oid_used')}</code>")
                if item.get("oid_port_power"):
                    parts.append(f"Port Power: <code>{item.get('oid_port_power')}</code>")
                oids = "<br>".join(parts)
            elif feature == "device_info":
                parts = []
                if item.get("oid_mfg"):
                    parts.append(f"Mfg: <code>{item.get('oid_mfg')}</code>")
                if item.get("oid_model"):
                    parts.append(f"Model: <code>{item.get('oid_model')}</code>")
                if item.get("oid_firmware"):
                    parts.append(f"Firmware: <code>{item.get('oid_firmware')}</code>")
                if item.get("oid_hostname"):
                    parts.append(f"Hostname: <code>{item.get('oid_hostname')}</code>")
                if item.get("oid_uptime"):
                    parts.append(f"Uptime: <code>{item.get('oid_uptime')}</code>")
                oids = "<br>".join(parts)
            else: # cpu, power
                oids = f"<code>{item.get('oid')}</code>"

            row_style = 'border-bottom: 1px solid var(--divider-color, #e0e0e0);'
            if idx % 2 == 1:
                row_style += ' background-color: var(--table-row-alternative-background-color, rgba(0,0,0,0.02));'

            html_lines.append(
                f'<tr style="{row_style}">'
                f'<td style="padding: 10px 12px; font-weight: 500; color: var(--primary-text-color, #212121);">{vendors}</td>'
                f'<td style="padding: 10px 12px; line-height: 1.4; color: var(--primary-text-color, #212121);">{oids}</td>'
                f'<td style="padding: 10px 12px; color: var(--secondary-text-color, #727272);">{desc}</td>'
                f'</tr>'
            )

        html_lines.extend([
            '</tbody>',
            '</table>',
            '</div>'
        ])
        return "".join(html_lines)

    async def async_step_device_options(self, user_input=None) -> FlowResult:
        """Top-level Device Options menu."""
        return await self.async_step_init(user_input)

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Manage the options."""
        if self._database is None:
            self._database = await self.hass.async_add_executor_job(load_database)
        return self.async_show_menu(
            step_id="device_options",
            menu_options=[
                "connection_and_naming_overrides",
                "manage_interfaces",
                "bandwidth_sensors",
                "environmental_sensors",
                "feature_overrides",
            ],
        )

    async def async_step_back(self, user_input=None):
        """Return to the previous/top-level menu."""
        return await self.async_step_init()

    async def async_step_connection_and_naming_overrides(self, user_input=None) -> FlowResult:
        """Per-device connection overrides."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input.get("back_to_menu"):
                return await self.async_step_init()

            def _opt_str(key: str) -> str:
                return (user_input.get(key) or "").strip()

            current_version = str(
                self._options.get(CONF_SNMP_VERSION)
                or self._entry.data.get(CONF_SNMP_VERSION)
                or SNMP_VERSION_V2C
            )
            version = str(user_input.get(CONF_SNMP_VERSION) or current_version)
            if version not in (SNMP_VERSION_V2C, SNMP_VERSION_V3):
                version = SNMP_VERSION_V2C

            if version != current_version:
                self._options[CONF_SNMP_VERSION] = version

            comm = _opt_str(CONF_OVERRIDE_COMMUNITY)
            if comm:
                self._options[CONF_OVERRIDE_COMMUNITY] = comm
            else:
                self._options.pop(CONF_OVERRIDE_COMMUNITY, None)

            v3_user = _opt_str(CONF_SNMPV3_USERNAME)
            auth_proto = str(user_input.get(CONF_SNMPV3_AUTH_PROTOCOL) or "").strip().lower()
            auth_pass = str(user_input.get(CONF_SNMPV3_AUTH_PASSWORD) or "")
            priv_proto = str(user_input.get(CONF_SNMPV3_PRIV_PROTOCOL) or "").strip().lower()
            priv_pass = str(user_input.get(CONF_SNMPV3_PRIV_PASSWORD) or "")

            if version == SNMP_VERSION_V3:
                if v3_user:
                    self._options[CONF_SNMPV3_USERNAME] = v3_user
                else:
                    self._options.pop(CONF_SNMPV3_USERNAME, None)

                if auth_proto:
                    self._options[CONF_SNMPV3_AUTH_PROTOCOL] = auth_proto
                else:
                    self._options.pop(CONF_SNMPV3_AUTH_PROTOCOL, None)

                if auth_pass:
                    self._options[CONF_SNMPV3_AUTH_PASSWORD] = auth_pass
                else:
                    self._options.pop(CONF_SNMPV3_AUTH_PASSWORD, None)

                if priv_proto:
                    self._options[CONF_SNMPV3_PRIV_PROTOCOL] = priv_proto
                else:
                    self._options.pop(CONF_SNMPV3_PRIV_PROTOCOL, None)

                if priv_pass:
                    self._options[CONF_SNMPV3_PRIV_PASSWORD] = priv_pass
                else:
                    self._options.pop(CONF_SNMPV3_PRIV_PASSWORD, None)

            if version == SNMP_VERSION_V3:
                if not v3_user:
                    errors[CONF_SNMPV3_USERNAME] = "required"
                if auth_proto and auth_proto != SNMPV3_AUTH_NONE:
                    if len(auth_pass) < 8 or len(auth_pass) > 31:
                        errors[CONF_SNMPV3_AUTH_PASSWORD] = "invalid_password_length"
                if priv_proto and priv_proto != SNMPV3_PRIV_NONE:
                    if len(priv_pass) < 8 or len(priv_pass) > 31:
                        errors[CONF_SNMPV3_PRIV_PASSWORD] = "invalid_password_length"

            port_raw = (user_input.get(CONF_OVERRIDE_PORT) or "").strip()
            if not port_raw:
                self._options.pop(CONF_OVERRIDE_PORT, None)
            else:
                try:
                    self._options[CONF_OVERRIDE_PORT] = int(port_raw)
                except Exception:
                    errors[CONF_OVERRIDE_PORT] = "invalid_port"

            uptime_raw = str(user_input.get(CONF_UPTIME_POLL_INTERVAL, "")).strip()
            try:
                uptime_val = int(uptime_raw)
                if uptime_val < MIN_UPTIME_POLL_INTERVAL or uptime_val > MAX_UPTIME_POLL_INTERVAL:
                    raise ValueError("out_of_range")
                current_uptime = int(self._options.get(CONF_UPTIME_POLL_INTERVAL, DEFAULT_UPTIME_POLL_INTERVAL))
                if uptime_val != current_uptime:
                    self._options[CONF_UPTIME_POLL_INTERVAL] = uptime_val
            except Exception:
                errors[CONF_UPTIME_POLL_INTERVAL] = "invalid_uptime_interval"

            if not errors:
                self._apply_options()
                return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SNMP_VERSION,
                    default=str(self._options.get(CONF_SNMP_VERSION, self._entry.data.get(CONF_SNMP_VERSION, SNMP_VERSION_V2C))),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=SNMP_VERSION_V2C, label="SNMP v2c"),
                            selector.SelectOptionDict(value=SNMP_VERSION_V3, label="SNMP v3"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_OVERRIDE_COMMUNITY,
                    default=str(self._options.get(CONF_OVERRIDE_COMMUNITY, "")),
                ): str,
                vol.Optional(
                    CONF_OVERRIDE_PORT,
                    default=str(self._options.get(CONF_OVERRIDE_PORT, "")),
                ): str,
                vol.Optional(
                    CONF_UPTIME_POLL_INTERVAL,
                    default=str(self._options.get(CONF_UPTIME_POLL_INTERVAL, DEFAULT_UPTIME_POLL_INTERVAL)),
                ): str,
                vol.Optional(
                    CONF_SNMPV3_USERNAME,
                    default=str(self._options.get(CONF_SNMPV3_USERNAME, self._entry.data.get(CONF_SNMPV3_USERNAME, ""))),
                ): str,
                vol.Optional(
                    CONF_SNMPV3_AUTH_PROTOCOL,
                    default=str(self._options.get(CONF_SNMPV3_AUTH_PROTOCOL, self._entry.data.get(CONF_SNMPV3_AUTH_PROTOCOL, SNMPV3_AUTH_SHA))),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=SNMPV3_AUTH_SHA, label="HMAC-SHA"),
                            selector.SelectOptionDict(value=SNMPV3_AUTH_MD5, label="HMAC-MD5"),
                            selector.SelectOptionDict(value=SNMPV3_AUTH_NONE, label="None"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_SNMPV3_AUTH_PASSWORD,
                    default=str(self._options.get(CONF_SNMPV3_AUTH_PASSWORD, self._entry.data.get(CONF_SNMPV3_AUTH_PASSWORD, ""))),
                ): str,
                vol.Optional(
                    CONF_SNMPV3_PRIV_PROTOCOL,
                    default=str(self._options.get(CONF_SNMPV3_PRIV_PROTOCOL, self._entry.data.get(CONF_SNMPV3_PRIV_PROTOCOL, SNMPV3_PRIV_NONE))),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=SNMPV3_PRIV_DES, label="CBC-DES"),
                            selector.SelectOptionDict(value=SNMPV3_PRIV_NONE, label="None"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_SNMPV3_PRIV_PASSWORD,
                    default=str(self._options.get(CONF_SNMPV3_PRIV_PASSWORD, self._entry.data.get(CONF_SNMPV3_PRIV_PASSWORD, ""))),
                ): str,
                vol.Optional("back_to_menu", default=False): cv.boolean,
            }
        )

        return self.async_show_form(
            step_id="connection_and_naming_overrides",
            data_schema=schema,
            errors=errors,
        )
