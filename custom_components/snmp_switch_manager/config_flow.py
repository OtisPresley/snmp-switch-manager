from __future__ import annotations

import os
import json
import re
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_COMMUNITY,
    DEFAULT_PORT,
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
    CONF_LEGACY_DEVICE_ID,
)
from .helpers import test_connection, get_sysname

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_SNMP_VERSION, default=SNMP_VERSION_V2C): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value=SNMP_VERSION_V2C, label="SNMP v2c"),
                    selector.SelectOptionDict(value=SNMP_VERSION_V3, label="SNMP v3"),
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        from .options_flow import OptionsFlowHandler
        return OptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = str(user_input[CONF_HOST]).strip()
            port = int(user_input.get(CONF_PORT, DEFAULT_PORT))
            version = str(user_input.get(CONF_SNMP_VERSION, SNMP_VERSION_V2C))

            await self.async_set_unique_id(f"{host}_{port}")

            # Stash for subsequent credential steps
            self._setup_host = host
            self._setup_port = port
            self._setup_version = version

            if version == SNMP_VERSION_V3:
                return await self.async_step_snmpv3()
            return await self.async_step_snmpv2c()

        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors)

    async def async_step_snmpv2c(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            community = str(user_input.get(CONF_COMMUNITY) or "").strip()
            if not community:
                errors[CONF_COMMUNITY] = "required"
            else:
                host = getattr(self, "_setup_host", "")
                port = int(getattr(self, "_setup_port", DEFAULT_PORT))

                try:
                    ok = await test_connection(self.hass, host, community, port)
                except Exception:
                    ok = False
                    errors["base"] = "unknown"
                if not ok:
                    if "base" not in errors:
                        errors["base"] = "cannot_connect"
                else:
                    try:
                        sysname = await get_sysname(self.hass, host, community, port)
                    except Exception:
                        sysname = ""
                    title = sysname or host

                    legacy_device_id = f"{host}:{port}:{community}"

                    await self.async_set_unique_id(f"{host}:{port}:{community}")
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=title,
                        data={
                            "host": host,
                            "port": port,
                            "community": community,
                            CONF_LEGACY_DEVICE_ID: legacy_device_id,
                            CONF_SNMP_VERSION: SNMP_VERSION_V2C,
                            "name": title,
                        },
                    )

        schema = vol.Schema({vol.Required(CONF_COMMUNITY): str})
        return self.async_show_form(step_id="snmpv2c", data_schema=schema, errors=errors)

    async def async_step_snmpv3(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = getattr(self, "_setup_host", "")
            port = int(getattr(self, "_setup_port", DEFAULT_PORT))

            username = str(user_input.get(CONF_SNMPV3_USERNAME) or "").strip()
            auth_protocol = str(user_input.get(CONF_SNMPV3_AUTH_PROTOCOL) or SNMPV3_AUTH_SHA).strip().lower()
            auth_password = str(user_input.get(CONF_SNMPV3_AUTH_PASSWORD) or "")
            priv_protocol = str(user_input.get(CONF_SNMPV3_PRIV_PROTOCOL) or SNMPV3_PRIV_NONE).strip().lower()
            priv_password = str(user_input.get(CONF_SNMPV3_PRIV_PASSWORD) or "")

            if not username:
                errors[CONF_SNMPV3_USERNAME] = "required"

            # Basic length validation (common device constraints)
            if auth_protocol != SNMPV3_AUTH_NONE:
                if len(auth_password) < 8 or len(auth_password) > 31:
                    errors[CONF_SNMPV3_AUTH_PASSWORD] = "invalid_password_length"
            if priv_protocol != SNMPV3_PRIV_NONE:
                if len(priv_password) < 8 or len(priv_password) > 31:
                    errors[CONF_SNMPV3_PRIV_PASSWORD] = "invalid_password_length"

            if not errors:
                settings = {
                    "host": host,
                    "port": port,
                    "version": SNMP_VERSION_V3,
                    "community": "",
                    CONF_SNMPV3_USERNAME: username,
                    CONF_SNMPV3_AUTH_PROTOCOL: auth_protocol,
                    CONF_SNMPV3_AUTH_PASSWORD: auth_password,
                    CONF_SNMPV3_PRIV_PROTOCOL: priv_protocol,
                    CONF_SNMPV3_PRIV_PASSWORD: priv_password,
                }
                ok = await test_connection(self.hass, host, "", port, snmp_settings=settings)
                if not ok:
                    errors["base"] = "cannot_connect"
                else:
                    sysname = await get_sysname(self.hass, host, "", port, snmp_settings=settings)
                    title = sysname or host

                    await self.async_set_unique_id(f"{host}:{port}:v3:{username}")
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=title,
                        data={
                            "host": host,
                            "port": port,
                            CONF_SNMP_VERSION: SNMP_VERSION_V3,
                            CONF_SNMPV3_USERNAME: username,
                            CONF_SNMPV3_AUTH_PROTOCOL: auth_protocol,
                            CONF_SNMPV3_AUTH_PASSWORD: auth_password,
                            CONF_SNMPV3_PRIV_PROTOCOL: priv_protocol,
                            CONF_SNMPV3_PRIV_PASSWORD: priv_password,
                            "name": title,
                        },
                    )

        schema = vol.Schema(
            {
                vol.Required(CONF_SNMPV3_USERNAME): str,
                vol.Required(CONF_SNMPV3_AUTH_PROTOCOL, default=SNMPV3_AUTH_SHA): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=SNMPV3_AUTH_SHA, label="HMAC-SHA"),
                            selector.SelectOptionDict(value=SNMPV3_AUTH_MD5, label="HMAC-MD5"),
                            selector.SelectOptionDict(value=SNMPV3_AUTH_NONE, label="None"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_SNMPV3_AUTH_PASSWORD, default=""): str,
                vol.Required(CONF_SNMPV3_PRIV_PROTOCOL, default=SNMPV3_PRIV_NONE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=SNMPV3_PRIV_DES, label="CBC-DES"),
                            selector.SelectOptionDict(value=SNMPV3_PRIV_NONE, label="None"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_SNMPV3_PRIV_PASSWORD, default=""): str,
            }
        )

        return self.async_show_form(step_id="snmpv3", data_schema=schema, errors=errors)


OID_FIELDS = [
    ("manufacturer", "Manufacturer OID"),
    ("model", "Model OID"),
    ("firmware", "Firmware OID"),
    ("hostname", "Hostname OID"),
    ("uptime", "Uptime OID"),
    ("contact", "Contact OID"),
    ("name", "Name OID"),
    ("location", "Location OID"),
]


def _normalize_oid(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    # Allow leading dot, store numeric dotted OID without it
    if v.startswith("."):
        v = v[1:]
    return v


def _is_valid_numeric_oid(value: str) -> bool:
    v = _normalize_oid(value)
    if not v:
        return True
    return bool(re.fullmatch(r"(\d+\.)*\d+", v))


def _split_list(value: str) -> list[str]:
    """Split a comma/newline separated string into a list of non-empty strings."""
    if not value:
        return []
    raw = value.replace(",", "\n").splitlines()
    return [v.strip() for v in raw if v.strip()]


def _join_list(values) -> str:
    if not values:
        return ""
    return "\n".join(str(v) for v in values if str(v).strip())


def load_database() -> dict:
    """Load the OID database from JSON files."""
    database = {}
    db_path = os.path.join(os.path.dirname(__file__), "database")
    if not os.path.exists(db_path):
        return database
    for filename in os.listdir(db_path):
        if filename.endswith(".json"):
            key = filename[:-5]
            try:
                with open(os.path.join(db_path, filename), "r", encoding="utf-8") as f:
                    database[key] = json.load(f)
            except Exception:
                pass
    return database

