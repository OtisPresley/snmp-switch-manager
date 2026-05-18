"""Device info initialisation and per-poll vendor/firmware refresh."""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..snmp import SwitchSnmpClient

from ..helpers import parse_pfsense_sysdescr
from ..const import OID_entPhysicalModelName, OID_sysDescr, OID_sysObjectID, OID_sysName, OID_sysUpTime

# Vendor-specific OIDs (fetched once; firmware/model never change at runtime)
OID_entPhysicalSoftwareRev_CBS350 = "1.3.6.1.2.1.47.1.1.1.1.10.67109120"
OID_entPhysicalMfgName_Zyxel = "1.3.6.1.2.1.47.1.1.1.1.12"
OID_zyxel_firmware_version = "1.3.6.1.4.1.890.1.15.3.1.6.0"
OID_mikrotik_software_version = "1.3.6.1.4.1.14988.1.1.7.4.0"
OID_mikrotik_model = "1.3.6.1.4.1.14988.1.1.7.8.0"


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
    desc_lower = sd.lower()
    pfs = parse_pfsense_sysdescr(sd)

    manufacturer: Optional[str] = None
    firmware: Optional[str] = None

    # Specialty vendor detection
    client._is_jtcom = False
    client._is_h3c = False
    client._is_zyxel = False

    if any(x in desc_lower for x in ("jt-com", "jtcom", "goodtop")):
        manufacturer = "Jt-Com"
        client.cache["model"] = "Managed Switch"
        client._is_jtcom = True
    elif "h3c" in desc_lower:
        manufacturer = "H3C"
        client._is_h3c = True
    elif "zyxel" in desc_lower:
        manufacturer = "Zyxel"
        client._is_zyxel = True

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

    if vendor == "Mikrotik" and not manufacturer:
        manufacturer = "MikroTik"

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

    # Vendor-specific OIDs are fetched at most once per session
    if not client._vendor_oids_fetched:
        sd_lower = sd.lower()

        if (model_hint and "CBS" in model_hint) or "CBS" in sd:
            firmware = await _fetch_oid_str(client, OID_entPhysicalSoftwareRev_CBS350) or firmware

        if "zyxel" in sd_lower:
            manufacturer = await _fetch_oid_str(client, OID_entPhysicalMfgName_Zyxel) or manufacturer
            firmware = await _fetch_oid_str(client, OID_zyxel_firmware_version) or firmware

        if "mikrotik" in sd_lower or "routeros" in sd_lower:
            manufacturer = "MikroTik"
            firmware = await _fetch_oid_str(client, OID_mikrotik_software_version) or firmware
            if val := await _fetch_oid_str(client, OID_mikrotik_model):
                client.cache["model"] = val or client.cache.get("model")

        client._vendor_oids_fetched = True

    # Custom OIDs (highest precedence)
    if oid := client._custom_oid("manufacturer"):
        manufacturer = await _fetch_oid_str(client, oid) or manufacturer
    if oid := client._custom_oid("firmware"):
        firmware = await _fetch_oid_str(client, oid) or firmware

    client.cache["manufacturer"] = manufacturer
    client.cache["firmware"] = firmware
