from __future__ import annotations

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ..const import CONF_ICON_RULES


class InterfacesIconsMixin:
    """Mixin for OptionsFlowHandler to handle entity icon rules steps."""

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
                vol.Optional("back_to_menu", default=False): cv.boolean,
            }
        )

    async def _step_icon_rules(self, user_input) -> FlowResult:
        if user_input.get("back_to_menu"):
            return await self.async_step_manage_interfaces()

        KEY_ACTION = "icon_action"
        KEY_MATCH = "icon_match"
        KEY_VALUE = "icon_value"
        KEY_ICON = "icon_icon"
        KEY_EXISTING = "icon_existing"

        action = user_input.get(KEY_ACTION)
        if action == "done":
            return await self.async_step_manage_interfaces()

        rules = list(self._options.get(CONF_ICON_RULES, []) or [])
        label_to_index: dict[str, int] = {}
        for idx, r in enumerate(rules):
            label = f"{idx+1}. {r.get('match')}: {r.get('value')} -> {r.get('icon')}"
            label_to_index[label] = idx

        if action == "clear":
            self._options.pop(CONF_ICON_RULES, None)
            self._apply_options()
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

        return await self.async_step_entity_icon_rules()
