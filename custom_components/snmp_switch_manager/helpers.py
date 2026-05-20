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

def _abbr_from_speed_or_name(name: str) -> str:
    n = (name or "").lower()
    prefixes = {"gi": "Gi", "te": "Te", "tw": "Tw", "fa": "Fa", "fi": "Fi", "hu": "Hu", "lo": "Lo", "vl": "Vl"}
    for p, abbr in prefixes.items():
        if n.startswith(p):
            return abbr
    if n.startswith(("po", "port-channel", "portchannel")):
        return "Po"
    if "100g" in n:
        return "Hu"
    if "10g" in n:
        return "Te"
    if "20g" in n:
        return "Tw"
    return "Gi"


def format_interface_name(raw_name: str, unit: int = 1, slot: int = 0, port: Optional[int] = None) -> str:
    rn = (raw_name or "").strip()
    if port is not None:
        abbr = _abbr_from_speed_or_name(rn)
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
)


def classify_port_type(
    *,
    if_type: int | None,
    name: str,
    is_bridge_port: bool,
    classification_db: dict | None = None,
) -> str:
    """Classify an interface as physical, virtual, or unknown.

    Heuristic-based and centralized here to make it easier to update as new
    switch families are added.
    """
    nm = (name or "").strip().lower()

    if isinstance(if_type, int) and if_type in VIRTUAL_IFTYPES:
        return "virtual"

    virtual_tokens = _VIRTUAL_NAME_TOKENS
    physical_tokens = _PHYSICAL_NAME_TOKENS

    if classification_db:
        virtual_tokens = classification_db.get("virtual_tokens", _VIRTUAL_NAME_TOKENS)
        physical_tokens = classification_db.get("physical_tokens", _PHYSICAL_NAME_TOKENS)

    if any(tok in nm for tok in virtual_tokens) or nm.startswith(("br", "lo")):
        return "virtual"

    if is_bridge_port:
        return "physical"

    if if_type == 6 and (nm.startswith("port") or any(tok in nm for tok in physical_tokens)):
        return "physical"

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

def check_vendor_interface_rules(
    normalized_name: str,
    raw_name: str,
    admin: int | None,
    oper: int | None,
    has_ip: bool,
    is_cisco_sg: bool,
    is_junos: bool,
    disabled_vendor_filter_ids: set[str],
) -> tuple[bool, str]:
    """Check if an interface is included based on vendor-specific rules.

    Returns (include, modified_raw_name).
    """
    if is_cisco_sg:
        enable_physical = "cisco_sg_physical_fa_gi" not in disabled_vendor_filter_ids
        enable_vlan = "cisco_sg_vlan_admin_or_oper" not in disabled_vendor_filter_ids
        enable_has_ip = "cisco_sg_other_has_ip" not in disabled_vendor_filter_ids
        include = False

        if enable_physical and (normalized_name.startswith("fa") or normalized_name.startswith("gi")) and oper != 6:
            include = True
        elif enable_vlan and (normalized_name.startswith("vlan") or normalized_name.isdigit()):
            if normalized_name.isdigit():
                if (oper == 1 or admin == 2) and has_ip:
                    raw_name = "VLAN " + raw_name
                    include = True
            elif admin in (1, 2) and oper in (1, 2, 6, 7):
                include = True
        elif enable_vlan and normalized_name.startswith("po") and (oper == 1 or admin == 2):
            include = True
        elif enable_has_ip and has_ip:
            include = True

        return include, raw_name

    if is_junos:
        enable_physical = "junos_physical_ge" not in disabled_vendor_filter_ids
        enable_l3_subif = "junos_l3_subif_has_ip" not in disabled_vendor_filter_ids
        enable_vlan = "junos_vlan_admin_or_oper" not in disabled_vendor_filter_ids
        enable_has_ip = "junos_other_has_ip" not in disabled_vendor_filter_ids
        include = False

        if enable_physical and normalized_name.startswith("ge-") and "." not in raw_name:
            include = True
        elif enable_l3_subif and normalized_name.startswith("ge-") and "." in raw_name:
            try:
                _, sub = raw_name.split(".", 1)
                include = sub != "0" and has_ip
            except Exception:
                pass
        elif enable_vlan and normalized_name.startswith("vlan") and admin in (1, 2) and oper in (1, 2, 6, 7):
            include = True
        elif enable_has_ip and has_ip:
            include = True

        return include, raw_name

    return True, raw_name


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



