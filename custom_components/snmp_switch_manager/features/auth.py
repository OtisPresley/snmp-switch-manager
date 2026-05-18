"""SNMP authentication data builder (v2c CommunityData or v3 UsmUserData)."""
from __future__ import annotations
from typing import Any, Dict

from ..snmp_compat import (
    CommunityData,
    UsmUserData,
    usmNoAuthProtocol,
    usmHMACMD5AuthProtocol,
    usmHMACSHAAuthProtocol,
    usmNoPrivProtocol,
    usmDESPrivProtocol,
    usmAesCfb128Protocol,
)
from ..const import (
    SNMP_VERSION_V2C,
    SNMP_VERSION_V3,
    CONF_SNMPV3_USERNAME,
    CONF_SNMPV3_AUTH_PROTOCOL,
    CONF_SNMPV3_AUTH_PASSWORD,
    CONF_SNMPV3_PRIV_PROTOCOL,
    CONF_SNMPV3_PRIV_PASSWORD,
    SNMPV3_AUTH_NONE,
    SNMPV3_AUTH_MD5,
    SNMPV3_PRIV_NONE,
    SNMPV3_PRIV_AES,
)


def build_auth_data(settings: Dict[str, Any]):
    """Build pysnmp authData object (v2c CommunityData or v3 UsmUserData).

    This is the only place in the codebase that should care about SNMP
    security model differences. Everything else must remain version-agnostic.
    """
    version = str((settings or {}).get("version") or SNMP_VERSION_V2C).lower()
    if version != SNMP_VERSION_V3:
        community = str((settings or {}).get("community") or "").strip()
        return CommunityData(community, mpModel=1)

    username = str((settings or {}).get(CONF_SNMPV3_USERNAME) or "").strip()
    auth_proto = str((settings or {}).get(CONF_SNMPV3_AUTH_PROTOCOL) or SNMPV3_AUTH_NONE).strip().lower()
    auth_pass = str((settings or {}).get(CONF_SNMPV3_AUTH_PASSWORD) or "")
    priv_proto = str((settings or {}).get(CONF_SNMPV3_PRIV_PROTOCOL) or SNMPV3_PRIV_NONE).strip().lower()
    priv_pass = str((settings or {}).get(CONF_SNMPV3_PRIV_PASSWORD) or "")

    # Map string selections to pysnmp protocol constants
    if auth_proto in ("", SNMPV3_AUTH_NONE):
        auth_protocol = usmNoAuthProtocol
        auth_key = None
    elif auth_proto == SNMPV3_AUTH_MD5:
        auth_protocol = usmHMACMD5AuthProtocol
        auth_key = auth_pass
    else:
        # Default to SHA
        auth_protocol = usmHMACSHAAuthProtocol
        auth_key = auth_pass

    if priv_proto in ("", SNMPV3_PRIV_NONE):
        priv_protocol = usmNoPrivProtocol
        priv_key = None
    elif priv_proto == SNMPV3_PRIV_AES:
        priv_protocol = usmAesCfb128Protocol
        priv_key = priv_pass
    else:
        # Default to DES
        priv_protocol = usmDESPrivProtocol
        priv_key = priv_pass

    # Build UsmUserData with appropriate security level
    try:
        if auth_key is None and priv_key is None:
            return UsmUserData(username)
        if auth_key is not None and priv_key is None:
            return UsmUserData(username, auth_key, authProtocol=auth_protocol)
        if auth_key is None and priv_key is not None:
            # Priv without auth is uncommon and often unsupported; fall back to noPriv.
            return UsmUserData(username)
        return UsmUserData(username, auth_key, priv_key, authProtocol=auth_protocol, privProtocol=priv_protocol)
    except Exception:
        # Fall back to the safest noAuthNoPriv when input is invalid.
        return UsmUserData(username)
