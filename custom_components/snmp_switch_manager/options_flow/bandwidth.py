from __future__ import annotations

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ..const import (
    CONF_BW_ENABLE,
    CONF_BW_MODE,
    BW_MODE_SENSORS,
    BW_MODE_ATTRIBUTES,
    CONF_BANDWIDTH_POLL_INTERVAL,
    DEFAULT_BANDWIDTH_POLL_INTERVAL,
    CONF_BW_INCLUDE_STARTS_WITH,
    CONF_BW_INCLUDE_CONTAINS,
    CONF_BW_INCLUDE_ENDS_WITH,
    CONF_BW_EXCLUDE_STARTS_WITH,
    CONF_BW_EXCLUDE_CONTAINS,
    CONF_BW_EXCLUDE_ENDS_WITH,
    CONF_BW_RX_THROUGHPUT_ICON,
    CONF_BW_TX_THROUGHPUT_ICON,
    CONF_BW_RX_TOTAL_ICON,
    CONF_BW_TX_TOTAL_ICON,
)


class BandwidthOptionsMixin:
    """Mixin for OptionsFlowHandler to handle bandwidth-related steps."""

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
            if user_input.get("back_to_menu"):
                return await self.async_step_bandwidth_sensors()

            self._options[CONF_BW_ENABLE] = bool(user_input.get(CONF_BW_ENABLE))
            self._options[CONF_BW_MODE] = user_input.get(CONF_BW_MODE, BW_MODE_SENSORS)
            self._apply_options()
            return await self.async_step_bandwidth_sensors()

        enabled = self._options.get(CONF_BW_ENABLE, False)
        mode = self._options.get(CONF_BW_MODE, BW_MODE_SENSORS)

        schema = vol.Schema(
            {
                vol.Required(CONF_BW_ENABLE, default=enabled): cv.boolean,
                vol.Required(CONF_BW_MODE, default=mode): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[BW_MODE_SENSORS, BW_MODE_ATTRIBUTES],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="bandwidth_data_as",
                    )
                ),
                vol.Optional("back_to_menu", default=False): cv.boolean,
            }
        )
        return self.async_show_form(step_id="bandwidth_enable_disable", data_schema=schema)

    async def async_step_bandwidth_poll_interval(self, user_input=None) -> FlowResult:
        """Set poll interval for bandwidth sensors."""
        errors = {}
        current = self._options.get(CONF_BANDWIDTH_POLL_INTERVAL, DEFAULT_BANDWIDTH_POLL_INTERVAL)

        if user_input is not None:
            if user_input.get("back_to_menu"):
                return await self.async_step_bandwidth_sensors()

            raw = user_input.get(CONF_BANDWIDTH_POLL_INTERVAL, current)
            try:
                if isinstance(raw, dict) and "value" in raw:
                    raw = raw["value"]
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
            ),
            vol.Optional("back_to_menu", default=False): cv.boolean,
        })
        return self.async_show_form(step_id="bandwidth_poll_interval", data_schema=schema, errors=errors)

    async def async_step_bandwidth_include_rules(self, user_input=None) -> FlowResult:
        return await self._async_step_bw_rules(include=True, user_input=user_input, return_to="bandwidth_sensors")

    async def async_step_bandwidth_exclude_rules(self, user_input=None) -> FlowResult:
        return await self._async_step_bw_rules(include=False, user_input=user_input, return_to="bandwidth_sensors")

    def _render_bw_rules(self, *, include: bool) -> str:
        """Render bandwidth include/exclude rules from bandwidth option keys."""
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

        return "\n".join(f"- {p}" for p in parts) if parts else "none"

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

    async def async_step_bandwidth_icons(self, user_input=None) -> FlowResult:
        """Optional icon overrides for bandwidth sensors."""
        options = dict(self._options)

        current = {
            CONF_BW_RX_THROUGHPUT_ICON: (options.get(CONF_BW_RX_THROUGHPUT_ICON) or "").strip(),
            CONF_BW_TX_THROUGHPUT_ICON: (options.get(CONF_BW_TX_THROUGHPUT_ICON) or "").strip(),
            CONF_BW_RX_TOTAL_ICON: (options.get(CONF_BW_RX_TOTAL_ICON) or "").strip(),
            CONF_BW_TX_TOTAL_ICON: (options.get(CONF_BW_TX_TOTAL_ICON) or "").strip(),
        }

        if user_input is not None:
            if user_input.get("back_to_menu"):
                return await self.async_step_bandwidth_sensors()

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
                vol.Optional("back_to_menu", default=False): cv.boolean,
            }
        )

        return self.async_show_form(
            step_id="bandwidth_icons",
            data_schema=schema,
        )
