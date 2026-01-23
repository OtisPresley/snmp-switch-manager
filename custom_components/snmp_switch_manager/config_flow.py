from __future__ import annotations

import re
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_COMMUNITY,
    DEFAULT_PORT,
    CONF_CUSTOM_OIDS,
    CONF_ENABLE_CUSTOM_OIDS,
    CONF_RESET_CUSTOM_OIDS,
    CONF_OVERRIDE_COMMUNITY,
    CONF_OVERRIDE_PORT,
    CONF_UPTIME_POLL_INTERVAL,
    DEFAULT_UPTIME_POLL_INTERVAL,
    MIN_UPTIME_POLL_INTERVAL,
    MAX_UPTIME_POLL_INTERVAL,
    CONF_INCLUDE_STARTS_WITH,
    CONF_INCLUDE_CONTAINS,
    CONF_INCLUDE_ENDS_WITH,
    CONF_EXCLUDE_STARTS_WITH,
    CONF_EXCLUDE_CONTAINS,
    CONF_EXCLUDE_ENDS_WITH,
    CONF_PORT_RENAME_USER_RULES,
    CONF_PORT_RENAME_DISABLED_DEFAULT_IDS,
    CONF_ICON_RULES,
    DEFAULT_PORT_RENAME_RULES,
    BUILTIN_VENDOR_FILTER_RULES,
    CONF_DISABLED_VENDOR_FILTER_RULE_IDS,
    CONF_BW_ENABLE,
    CONF_BW_INCLUDE_RULES,
    CONF_BW_EXCLUDE_RULES,
    CONF_BANDWIDTH_POLL_INTERVAL,
    DEFAULT_BANDWIDTH_POLL_INTERVAL,
    CONF_POE_POLL_INTERVAL,
    DEFAULT_POE_POLL_INTERVAL,
    CONF_ENV_POLL_INTERVAL,
    DEFAULT_ENV_POLL_INTERVAL,
    CONF_BW_INCLUDE_STARTS_WITH,
    CONF_BW_INCLUDE_CONTAINS,
    CONF_BW_INCLUDE_ENDS_WITH,
    CONF_BW_EXCLUDE_STARTS_WITH,
    CONF_BW_EXCLUDE_CONTAINS,
    CONF_BW_EXCLUDE_ENDS_WITH,
    # Bandwidth history mode
    CONF_BW_MODE,
    BW_MODE_SENSORS,
    BW_MODE_ATTRIBUTES,
    # Environmental & PoE options
    CONF_ENV_ENABLE,
    CONF_ENV_MODE,
    ENV_MODE_SENSORS,
    ENV_MODE_ATTRIBUTES,
    CONF_POE_ENABLE,
    CONF_POE_MODE,
    POE_MODE_SENSORS,
    CONF_POE_PER_PORT_POWER,
    POE_MODE_ATTRIBUTES,
    CONF_BW_RX_THROUGHPUT_ICON,
    CONF_BW_TX_THROUGHPUT_ICON,
    CONF_BW_RX_TOTAL_ICON,
    CONF_BW_TX_TOTAL_ICON,
    CONF_HIDE_IP_ON_PHYSICAL,
    CONF_HIDE_IP_ON_PHYSICAL_INTERFACES,
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
    SNMPV3_PRIV_AES,
    CONF_LEGACY_DEVICE_ID,
)
from .snmp import test_connection, get_sysname

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
        return OptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = str(user_input[CONF_HOST]).strip()
            port = int(user_input.get(CONF_PORT, DEFAULT_PORT))
            version = str(user_input.get(CONF_SNMP_VERSION, SNMP_VERSION_V2C))

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


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry
        # Work on a mutable copy; persisted via async_update_entry
        self._options: dict = dict(config_entry.options)

    def _apply_options(self) -> None:
        """Persist options immediately (only if changed).

        We avoid forcing a reload when the resulting options are identical,
        to prevent unnecessary coordinator churn.
        """
        old = dict(self._entry.options)
        new = dict(self._options)
        if old == new:
            return

        self.hass.config_entries.async_update_entry(self._entry, options=new)

        # Reload entry so changes apply without requiring user to restart HA.
        # Schedule rather than await (OptionsFlow methods are sync helpers here).
        self.hass.async_create_task(self.hass.config_entries.async_reload(self._entry.entry_id))


    async def async_step_device_options(self, user_input=None) -> FlowResult:
        """Top-level Device Options menu.

        The menu step_id is "device_options". Home Assistant may resume
        an options flow directly at that step, so we provide a handler
        method with the matching name.
        """

        return await self.async_step_init(user_input)

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Manage the options."""
        return self.async_show_menu(
            step_id="device_options",
            menu_options=[
                # Keep Connection & Name first per UX request
                "connection_and_naming_overrides",
                "manage_interfaces",
                "bandwidth_sensors",
                "environmental_sensors",
                "custom_oids",
            ],
        )

    async def async_step_back(self, user_input=None):
        """Return to the previous/top-level menu."""
        return await self.async_step_init()

    async def async_step_manage_interfaces(self, user_input=None) -> FlowResult:
        """Interface management options."""
        return self.async_show_menu(
            step_id="manage_interfaces",
            menu_options=[
                "included_interfaces",
                "excluded_interfaces",
                "builtin_vendor_filters",
                "interface_name_rules",
                "interface_ip_display",
                "entity_icon_rules",
                "back",
            ],
        )


    async def async_step_interface_ip_display(self, user_input=None) -> FlowResult:
        """Interface IP Display options (Manage Interfaces submenu)."""
        if user_input is not None:
            # Store under the primary (beta.2) option key, but accept either key from the form
            enabled = bool(
                user_input.get(CONF_HIDE_IP_ON_PHYSICAL_INTERFACES,
                               user_input.get(CONF_HIDE_IP_ON_PHYSICAL, False))
            )
            self._options[CONF_HIDE_IP_ON_PHYSICAL_INTERFACES] = enabled
            # Clean up legacy key if present
            self._options.pop(CONF_HIDE_IP_ON_PHYSICAL, None)
            self._apply_options()
            return await self.async_step_manage_interfaces()

        return self.async_show_form(
            step_id="interface_ip_display",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_HIDE_IP_ON_PHYSICAL_INTERFACES,
                        default=bool(
                            self._options.get(
                                CONF_HIDE_IP_ON_PHYSICAL_INTERFACES,
                                self._options.get(CONF_HIDE_IP_ON_PHYSICAL, False),
                            )
                        ),
                    ): cv.boolean,
                }
            ),
        )

    async def async_step_builtin_vendor_filters(self, user_input=None) -> FlowResult:
        """Alias for built-in vendor filters (Manage Interfaces submenu)."""
        return await self.async_step_builtin_filters(user_input)

    async def async_step_included_interfaces(self, user_input=None) -> FlowResult:
        """Alias for interface include rules (Manage Interfaces submenu)."""
        return await self.async_step_include_rules(user_input)

    async def async_step_excluded_interfaces(self, user_input=None) -> FlowResult:
        """Alias for interface exclude rules (Manage Interfaces submenu)."""
        return await self.async_step_exclude_rules(user_input)

    async def async_step_interface_name_rules(self, user_input=None) -> FlowResult:
        """Alias for interface name rules (Manage Interfaces submenu)."""
        return await self.async_step_port_name_rules(user_input)


    async def async_step_entity_icon_rules(self, user_input=None) -> FlowResult:
        """Manage per-interface entity icon override rules."""
        if user_input is not None:
            return await self._step_icon_rules(user_input)

        return self.async_show_form(
            step_id="entity_icon_rules",
            data_schema=self._icon_rules_schema(),
            description_placeholders={
                "current": self._describe_icon_rules(),
            },
        )

    def _describe_icon_rules(self) -> str:
        rules = self._options.get(CONF_ICON_RULES, []) or []
        parts: list[str] = []
        for r in rules:
            try:
                m = str(r.get("match") or "")
                v = str(r.get("value") or "")
                ic = str(r.get("icon") or "")
                if m and v and ic:
                    parts.append(f"{m}: {v} -> {ic}")
            except Exception:
                continue
        return "\n".join(parts) if parts else "(none)"

    def _icon_rules_schema(self) -> vol.Schema:
        KEY_ACTION = "icon_action"
        KEY_MATCH = "icon_match"
        KEY_VALUE = "icon_value"
        KEY_ICON = "icon_icon"
        KEY_EXISTING = "icon_existing"

        existing = self._options.get(CONF_ICON_RULES, []) or []
        existing_labels: list[str] = []
        for idx, r in enumerate(existing):
            try:
                existing_labels.append(f"{idx+1}. {r.get('match')}: {r.get('value')} -> {r.get('icon')}")
            except Exception:
                continue

        return vol.Schema(
            {
                vol.Required(KEY_ACTION, default="add"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="add", label="Add"),
                            selector.SelectOptionDict(value="edit", label="Edit"),
                            selector.SelectOptionDict(value="remove", label="Remove"),
                            selector.SelectOptionDict(value="clear", label="Clear all"),
                            selector.SelectOptionDict(value="done", label="Back"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                # Only meaningful for edit/remove when rules exist
                vol.Optional(KEY_EXISTING): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[selector.SelectOptionDict(value=v, label=v) for v in existing_labels],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ) if existing_labels else cv.string,
                vol.Optional(KEY_MATCH, default="starts with"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="starts with", label="Starts with"),
                            selector.SelectOptionDict(value="contains", label="Contains"),
                            selector.SelectOptionDict(value="ends with", label="Ends with"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(KEY_VALUE): cv.string,
                vol.Optional(KEY_ICON): cv.string,
            }
        )

    async def _step_icon_rules(self, user_input) -> FlowResult:
        KEY_ACTION = "icon_action"
        KEY_MATCH = "icon_match"
        KEY_VALUE = "icon_value"
        KEY_ICON = "icon_icon"
        KEY_EXISTING = "icon_existing"

        action = user_input.get(KEY_ACTION)
        if action == "done":
            return await self.async_step_manage_interfaces()

        rules = list(self._options.get(CONF_ICON_RULES, []) or [])
        # Build mapping label -> index
        label_to_index: dict[str, int] = {}
        for idx, r in enumerate(rules):
            label = f"{idx+1}. {r.get('match')}: {r.get('value')} -> {r.get('icon')}"
            label_to_index[label] = idx

        if action == "clear":
            self._options.pop(CONF_ICON_RULES, None)
            return await self.async_step_manage_interfaces()

        if action in ("remove", "edit"):
            existing_label = user_input.get(KEY_EXISTING) or ""
            if existing_label in label_to_index:
                idx = label_to_index[existing_label]
                if action == "remove":
                    rules.pop(idx)
                    self._options[CONF_ICON_RULES] = rules
                    self._apply_options()
                    return await self.async_step_entity_icon_rules()

                # edit: replace selected rule with provided fields (match/value/icon).
                match = (user_input.get(KEY_MATCH) or rules[idx].get("match") or "").strip()
                value = (user_input.get(KEY_VALUE) or rules[idx].get("value") or "").strip()
                icon = (user_input.get(KEY_ICON) or rules[idx].get("icon") or "").strip()
                if match and value and icon:
                    rules[idx] = {"match": match, "value": value, "icon": icon}
                    self._options[CONF_ICON_RULES] = rules
                    self._apply_options()
                    return await self.async_step_entity_icon_rules()

        if action == "add":
            match = (user_input.get(KEY_MATCH) or "").strip()
            value = (user_input.get(KEY_VALUE) or "").strip()
            icon = (user_input.get(KEY_ICON) or "").strip()
            if match and value and icon:
                rules.append({"match": match, "value": value, "icon": icon})
                self._options[CONF_ICON_RULES] = rules
                self._apply_options()
                return await self.async_step_entity_icon_rules()

        # If validation fails, just re-render the form
        return await self.async_step_entity_icon_rules()
    async def async_step_environmental_sensors(self, user_input=None) -> FlowResult:
        """Environmental / PoE options."""
        return self.async_show_menu(
            step_id="environmental_sensors",
            menu_options=[
                "environmental_enable_disable",
                "poe_poll_interval",
                "environmental_poll_interval",
                "back",
            ],
        )
    async def async_step_custom_oids(self, user_input=None) -> FlowResult:
            """Manage per-device custom diagnostic OIDs."""
            errors: dict[str, str] = {}
            custom_oids: dict = dict(self._options.get(CONF_CUSTOM_OIDS, {}) or {})
            enabled_default = bool(custom_oids)
    
            if user_input is not None:
                enable_custom = user_input.get(CONF_ENABLE_CUSTOM_OIDS, False)
                reset = user_input.get(CONF_RESET_CUSTOM_OIDS, False)
    
                if reset or not enable_custom:
                    self._options[CONF_CUSTOM_OIDS] = {}
                    self._apply_options()
                    return await self.async_step_init()
    
                new_custom: dict[str, str] = {}
                for key, _label in OID_FIELDS:
                    field = f"{key}_oid"
                    raw = (user_input.get(field) or "").strip()
                    if raw and not _is_valid_numeric_oid(raw):
                        errors[field] = "invalid_oid"
                        continue
                    norm = _normalize_oid(raw)
                    if norm:
                        new_custom[key] = norm
    
                if not errors:
                    self._options[CONF_CUSTOM_OIDS] = new_custom
                    self._apply_options()
                    return await self.async_step_init()
    
            schema_dict = {
                vol.Optional(CONF_ENABLE_CUSTOM_OIDS, default=enabled_default): bool,
                vol.Optional(CONF_RESET_CUSTOM_OIDS, default=False): bool,
            }
            for key, _label in OID_FIELDS:
                schema_dict[
                    vol.Optional(f"{key}_oid", default=str(custom_oids.get(key, "")))
                ] = str
    
            return self.async_show_form(
                step_id="custom_oids",
                data_schema=vol.Schema(schema_dict),
                errors=errors,
            )



    async def async_step_bandwidth_sensors(self, user_input=None) -> FlowResult:
        """Bandwidth Sensors menu."""
        return self.async_show_menu(
            step_id="bandwidth_sensors",
            menu_options=[
                "bandwidth_enable_disable",
                "bandwidth_poll_interval",
                "bandwidth_include_rules",
                "bandwidth_exclude_rules",
                "bandwidth_icons",
                "back",
            ],
        )

    async def async_step_bandwidth_enable_disable(self, user_input=None) -> FlowResult:
        """Enable/Disable bandwidth sensors."""
        if user_input is not None:
            self._options[CONF_BW_ENABLE] = bool(user_input.get(CONF_BW_ENABLE))
            self._options[CONF_BW_MODE] = user_input.get(CONF_BW_MODE, BW_MODE_SENSORS)
            self._apply_options()
            # Return to the Bandwidth Sensors submenu (do not exit the options flow).
            return await self.async_step_bandwidth_sensors()

        enabled = self._options.get(CONF_BW_ENABLE, False)
        mode = self._options.get(CONF_BW_MODE, BW_MODE_SENSORS)

        schema = vol.Schema(
            {
                vol.Required(CONF_BW_ENABLE, default=enabled): selector.BooleanSelector(),
                vol.Required(CONF_BW_MODE, default=mode): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[BW_MODE_SENSORS, BW_MODE_ATTRIBUTES],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="bandwidth_data_as",
                    )
                ),
            }
        )
        return self.async_show_form(step_id="bandwidth_enable_disable", data_schema=schema)

    async def async_step_bandwidth_poll_interval(self, user_input=None) -> FlowResult:
        """Set poll interval for bandwidth sensors."""
        errors = {}
        current = self._options.get(CONF_BANDWIDTH_POLL_INTERVAL, DEFAULT_BANDWIDTH_POLL_INTERVAL)

        # In some HA builds, optional selector fields may be omitted from user_input
        # if the user leaves them unchanged. Treat a missing value as "keep current".
        if user_input is not None:
            raw = user_input.get(CONF_BANDWIDTH_POLL_INTERVAL, current)
            try:
                # Some frontends/versions return a dict like {"value": 30}.
                if isinstance(raw, dict) and "value" in raw:
                    raw = raw["value"]
                # NumberSelector may return int or float depending on frontend; accept both.
                if isinstance(raw, (int, float)):
                    value = int(raw)
                else:
                    value = int(float(str(raw).strip()))
                if value < 5 or value > 3600:
                    raise ValueError
            except Exception:
                errors["base"] = "invalid_poll_interval"
            else:
                self._options[CONF_BANDWIDTH_POLL_INTERVAL] = value
                self._apply_options()
                # Return to the Bandwidth Sensors submenu (do not exit the options flow).
                return await self.async_step_bandwidth_sensors()
        schema = vol.Schema({
            vol.Required(
                CONF_BANDWIDTH_POLL_INTERVAL,
                default=int(current),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=5,
                    max=3600,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="s",
                )
            )
        })
        return self.async_show_form(step_id="bandwidth_poll_interval", data_schema=schema, errors=errors)

    async def async_step_bandwidth_include_rules(self, user_input=None) -> FlowResult:
        return await self._async_step_bw_rules(include=True, user_input=user_input, return_to="bandwidth_sensors")

    async def async_step_bandwidth_exclude_rules(self, user_input=None) -> FlowResult:
        return await self._async_step_bw_rules(include=False, user_input=user_input, return_to="bandwidth_sensors")

    async def async_step_connection_and_naming_overrides(self, user_input=None) -> FlowResult:
        """Per-device connection overrides."""
        errors: dict[str, str] = {}

        if user_input is not None:

            def _opt_str(key: str) -> str:
                return (user_input.get(key) or "").strip()

            # SNMP version selection (v2c / v3)
            current_version = str(
                self._options.get(CONF_SNMP_VERSION)
                or self._entry.data.get(CONF_SNMP_VERSION)
                or SNMP_VERSION_V2C
            )
            version = str(user_input.get(CONF_SNMP_VERSION) or current_version)
            if version not in (SNMP_VERSION_V2C, SNMP_VERSION_V3):
                version = SNMP_VERSION_V2C

            # Only persist if it actually changes; avoids unnecessary reloads
            if version != current_version:
                self._options[CONF_SNMP_VERSION] = version

            # Community override (v2c)
            comm = _opt_str(CONF_OVERRIDE_COMMUNITY)
            if comm:
                self._options[CONF_OVERRIDE_COMMUNITY] = comm
            else:
                self._options.pop(CONF_OVERRIDE_COMMUNITY, None)

            # SNMPv3 credentials
            # NOTE: The options form is not dynamic (all fields are always visible).
            # To prevent "no-op submit" from causing reloads, only mutate SNMPv3 keys
            # when SNMP v3 is selected.
            v3_user = _opt_str(CONF_SNMPV3_USERNAME)
            auth_proto = str(user_input.get(CONF_SNMPV3_AUTH_PROTOCOL) or "").strip().lower()
            auth_pass = str(user_input.get(CONF_SNMPV3_AUTH_PASSWORD) or "")
            priv_proto = str(user_input.get(CONF_SNMPV3_PRIV_PROTOCOL) or "").strip().lower()
            priv_pass = str(user_input.get(CONF_SNMPV3_PRIV_PASSWORD) or "")

            if version == SNMP_VERSION_V3:
                # Allow explicit clearing when v3 is active
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

            # Validation when v3 is selected
            if version == SNMP_VERSION_V3:
                if not v3_user:
                    errors[CONF_SNMPV3_USERNAME] = "required"
                if auth_proto and auth_proto != SNMPV3_AUTH_NONE:
                    if len(auth_pass) < 8 or len(auth_pass) > 31:
                        errors[CONF_SNMPV3_AUTH_PASSWORD] = "invalid_password_length"
                if priv_proto and priv_proto != SNMPV3_PRIV_NONE:
                    if len(priv_pass) < 8 or len(priv_pass) > 31:
                        errors[CONF_SNMPV3_PRIV_PASSWORD] = "invalid_password_length"

            # Port override
            port_raw = (user_input.get(CONF_OVERRIDE_PORT) or "").strip()
            if not port_raw:
                self._options.pop(CONF_OVERRIDE_PORT, None)
            else:
                try:
                    self._options[CONF_OVERRIDE_PORT] = int(port_raw)
                except Exception:
                    errors[CONF_OVERRIDE_PORT] = "invalid_port"

            # Uptime (sysUpTime) refresh interval (seconds)

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
            }
        )

        return self.async_show_form(
            step_id="connection_and_naming_overrides",
            data_schema=schema,
            errors=errors,
        )

    def _render_rules(self, *, include: bool) -> str:
        """Render current include/exclude rules for description text."""
        if include:
            sw = self._options.get(CONF_INCLUDE_STARTS_WITH) or []
            ct = self._options.get(CONF_INCLUDE_CONTAINS) or []
            ew = self._options.get(CONF_INCLUDE_ENDS_WITH) or []
        else:
            sw = self._options.get(CONF_EXCLUDE_STARTS_WITH) or []
            ct = self._options.get(CONF_EXCLUDE_CONTAINS) or []
            ew = self._options.get(CONF_EXCLUDE_ENDS_WITH) or []

        lines: list[str] = []
        if sw:
            lines.append("• Starts with: " + ", ".join(sw))
        if ct:
            lines.append("• Contains: " + ", ".join(ct))
        if ew:
            lines.append("• Ends with: " + ", ".join(ew))

        return "\n".join(lines) if lines else "• (none)"

    def _render_bw_rules(self, *, include: bool) -> str:
        '''Render bandwidth include/exclude rules from bandwidth option keys.'''
        if include:
            starts = self._options.get(CONF_BW_INCLUDE_STARTS_WITH, [])
            contains = self._options.get(CONF_BW_INCLUDE_CONTAINS, [])
            ends = self._options.get(CONF_BW_INCLUDE_ENDS_WITH, [])
        else:
            starts = self._options.get(CONF_BW_EXCLUDE_STARTS_WITH, [])
            contains = self._options.get(CONF_BW_EXCLUDE_CONTAINS, [])
            ends = self._options.get(CONF_BW_EXCLUDE_ENDS_WITH, [])

        parts: list[str] = []
        if starts:
            parts.extend([f"starts with: {v}" for v in starts])
        if contains:
            parts.extend([f"contains: {v}" for v in contains])
        if ends:
            parts.extend([f"ends with: {v}" for v in ends])

        return '\n'.join(f"- {p}" for p in parts) if parts else 'none'


    
    async def async_step_include_rules(self, user_input=None) -> FlowResult:
        """Interface include rules (Add/Edit/Remove/Clear)."""
        return await self._async_step_rules(include=True, user_input=user_input, return_to="manage_interfaces")

    async def async_step_exclude_rules(self, user_input=None) -> FlowResult:
        """Interface exclude rules (Add/Edit/Remove/Clear)."""
        return await self._async_step_rules(include=False, user_input=user_input, return_to="manage_interfaces")

    async def _async_step_rules(
        self, *, include: bool, user_input=None, return_to: str = "init"
    ) -> FlowResult:
        """Shared handler for interface include/exclude rule management.

        Uses the same Add/Edit/Remove/Clear pattern as Entity Icon Rules.
        """

        STEP_ID = "include_rules" if include else "exclude_rules"

        KEY_ACTION = "rule_action"
        KEY_EXISTING = "rule_existing"
        KEY_MATCH = "rule_match"
        KEY_VALUE = "rule_value"

        # Map UI match -> option keys
        if include:
            k_map = {
                "starts with": CONF_INCLUDE_STARTS_WITH,
                "contains": CONF_INCLUDE_CONTAINS,
                "ends with": CONF_INCLUDE_ENDS_WITH,
            }
        else:
            k_map = {
                "starts with": CONF_EXCLUDE_STARTS_WITH,
                "contains": CONF_EXCLUDE_CONTAINS,
                "ends with": CONF_EXCLUDE_ENDS_WITH,
            }

        # Build current rules + labels
        existing_labels: list[str] = []
        label_to_rule: dict[str, tuple[str, str]] = {}  # label -> (match, value)

        parts: list[str] = []
        idx = 1
        for m, opt_key in k_map.items():
            vals = list(self._options.get(opt_key) or [])
            for v in vals:
                label = f"{idx}. {m}: {v}"
                existing_labels.append(label)
                label_to_rule[label] = (m, v)
                parts.append(f"{m}: {v}")
                idx += 1

        current_rules = "\n".join(parts) if parts else "(none)"

        if user_input is not None:
            action = user_input.get(KEY_ACTION)

            if action == "done":
                return await getattr(self, f"async_step_{return_to}")()

            if action == "clear":
                for opt_key in k_map.values():
                    self._options.pop(opt_key, None)
                self._apply_options()
                return await getattr(self, f"async_step_{STEP_ID}")()

            if action == "add":
                match = (user_input.get(KEY_MATCH) or "starts with").strip()
                value = (user_input.get(KEY_VALUE) or "").strip()
                if match in k_map and value:
                    opt_key = k_map[match]
                    cur = list(self._options.get(opt_key) or [])
                    if value not in cur:
                        cur.append(value)
                    self._options[opt_key] = cur
                    self._apply_options()
                return await getattr(self, f"async_step_{STEP_ID}")()

            if action in ("remove", "edit"):
                selected = user_input.get(KEY_EXISTING) or ""
                if selected in label_to_rule:
                    old_match, old_value = label_to_rule[selected]
                    # remove old
                    old_key = k_map[old_match]
                    cur_old = [v for v in (self._options.get(old_key) or []) if v != old_value]
                    if cur_old:
                        self._options[old_key] = cur_old
                    else:
                        self._options.pop(old_key, None)

                    if action == "edit":
                        new_match = (user_input.get(KEY_MATCH) or old_match).strip()
                        new_value = (user_input.get(KEY_VALUE) or old_value).strip() or old_value
                        if new_match in k_map and new_value:
                            new_key = k_map[new_match]
                            cur_new = list(self._options.get(new_key) or [])
                            if new_value not in cur_new:
                                cur_new.append(new_value)
                            self._options[new_key] = cur_new

                    self._apply_options()

                return await getattr(self, f"async_step_{STEP_ID}")()

            # Anything else -> re-show
            return await getattr(self, f"async_step_{STEP_ID}")()

        # Schema (selectors)
        schema = vol.Schema(
            {
                vol.Required(KEY_ACTION, default="add"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="add", label="Add"),
                            selector.SelectOptionDict(value="edit", label="Edit"),
                            selector.SelectOptionDict(value="remove", label="Remove"),
                            selector.SelectOptionDict(value="clear", label="Clear all"),
                            selector.SelectOptionDict(value="done", label="Back"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(KEY_EXISTING): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[selector.SelectOptionDict(value=v, label=v) for v in existing_labels],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ) if existing_labels else cv.string,
                vol.Optional(KEY_MATCH, default="starts with"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="starts with", label="Starts with"),
                            selector.SelectOptionDict(value="contains", label="Contains"),
                            selector.SelectOptionDict(value="ends with", label="Ends with"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(KEY_VALUE, default=""): cv.string,
            }
        )

        return self.async_show_form(
            step_id=STEP_ID,
            data_schema=schema,
            # Must match the {current_rules} placeholder used in translations/strings.
            description_placeholders={"current_rules": current_rules},
        )


    async def _async_step_bw_rules(
        self, *, include: bool, user_input=None, return_to: str = "bandwidth_sensors"
    ) -> FlowResult:
        """Shared handler for bandwidth include/exclude rule management.

        Uses the same Add/Edit/Remove/Clear pattern as Entity Icon Rules.
        """

        STEP_ID = "bandwidth_include_rules" if include else "bandwidth_exclude_rules"

        KEY_ACTION = "rule_action"
        KEY_EXISTING = "rule_existing"
        KEY_MATCH = "rule_match"
        KEY_VALUE = "rule_value"

        if include:
            k_map = {
                "starts with": CONF_BW_INCLUDE_STARTS_WITH,
                "contains": CONF_BW_INCLUDE_CONTAINS,
                "ends with": CONF_BW_INCLUDE_ENDS_WITH,
            }
        else:
            k_map = {
                "starts with": CONF_BW_EXCLUDE_STARTS_WITH,
                "contains": CONF_BW_EXCLUDE_CONTAINS,
                "ends with": CONF_BW_EXCLUDE_ENDS_WITH,
            }

        existing_labels: list[str] = []
        label_to_rule: dict[str, tuple[str, str]] = {}

        parts: list[str] = []
        idx = 1
        for m, opt_key in k_map.items():
            vals = list(self._options.get(opt_key) or [])
            for v in vals:
                label = f"{idx}. {m}: {v}"
                existing_labels.append(label)
                label_to_rule[label] = (m, v)
                parts.append(f"{m}: {v}")
                idx += 1

        current_rules = "\n".join(parts) if parts else "(none)"

        if user_input is not None:
            action = user_input.get(KEY_ACTION)

            if action == "done":
                return await getattr(self, f"async_step_{return_to}")()

            if action == "clear":
                for opt_key in k_map.values():
                    self._options.pop(opt_key, None)
                self._apply_options()
                return await getattr(self, f"async_step_{STEP_ID}")()

            if action == "add":
                match = (user_input.get(KEY_MATCH) or "starts with").strip()
                value = (user_input.get(KEY_VALUE) or "").strip()
                if match in k_map and value:
                    opt_key = k_map[match]
                    cur = list(self._options.get(opt_key) or [])
                    if value not in cur:
                        cur.append(value)
                    self._options[opt_key] = cur
                    self._apply_options()
                return await getattr(self, f"async_step_{STEP_ID}")()

            if action in ("remove", "edit"):
                selected = user_input.get(KEY_EXISTING) or ""
                if selected in label_to_rule:
                    old_match, old_value = label_to_rule[selected]
                    old_key = k_map[old_match]
                    cur_old = [v for v in (self._options.get(old_key) or []) if v != old_value]
                    if cur_old:
                        self._options[old_key] = cur_old
                    else:
                        self._options.pop(old_key, None)

                    if action == "edit":
                        new_match = (user_input.get(KEY_MATCH) or old_match).strip()
                        new_value = (user_input.get(KEY_VALUE) or old_value).strip() or old_value
                        if new_match in k_map and new_value:
                            new_key = k_map[new_match]
                            cur_new = list(self._options.get(new_key) or [])
                            if new_value not in cur_new:
                                cur_new.append(new_value)
                            self._options[new_key] = cur_new

                    self._apply_options()

                return await getattr(self, f"async_step_{STEP_ID}")()

            return await getattr(self, f"async_step_{STEP_ID}")()

        schema = vol.Schema(
            {
                vol.Required(KEY_ACTION, default="add"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="add", label="Add"),
                            selector.SelectOptionDict(value="edit", label="Edit"),
                            selector.SelectOptionDict(value="remove", label="Remove"),
                            selector.SelectOptionDict(value="clear", label="Clear all"),
                            selector.SelectOptionDict(value="done", label="Back"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(KEY_EXISTING): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[selector.SelectOptionDict(value=v, label=v) for v in existing_labels],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ) if existing_labels else cv.string,
                vol.Optional(KEY_MATCH, default="starts with"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="starts with", label="Starts with"),
                            selector.SelectOptionDict(value="contains", label="Contains"),
                            selector.SelectOptionDict(value="ends with", label="Ends with"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(KEY_VALUE, default=""): cv.string,
            }
        )

        return self.async_show_form(
            step_id=STEP_ID,
            data_schema=schema,
            description_placeholders={"current": current_rules},
        )


    async def async_step_builtin_filters(self, user_input=None) -> FlowResult:
        """Enable/disable built-in vendor interface filtering rules."""
        # Store disabled rule IDs (unchecked == enabled)
        current_disabled: list[str] = list(self._options.get(CONF_DISABLED_VENDOR_FILTER_RULE_IDS, []) or [])
        options_map = {r["id"]: r["label"] for r in BUILTIN_VENDOR_FILTER_RULES}

        if user_input is not None:
            disabled = list(user_input.get(CONF_DISABLED_VENDOR_FILTER_RULE_IDS, []) or [])
            if disabled:
                self._options[CONF_DISABLED_VENDOR_FILTER_RULE_IDS] = disabled
            else:
                self._options.pop(CONF_DISABLED_VENDOR_FILTER_RULE_IDS, None)
            self._apply_options()
            return await self.async_step_manage_interfaces()

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_DISABLED_VENDOR_FILTER_RULE_IDS,
                    default=current_disabled,
                ): cv.multi_select(options_map),
            }
        )

        return self.async_show_form(
            step_id="builtin_filters",
            description_placeholders={},
            data_schema=schema,
        )


    async def async_step_port_name_rules(self, user_input=None) -> FlowResult:
        """Menu for managing port display name rules."""
        return self.async_show_menu(
            step_id="port_name_rules",
            menu_options=[
                "port_rename_defaults",
                "port_rename_custom",
                "port_rename_restore_defaults",
                "manage_interfaces",
            ],
        )


    async def async_step_port_rename_custom(self, user_input=None) -> FlowResult:
        """Manage Custom Rename Rules using the standard rule dialog.

        This replaces the legacy submenu (Add/Edit/Remove) with the same
        dialog pattern used by Include/Exclude rules.
        """

        STEP_ID = "port_rename_custom"

        KEY_ACTION = "rule_action"
        KEY_EXISTING = "rule_existing"
        KEY_MATCH = "rule_match"
        KEY_VALUE = "rule_value"
        KEY_REPLACE = "rule_replace"

        rules: list[dict] = list(self._options.get(CONF_PORT_RENAME_USER_RULES) or [])

        # Build labels for existing rules
        existing_labels: list[str] = []
        label_to_idx: dict[str, int] = {}
        parts: list[str] = []

        for idx, r in enumerate(rules):
            pat = str(r.get("pattern") or "")
            rep = str(r.get("replace") or "")
            label = f"{idx+1}. {pat} → {rep}"
            existing_labels.append(label)
            label_to_idx[label] = idx
            parts.append(f"{pat} → {rep}")

        current_rules = "\n".join(parts) if parts else "(none)"

        def _build_pattern(match: str, value: str) -> str:
            """Convert a simple match helper into a regex pattern."""
            v = (value or "").strip()
            if match == "starts with":
                return "^" + re.escape(v)
            if match == "ends with":
                return re.escape(v) + "$"
            if match == "contains":
                return re.escape(v)
            # regex
            return v

        def _is_valid_regex(pat: str) -> bool:
            try:
                re.compile(pat)
                return True
            except Exception:
                return False

        errors: dict[str, str] = {}

        if user_input is not None:
            action = user_input.get(KEY_ACTION)

            if action == "done":
                return await self.async_step_port_name_rules()

            if action == "clear":
                self._options.pop(CONF_PORT_RENAME_USER_RULES, None)
                self._apply_options()
                return await self.async_step_port_rename_custom()

            match = (user_input.get(KEY_MATCH) or "starts with").strip()
            value = (user_input.get(KEY_VALUE) or "").strip()
            replace = user_input.get(KEY_REPLACE, "")

            if action == "add":
                if not value:
                    errors[KEY_VALUE] = "required"
                else:
                    pat = _build_pattern(match, value)
                    if not _is_valid_regex(pat):
                        errors[KEY_VALUE] = "invalid_regex"
                    else:
                        rules.append({"pattern": pat, "replace": replace, "description": ""})
                        self._options[CONF_PORT_RENAME_USER_RULES] = rules
                        self._apply_options()
                        return await self.async_step_port_rename_custom()

            if action in ("remove", "edit"):
                selected = user_input.get(KEY_EXISTING) or ""
                if selected not in label_to_idx:
                    return await self.async_step_port_rename_custom()

                idx = label_to_idx[selected]
                old = rules[idx]
                old_pat = str(old.get("pattern") or "")
                old_rep = str(old.get("replace") or "")

                # Remove the old rule
                rules = [r for i, r in enumerate(rules) if i != idx]

                if action == "edit":
                    # If no new value was provided, keep the existing pattern.
                    if value:
                        pat = _build_pattern(match, value)
                        if not _is_valid_regex(pat):
                            errors[KEY_VALUE] = "invalid_regex"
                            # Re-add original rule if validation fails
                            rules.insert(idx, old)
                            self._options[CONF_PORT_RENAME_USER_RULES] = rules
                            return self.async_show_form(
                                step_id=STEP_ID,
                                data_schema=self._port_rename_custom_schema(existing_labels),
                                description_placeholders={"current": current_rules},
                                errors=errors,
                            )
                    else:
                        pat = old_pat

                    # NOTE: For edits, leaving Replacement blank keeps the existing replacement.
                    rep = replace if (replace is not None and replace != "") else old_rep

                    rules.insert(idx, {"pattern": pat, "replace": rep, "description": str(old.get("description") or "")})
                    self._options[CONF_PORT_RENAME_USER_RULES] = rules if rules else []
                    if not rules:
                        self._options.pop(CONF_PORT_RENAME_USER_RULES, None)
                    self._apply_options()
                    return await self.async_step_port_rename_custom()

                # remove
                if rules:
                    self._options[CONF_PORT_RENAME_USER_RULES] = rules
                else:
                    self._options.pop(CONF_PORT_RENAME_USER_RULES, None)
                self._apply_options()
                return await self.async_step_port_rename_custom()

        # Show form
        return self.async_show_form(
            step_id=STEP_ID,
            data_schema=self._port_rename_custom_schema(existing_labels),
            description_placeholders={"current": current_rules},
            errors=errors,
        )


    def _port_rename_custom_schema(self, existing_labels: list[str]) -> vol.Schema:
        """Schema for the Custom Rename Rules dialog."""
        KEY_ACTION = "rule_action"
        KEY_EXISTING = "rule_existing"
        KEY_MATCH = "rule_match"
        KEY_VALUE = "rule_value"
        KEY_REPLACE = "rule_replace"

        return vol.Schema(
            {
                vol.Required(KEY_ACTION, default="add"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="add", label="Add"),
                            selector.SelectOptionDict(value="edit", label="Edit"),
                            selector.SelectOptionDict(value="remove", label="Remove"),
                            selector.SelectOptionDict(value="clear", label="Clear all"),
                            selector.SelectOptionDict(value="done", label="Back"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(KEY_EXISTING): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[selector.SelectOptionDict(value=v, label=v) for v in existing_labels],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ) if existing_labels else cv.string,
                vol.Optional(KEY_MATCH, default="starts with"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="starts with", label="Starts with"),
                            selector.SelectOptionDict(value="contains", label="Contains"),
                            selector.SelectOptionDict(value="ends with", label="Ends with"),
                            selector.SelectOptionDict(value="regex", label="Regex"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(KEY_VALUE, default=""): cv.string,
                vol.Optional(KEY_REPLACE, default=""): cv.string,
            }
        )


    async def async_step_port_rename_custom_add(self, user_input=None) -> FlowResult:
        """Add a custom port rename regex rule."""
        errors: dict[str, str] = {}

        if user_input is not None:
            pattern = (user_input.get("pattern") or "").strip()
            replace = user_input.get("replace") or ""
            description = (user_input.get("description") or "").strip()

            if not pattern:
                errors["pattern"] = "required"
            else:
                try:
                    re.compile(pattern)
                except Exception:
                    errors["pattern"] = "invalid_regex"

            if not errors:
                rules = list(self._options.get(CONF_PORT_RENAME_USER_RULES) or [])
                rules.append({"pattern": pattern, "replace": replace, "description": description})
                self._options[CONF_PORT_RENAME_USER_RULES] = rules
                self._apply_options()
                return await self.async_step_port_rename_custom()

        schema = vol.Schema(
            {
                vol.Required("pattern"): str,
                vol.Optional("replace", default=""): str,
                vol.Optional("description", default=""): str,
            }
        )
        return self.async_show_form(step_id="port_rename_custom_add", data_schema=schema, errors=errors)



    async def async_step_port_rename_custom_edit(self, user_input=None) -> FlowResult:
        """Edit an existing custom port rename regex rule."""
        rules = list(self._options.get(CONF_PORT_RENAME_USER_RULES, []) or [])
        # Build label -> index mapping
        labels: dict[str, int] = {}
        for idx, r in enumerate(rules):
            pat = r.get("pattern")
            rep = r.get("replace")
            labels[f"{idx+1}. {pat} -> {rep}"] = idx

        if user_input is not None:
            sel = user_input.get("selected")
            if sel in labels:
                idx = labels[sel]
                pattern = (user_input.get("pattern") or "").strip()
                # IMPORTANT: preserve spaces in replacement values (no .strip())
                replace = user_input.get("replace") or ""
                description = (user_input.get("description") or "").strip()
                errors = {}
                try:
                    re.compile(pattern)
                except Exception:
                    errors["pattern"] = "invalid_regex"
                if errors:
                    return self.async_show_form(
                        step_id="port_rename_custom_edit",
                        data_schema=self._port_rename_edit_schema(labels, rules, sel),
                        errors=errors,
                    )
                rules[idx] = {"pattern": pattern, "replace": replace, "description": description}
                self._options[CONF_PORT_RENAME_USER_RULES] = rules
                self._apply_options()
                return await self.async_step_port_rename_custom()
            return await self.async_step_port_rename_custom()

        return self.async_show_form(
            step_id="port_rename_custom_edit",
            data_schema=self._port_rename_edit_schema(labels, rules),
        )

    def _port_rename_edit_schema(self, labels: dict[str, int], rules: list[dict], selected: str | None = None) -> vol.Schema:
        if not labels:
            return vol.Schema({vol.Optional("selected"): str})
        if selected is None:
            selected = list(labels.keys())[0]
        idx = labels.get(selected, 0)
        cur = rules[idx] if rules else {"pattern": "", "replace": "", "description": ""}
        return vol.Schema(
            {
                vol.Required("selected", default=selected): vol.In(list(labels.keys())),
                vol.Required("pattern", default=str(cur.get("pattern") or "")): str,
                vol.Required("replace", default=str(cur.get("replace") or "")): str,
                vol.Optional("description", default=str(cur.get("description") or "")): str,
            }
        )
    async def async_step_port_rename_custom_remove(self, user_input=None) -> FlowResult:
        """Remove a custom port rename rule."""
        rules = list(self._options.get(CONF_PORT_RENAME_USER_RULES) or [])

        if not rules:
            return self.async_show_form(
                step_id="port_rename_custom_remove",
                data_schema=vol.Schema({}),
                description_placeholders={"current_rules": "• (none)"},
            )

        if user_input is not None:
            idx = user_input.get("remove_index")
            try:
                i = int(idx)
                if 0 <= i < len(rules):
                    rules.pop(i)
            except Exception:
                pass

            if rules:
                self._options[CONF_PORT_RENAME_USER_RULES] = rules
            else:
                self._options.pop(CONF_PORT_RENAME_USER_RULES, None)

            self._apply_options()
            return await self.async_step_port_rename_custom()

        opts = {}
        lines: list[str] = []
        for i, r in enumerate(rules):
            pat = (r.get("pattern") or "").strip()
            rep = (r.get("replace") or "").strip()
            desc = (r.get("description") or "").strip()
            label = desc or f"{pat} → {rep}"
            opts[str(i)] = f"{i+1}. {label}"
            lines.append(f"{i+1}. {pat} → {rep}" + (f" — {desc}" if desc else ""))

        schema = vol.Schema({vol.Required("remove_index"): vol.In(opts)})
        return self.async_show_form(
            step_id="port_rename_custom_remove",
            data_schema=schema,
            description_placeholders={"current_rules": "\n".join(lines) if lines else "• (none)"},
        )


    async def async_step_port_rename_defaults(self, user_input=None) -> FlowResult:
        """Enable/disable built-in display name rules for this device."""
        current_disabled: list[str] = list(self._options.get(CONF_PORT_RENAME_DISABLED_DEFAULT_IDS, []) or [])
        options_map: dict[str, str] = {}

        for r in DEFAULT_PORT_RENAME_RULES:
            rid = str(r.get("id") or "").strip()
            if not rid:
                continue
            desc = str(r.get("description") or "").strip()
            pat = str(r.get("pattern") or "").strip()
            rep = str(r.get("replace") or "").strip()
            label = f"{rid}: {desc}" if desc else rid
            if pat and rep:
                label = f"{label} ({pat} → {rep})"
            options_map[rid] = label

        if user_input is not None:
            disabled = list(user_input.get(CONF_PORT_RENAME_DISABLED_DEFAULT_IDS, []) or [])
            changed = disabled != current_disabled

            if disabled:
                self._options[CONF_PORT_RENAME_DISABLED_DEFAULT_IDS] = disabled
            else:
                self._options.pop(CONF_PORT_RENAME_DISABLED_DEFAULT_IDS, None)

            if changed:
                self._apply_options()

            return await self.async_step_port_name_rules()


        # Build the {rules} placeholder text used by the translation string
        enabled_ids = [rid for rid in options_map.keys() if rid not in current_disabled]
        if enabled_ids:
            rules_text = "\n".join([f"- {rid}" for rid in enabled_ids])
        else:
            rules_text = "(none)"

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_PORT_RENAME_DISABLED_DEFAULT_IDS,
                    default=current_disabled,
                ): cv.multi_select(options_map),
            }
        )

        return self.async_show_form(
            step_id="port_rename_defaults",
            data_schema=schema,
            description_placeholders={"rules": rules_text},
        )
    async def async_step_port_rename_restore_defaults(self, user_input=None) -> FlowResult:
        """Restore built-in default port rename rules (re-enable all)."""
        self._options.pop(CONF_PORT_RENAME_DISABLED_DEFAULT_IDS, None)
        self._apply_options()
        return await self.async_step_port_name_rules()


    async def async_step_interface_name_rules(self, user_input=None):
        """Backward/forward-compatible alias for the Interface Name Rules menu."""
        return await self.async_step_port_name_rules(user_input)


    async def async_step_environmental_enable_disable(self, user_input=None) -> FlowResult:
        """Enable/disable Environmental + PoE options (and choose attributes vs sensors mode)."""

        if user_input is not None:
            self._options[CONF_ENV_ENABLE] = user_input.get(CONF_ENV_ENABLE, False)
            self._options[CONF_ENV_MODE] = user_input.get(CONF_ENV_MODE, ENV_MODE_ATTRIBUTES)
            self._options[CONF_POE_ENABLE] = user_input.get(CONF_POE_ENABLE, False)
            self._options[CONF_POE_MODE] = user_input.get(CONF_POE_MODE, POE_MODE_ATTRIBUTES)
            self._options[CONF_POE_PER_PORT_POWER] = user_input.get(CONF_POE_PER_PORT_POWER, False)
            self._apply_options()
            return await self.async_step_environmental_sensors()

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_ENV_ENABLE,
                    default=self._options.get(CONF_ENV_ENABLE, False),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_ENV_MODE,
                    default=self._options.get(CONF_ENV_MODE, ENV_MODE_SENSORS),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[ENV_MODE_SENSORS, ENV_MODE_ATTRIBUTES],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="env_data_as",
                    )
                ),
                vol.Optional(
                    CONF_POE_ENABLE,
                    default=self._options.get(CONF_POE_ENABLE, False),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_POE_MODE,
                    default=self._options.get(CONF_POE_MODE, POE_MODE_SENSORS),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[POE_MODE_SENSORS, POE_MODE_ATTRIBUTES],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="poe_data_as",
                    )
                ),
                vol.Optional(
                    CONF_POE_PER_PORT_POWER,
                    default=self._options.get(CONF_POE_PER_PORT_POWER, False),
                ): selector.BooleanSelector(),
            }
        )

        return self.async_show_form(step_id="environmental_enable_disable", data_schema=schema)

    async def async_step_poe_poll_interval(self, user_input=None) -> FlowResult:
        """Set PoE polling interval (seconds)."""
        if user_input is not None:
            self._options[CONF_POE_POLL_INTERVAL] = user_input[CONF_POE_POLL_INTERVAL]
            self._apply_options()
            return await self.async_step_environmental_sensors()

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_POE_POLL_INTERVAL,
                    default=self._options.get(CONF_POE_POLL_INTERVAL, DEFAULT_POE_POLL_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=3600))
            }
        )
        return self.async_show_form(step_id="poe_poll_interval", data_schema=schema)

    async def async_step_environmental_poll_interval(self, user_input=None) -> FlowResult:
        """Set Environmental polling interval (seconds)."""
        if user_input is not None:
            self._options[CONF_ENV_POLL_INTERVAL] = user_input[CONF_ENV_POLL_INTERVAL]
            self._apply_options()
            return await self.async_step_environmental_sensors()

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_ENV_POLL_INTERVAL,
                    default=self._options.get(CONF_ENV_POLL_INTERVAL, DEFAULT_ENV_POLL_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=3600))
            }
        )
        return self.async_show_form(step_id="environmental_poll_interval", data_schema=schema)


    async def async_step_bandwidth_icons(self, user_input=None) -> FlowResult:
        """Optional icon overrides for bandwidth sensors (configured separately from interface icon rules)."""
        options = dict(self._options)

        current = {
            CONF_BW_RX_THROUGHPUT_ICON: (options.get(CONF_BW_RX_THROUGHPUT_ICON) or "").strip(),
            CONF_BW_TX_THROUGHPUT_ICON: (options.get(CONF_BW_TX_THROUGHPUT_ICON) or "").strip(),
            CONF_BW_RX_TOTAL_ICON: (options.get(CONF_BW_RX_TOTAL_ICON) or "").strip(),
            CONF_BW_TX_TOTAL_ICON: (options.get(CONF_BW_TX_TOTAL_ICON) or "").strip(),
        }

        if user_input is not None:
            changed = False
            for k, old in current.items():
                new = (user_input.get(k) or "").strip()
                if new != old:
                    changed = True
                if new:
                    options[k] = new
                else:
                    options.pop(k, None)

            if changed:
                self._options = options
                self._apply_options()

            return await self.async_step_bandwidth_sensors()

        schema = vol.Schema(
            {
                vol.Optional(CONF_BW_RX_THROUGHPUT_ICON, default=current[CONF_BW_RX_THROUGHPUT_ICON]): cv.string,
                vol.Optional(CONF_BW_TX_THROUGHPUT_ICON, default=current[CONF_BW_TX_THROUGHPUT_ICON]): cv.string,
                vol.Optional(CONF_BW_RX_TOTAL_ICON, default=current[CONF_BW_RX_TOTAL_ICON]): cv.string,
                vol.Optional(CONF_BW_TX_TOTAL_ICON, default=current[CONF_BW_TX_TOTAL_ICON]): cv.string,
            }
        )

        return self.async_show_form(
            step_id="bandwidth_icons",
            data_schema=schema,
        )
