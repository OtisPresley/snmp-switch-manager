from __future__ import annotations

import re
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ..const import (
    CONF_PORT_RENAME_USER_RULES,
    DEFAULT_PORT_RENAME_RULES,
    CONF_PORT_RENAME_DISABLED_DEFAULT_IDS,
)


class InterfacesNamingMixin:
    """Mixin for OptionsFlowHandler to handle port rename and naming rules steps."""

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
        """Manage Custom Rename Rules using the standard rule dialog."""
        STEP_ID = "port_rename_custom"

        KEY_ACTION = "rule_action"
        KEY_EXISTING = "rule_existing"
        KEY_MATCH = "rule_match"
        KEY_VALUE = "rule_value"
        KEY_REPLACE = "rule_replace"

        rules: list[dict] = list(self._options.get(CONF_PORT_RENAME_USER_RULES) or [])

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

                rules = [r for i, r in enumerate(rules) if i != idx]

                if action == "edit":
                    if value:
                        pat = _build_pattern(match, value)
                        if not _is_valid_regex(pat):
                            errors[KEY_VALUE] = "invalid_regex"
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

                    rep = replace if (replace is not None and replace != "") else old_rep

                    rules.insert(idx, {"pattern": pat, "replace": rep, "description": str(old.get("description") or "")})
                    self._options[CONF_PORT_RENAME_USER_RULES] = rules if rules else []
                    if not rules:
                        self._options.pop(CONF_PORT_RENAME_USER_RULES, None)
                    self._apply_options()
                    return await self.async_step_port_rename_custom()

                if rules:
                    self._options[CONF_PORT_RENAME_USER_RULES] = rules
                else:
                    self._options.pop(CONF_PORT_RENAME_USER_RULES, None)
                self._apply_options()
                return await self.async_step_port_rename_custom()

        return self.async_show_form(
            step_id=STEP_ID,
            data_schema=self._port_rename_custom_schema(existing_labels),
            description_placeholders={"current": current_rules},
            errors=errors,
        )

    def _port_rename_custom_schema(self, existing_labels: list[str]) -> vol.Schema:
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
