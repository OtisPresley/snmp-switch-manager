
from __future__ import annotations

import ipaddress
from typing import Optional

def _abbr_from_speed_or_name(name: str) -> str:
    n = (name or "").lower()
    if n.startswith("gi"):
        return "Gi"
    if n.startswith("te"):
        return "Te"
    if n.startswith("tw"):
        return "Tw"
    if n.startswith("fa"):
        return "Fa"
    if n.startswith("fi"):
        return "Fi"
    if n.startswith("hu"):
        return "Hu"
    if n.startswith("po") or n.startswith("port-channel") or n.startswith("portchannel"):
        return "Po"
    if n.startswith("lo"):
        return "Lo"
    if n.startswith("vl"):
        return "Vl"
    if "100g" in n: return "Hu"
    if "10g" in n: return "Te"
    if "20g" in n: return "Tw"
    if "1g" in n or "1000" in n: return "Gi"
    return "Gi"

def format_interface_name(raw_name: str, unit: int=1, slot: int=0, port: Optional[int]=None) -> str:
    rn = (raw_name or "").strip()
    # NOTE: Vendor-specific display normalizations (e.g., link aggregate -> Po)
    # are handled by the configurable port rename rules. This function provides
    # a stable base formatting for unit/slot/port style names.

    if port is not None:
        abbr = _abbr_from_speed_or_name(rn)
        return f"{abbr}{unit}/{slot}/{port}"
    return rn

def ip_to_cidr(ip: str, mask: str) -> Optional[str]:
    try:
        net = ipaddress.IPv4Network((ip, mask), strict=False)
        return f"{ip}/{net.prefixlen}"
    except Exception:
        return None


# ----------------------------
# Port type classification
# ----------------------------

# Strong virtual indicators by IF-MIB ifType
# (loopback, propVirtual, l2vlan, lag, tunnel)
VIRTUAL_IFTYPES: set[int] = {24, 53, 135, 161, 131}


def classify_port_type(
    *,
    if_type: int | None,
    name: str,
    is_bridge_port: bool,
) -> str:
    """Classify an interface as physical, virtual, or unknown.

    This is intentionally heuristic-based and centralized here to make it easier
    to update as new switch families are added.
    """

    nm = (name or "").strip().lower()
    port_type = "unknown"

    # Strong virtual indicators
    if isinstance(if_type, int) and if_type in VIRTUAL_IFTYPES:
        port_type = "virtual"
    elif any(
        tok in nm
        for tok in (
            "vlan",
            "loopback",
            "mgmt",
            "management",
            "irb",
            "bdi",
            "svi",
            "bridge",
            "port-channel",
            "bond",
            "lag",
        )
    ) or nm.startswith(("br", "lo")):
        port_type = "virtual"

    # Bridge membership is a strong physical indicator
    if port_type == "unknown" and is_bridge_port:
        port_type = "physical"

    # Fallback: ethernetCsmacd(6) and looks like an ethernet port
    if port_type == "unknown" and if_type == 6:
        if nm.startswith("port") or any(
            tok in nm
            for tok in (
                "gigabit",
                "gige",
                "gi",
                "fastethernet",
                "fa",
                "ethernet",
                "eth",
                "tengig",
                "ten",
                "te",
                "ge",
                "xe",
            )
        ):
            port_type = "physical"

    return port_type
