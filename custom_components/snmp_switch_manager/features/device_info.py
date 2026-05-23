"""Device info initialisation and per-poll vendor/firmware refresh."""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..snmp import SwitchSnmpClient

from ..helpers import parse_pfsense_sysdescr
from ..const import OID_entPhysicalModelName, OID_sysDescr, OID_sysObjectID, OID_sysName, OID_sysUpTime


async def _fetch_oid_str(client: "SwitchSnmpClient", oid: str) -> Optional[str]:
    """Fetch a single OID value, returning a stripped string or None."""
    try:
        val = await client._async_get_one(oid)
        return val.strip() if val else None
    except Exception:
        return None


def _parse_sysdescr_generic(sd: str, model_hint: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Parse manufacturer and firmware from a generic comma-split sysDescr."""
    parts = [p.strip() for p in sd.split(",")]
    firmware = parts[1] if len(parts) >= 2 else None
    head = parts[0]
    if model_hint and model_hint in head:
        manufacturer = head.replace(model_hint, "").strip() or None
    else:
        toks = head.split()
        manufacturer = " ".join(toks[:-1]) if len(toks) > 1 else None
    return manufacturer, firmware or None


async def initialize_device_info(client: "SwitchSnmpClient") -> None:
    """Populate manufacturer, firmware, model, and vendor flags on first connect."""
    # Core system fields
    client.cache["sysDescr"] = await client._async_get_one(OID_sysDescr)
    client.cache["sysObjectID"] = await client._async_get_one(OID_sysObjectID)
    client.cache["vendor"] = client._get_vendor()
    client.cache["sysName"] = await client._async_get_one(client._custom_oid("hostname") or OID_sysName)
    client.cache["sysUpTime"] = await client._async_get_one(client._custom_oid("uptime") or OID_sysUpTime)

    # Model hint from ENTITY-MIB (first non-empty entry)
    model_hint: Optional[str] = next(
        (str(val).strip() for _, val in await client._async_walk(OID_entPhysicalModelName) if str(val).strip()),
        None,
    )
    client.cache["model"] = model_hint

    sd = (client.cache.get("sysDescr") or "").strip()
    pfs = parse_pfsense_sysdescr(sd)

    manufacturer: Optional[str] = None
    firmware: Optional[str] = None

    # Specialty vendor detection using dynamic database engine
    vendor_info = client._get_vendor_info()
    vendor_name = vendor_info.get("name", "Unknown")

    if vendor_name not in ("Unknown", "Standard"):
        manufacturer = vendor_name
        if "model_fallback" in vendor_info:
            client.cache["model"] = vendor_info["model_fallback"]

    # pfSense overrides generic parsing
    if pfs.get("manufacturer"):
        manufacturer = pfs["manufacturer"] or manufacturer
        firmware = pfs["firmware"] or firmware
        if pfs.get("model"):
            client.cache["model"] = pfs["model"]
            model_hint = client.cache["model"]
    elif sd:
        manufacturer, firmware = _parse_sysdescr_generic(sd, model_hint)

    # Vendor-specific OID overrides from database
    vendor = client.cache.get("vendor", "Unknown")
    for item in client._get_database_oids("device_info", vendor):
        if oid_fw := item.get("oid_firmware"):
            firmware = await _fetch_oid_str(client, oid_fw) or firmware
        if oid_mdl := item.get("oid_model"):
            if val := await _fetch_oid_str(client, oid_mdl):
                client.cache["model"] = val or client.cache.get("model")
        if oid_mfg := item.get("oid_mfg"):
            manufacturer = await _fetch_oid_str(client, oid_mfg) or manufacturer

    if not manufacturer:
        manufacturer = vendor_info.get("manufacturer_fallback")

    # Custom OID overrides (highest precedence)
    if oid := client._custom_oid("manufacturer"):
        manufacturer = await _fetch_oid_str(client, oid) or manufacturer
    if oid := client._custom_oid("firmware"):
        firmware = await _fetch_oid_str(client, oid) or firmware
    if oid := client._custom_oid("model"):
        if val := await _fetch_oid_str(client, oid):
            client.cache["model"] = val or client.cache.get("model")

    client.cache["manufacturer"] = manufacturer
    client.cache["firmware"] = firmware


async def refresh_device_info(client: "SwitchSnmpClient") -> None:
    """Re-evaluate manufacturer/firmware from sysDescr on every poll cycle."""
    sd = (client.cache.get("sysDescr") or "").strip()
    if not sd:
        return

    pfs = parse_pfsense_sysdescr(sd)
    if pfs.get("manufacturer"):
        client.cache["manufacturer"] = pfs["manufacturer"]
        client.cache["firmware"] = pfs["firmware"]
        if pfs.get("model"):
            client.cache["model"] = pfs["model"]
        return

    model_hint = client.cache.get("model")
    manufacturer, firmware = _parse_sysdescr_generic(sd, model_hint)

    vendor = client.cache.get("vendor", "Unknown")

    # Vendor-specific OIDs are fetched at most once per session
    if not client._vendor_oids_fetched:
        for item in client._get_database_oids("device_info", vendor):
            if oid_fw := item.get("oid_firmware"):
                firmware = await _fetch_oid_str(client, oid_fw) or firmware
            if oid_mdl := item.get("oid_model"):
                if val := await _fetch_oid_str(client, oid_mdl):
                    client.cache["model"] = val or client.cache.get("model")
            if oid_mfg := item.get("oid_mfg"):
                manufacturer = await _fetch_oid_str(client, oid_mfg) or manufacturer

        client._vendor_oids_fetched = True

    if not manufacturer:
        vendor_info = client._get_vendor_info()
        manufacturer = vendor_info.get("manufacturer_fallback")

    # Custom OIDs (highest precedence)
    if oid := client._custom_oid("manufacturer"):
        manufacturer = await _fetch_oid_str(client, oid) or manufacturer
    if oid := client._custom_oid("firmware"):
        firmware = await _fetch_oid_str(client, oid) or firmware

    client.cache["manufacturer"] = manufacturer
    client.cache["firmware"] = firmware
