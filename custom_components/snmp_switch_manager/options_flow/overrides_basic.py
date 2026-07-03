from __future__ import annotations

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ..const import CONF_FEATURE_OVERRIDES
from ..config_flow import _is_valid_numeric_oid, _normalize_oid, OID_FIELDS


class OverridesBasicMixin:
    """Mixin for OptionsFlowHandler to handle basic feature overrides (Device Info, CPU, Memory)."""

    async def async_step_feature_overrides(self, user_input=None) -> FlowResult:
        """Manage feature OID overrides."""
        return self.async_show_menu(
            step_id="feature_overrides",
            menu_options=[
                "override_device_info",
                "override_cpu",
                "override_memory",
                "override_fans",
                "override_psu",
                "override_temperature",
                "override_power",
                "override_poe",
                "back",
            ],
        )

    async def async_step_override_device_info(self, user_input=None) -> FlowResult:
        """Override Device Info OIDs."""
        errors: dict[str, str] = {}
        overrides_all = dict(self._options.get(CONF_FEATURE_OVERRIDES, {}) or {})
        defaults = overrides_all.get("device_info", {})
        
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

            vendor = user_input.get("vendor", "").strip()
            attestation = user_input.get("attestation", False)
            share_with_community = user_input.get("share_with_community", False)

            new_custom: dict[str, str] = {}
            has_any = False
            for key, _label in OID_FIELDS:
                field = f"{key}_oid"
                raw = (user_input.get(field) or "").strip()
                if raw:
                    has_any = True
                    if not _is_valid_numeric_oid(raw):
                        errors[field] = "invalid_oid"
                        continue
                    norm = _normalize_oid(raw)
                    if norm:
                        new_custom[key] = norm

            if not vendor:
                errors["vendor"] = "required"

            if share_with_community and not attestation:
                errors["attestation"] = "required_attestation_to_share"
            elif attestation and not share_with_community:
                errors["share_with_community"] = "required_share"

            if not has_any and not errors:
                overrides_all.pop("device_info", None)
                self._options[CONF_FEATURE_OVERRIDES] = overrides_all
                self._apply_options()
                return await self.async_step_feature_overrides()

            if not errors:
                norm_mfg = new_custom.get("manufacturer", "")
                norm_model = new_custom.get("model", "")
                norm_firm = new_custom.get("firmware", "")
                norm_host = new_custom.get("hostname", "")
                norm_up = new_custom.get("uptime", "")
                norm_contact = new_custom.get("contact", "")
                norm_name = new_custom.get("name", "")
                norm_loc = new_custom.get("location", "")
                
                items = db.get("device_info", {}).get("device_info", [])
                for item in items:
                    match_mfg = (norm_mfg and _normalize_oid(item.get("oid_mfg", "")) == norm_mfg)
                    match_model = (norm_model and _normalize_oid(item.get("oid_model", "")) == norm_model)
                    match_firm = (norm_firm and _normalize_oid(item.get("oid_firmware", "")) == norm_firm)
                    match_host = (norm_host and _normalize_oid(item.get("oid_hostname", "")) == norm_host)
                    match_up = (norm_up and _normalize_oid(item.get("oid_uptime", "")) == norm_up)
                    match_contact = (norm_contact and _normalize_oid(item.get("oid_contact", "")) == norm_contact)
                    match_name = (norm_name and _normalize_oid(item.get("oid_name", "")) == norm_name)
                    match_loc = (norm_loc and _normalize_oid(item.get("oid_location", "")) == norm_loc)
                    
                    if match_mfg or match_model or match_firm or match_host or match_up or match_contact or match_name or match_loc:
                        if vendor.lower() in [v.lower() for v in item.get("vendors", [])]:
                            if match_mfg:
                                errors["manufacturer_oid"] = "duplicate_oid"
                            elif match_model:
                                errors["model_oid"] = "duplicate_oid"
                            elif match_firm:
                                errors["firmware_oid"] = "duplicate_oid"
                            elif match_host:
                                errors["hostname_oid"] = "duplicate_oid"
                            elif match_up:
                                errors["uptime_oid"] = "duplicate_oid"
                            elif match_contact:
                                errors["contact_oid"] = "duplicate_oid"
                            elif match_name:
                                errors["name_oid"] = "duplicate_oid"
                            elif match_loc:
                                errors["location_oid"] = "duplicate_oid"
                            break

            if not errors:
                new_custom["vendor"] = vendor
                overrides_all["device_info"] = new_custom
                self._options[CONF_FEATURE_OVERRIDES] = overrides_all
                self._apply_options()
                
                if share_with_community and attestation:
                    self._last_override_feature = "device_info"
                    return await self.async_step_submit_pr()
                else:
                    return await self.async_step_feature_overrides()
        else:
            vendor = defaults.get("vendor") or self._get_device_vendor()
            attestation = False
            share_with_community = False

        schema_dict = {}
        for key, _label in OID_FIELDS:
            schema_dict[vol.Optional(f"{key}_oid")] = str

        schema_dict.update({
            vol.Optional("vendor"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=vendor_options,
                    custom_value=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional("attestation"): cv.boolean,
            vol.Optional("share_with_community"): cv.boolean,
            vol.Optional("back_to_menu", default=False): cv.boolean,
        })

        suggested = {}
        for key, _label in OID_FIELDS:
            suggested[f"{key}_oid"] = str(defaults.get(key, ""))
        suggested.update({
            "vendor": vendor,
            "attestation": attestation,
            "share_with_community": share_with_community,
        })

        return self.async_show_form(
            step_id="override_device_info",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(schema_dict),
                suggested
            ),
            description_placeholders={
                "existing_entries": self._get_existing_entries_html("device_info")
            },
            errors=errors,
        )

    async def async_step_override_cpu(self, user_input=None) -> FlowResult:
        """Override CPU OID."""
        errors: dict[str, str] = {}
        defaults = self._get_override_defaults("cpu")
        
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
            scale_str = str(user_input.get("scale", "1.0")).strip()
            unit = user_input.get("unit", "%")
            description = user_input.get("description", "")
            attestation = user_input.get("attestation", False)
            share_with_community = user_input.get("share_with_community", False)
            
            if not oid:
                overrides = dict(self._options.get(CONF_FEATURE_OVERRIDES, {}) or {})
                overrides.pop("cpu", None)
                self._options[CONF_FEATURE_OVERRIDES] = overrides
                self._apply_options()
                return await self.async_step_feature_overrides()
            elif not _is_valid_numeric_oid(oid):
                errors["oid"] = "invalid_oid"
            else:
                norm_oid = _normalize_oid(oid)
                items = db.get("cpu", {}).get("cpu", [])
                for item in items:
                    if _normalize_oid(item.get("oid", "")) == norm_oid:
                        if vendor.lower() in [v.lower() for v in item.get("vendors", [])]:
                            errors["oid"] = "duplicate_oid"
                            break
                
            if not vendor:
                errors["vendor"] = "required"
                
            try:
                scale = float(scale_str)
            except ValueError:
                errors["scale"] = "invalid_float"
                scale = 1.0

            if share_with_community and not attestation:
                errors["attestation"] = "required_attestation_to_share"
            elif attestation and not share_with_community:
                errors["share_with_community"] = "required_share"
                
            if not errors:
                overrides = dict(self._options.get(CONF_FEATURE_OVERRIDES, {}) or {})
                overrides["cpu"] = {
                    "oid": _normalize_oid(oid),
                    "vendor": vendor,
                    "method": method,
                    "scale": scale,
                    "unit": unit,
                    "description": description,
                }
                self._options[CONF_FEATURE_OVERRIDES] = overrides
                self._apply_options()
                
                if share_with_community and attestation:
                    self._last_override_feature = "cpu"
                    return await self.async_step_submit_pr()
                else:
                    return await self.async_step_feature_overrides()
        else:
            oid = defaults.get("oid", "")
            vendor = defaults.get("vendor", "")
            method = defaults.get("method", "get")
            scale_str = str(defaults.get("scale", 1.0))
            unit = defaults.get("unit", "%")
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
                vol.Optional("scale"): str,
                vol.Optional("unit"): str,
                vol.Optional("description"): str,
                vol.Optional("attestation"): cv.boolean,
                vol.Optional("share_with_community"): cv.boolean,
                vol.Optional("back_to_menu", default=False): cv.boolean,
            }
        )
        
        return self.async_show_form(
            step_id="override_cpu",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    "oid": oid,
                    "vendor": vendor,
                    "method": method,
                    "scale": scale_str,
                    "unit": unit,
                    "description": description,
                    "attestation": attestation,
                    "share_with_community": share_with_community,
                }
            ),
            description_placeholders={
                "existing_entries": self._get_existing_entries_html("cpu")
            },
            errors=errors,
        )

    async def async_step_override_memory(self, user_input=None) -> FlowResult:
        """Override Memory OIDs."""
        errors: dict[str, str] = {}
        defaults = self._get_override_defaults("memory")
        
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
            oid_free = user_input.get("oid_free", "").strip()
            oid_total = user_input.get("oid_total", "").strip()
            vendor = user_input.get("vendor", "").strip()
            method = user_input.get("method", "get")
            scale_str = str(user_input.get("scale", "1.0")).strip()
            attestation = user_input.get("attestation", False)
            share_with_community = user_input.get("share_with_community", False)
            
            if not oid and not oid_free and not oid_total:
                overrides = dict(self._options.get(CONF_FEATURE_OVERRIDES, {}) or {})
                overrides.pop("memory", None)
                self._options[CONF_FEATURE_OVERRIDES] = overrides
                self._apply_options()
                return await self.async_step_feature_overrides()

            if oid:
                if oid_free or oid_total:
                    errors["base"] = "either_percentage_or_free_total"
                elif not _is_valid_numeric_oid(oid):
                    errors["oid"] = "invalid_oid"
            else:
                if not oid_free or not oid_total:
                    if not oid_free:
                        errors["oid_free"] = "required"
                    if not oid_total:
                        errors["oid_total"] = "required"
                else:
                    if not _is_valid_numeric_oid(oid_free):
                        errors["oid_free"] = "invalid_oid"
                    if not _is_valid_numeric_oid(oid_total):
                        errors["oid_total"] = "invalid_oid"

            try:
                scale = float(scale_str)
            except ValueError:
                errors["scale"] = "invalid_float"
                scale = 1.0

            if not errors:
                norm_oid = _normalize_oid(oid) if oid else ""
                norm_free = _normalize_oid(oid_free) if oid_free else ""
                norm_total = _normalize_oid(oid_total) if oid_total else ""
                items = db.get("memory", {}).get("memory", [])
                for item in items:
                    if oid:
                        if item.get("type", "free_total") == "percentage":
                            if _normalize_oid(item.get("oid", "")) == norm_oid:
                                if vendor.lower() in [v.lower() for v in item.get("vendors", [])]:
                                    errors["oid"] = "duplicate_oid"
                                    break
                    else:
                        if item.get("type", "free_total") == "percentage":
                            continue
                        if _normalize_oid(item.get("oid_free", "")) == norm_free and _normalize_oid(item.get("oid_total", "")) == norm_total:
                            if vendor.lower() in [v.lower() for v in item.get("vendors", [])]:
                                errors["oid_free"] = "duplicate_oid"
                                errors["oid_total"] = "duplicate_oid"
                                break
                            
            if not vendor:
                errors["vendor"] = "required"
                
            if share_with_community and not attestation:
                errors["attestation"] = "required_attestation_to_share"
            elif attestation and not share_with_community:
                errors["share_with_community"] = "required_share"
                
            if not errors:
                overrides = dict(self._options.get(CONF_FEATURE_OVERRIDES, {}) or {})
                if oid:
                    overrides["memory"] = {
                        "type": "percentage",
                        "oid": _normalize_oid(oid),
                        "vendor": vendor,
                        "method": method,
                        "scale": scale,
                    }
                else:
                    overrides["memory"] = {
                        "type": "free_total",
                        "oid_free": _normalize_oid(oid_free),
                        "oid_total": _normalize_oid(oid_total),
                        "vendor": vendor,
                        "method": method,
                        "scale": scale,
                    }
                self._options[CONF_FEATURE_OVERRIDES] = overrides
                self._apply_options()
                
                if share_with_community and attestation:
                    self._last_override_feature = "memory"
                    return await self.async_step_submit_pr()
                else:
                    return await self.async_step_feature_overrides()
        else:
            oid = defaults.get("oid", "")
            oid_free = defaults.get("oid_free", "")
            oid_total = defaults.get("oid_total", "")
            vendor = defaults.get("vendor", "")
            method = defaults.get("method", "get")
            scale_str = str(defaults.get("scale", 1.0))
            attestation = False
            share_with_community = False

        schema = vol.Schema(
            {
                vol.Optional("oid"): str,
                vol.Optional("oid_free"): str,
                vol.Optional("oid_total"): str,
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
            step_id="override_memory",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    "oid": oid,
                    "oid_free": oid_free,
                    "oid_total": oid_total,
                    "vendor": vendor,
                    "method": method,
                    "scale": scale_str,
                    "attestation": attestation,
                    "share_with_community": share_with_community,
                }
            ),
            description_placeholders={
                "existing_entries": self._get_existing_entries_html("memory")
            },
            errors=errors,
        )
