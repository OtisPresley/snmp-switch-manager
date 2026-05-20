from __future__ import annotations

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ..const import CONF_FEATURE_OVERRIDES
from ..config_flow import _is_valid_numeric_oid, _normalize_oid


class OverridesHardwareMixin:
    """Mixin for OptionsFlowHandler to handle hardware overrides (Fans, PSU, Temperature)."""

    async def async_step_override_fans(self, user_input=None) -> FlowResult:
        """Override Fans OIDs."""
        errors: dict[str, str] = {}
        defaults = self._get_override_defaults("fans")
        
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

            oid_rpm = user_input.get("oid_rpm", "").strip()
            oid_status = user_input.get("oid_status", "").strip()
            vendor = user_input.get("vendor", "").strip()
            method = user_input.get("method", "walk")
            scale_str = str(user_input.get("scale", "1.0")).strip()
            attestation = user_input.get("attestation", False)
            share_with_community = user_input.get("share_with_community", False)
            
            if oid_rpm and not _is_valid_numeric_oid(oid_rpm):
                errors["oid_rpm"] = "invalid_oid"
                
            if oid_status and not _is_valid_numeric_oid(oid_status):
                errors["oid_status"] = "invalid_oid"
                
            if not oid_rpm and not oid_status:
                overrides = dict(self._options.get(CONF_FEATURE_OVERRIDES, {}) or {})
                overrides.pop("fans", None)
                self._options[CONF_FEATURE_OVERRIDES] = overrides
                self._apply_options()
                return await self.async_step_feature_overrides()

            try:
                scale = float(scale_str)
            except ValueError:
                errors["scale"] = "invalid_float"
                scale = 1.0

            if not errors:
                norm_rpm = _normalize_oid(oid_rpm) if oid_rpm else ""
                norm_status = _normalize_oid(oid_status) if oid_status else ""
                if norm_rpm or norm_status:
                    items = db.get("fans", {}).get("fans", [])
                    for item in items:
                        match_rpm = (norm_rpm and _normalize_oid(item.get("oid_rpm", "")) == norm_rpm)
                        match_status = (norm_status and _normalize_oid(item.get("oid_status", "")) == norm_status)
                        if match_rpm or match_status:
                            if vendor.lower() in [v.lower() for v in item.get("vendors", [])]:
                                errors["oid_rpm"] = "duplicate_oid"
                                errors["oid_status"] = "duplicate_oid"
                                break
                            
            if not vendor:
                errors["vendor"] = "required"
                
            if share_with_community and not attestation:
                errors["attestation"] = "required_attestation_to_share"
            elif attestation and not share_with_community:
                errors["share_with_community"] = "required_share"
                
            if not errors:
                overrides = dict(self._options.get(CONF_FEATURE_OVERRIDES, {}) or {})
                overrides["fans"] = {
                    "oid_rpm": _normalize_oid(oid_rpm),
                    "oid_status": _normalize_oid(oid_status),
                    "vendor": vendor,
                    "method": method,
                    "scale": scale,
                }
                self._options[CONF_FEATURE_OVERRIDES] = overrides
                self._apply_options()
                
                if share_with_community and attestation:
                    self._last_override_feature = "fans"
                    return await self.async_step_submit_pr()
                else:
                    return await self.async_step_feature_overrides()
        else:
            oid_rpm = defaults.get("oid_rpm", "")
            oid_status = defaults.get("oid_status", "")
            vendor = defaults.get("vendor", "")
            method = defaults.get("method", "walk")
            scale_str = str(defaults.get("scale", 1.0))
            attestation = False
            share_with_community = False

        schema = vol.Schema(
            {
                vol.Optional("oid_rpm"): str,
                vol.Optional("oid_status"): str,
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
                vol.Optional("scale"): str,
                vol.Optional("attestation"): cv.boolean,
                vol.Optional("share_with_community"): cv.boolean,
                vol.Optional("back_to_menu", default=False): cv.boolean,
            }
        )
        
        return self.async_show_form(
            step_id="override_fans",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    "oid_rpm": oid_rpm,
                    "oid_status": oid_status,
                    "vendor": vendor,
                    "method": method,
                    "scale": scale_str,
                    "attestation": attestation,
                    "share_with_community": share_with_community,
                }
            ),
            description_placeholders={
                "existing_entries": self._get_existing_entries_html("fans")
            },
            errors=errors,
        )

    async def async_step_override_psu(self, user_input=None) -> FlowResult:
        """Override PSU OIDs."""
        errors: dict[str, str] = {}
        defaults = self._get_override_defaults("psu")
        
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

            oid_status = user_input.get("oid_status", "").strip()
            vendor = user_input.get("vendor", "").strip()
            method = user_input.get("method", "walk")
            oid_label = user_input.get("oid_label", "").strip()
            filter_str = user_input.get("filter", "").strip()
            attestation = user_input.get("attestation", False)
            share_with_community = user_input.get("share_with_community", False)
            
            if not oid_status:
                overrides = dict(self._options.get(CONF_FEATURE_OVERRIDES, {}) or {})
                overrides.pop("psu", None)
                self._options[CONF_FEATURE_OVERRIDES] = overrides
                self._apply_options()
                return await self.async_step_feature_overrides()
            elif not _is_valid_numeric_oid(oid_status):
                errors["oid_status"] = "invalid_oid"
                
            if oid_label and not _is_valid_numeric_oid(oid_label):
                errors["oid_label"] = "invalid_oid"
                
            if not errors:
                norm_status = _normalize_oid(oid_status)
                items = db.get("psu", {}).get("psu", [])
                for item in items:
                    if _normalize_oid(item.get("oid_status", "")) == norm_status:
                        if vendor.lower() in [v.lower() for v in item.get("vendors", [])]:
                            errors["oid_status"] = "duplicate_oid"
                            break
                
            if not vendor:
                errors["vendor"] = "required"
                
            if share_with_community and not attestation:
                errors["attestation"] = "required_attestation_to_share"
            elif attestation and not share_with_community:
                errors["share_with_community"] = "required_share"
                
            if not errors:
                overrides = dict(self._options.get(CONF_FEATURE_OVERRIDES, {}) or {})
                overrides["psu"] = {
                    "oid_status": _normalize_oid(oid_status),
                    "vendor": vendor,
                    "method": method,
                }
                if oid_label:
                    overrides["psu"]["oid_label"] = _normalize_oid(oid_label)
                if filter_str:
                    overrides["psu"]["filter"] = filter_str
                    
                self._options[CONF_FEATURE_OVERRIDES] = overrides
                self._apply_options()
                
                if share_with_community and attestation:
                    self._last_override_feature = "psu"
                    return await self.async_step_submit_pr()
                else:
                    return await self.async_step_feature_overrides()
        else:
            oid_status = defaults.get("oid_status", "")
            vendor = defaults.get("vendor", "")
            method = defaults.get("method", "walk")
            oid_label = defaults.get("oid_label", "")
            filter_str = defaults.get("filter", "")
            attestation = False
            share_with_community = False

        schema = vol.Schema(
            {
                vol.Optional("oid_status"): str,
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
                vol.Optional("oid_label"): str,
                vol.Optional("filter"): str,
                vol.Optional("attestation"): cv.boolean,
                vol.Optional("share_with_community"): cv.boolean,
                vol.Optional("back_to_menu", default=False): cv.boolean,
            }
        )
        
        return self.async_show_form(
            step_id="override_psu",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    "oid_status": oid_status,
                    "vendor": vendor,
                    "method": method,
                    "oid_label": oid_label,
                    "filter": filter_str,
                    "attestation": attestation,
                    "share_with_community": share_with_community,
                }
            ),
            description_placeholders={
                "existing_entries": self._get_existing_entries_html("psu")
            },
            errors=errors,
        )

    async def async_step_override_temperature(self, user_input=None) -> FlowResult:
        """Override Temperature OIDs."""
        errors: dict[str, str] = {}
        defaults = self._get_override_defaults("temperature")
        
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
            method = user_input.get("method", "walk")
            oid_state = user_input.get("oid_state", "").strip()
            oid_label = user_input.get("oid_label", "").strip()
            scale_str = str(user_input.get("scale", "1.0")).strip()
            attestation = user_input.get("attestation", False)
            share_with_community = user_input.get("share_with_community", False)
            
            if not oid:
                overrides = dict(self._options.get(CONF_FEATURE_OVERRIDES, {}) or {})
                overrides.pop("temperature", None)
                self._options[CONF_FEATURE_OVERRIDES] = overrides
                self._apply_options()
                return await self.async_step_feature_overrides()
            elif not _is_valid_numeric_oid(oid):
                errors["oid"] = "invalid_oid"
                
            if oid_state and not _is_valid_numeric_oid(oid_state):
                errors["oid_state"] = "invalid_oid"
                
            if oid_label and not _is_valid_numeric_oid(oid_label):
                errors["oid_label"] = "invalid_oid"
                
            try:
                scale = float(scale_str)
            except ValueError:
                errors["scale"] = "invalid_float"
                scale = 1.0

            if not errors:
                norm_oid = _normalize_oid(oid)
                items = db.get("temperature", {}).get("temperature", [])
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
                overrides["temperature"] = {
                    "oid": _normalize_oid(oid),
                    "vendor": vendor,
                    "method": method,
                    "scale": scale,
                }
                if oid_state:
                    overrides["temperature"]["oid_state"] = _normalize_oid(oid_state)
                if oid_label:
                    overrides["temperature"]["oid_label"] = _normalize_oid(oid_label)
                    
                self._options[CONF_FEATURE_OVERRIDES] = overrides
                self._apply_options()
                
                if share_with_community and attestation:
                    self._last_override_feature = "temperature"
                    return await self.async_step_submit_pr()
                else:
                    return await self.async_step_feature_overrides()
        else:
            oid = defaults.get("oid", "")
            vendor = defaults.get("vendor", "")
            method = defaults.get("method", "walk")
            oid_state = defaults.get("oid_state", "")
            oid_label = defaults.get("oid_label", "")
            scale_str = str(defaults.get("scale", 1.0))
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
                vol.Optional("oid_state"): str,
                vol.Optional("oid_label"): str,
                vol.Optional("scale"): str,
                vol.Optional("attestation"): cv.boolean,
                vol.Optional("share_with_community"): cv.boolean,
                vol.Optional("back_to_menu", default=False): cv.boolean,
            }
        )
        
        return self.async_show_form(
            step_id="override_temperature",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    "oid": oid,
                    "vendor": vendor,
                    "method": method,
                    "oid_state": oid_state,
                    "oid_label": oid_label,
                    "scale": scale_str,
                    "attestation": attestation,
                    "share_with_community": share_with_community,
                }
            ),
            description_placeholders={
                "existing_entries": self._get_existing_entries_html("temperature")
            },
            errors=errors,
        )
