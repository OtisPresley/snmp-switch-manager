from __future__ import annotations

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ..const import (
    CONF_HIDE_IP_ON_PHYSICAL,
    CONF_HIDE_IP_ON_PHYSICAL_INTERFACES,
    CONF_INCLUDE_STARTS_WITH,
    CONF_INCLUDE_CONTAINS,
    CONF_INCLUDE_ENDS_WITH,
    CONF_EXCLUDE_STARTS_WITH,
    CONF_EXCLUDE_CONTAINS,
    CONF_EXCLUDE_ENDS_WITH,
    CONF_DISABLED_VENDOR_FILTER_RULE_IDS,
    BUILTIN_VENDOR_FILTER_RULES,
)


class InterfacesOptionsMixin:
    """Mixin for OptionsFlowHandler to handle interface-related steps."""

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
            if user_input.get("back_to_menu"):
                return await self.async_step_manage_interfaces()

            enabled = bool(
                user_input.get(CONF_HIDE_IP_ON_PHYSICAL_INTERFACES,
                               user_input.get(CONF_HIDE_IP_ON_PHYSICAL, False))
            )
            self._options[CONF_HIDE_IP_ON_PHYSICAL_INTERFACES] = enabled
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
                    vol.Optional("back_to_menu", default=False): cv.boolean,
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
            if user_input.get("back_to_menu"):
                return await getattr(self, f"async_step_{return_to}")()

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
                vol.Optional("back_to_menu", default=False): cv.boolean,
            }
        )

        return self.async_show_form(
            step_id=STEP_ID,
            data_schema=schema,
            description_placeholders={"current_rules": current_rules},
        )

    async def async_step_builtin_filters(self, user_input=None) -> FlowResult:
        """Enable/disable built-in vendor interface filtering rules."""
        current_disabled: list[str] = list(self._options.get(CONF_DISABLED_VENDOR_FILTER_RULE_IDS, []) or [])
        options_map = {r["id"]: r["label"] for r in BUILTIN_VENDOR_FILTER_RULES}

        if user_input is not None:
            if user_input.get("back_to_menu"):
                return await self.async_step_manage_interfaces()

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
                vol.Optional("back_to_menu", default=False): cv.boolean,
            }
        )

        return self.async_show_form(
            step_id="builtin_filters",
            description_placeholders={},
            data_schema=schema,
        )
