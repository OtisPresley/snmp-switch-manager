from __future__ import annotations

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ..const import CONF_FEATURE_OVERRIDES
from ..config_flow import _is_valid_numeric_oid, _normalize_oid


class OverridesPowerMixin:
    """Mixin for OptionsFlowHandler to handle power-related overrides (Power, PoE)."""

    async def async_step_override_power(self, user_input=None) -> FlowResult:
        """Override Power OIDs."""
        errors: dict[str, str] = {}
        defaults = self._get_override_defaults("power")
        
        db = self._get_database()
        db_vendors = db.get("vendors", {}).get("vendors", [])
        vendor_options = [
            selector.SelectOptionDict(value=v["name"], label=v["name"])
            for v in db_vendors
        ]
        if not vendor_options:
            vendor_options = [
                selector.SelectOptionDict(value="Dell", label="Dell"),
                selector.SelectOptionDict(value="Cisco", label="Cisco"),
                selector.SelectOptionDict(value="H3C", label="H3C"),
            ]

        if user_input is not None:
            if user_input.get("back_to_menu"):
                return await self.async_step_feature_overrides()

            oid = user_input.get("oid", "").strip()
            vendor = user_input.get("vendor", "").strip()
            method = user_input.get("method", "get")
            description = user_input.get("description", "")
            attestation = user_input.get("attestation", False)
            share_with_community = user_input.get("share_with_community", False)
            
            if not oid:
                overrides = dict(self._options.get(CONF_FEATURE_OVERRIDES, {}) or {})
                overrides.pop("power", None)
                self._options[CONF_FEATURE_OVERRIDES] = overrides
                self._apply_options()
                return await self.async_step_feature_overrides()
            elif not _is_valid_numeric_oid(oid):
                errors["oid"] = "invalid_oid"
                
            if not errors:
                norm_oid = _normalize_oid(oid)
                items = db.get("power", {}).get("power", [])
                for item in items:
                    if _normalize_oid(item.get("oid", "")) == norm_oid:
                        if vendor.lower() in [v.lower() for v in item.get("vendors", [])]:
                            errors["oid"] = "duplicate_oid"
                            break
                            
            if not vendor:
                errors["vendor"] = "required"
                
            if share_with_community and not attestation:
                errors["attestation"] = "required_attestation_to_share"
            elif attestation and not share_with_community:
                errors["share_with_community"] = "required_share"
                
            if not errors:
                overrides = dict(self._options.get(CONF_FEATURE_OVERRIDES, {}) or {})
                overrides["power"] = {
                    "oid": _normalize_oid(oid),
                    "vendor": vendor,
                    "method": method,
                    "description": description,
                }
                self._options[CONF_FEATURE_OVERRIDES] = overrides
                self._apply_options()
                
                if share_with_community and attestation:
                    self._last_override_feature = "power"
                    return await self.async_step_submit_pr()
                else:
                    return await self.async_step_feature_overrides()
        else:
            oid = defaults.get("oid", "")
            vendor = defaults.get("vendor", "")
            method = defaults.get("method", "get")
            description = defaults.get("description", "")
            attestation = False
            share_with_community = False

        schema = vol.Schema(
            {
                vol.Optional("oid"): str,
                vol.Optional("vendor"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=vendor_options,
                        custom_value=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional("method"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="get", label="GET"),
                            selector.SelectOptionDict(value="walk", label="WALK"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional("description"): str,
                vol.Optional("attestation"): cv.boolean,
                vol.Optional("share_with_community"): cv.boolean,
                vol.Optional("back_to_menu", default=False): cv.boolean,
            }
        )
        
        return self.async_show_form(
            step_id="override_power",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    "oid": oid,
                    "vendor": vendor,
                    "method": method,
                    "description": description,
                    "attestation": attestation,
                    "share_with_community": share_with_community,
                }
            ),
            description_placeholders={
                "existing_entries": self._get_existing_entries_html("power")
            },
            errors=errors,
        )

    async def async_step_override_poe(self, user_input=None) -> FlowResult:
        """Override PoE OIDs."""
        errors: dict[str, str] = {}
        defaults = self._get_override_defaults("poe")
        
        db = self._get_database()
        db_vendors = db.get("vendors", {}).get("vendors", [])
        vendor_options = [
            selector.SelectOptionDict(value=v["name"], label=v["name"])
            for v in db_vendors
        ]
        if not vendor_options:
            vendor_options = [
                selector.SelectOptionDict(value="Dell", label="Dell"),
                selector.SelectOptionDict(value="Cisco", label="Cisco"),
                selector.SelectOptionDict(value="H3C", label="H3C"),
            ]

        if user_input is not None:
            if user_input.get("back_to_menu"):
                return await self.async_step_feature_overrides()

            oid_budget = user_input.get("oid_budget", "").strip()
            oid_used = user_input.get("oid_used", "").strip()
            oid_port_power = user_input.get("oid_port_power", "").strip()
            vendor = user_input.get("vendor", "").strip()
            method = user_input.get("method", "get")
            description = user_input.get("description", "")
            attestation = user_input.get("attestation", False)
            share_with_community = user_input.get("share_with_community", False)
            
            if oid_budget and not _is_valid_numeric_oid(oid_budget):
                errors["oid_budget"] = "invalid_oid"
            if oid_used and not _is_valid_numeric_oid(oid_used):
                errors["oid_used"] = "invalid_oid"
            if oid_port_power and not _is_valid_numeric_oid(oid_port_power):
                errors["oid_port_power"] = "invalid_oid"

            if not oid_budget and not oid_used and not oid_port_power:
                overrides = dict(self._options.get(CONF_FEATURE_OVERRIDES, {}) or {})
                overrides.pop("poe", None)
                self._options[CONF_FEATURE_OVERRIDES] = overrides
                self._apply_options()
                return await self.async_step_feature_overrides()
                
            if not vendor:
                errors["vendor"] = "required"
                
            if share_with_community and not attestation:
                errors["attestation"] = "required_attestation_to_share"
            elif attestation and not share_with_community:
                errors["share_with_community"] = "required_share"
                
            if not errors:
                norm_budget = _normalize_oid(oid_budget) if oid_budget else ""
                norm_used = _normalize_oid(oid_used) if oid_used else ""
                norm_port = _normalize_oid(oid_port_power) if oid_port_power else ""
                
                items = db.get("poe", {}).get("poe", [])
                for item in items:
                    match_budget = (norm_budget and _normalize_oid(item.get("oid_budget", "")) == norm_budget)
                    match_used = (norm_used and _normalize_oid(item.get("oid_used", "")) == norm_used)
                    match_port = (norm_port and _normalize_oid(item.get("oid_port_power", "")) == norm_port)
                    
                    if match_budget or match_used or match_port:
                        if vendor.lower() in [v.lower() for v in item.get("vendors", [])]:
                            if match_budget:
                                errors["oid_budget"] = "duplicate_oid"
                            elif match_used:
                                errors["oid_used"] = "duplicate_oid"
                            elif match_port:
                                errors["oid_port_power"] = "duplicate_oid"
                            break

            if not errors:
                overrides = dict(self._options.get(CONF_FEATURE_OVERRIDES, {}) or {})
                overrides["poe"] = {
                    "vendor": vendor,
                    "method": method,
                    "description": description,
                }
                if oid_budget:
                    overrides["poe"]["oid_budget"] = _normalize_oid(oid_budget)
                if oid_used:
                    overrides["poe"]["oid_used"] = _normalize_oid(oid_used)
                if oid_port_power:
                    overrides["poe"]["oid_port_power"] = _normalize_oid(oid_port_power)

                self._options[CONF_FEATURE_OVERRIDES] = overrides
                self._apply_options()
                
                if share_with_community and attestation:
                    self._last_override_feature = "poe"
                    return await self.async_step_submit_pr()
                else:
                    return await self.async_step_feature_overrides()
        else:
            oid_budget = defaults.get("oid_budget", "")
            oid_used = defaults.get("oid_used", "")
            oid_port_power = defaults.get("oid_port_power", "")
            vendor = defaults.get("vendor", "")
            method = defaults.get("method", "get")
            description = defaults.get("description", "")
            attestation = False
            share_with_community = False

        schema = vol.Schema(
            {
                vol.Optional("oid_budget"): str,
                vol.Optional("oid_used"): str,
                vol.Optional("oid_port_power"): str,
                vol.Optional("vendor"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=vendor_options,
                        custom_value=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional("method"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="get", label="GET"),
                            selector.SelectOptionDict(value="walk", label="WALK"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional("description"): str,
                vol.Optional("attestation"): cv.boolean,
                vol.Optional("share_with_community"): cv.boolean,
                vol.Optional("back_to_menu", default=False): cv.boolean,
            }
        )
        
        return self.async_show_form(
            step_id="override_poe",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    "oid_budget": oid_budget,
                    "oid_used": oid_used,
                    "oid_port_power": oid_port_power,
                    "vendor": vendor,
                    "method": method,
                    "description": description,
                    "attestation": attestation,
                    "share_with_community": share_with_community,
                }
            ),
            description_placeholders={
                "existing_entries": self._get_existing_entries_html("poe")
            },
            errors=errors,
        )
