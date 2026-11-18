"""Options flow mixin for Interface Errors & Discards."""
from __future__ import annotations

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ..config_flow import _is_valid_numeric_oid, _normalize_oid
from ..const import (
    CONF_FEATURE_OVERRIDES,
    CONF_IF_ERRORS_ENABLE,
    CONF_IF_ERRORS_EXCLUDE_CONTAINS,
    CONF_IF_ERRORS_EXCLUDE_ENDS_WITH,
    CONF_IF_ERRORS_EXCLUDE_STARTS_WITH,
    CONF_IF_ERRORS_INCLUDE_CONTAINS,
    CONF_IF_ERRORS_INCLUDE_DISCARDS,
    CONF_IF_ERRORS_INCLUDE_ENDS_WITH,
    CONF_IF_ERRORS_INCLUDE_STARTS_WITH,
    CONF_IF_ERRORS_MODE,
    CONF_IF_ERRORS_POLL_INTERVAL,
    CONF_IF_ERRORS_RX_DISCARDS_ICON,
    CONF_IF_ERRORS_RX_ICON,
    CONF_IF_ERRORS_TX_DISCARDS_ICON,
    CONF_IF_ERRORS_TX_ICON,
    DEFAULT_IF_ERRORS_POLL_INTERVAL,
    IF_ERRORS_MODE_ATTRIBUTES,
    IF_ERRORS_MODE_SENSORS,
)


class InterfaceErrorsOptionsMixin:
    """Mixin for OptionsFlowHandler to handle interface error & discard counter steps."""

    async def async_step_interface_errors(self, user_input=None) -> FlowResult:
        """Interface Errors submenu (under Manage Interfaces)."""
        return self.async_show_menu(
            step_id="interface_errors",
            menu_options=[
                "interface_errors_enable_disable",
                "interface_errors_poll_interval",
                "interface_errors_include_rules",
                "interface_errors_exclude_rules",
                "interface_errors_icons",
                "interface_errors_oid_override",
                "back_to_manage_interfaces",
            ],
        )

    async def async_step_back_to_manage_interfaces(self, user_input=None) -> FlowResult:
        """Return to the Manage Interfaces submenu."""
        return await self.async_step_manage_interfaces()

    async def async_step_interface_errors_enable_disable(self, user_input=None) -> FlowResult:
        """Enable/Disable interface error & discard counters."""
        if user_input is not None:
            if user_input.get("back_to_menu"):
                return await self.async_step_interface_errors()

            self._options[CONF_IF_ERRORS_ENABLE] = bool(user_input.get(CONF_IF_ERRORS_ENABLE))
            self._options[CONF_IF_ERRORS_MODE] = user_input.get(
                CONF_IF_ERRORS_MODE, IF_ERRORS_MODE_SENSORS
            )
            self._options[CONF_IF_ERRORS_INCLUDE_DISCARDS] = bool(
                user_input.get(CONF_IF_ERRORS_INCLUDE_DISCARDS)
            )
            self._apply_options()
            return await self.async_step_interface_errors()

        enabled = bool(self._options.get(CONF_IF_ERRORS_ENABLE, False))
        mode = self._options.get(CONF_IF_ERRORS_MODE, IF_ERRORS_MODE_SENSORS)
        include_discards = bool(self._options.get(CONF_IF_ERRORS_INCLUDE_DISCARDS, False))

        schema = vol.Schema(
            {
                vol.Required(CONF_IF_ERRORS_ENABLE, default=enabled): cv.boolean,
                vol.Required(CONF_IF_ERRORS_MODE, default=mode): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[IF_ERRORS_MODE_SENSORS, IF_ERRORS_MODE_ATTRIBUTES],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="interface_errors_data_as",
                    )
                ),
                vol.Optional(CONF_IF_ERRORS_INCLUDE_DISCARDS, default=include_discards): cv.boolean,
                vol.Optional("back_to_menu", default=False): cv.boolean,
            }
        )
        return self.async_show_form(step_id="interface_errors_enable_disable", data_schema=schema)

    async def async_step_interface_errors_poll_interval(self, user_input=None) -> FlowResult:
        """Set poll interval for interface error counters."""
        errors: dict[str, str] = {}
        current = self._options.get(CONF_IF_ERRORS_POLL_INTERVAL, DEFAULT_IF_ERRORS_POLL_INTERVAL)

        if user_input is not None:
            if user_input.get("back_to_menu"):
                return await self.async_step_interface_errors()

            raw = user_input.get(CONF_IF_ERRORS_POLL_INTERVAL, current)
            try:
                if isinstance(raw, dict) and "value" in raw:
                    raw = raw["value"]
                value = int(raw) if isinstance(raw, (int, float)) else int(float(str(raw).strip()))
                if value < 5 or value > 3600:
                    raise ValueError
            except Exception:
                errors["base"] = "invalid_poll_interval"
            else:
                self._options[CONF_IF_ERRORS_POLL_INTERVAL] = value
                self._apply_options()
                return await self.async_step_interface_errors()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_IF_ERRORS_POLL_INTERVAL,
                    default=int(current),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5,
                        max=3600,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
                vol.Optional("back_to_menu", default=False): cv.boolean,
            }
        )
        return self.async_show_form(
            step_id="interface_errors_poll_interval",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_interface_errors_include_rules(self, user_input=None) -> FlowResult:
        return await self._async_step_if_errors_rules(
            include=True, user_input=user_input, return_to="interface_errors"
        )

    async def async_step_interface_errors_exclude_rules(self, user_input=None) -> FlowResult:
        return await self._async_step_if_errors_rules(
            include=False, user_input=user_input, return_to="interface_errors"
        )

    async def _async_step_if_errors_rules(
        self, *, include: bool, user_input=None, return_to: str = "interface_errors"
    ) -> FlowResult:
        """Shared handler for interface errors include/exclude rule management."""
        step_id = "interface_errors_include_rules" if include else "interface_errors_exclude_rules"

        key_action = "rule_action"
        key_existing = "rule_existing"
        key_match = "rule_match"
        key_value = "rule_value"

        if include:
            k_map = {
                "starts with": CONF_IF_ERRORS_INCLUDE_STARTS_WITH,
                "contains": CONF_IF_ERRORS_INCLUDE_CONTAINS,
                "ends with": CONF_IF_ERRORS_INCLUDE_ENDS_WITH,
            }
        else:
            k_map = {
                "starts with": CONF_IF_ERRORS_EXCLUDE_STARTS_WITH,
                "contains": CONF_IF_ERRORS_EXCLUDE_CONTAINS,
                "ends with": CONF_IF_ERRORS_EXCLUDE_ENDS_WITH,
            }

        existing_labels: list[str] = []
        label_to_rule: dict[str, tuple[str, str]] = {}
        parts: list[str] = []
        idx = 1
        for m, opt_key in k_map.items():
            for v in list(self._options.get(opt_key) or []):
                label = f"{idx}. {m}: {v}"
                existing_labels.append(label)
                label_to_rule[label] = (m, v)
                parts.append(f"{m}: {v}")
                idx += 1

        current_rules = "\n".join(parts) if parts else "(none)"

        if user_input is not None:
            if user_input.get("back_to_menu"):
                return await getattr(self, f"async_step_{return_to}")()

            action = user_input.get(key_action)
            if action == "done":
                return await getattr(self, f"async_step_{return_to}")()

            if action == "clear":
                for opt_key in k_map.values():
                    self._options.pop(opt_key, None)
                self._apply_options()
                return await getattr(self, f"async_step_{step_id}")()

            if action == "add":
                match = (user_input.get(key_match) or "starts with").strip()
                value = (user_input.get(key_value) or "").strip()
                if match in k_map and value:
                    opt_key = k_map[match]
                    cur = list(self._options.get(opt_key) or [])
                    if value not in cur:
                        cur.append(value)
                    self._options[opt_key] = cur
                    self._apply_options()
                return await getattr(self, f"async_step_{step_id}")()

            if action in ("remove", "edit"):
                selected = user_input.get(key_existing) or ""
                if selected in label_to_rule:
                    old_match, old_value = label_to_rule[selected]
                    old_key = k_map[old_match]
                    cur_old = [v for v in (self._options.get(old_key) or []) if v != old_value]
                    if cur_old:
                        self._options[old_key] = cur_old
                    else:
                        self._options.pop(old_key, None)

                    if action == "edit":
                        new_match = (user_input.get(key_match) or old_match).strip()
                        new_value = (user_input.get(key_value) or old_value).strip() or old_value
                        if new_match in k_map and new_value:
                            new_key = k_map[new_match]
                            cur_new = list(self._options.get(new_key) or [])
                            if new_value not in cur_new:
                                cur_new.append(new_value)
                            self._options[new_key] = cur_new

                    self._apply_options()
                return await getattr(self, f"async_step_{step_id}")()

            return await getattr(self, f"async_step_{step_id}")()

        schema = vol.Schema(
            {
                vol.Required(key_action, default="add"): selector.SelectSelector(
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
                vol.Optional(key_existing): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[selector.SelectOptionDict(value=v, label=v) for v in existing_labels],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ) if existing_labels else cv.string,
                vol.Optional(key_match, default="starts with"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="starts with", label="Starts with"),
                            selector.SelectOptionDict(value="contains", label="Contains"),
                            selector.SelectOptionDict(value="ends with", label="Ends with"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(key_value, default=""): cv.string,
                vol.Optional("back_to_menu", default=False): cv.boolean,
            }
        )

        return self.async_show_form(
            step_id=step_id,
            data_schema=schema,
            description_placeholders={"current": current_rules},
        )

    async def async_step_interface_errors_icons(self, user_input=None) -> FlowResult:
        """Optional icon overrides for interface error & discard sensors."""
        options = dict(self._options)
        current = {
            CONF_IF_ERRORS_RX_ICON: (options.get(CONF_IF_ERRORS_RX_ICON) or "").strip(),
            CONF_IF_ERRORS_TX_ICON: (options.get(CONF_IF_ERRORS_TX_ICON) or "").strip(),
            CONF_IF_ERRORS_RX_DISCARDS_ICON: (options.get(CONF_IF_ERRORS_RX_DISCARDS_ICON) or "").strip(),
            CONF_IF_ERRORS_TX_DISCARDS_ICON: (options.get(CONF_IF_ERRORS_TX_DISCARDS_ICON) or "").strip(),
        }

        if user_input is not None:
            if user_input.get("back_to_menu"):
                return await self.async_step_interface_errors()

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
            return await self.async_step_interface_errors()

        schema = vol.Schema(
            {
                vol.Optional(CONF_IF_ERRORS_RX_ICON, default=current[CONF_IF_ERRORS_RX_ICON]): cv.string,
                vol.Optional(CONF_IF_ERRORS_TX_ICON, default=current[CONF_IF_ERRORS_TX_ICON]): cv.string,
                vol.Optional(CONF_IF_ERRORS_RX_DISCARDS_ICON, default=current[CONF_IF_ERRORS_RX_DISCARDS_ICON]): cv.string,
                vol.Optional(CONF_IF_ERRORS_TX_DISCARDS_ICON, default=current[CONF_IF_ERRORS_TX_DISCARDS_ICON]): cv.string,
                vol.Optional("back_to_menu", default=False): cv.boolean,
            }
        )
        return self.async_show_form(step_id="interface_errors_icons", data_schema=schema)

    async def async_step_interface_errors_oid_override(self, user_input=None) -> FlowResult:
        """Override interface error/discard OIDs and optionally share with community."""
        errors: dict[str, str] = {}
        defaults = self._get_override_defaults("interface_errors")
        db = self._get_database()
        db_vendors = db.get("vendors", {}).get("vendors", [])
        vendor_options = [
            selector.SelectOptionDict(value=v["name"], label=v["name"])
            for v in db_vendors
        ]

        oid_keys = ("oid_in_errors", "oid_out_errors", "oid_in_discards", "oid_out_discards")

        if user_input is not None:
            if user_input.get("back_to_menu"):
                return await self.async_step_interface_errors()

            raw_oids = {k: (user_input.get(k) or "").strip() for k in oid_keys}
            vendor = (user_input.get("vendor") or "").strip()
            description = (user_input.get("description") or "").strip()
            attestation = bool(user_input.get("attestation", False))
            share_with_community = bool(user_input.get("share_with_community", False))

            if not any(raw_oids.values()):
                overrides = dict(self._options.get(CONF_FEATURE_OVERRIDES, {}) or {})
                overrides.pop("interface_errors", None)
                self._options[CONF_FEATURE_OVERRIDES] = overrides
                self._apply_options()
                return await self.async_step_interface_errors()

            for k, val in raw_oids.items():
                if val and not _is_valid_numeric_oid(val):
                    errors[k] = "invalid_oid"

            if share_with_community and not errors:
                norm_in = _normalize_oid(raw_oids["oid_in_errors"]) if raw_oids["oid_in_errors"] else ""
                norm_out = _normalize_oid(raw_oids["oid_out_errors"]) if raw_oids["oid_out_errors"] else ""
                for item in db.get("interface_errors", {}).get("interface_errors", []):
                    if (
                        norm_in
                        and norm_out
                        and _normalize_oid(item.get("oid_in_errors", "")) == norm_in
                        and _normalize_oid(item.get("oid_out_errors", "")) == norm_out
                        and vendor.lower() in [v.lower() for v in item.get("vendors", [])]
                    ):
                        errors["oid_in_errors"] = "duplicate_oid"
                        break

            if not vendor:
                errors["vendor"] = "required"

            if share_with_community and not attestation:
                errors["attestation"] = "required_attestation_to_share"
            elif attestation and not share_with_community:
                errors["share_with_community"] = "required_share"

            if not errors:
                overrides = dict(self._options.get(CONF_FEATURE_OVERRIDES, {}) or {})
                overrides["interface_errors"] = {
                    k: (_normalize_oid(v) if v else "") for k, v in raw_oids.items()
                }
                overrides["interface_errors"]["vendor"] = vendor
                overrides["interface_errors"]["description"] = description
                self._options[CONF_FEATURE_OVERRIDES] = overrides
                self._apply_options()

                if share_with_community and attestation:
                    self._last_override_feature = "interface_errors"
                    return await self.async_step_submit_pr()
                return await self.async_step_interface_errors()
        else:
            raw_oids = {k: defaults.get(k, "") for k in oid_keys}
            vendor = defaults.get("vendor", "")
            description = defaults.get("description", "")
            attestation = False
            share_with_community = False

        schema = vol.Schema(
            {
                vol.Optional("oid_in_errors"): str,
                vol.Optional("oid_out_errors"): str,
                vol.Optional("oid_in_discards"): str,
                vol.Optional("oid_out_discards"): str,
                vol.Optional("vendor"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=vendor_options,
                        custom_value=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional("description"): str,
                vol.Optional("attestation"): cv.boolean,
                vol.Optional("share_with_community"): cv.boolean,
                vol.Optional("back_to_menu", default=False): cv.boolean,
            }
        )

        suggested = dict(raw_oids)
        suggested.update(
            {
                "vendor": vendor,
                "description": description,
                "attestation": attestation,
                "share_with_community": share_with_community,
            }
        )
        return self.async_show_form(
            step_id="interface_errors_oid_override",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
            description_placeholders={
                "existing_entries": self._get_existing_entries_html("interface_errors")
            },
            errors=errors,
        )
