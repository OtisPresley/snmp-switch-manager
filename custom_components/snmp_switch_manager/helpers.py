"""SNMP Switch Manager helper utilities."""
from __future__ import annotations

import ipaddress
import re
from typing import Any, Optional

from .const import (
    CONF_OVERRIDE_COMMUNITY,
    CONF_OVERRIDE_PORT,
    CONF_SNMP_VERSION,
    SNMP_VERSION_V2C,
    SNMP_VERSION_V3,
    CONF_SNMPV3_USERNAME,
    CONF_SNMPV3_AUTH_PROTOCOL,
    CONF_SNMPV3_AUTH_PASSWORD,
    CONF_SNMPV3_PRIV_PROTOCOL,
    CONF_SNMPV3_PRIV_PASSWORD,
)



# ---------- connection settings ----------

def get_snmp_connection_settings(entry_data: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    """Return effective SNMP connection settings for an entry.

    This is intentionally a *pure* helper: it does not create pysnmp objects.
    It only merges entry data + per-device overrides into a single dict.

    Precedence rules:
      1) options override entry_data where applicable
      2) SNMP version defaults to v2c

    Returned keys:
      host, port, version, community, v3_username, v3_auth_protocol,
      v3_auth_password, v3_priv_protocol, v3_priv_password
    """
    host = str((entry_data or {}).get("host") or "").strip()
    base_port = (entry_data or {}).get("port")
    try:
        port = int((options or {}).get(CONF_OVERRIDE_PORT, base_port))
    except Exception:
        port = int(base_port or 161)

    version = str(
        (options or {}).get(CONF_SNMP_VERSION)
        or (entry_data or {}).get(CONF_SNMP_VERSION)
        or SNMP_VERSION_V2C
    )
    version = version if version in (SNMP_VERSION_V2C, SNMP_VERSION_V3) else SNMP_VERSION_V2C

    community = str(
        (options or {}).get(CONF_OVERRIDE_COMMUNITY)
        or (entry_data or {}).get("community")
        or ""
    ).strip()

    def _v3(key: str) -> str:
        return str(
            (options or {}).get(key) or (entry_data or {}).get(key) or ""
        ).strip()

    return {
        "host": host,
        "port": port,
        "version": version,
        "community": community,
        CONF_SNMPV3_USERNAME: _v3(CONF_SNMPV3_USERNAME),
        CONF_SNMPV3_AUTH_PROTOCOL: _v3(CONF_SNMPV3_AUTH_PROTOCOL).lower(),
        CONF_SNMPV3_AUTH_PASSWORD: str(
            (options or {}).get(CONF_SNMPV3_AUTH_PASSWORD)
            or (entry_data or {}).get(CONF_SNMPV3_AUTH_PASSWORD)
            or ""
        ),
        CONF_SNMPV3_PRIV_PROTOCOL: _v3(CONF_SNMPV3_PRIV_PROTOCOL).lower(),
        CONF_SNMPV3_PRIV_PASSWORD: str(
            (options or {}).get(CONF_SNMPV3_PRIV_PASSWORD)
            or (entry_data or {}).get(CONF_SNMPV3_PRIV_PASSWORD)
            or ""
        ),
    }


# ---------- interface naming ----------

def _abbr_from_speed_or_name(name: str, db: dict | None = None) -> str:
    n = (name or "").lower()

    # Load mapping configuration from dynamic database, falling back to static local dicts
    abbrev_config = (db or {}).get("abbreviations") if db else None
    if not abbrev_config:
        prefixes = {"gi": "Gi", "te": "Te", "tw": "Tw", "fa": "Fa", "fi": "Fi", "hu": "Hu", "lo": "Lo", "vl": "Vl"}
        startswith = {"po": "Po", "port-channel": "Po", "portchannel": "Po"}
        contains = {"100g": "Hu", "10g": "Te", "20g": "Tw"}
        default = "Gi"
    else:
        prefixes = abbrev_config.get("prefixes", {})
        startswith = abbrev_config.get("startswith", {})
        contains = abbrev_config.get("contains", {})
        default = abbrev_config.get("default", "Gi")

    for p, abbr in prefixes.items():
        if n.startswith(p):
            return abbr

    for p, abbr in startswith.items():
        if n.startswith(p):
            return abbr

    for p, abbr in contains.items():
        if p in n:
            return abbr

    return default


def format_interface_name(
    raw_name: str,
    unit: int = 1,
    slot: int = 0,
    port: Optional[int] = None,
    classification_db: dict | None = None,
) -> str:
    rn = (raw_name or "").strip()
    if port is not None:
        abbr = _abbr_from_speed_or_name(rn, classification_db)
        return f"{abbr}{unit}/{slot}/{port}"
    return rn


# ---------- IP / CIDR ----------

def ip_to_cidr(ip: str, mask: str) -> Optional[str]:
    try:
        mask_parts = [int(p) for p in mask.split(".") if p.isdigit()]
        if len(mask_parts) == 4:
            prefix_len = sum(bin(x).count("1") for x in mask_parts)
            return f"{ip}/{prefix_len}"
    except Exception:
        pass
    try:
        net = ipaddress.IPv4Network((ip, mask), strict=False)
        return f"{ip}/{net.prefixlen}"
    except Exception:
        return None


# ---------- port type classification ----------

# Strong virtual indicators by IF-MIB ifType
# (loopback, propVirtual, l2vlan, lag, tunnel)
VIRTUAL_IFTYPES: set[int] = {24, 53, 135, 161, 131}

_VIRTUAL_NAME_TOKENS = (
    "vlan", "loopback", "mgmt", "management",
    "irb", "bdi", "svi", "bridge", "port-channel", "bond", "lag",
)
_PHYSICAL_NAME_TOKENS = (
    "gigabit", "gige", "gi", "fastethernet", "fa",
    "ethernet", "eth", "tengig", "ten", "te", "ge", "xe",
    "tw", "fi", "hu",
)


def classify_port_type(
    *,
    if_type: int | None,
    name: str,
    is_bridge_port: bool,
    connector_present: bool | None = None,
    classification_db: dict | None = None,
) -> str:
    """Classify an interface as physical, virtual, or unknown.

    Heuristic-based and centralized here to make it easier to update as new
    switch families are added.
    """
    nm = (name or "").strip().lower()

    virtual_tokens = _VIRTUAL_NAME_TOKENS
    physical_tokens = _PHYSICAL_NAME_TOKENS
    virtual_iftypes = VIRTUAL_IFTYPES

    if classification_db:
        db_tokens = classification_db
        if "interface_classification" in classification_db:
            db_tokens = classification_db.get("interface_classification") or {}
        
        virtual_tokens = db_tokens.get("virtual_tokens", _VIRTUAL_NAME_TOKENS)
        physical_tokens = db_tokens.get("physical_tokens", _PHYSICAL_NAME_TOKENS)
        db_iftypes = db_tokens.get("virtual_iftypes")
        if isinstance(db_iftypes, list):
            virtual_iftypes = set(db_iftypes)

    # 1. Check absolute standard MIB type virtual indicators
    if isinstance(if_type, int) and if_type in virtual_iftypes:
        return "virtual"

    # 2. Check virtual token rules (VLANs, loopbacks, Port-Channels)
    if any(tok in nm for tok in virtual_tokens) or nm.startswith(("br", "lo")):
        return "virtual"

    # 3. Trust standard MIB connector_present if explicitly True
    if connector_present is True:
        return "physical"

    # 4. Check absolute physical indicators (bridge port or standard physical tokens)
    if is_bridge_port:
        return "physical"

    if if_type == 6 and (nm.startswith("port") or any(tok in nm for tok in physical_tokens)):
        return "physical"

    # 5. Fall back to connector_present being False
    if connector_present is False:
        return "virtual"

    return "unknown"


# ---------- pfSense sysDescr parsing ----------

def parse_pfsense_sysdescr(sys_descr: str) -> dict[str, str | None]:
    """Parse pfSense sysDescr into manufacturer/model/firmware.

    Expected format (typical):
      "pfSense <hostname> <firmware> FreeBSD <os_version>"

    This is intentionally conservative: returns None fields when not detected.
    """
    sd = (sys_descr or "").strip()
    if not sd.lower().startswith("pfsense"):
        return {"manufacturer": None, "model": None, "firmware": None}

    manufacturer = "pfSense"

    fw = None
    m = re.search(r"\b(\d+\.\d+\.\d+-(?:RELEASE|RC\d*|BETA\d*|DEVELOPMENT))\b", sd, flags=re.IGNORECASE)
    if m:
        fw = m.group(1)

    model = None
    m2 = re.search(r"\b(FreeBSD\s+[^,]+)$", sd)
    if m2:
        model = m2.group(1).strip()
    else:
        m3 = re.search(r"\b(FreeBSD\s+\S+(?:\s+\S+)*)\b", sd)
        if m3:
            model = m3.group(1).strip()

    if model:
        toks = model.split()
        if toks and toks[-1].lower() in {"amd64", "i386", "x86_64", "arm64", "aarch64"}:
            model = " ".join(toks[:-1]).strip() or model

    return {"manufacturer": manufacturer, "model": model, "firmware": fw}


# ---------- uptime ----------

def uptime_human(ticks: Any) -> str:
    """Convert sysUpTime (hundredths of seconds) to human-readable string."""
    try:
        t = int(ticks)
        sec = t // 100
        d, r = divmod(sec, 86400)
        h, r = divmod(r, 3600)
        m, s = divmod(r, 60)
        return f"{d}d {h}h {m}m {s}s"
    except Exception:
        return str(ticks) if ticks is not None else "Unknown"


# ---------- vendor interface rules ----------

def _load_local_interface_filters() -> list:
    """Load default interface filters dynamically from the database JSON to avoid hardcoding vendor details in python."""
    import os
    import json
    db_path = os.path.join(os.path.dirname(__file__), "database", "interface_filters.json")
    if os.path.exists(db_path):
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "interface_filters" in data:
                    return data["interface_filters"]
                elif isinstance(data, list):
                    return data
        except Exception:
            pass
    return []

LOCAL_INTERFACE_FILTERS = _load_local_interface_filters()



def _match_condition(
    cond: dict,
    normalized_name: str,
    raw_name: str,
    admin: int | None,
    oper: int | None,
    has_ip: bool,
) -> bool:
    match_type = cond.get("match_type")
    match_val = cond.get("match_value")
    
    if match_val is not None:
        vals = [str(v).lower() for v in match_val] if isinstance(match_val, list) else [str(match_val).lower()]
        if match_type == "equals":
            if not any(normalized_name == v for v in vals):
                return False
        elif match_type == "starts_with":
            if not any(normalized_name.startswith(v) for v in vals):
                return False
        elif match_type == "ends_with":
            if not any(normalized_name.endswith(v) for v in vals):
                return False
        elif match_type == "is_digit":
            if not normalized_name.isdigit():
                return False
        else:  # contains
            if not any(v in normalized_name for v in vals):
                return False
    elif match_type == "is_digit":
        if not normalized_name.isdigit():
            return False

    req_contains = cond.get("require_contains")
    if req_contains:
        reqs = req_contains if isinstance(req_contains, list) else [req_contains]
        if not all(r.lower() in normalized_name for r in reqs):
            return False
            
    ex_contains = cond.get("exclude_contains")
    if ex_contains:
        exs = ex_contains if isinstance(ex_contains, list) else [ex_contains]
        if any(e.lower() in normalized_name for e in exs):
            return False
            
    ex_ends = cond.get("exclude_ends_with")
    if ex_ends:
        exs = ex_ends if isinstance(ex_ends, list) else [ex_ends]
        if any(normalized_name.endswith(e.lower()) for e in exs):
            return False

    req_ip = cond.get("require_ip")
    if req_ip is not None:
        if has_ip != req_ip:
            return False

    admin_in = cond.get("admin_in")
    oper_in = cond.get("oper_in")
    oper_not_equal = cond.get("oper_not_equal")
    oper_or_admin_match = cond.get("oper_or_admin_match", False)

    if oper_not_equal is not None:
        if oper == oper_not_equal:
            return False

    admin_match = True
    if admin_in is not None:
        admin_match = admin in admin_in

    oper_match = True
    if oper_in is not None:
        oper_match = oper in oper_in

    if oper_or_admin_match:
        has_admin_spec = admin_in is not None
        has_oper_spec = oper_in is not None
        if has_admin_spec and has_oper_spec:
            if not (admin_match or oper_match):
                return False
        elif has_admin_spec:
            if not admin_match:
                return False
        elif has_oper_spec:
            if not oper_match:
                return False
    else:
        if not (admin_match and oper_match):
            return False

    return True


def check_interface_filter_rules(
    *,
    normalized_name: str,
    raw_name: str,
    admin: int | None,
    oper: int | None,
    has_ip: bool,
    vendor: str,
    manufacturer: str = "",
    sys_descr: str = "",
    disabled_vendor_filter_ids: set[str],
    classification_db: dict | None = None,
) -> tuple[bool, str]:
    """Check if an interface is included based on dynamic database rules.

    Returns (include, modified_raw_name).
    """
    db_rules = None
    if classification_db:
        if "interface_filters" in classification_db:
            val = classification_db.get("interface_filters")
            if isinstance(val, list):
                db_rules = val
            elif isinstance(val, dict):
                db_rules = val.get("interface_filters")
        else:
            db_rules = classification_db
            
    if not isinstance(db_rules, list):
        db_rules = LOCAL_INTERFACE_FILTERS

    vendor_l = (vendor or "").lower()
    mfg_l = (manufacturer or "").lower()
    sd_l = (sys_descr or "").lower()

    active_rules = []
    has_include_rule = False

    for rule in db_rules:
        rule_id = rule.get("id")
        if rule_id in disabled_vendor_filter_ids:
            continue

        rule_vendors = rule.get("vendors", [])
        vendor_match = False
        for v in rule_vendors:
            if v.lower() == "standard":
                vendor_match = True
            elif v.lower() == vendor_l:
                vkws = rule.get("vendor_keywords")
                if vkws:
                    if any(kw.lower() in mfg_l or kw.lower() in sd_l for kw in vkws):
                        vendor_match = True
                else:
                    vendor_match = True
        
        if vendor_match:
            active_rules.append(rule)
            if rule.get("rule_type") == "include":
                has_include_rule = True

    default_include = not has_include_rule
    include = default_include

    for rule in active_rules:
        conditions = rule.get("conditions")
        if not conditions:
            conditions = [rule]

        matched = False
        matched_cond = None
        for cond in conditions:
            if _match_condition(cond, normalized_name, raw_name, admin, oper, has_ip):
                matched = True
                matched_cond = cond
                break

        if matched:
            rule_type = rule.get("rule_type")
            if rule_type == "exclude":
                return False, raw_name
            elif rule_type == "include":
                include = True
                rename_prefix = matched_cond.get("rename_prefix") or rule.get("rename_prefix")
                if rename_prefix:
                    raw_name = rename_prefix + raw_name

    return include, raw_name




# ---------- SNMP value parsing ----------

def _parse_numeric(val) -> Optional[int]:
    """Parse an SNMP value to int, returning None on failure."""
    try:
        return int(val)
    except (TypeError, ValueError):
        try:
            return int(float(val))
        except (TypeError, ValueError):
            return None


def _as_bytes(val) -> bytes:
    """Best-effort conversion of pysnmp OctetString/bytes/hex-string to raw bytes."""
    if val is None:
        return b""
    if isinstance(val, (bytes, bytearray)):
        return bytes(val)
    try:
        as_octets = getattr(val, "asOctets", None)
        if callable(as_octets):
            return bytes(as_octets())
    except Exception:
        pass
    s = str(val).strip()
    if s.lower().startswith("hex-string:"):
        s = s.split(":", 1)[1].strip()
    if s.startswith("0x") and len(s) > 2:
        try:
            return bytes.fromhex(s[2:])
        except Exception:
            return b""
    if ":" in s and all(len(p) == 2 for p in s.split(":")):
        try:
            return bytes.fromhex(s.replace(":", ""))
        except Exception:
            return b""
    parts = s.split()
    if parts and all(len(p) == 2 and all(c in "0123456789abcdefABCDEF" for c in p) for p in parts):
        try:
            return bytes.fromhex("".join(parts))
        except Exception:
            return b""
    return b""


def _decode_bridge_port_bitmap(val) -> set[int]:
    """Decode Q-BRIDGE PortList bitmap into a set of 1-based bridge port numbers."""
    data = _as_bytes(val)
    ports: set[int] = set()
    for oct_i, b in enumerate(data):
        for bit in range(8):
            if b & (0x80 >> bit):
                ports.add(oct_i * 8 + bit + 1)
    return ports


def decode_label(lval) -> str:
    """Decode a pysnmp OctetString label value to a plain string."""
    if hasattr(lval, "asOctets"):
        return lval.asOctets().decode("utf-8", "ignore")
    return str(lval)


# ---------- ENTITY-SENSOR-MIB helpers ----------

def _entity_sensor_scale_power(scale: int) -> int:
    """ENTITY-SENSOR-MIB entPhySensorScale -> base-10 exponent."""
    scale_map = {
        1: -24, 2: -21, 3: -18, 4: -15, 5: -12, 6: -9, 7: -6, 8: -3,
        9: 0, 10: 3, 11: 6, 12: 9, 13: 12, 14: 15, 15: 18, 16: 21, 17: 24,
    }
    return scale_map.get(int(scale), 0)


def _entity_sensor_value_to_float(raw: Any, scale: int | None, precision: int | None) -> Optional[float]:
    """Convert ENTITY-SENSOR-MIB value/scale/precision to a float."""
    n = _parse_numeric(raw)
    if n is None:
        return None
    try:
        s_pow = _entity_sensor_scale_power(int(scale or 9))
    except Exception:
        s_pow = 0
    try:
        prec = int(precision or 0)
    except Exception:
        prec = 0
    try:
        return float(n) * (10 ** (s_pow - prec))
    except Exception:
        return None




def _make_settings(
    host: str,
    community: str,
    port: int,
    snmp_settings: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """Return a merged SNMP settings dict, falling back to v2c community defaults."""
    settings = dict(snmp_settings or {})
    if not settings:
        settings = {"host": host, "port": port, "version": SNMP_VERSION_V2C, "community": community}
    return settings


async def test_connection(
    hass: Any,
    host: str,
    community: str,
    port: int,
    *,
    snmp_settings: Optional[dict[str, Any]] = None,
) -> bool:
    """Test SNMP connectivity.

    Backwards compatible with the original v2c signature, but also supports
    passing a pre-merged settings dict for SNMPv3.
    """
    from .snmp import SwitchSnmpClient
    from .const import OID_sysName
    client = SwitchSnmpClient(hass, host, _make_settings(host, community, port, snmp_settings))
    return await client._async_get_one(OID_sysName) is not None


async def get_sysname(
    hass: Any,
    host: str,
    community: str,
    port: int,
    *,
    snmp_settings: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """Return sysName from the device, or None on failure."""
    from .snmp import SwitchSnmpClient
    from .const import OID_sysName
    client = SwitchSnmpClient(hass, host, _make_settings(host, community, port, snmp_settings))
    return await client._async_get_one(OID_sysName)
