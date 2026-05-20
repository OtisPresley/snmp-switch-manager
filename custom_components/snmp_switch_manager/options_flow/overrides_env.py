from __future__ import annotations

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ..const import (
    CONF_ENV_ENABLE,
    CONF_ENV_MODE,
    ENV_MODE_SENSORS,
    ENV_MODE_ATTRIBUTES,
    CONF_POE_ENABLE,
    CONF_POE_MODE,
    CONF_POE_PER_PORT_POWER,
    POE_MODE_SENSORS,
    POE_MODE_ATTRIBUTES,
    CONF_POE_POLL_INTERVAL,
    DEFAULT_POE_POLL_INTERVAL,
    CONF_ENV_POLL_INTERVAL,
    DEFAULT_ENV_POLL_INTERVAL,
)


class OverridesEnvMixin:
    """Mixin for OptionsFlowHandler to handle environmental sensor settings and PR submission steps."""

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

    async def async_step_environmental_enable_disable(self, user_input=None) -> FlowResult:
        """Enable/disable Environmental + PoE options."""
        if user_input is not None:
            if user_input.get("back_to_menu"):
                return await self.async_step_environmental_sensors()

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
                ): cv.boolean,
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
                ): cv.boolean,
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
                ): cv.boolean,
                vol.Optional("back_to_menu", default=False): cv.boolean,
            }
        )

        return self.async_show_form(step_id="environmental_enable_disable", data_schema=schema)

    async def async_step_poe_poll_interval(self, user_input=None) -> FlowResult:
        """Set PoE polling interval (seconds)."""
        if user_input is not None:
            if user_input.get("back_to_menu"):
                return await self.async_step_environmental_sensors()
            self._options[CONF_POE_POLL_INTERVAL] = user_input[CONF_POE_POLL_INTERVAL]
            self._apply_options()
            return await self.async_step_environmental_sensors()

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_POE_POLL_INTERVAL,
                    default=self._options.get(CONF_POE_POLL_INTERVAL, DEFAULT_POE_POLL_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=3600)),
                vol.Optional("back_to_menu", default=False): cv.boolean,
            }
        )
        return self.async_show_form(step_id="poe_poll_interval", data_schema=schema)

    async def async_step_environmental_poll_interval(self, user_input=None) -> FlowResult:
        """Set Environmental polling interval (seconds)."""
        if user_input is not None:
            if user_input.get("back_to_menu"):
                return await self.async_step_environmental_sensors()
            self._options[CONF_ENV_POLL_INTERVAL] = user_input[CONF_ENV_POLL_INTERVAL]
            self._apply_options()
            return await self.async_step_environmental_sensors()

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_ENV_POLL_INTERVAL,
                    default=self._options.get(CONF_ENV_POLL_INTERVAL, DEFAULT_ENV_POLL_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=3600)),
                vol.Optional("back_to_menu", default=False): cv.boolean,
            }
        )
        return self.async_show_form(step_id="environmental_poll_interval", data_schema=schema)

    async def async_step_ask_pr(self, user_input=None) -> FlowResult:
        """Ask if user wants to submit PR."""
        if user_input is not None:
            if user_input.get("submit"):
                return await self.async_step_submit_pr()
            return await self.async_step_feature_overrides()
            
        return self.async_show_form(
            step_id="ask_pr",
            data_schema=vol.Schema({vol.Required("submit", default=True): cv.boolean}),
        )

    async def async_step_submit_pr(self, user_input=None) -> FlowResult:
        """Show GitHub device auth code and wait for user to confirm they have authorized."""
        errors: dict[str, str] = {}

        # Ensure we have a device code
        if not hasattr(self, "_device_code") or not self._device_code:
            from ..github import request_device_code, GITHUB_CLIENT_ID
            data = await request_device_code(GITHUB_CLIENT_ID)
            if data:
                self._device_code = data.get("device_code")
                self._user_code = data.get("user_code")
                self._verification_uri = data.get("verification_uri")
            else:
                return await self.async_step_github_connection_error()

        if user_input is not None:
            if user_input.get("back_to_menu"):
                # Clear auth state and return
                self._device_code = None
                if hasattr(self, "_community_pr_feature"):
                    return await self.async_step_manage_interfaces()
                return await self.async_step_feature_overrides()

            if user_input.get("authorized"):
                from ..github import poll_for_token, GITHUB_CLIENT_ID
                token = await poll_for_token(
                    GITHUB_CLIENT_ID,
                    getattr(self, "_device_code", ""),
                    interval=1,
                )
                if token:
                    self._github_token = token
                    self._device_code = None
                    return await self.async_step_create_pr()
                else:
                    errors["authorized"] = "authorization_pending"

        return self.async_show_form(
            step_id="submit_pr",
            data_schema=vol.Schema({
                vol.Optional("authorized", default=False): cv.boolean,
                vol.Optional("back_to_menu", default=False): cv.boolean,
            }),
            description_placeholders={
                "code": getattr(self, "_user_code", "ERROR"),
                "url": getattr(self, "_verification_uri", "https://github.com/login/device"),
            },
            errors=errors,
        )

    async def async_step_create_pr(self, user_input=None) -> FlowResult:
        """Create PR and show result. user_input dismisses the result screen."""
        if user_input is not None:
            # Clear community PR state
            self._community_pr_feature = None
            self._community_pr_data = None
            if hasattr(self, "_last_override_feature") and self._last_override_feature:
                return await self.async_step_feature_overrides()
            return await self.async_step_manage_interfaces()

        feature = getattr(self, "_community_pr_feature", None) or getattr(self, "_last_override_feature", None)
        token = getattr(self, "_github_token", None)

        if not feature or not token:
            return self.async_show_form(
                step_id="create_pr",
                data_schema=vol.Schema({}),
                description_placeholders={"status": "Missing feature or token!"},
            )

        if hasattr(self, "_community_pr_data") and self._community_pr_data:
            overrides = self._community_pr_data
        else:
            overrides = (self._options.get("feature_overrides") or {}).get(feature)

        if not overrides:
            return self.async_show_form(
                step_id="create_pr",
                data_schema=vol.Schema({}),
                description_placeholders={"status": "No override data found for feature!"},
            )

        from ..github import submit_override
        success = await submit_override(token, feature, overrides)

        if success:
            status = "Successfully created Pull Request on GitHub! Thank you for contributing."
        else:
            status = "Failed to create Pull Request. Please check the Home Assistant logs for details."

        return self.async_show_form(
            step_id="create_pr",
            data_schema=vol.Schema({}),
            description_placeholders={"status": status},
        )

    async def async_step_github_connection_error(self, user_input=None) -> FlowResult:
        """Show error when connection to GitHub fails."""
        if user_input is not None:
            if hasattr(self, "_community_pr_feature"):
                return await self.async_step_manage_interfaces()
            return await self.async_step_feature_overrides()
            
        return self.async_show_form(
            step_id="github_connection_error",
            data_schema=vol.Schema({}),
        )
