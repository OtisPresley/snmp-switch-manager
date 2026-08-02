from __future__ import annotations

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ..const import CONF_FEATURE_OVERRIDES
from ..config_flow import _is_valid_numeric_oid, _normalize_oid


class OverridesTopologyMixin:
    """Mixin for OptionsFlowHandler to handle topology-related OID overrides (LLDP, FDB, ARP, Base MAC)."""

    async def async_step_override_lldp(self, user_input=None) -> FlowResult:
        """Override LLDP OIDs."""
        errors: dict[str, str] = {}
        defaults = self._get_override_defaults("lldp")
        
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

            oid_rem = user_input.get("oid_rem_sys_name", "").strip()
            oid_cdp = user_input.get("oid_cdp_sys_name", "").strip()
            vendor = user_input.get("vendor", "").strip()
            description = user_input.get("description", "")
            attestation = user_input.get("attestation", False)
            share_with_community = user_input.get("share_with_community", False)
            
            if not oid_rem and not oid_cdp:
                overrides = dict(self._options.get(CONF_FEATURE_OVERRIDES, {}) or {})
                overrides.pop("lldp", None)
                self._options[CONF_FEATURE_OVERRIDES] = overrides
                self._apply_options()
                return await self.async_step_feature_overrides()
            
            if oid_rem and not _is_valid_numeric_oid(oid_rem):
                errors["oid_rem_sys_name"] = "invalid_oid"
            if oid_cdp and not _is_valid_numeric_oid(oid_cdp):
                errors["oid_cdp_sys_name"] = "invalid_oid"

            if share_with_community:
                norm_rem = _normalize_oid(oid_rem)
                items = db.get("lldp", {}).get("lldp", [])
                for item in items:
                    if oid_rem and _normalize_oid(item.get("oid_rem_sys_name", "")) == norm_rem:
                        if vendor.lower() in [v.lower() for v in item.get("vendors", [])]:
                            errors["oid_rem_sys_name"] = "duplicate_oid"
                            break

            if not vendor:
                errors["vendor"] = "required"

            if share_with_community and not attestation:
                errors["attestation"] = "required_attestation_to_share"
            elif attestation and not share_with_community:
                errors["share_with_community"] = "required_share"
                
            if not errors:
                overrides = dict(self._options.get(CONF_FEATURE_OVERRIDES, {}) or {})
                overrides["lldp"] = {
                    "oid_rem_sys_name": _normalize_oid(oid_rem) if oid_rem else "",
                    "oid_cdp_sys_name": _normalize_oid(oid_cdp) if oid_cdp else "",
                    "vendor": vendor,
                    "description": description,
                }
                self._options[CONF_FEATURE_OVERRIDES] = overrides
                self._apply_options()
                
                if share_with_community and attestation:
                    self._last_override_feature = "lldp"
                    return await self.async_step_submit_pr()
                else:
                    return await self.async_step_feature_overrides()
        else:
            oid_rem = defaults.get("oid_rem_sys_name", "")
            oid_cdp = defaults.get("oid_cdp_sys_name", "")
            vendor = defaults.get("vendor", "")
            description = defaults.get("description", "")
            attestation = False
            share_with_community = False

        schema = vol.Schema(
            {
                vol.Optional("oid_rem_sys_name"): str,
                vol.Optional("oid_cdp_sys_name"): str,
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
        
        return self.async_show_form(
            step_id="override_lldp",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    "oid_rem_sys_name": oid_rem,
                    "oid_cdp_sys_name": oid_cdp,
                    "vendor": vendor,
                    "description": description,
                    "attestation": attestation,
                    "share_with_community": share_with_community,
                }
            ),
            description_placeholders={
                "existing_entries": self._get_existing_entries_html("lldp")
            },
            errors=errors,
        )

    async def async_step_override_fdb(self, user_input=None) -> FlowResult:
        """Override FDB OIDs."""
        errors: dict[str, str] = {}
        defaults = self._get_override_defaults("fdb")
        
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

            oid_fdb = user_input.get("oid_fdb_port", "").strip()
            oid_q_fdb = user_input.get("oid_q_fdb_port", "").strip()
            vendor = user_input.get("vendor", "").strip()
            description = user_input.get("description", "")
            attestation = user_input.get("attestation", False)
            share_with_community = user_input.get("share_with_community", False)
            
            if not oid_fdb and not oid_q_fdb:
                overrides = dict(self._options.get(CONF_FEATURE_OVERRIDES, {}) or {})
                overrides.pop("fdb", None)
                self._options[CONF_FEATURE_OVERRIDES] = overrides
                self._apply_options()
                return await self.async_step_feature_overrides()
            
            if oid_fdb and not _is_valid_numeric_oid(oid_fdb):
                errors["oid_fdb_port"] = "invalid_oid"
            if oid_q_fdb and not _is_valid_numeric_oid(oid_q_fdb):
                errors["oid_q_fdb_port"] = "invalid_oid"

            if share_with_community:
                norm_fdb = _normalize_oid(oid_fdb)
                items = db.get("fdb", {}).get("fdb", [])
                for item in items:
                    if oid_fdb and _normalize_oid(item.get("oid_fdb_port", "")) == norm_fdb:
                        if vendor.lower() in [v.lower() for v in item.get("vendors", [])]:
                            errors["oid_fdb_port"] = "duplicate_oid"
                            break

            if not vendor:
                errors["vendor"] = "required"

            if share_with_community and not attestation:
                errors["attestation"] = "required_attestation_to_share"
            elif attestation and not share_with_community:
                errors["share_with_community"] = "required_share"
                
            if not errors:
                overrides = dict(self._options.get(CONF_FEATURE_OVERRIDES, {}) or {})
                overrides["fdb"] = {
                    "oid_fdb_port": _normalize_oid(oid_fdb) if oid_fdb else "",
                    "oid_q_fdb_port": _normalize_oid(oid_q_fdb) if oid_q_fdb else "",
                    "vendor": vendor,
                    "description": description,
                }
                self._options[CONF_FEATURE_OVERRIDES] = overrides
                self._apply_options()
                
                if share_with_community and attestation:
                    self._last_override_feature = "fdb"
                    return await self.async_step_submit_pr()
                else:
                    return await self.async_step_feature_overrides()
        else:
            oid_fdb = defaults.get("oid_fdb_port", "")
            oid_q_fdb = defaults.get("oid_q_fdb_port", "")
            vendor = defaults.get("vendor", "")
            description = defaults.get("description", "")
            attestation = False
            share_with_community = False

        schema = vol.Schema(
            {
                vol.Optional("oid_fdb_port"): str,
                vol.Optional("oid_q_fdb_port"): str,
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
        
        return self.async_show_form(
            step_id="override_fdb",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    "oid_fdb_port": oid_fdb,
                    "oid_q_fdb_port": oid_q_fdb,
                    "vendor": vendor,
                    "description": description,
                    "attestation": attestation,
                    "share_with_community": share_with_community,
                }
            ),
            description_placeholders={
                "existing_entries": self._get_existing_entries_html("fdb")
            },
            errors=errors,
        )

    async def async_step_override_arp(self, user_input=None) -> FlowResult:
        """Override ARP OID."""
        errors: dict[str, str] = {}
        defaults = self._get_override_defaults("arp")
        
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

            oid_arp = user_input.get("oid_arp_mac", "").strip()
            vendor = user_input.get("vendor", "").strip()
            description = user_input.get("description", "")
            attestation = user_input.get("attestation", False)
            share_with_community = user_input.get("share_with_community", False)
            
            if not oid_arp:
                overrides = dict(self._options.get(CONF_FEATURE_OVERRIDES, {}) or {})
                overrides.pop("arp", None)
                self._options[CONF_FEATURE_OVERRIDES] = overrides
                self._apply_options()
                return await self.async_step_feature_overrides()
            
            if not _is_valid_numeric_oid(oid_arp):
                errors["oid_arp_mac"] = "invalid_oid"

            if share_with_community:
                norm_arp = _normalize_oid(oid_arp)
                items = db.get("arp", {}).get("arp", [])
                for item in items:
                    if _normalize_oid(item.get("oid_arp_mac", "")) == norm_arp:
                        if vendor.lower() in [v.lower() for v in item.get("vendors", [])]:
                            errors["oid_arp_mac"] = "duplicate_oid"
                            break

            if not vendor:
                errors["vendor"] = "required"

            if share_with_community and not attestation:
                errors["attestation"] = "required_attestation_to_share"
            elif attestation and not share_with_community:
                errors["share_with_community"] = "required_share"
                
            if not errors:
                overrides = dict(self._options.get(CONF_FEATURE_OVERRIDES, {}) or {})
                overrides["arp"] = {
                    "oid_arp_mac": _normalize_oid(oid_arp),
                    "vendor": vendor,
                    "description": description,
                }
                self._options[CONF_FEATURE_OVERRIDES] = overrides
                self._apply_options()
                
                if share_with_community and attestation:
                    self._last_override_feature = "arp"
                    return await self.async_step_submit_pr()
                else:
                    return await self.async_step_feature_overrides()
        else:
            oid_arp = defaults.get("oid_arp_mac", "")
            vendor = defaults.get("vendor", "")
            description = defaults.get("description", "")
            attestation = False
            share_with_community = False

        schema = vol.Schema(
            {
                vol.Optional("oid_arp_mac"): str,
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
        
        return self.async_show_form(
            step_id="override_arp",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    "oid_arp_mac": oid_arp,
                    "vendor": vendor,
                    "description": description,
                    "attestation": attestation,
                    "share_with_community": share_with_community,
                }
            ),
            description_placeholders={
                "existing_entries": self._get_existing_entries_html("arp")
            },
            errors=errors,
        )

    async def async_step_override_base_mac(self, user_input=None) -> FlowResult:
        """Override Base MAC OID."""
        errors: dict[str, str] = {}
        defaults = self._get_override_defaults("base_mac")
        
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

            oid_base = user_input.get("oid_base_mac", "").strip()
            vendor = user_input.get("vendor", "").strip()
            description = user_input.get("description", "")
            attestation = user_input.get("attestation", False)
            share_with_community = user_input.get("share_with_community", False)
            
            if not oid_base:
                overrides = dict(self._options.get(CONF_FEATURE_OVERRIDES, {}) or {})
                overrides.pop("base_mac", None)
                self._options[CONF_FEATURE_OVERRIDES] = overrides
                self._apply_options()
                return await self.async_step_feature_overrides()
            
            if not _is_valid_numeric_oid(oid_base):
                errors["oid_base_mac"] = "invalid_oid"

            if share_with_community:
                norm_base = _normalize_oid(oid_base)
                items = db.get("base_mac", {}).get("base_mac", [])
                for item in items:
                    if _normalize_oid(item.get("oid_base_mac", "")) == norm_base:
                        if vendor.lower() in [v.lower() for v in item.get("vendors", [])]:
                            errors["oid_base_mac"] = "duplicate_oid"
                            break

            if not vendor:
                errors["vendor"] = "required"

            if share_with_community and not attestation:
                errors["attestation"] = "required_attestation_to_share"
            elif attestation and not share_with_community:
                errors["share_with_community"] = "required_share"
                
            if not errors:
                overrides = dict(self._options.get(CONF_FEATURE_OVERRIDES, {}) or {})
                overrides["base_mac"] = {
                    "oid_base_mac": _normalize_oid(oid_base),
                    "vendor": vendor,
                    "description": description,
                }
                self._options[CONF_FEATURE_OVERRIDES] = overrides
                self._apply_options()
                
                if share_with_community and attestation:
                    self._last_override_feature = "base_mac"
                    return await self.async_step_submit_pr()
                else:
                    return await self.async_step_feature_overrides()
        else:
            oid_base = defaults.get("oid_base_mac", "")
            vendor = defaults.get("vendor", "")
            description = defaults.get("description", "")
            attestation = False
            share_with_community = False

        schema = vol.Schema(
            {
                vol.Optional("oid_base_mac"): str,
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
        
        return self.async_show_form(
            step_id="override_base_mac",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    "oid_base_mac": oid_base,
                    "vendor": vendor,
                    "description": description,
                    "attestation": attestation,
                    "share_with_community": share_with_community,
                }
            ),
            description_placeholders={
                "existing_entries": self._get_existing_entries_html("base_mac")
            },
            errors=errors,
        )
