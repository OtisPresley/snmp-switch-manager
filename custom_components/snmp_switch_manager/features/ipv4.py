from __future__ import annotations
import ipaddress
from typing import TYPE_CHECKING, Dict, List, Tuple, Any, Optional

if TYPE_CHECKING:
    from ..snmp import SwitchSnmpClient

from ..const import (
    OID_ipAdEntAddr,
    OID_ipAdEntIfIndex,
    OID_ipAdEntNetMask,
    OID_ipAddressIfIndex,
    OID_ospfIfIpAddress,
    OID_routeCol,
)

try:
    from ..helpers import _parse_numeric
except ImportError:
    from custom_components.snmp_switch_manager.helpers import _parse_numeric

async def poll_ipv4(client: SwitchSnmpClient) -> None:
    """Walk IPv4 addresses and attach them to interfaces."""
    ip_index: Dict[str, int] = {}
    ip_mask: Dict[str, str] = {}  # primarily from (1) and (4)

    def _normalize_ipv4(val: Any) -> str:
        """Convert SNMP IPv4 values to dotted-quad strings."""
        s = str(val)
        parts = s.split(".")
        if len(parts) == 4 and all(p.isdigit() for p in parts):
            return s
    
        b: Optional[bytes] = None
        if isinstance(val, (bytes, bytearray)):
            b = bytes(val)
        else:
            try:
                b = bytes(val)
            except Exception:
                if isinstance(val, str):
                    try:
                        b = val.encode("latin-1")
                    except Exception:
                        b = None
                if b is None:
                    try:
                        b = val.asOctets()
                    except Exception:
                        b = None
    
        if b and len(b) == 4:
            return ".".join(str(x) for x in b)
    
        return s

    def _is_usable_ipv4(ip: str) -> bool:
        """Filter out addresses that are almost always meaningless on L2 switch ports."""
        try:
            addr = ipaddress.IPv4Address(ip)
        except Exception:
            return False
        if (
            addr.is_loopback
            or addr.is_unspecified
            or addr.is_link_local
            or addr.is_multicast
            or addr.is_reserved
        ):
            return False
        if ip == "255.255.255.255":
            return False
        return True

    # ---- (1) Legacy table: ipAdEnt* ----
    legacy_addrs = await client._async_walk(OID_ipAdEntAddr)
    if legacy_addrs:
        for _oid, val in legacy_addrs:
            ip = _normalize_ipv4(val)
            if not _is_usable_ipv4(ip):
                continue
            ip_index[ip] = None  # type: ignore[assignment]

        for oid, val in await client._async_walk(OID_ipAdEntIfIndex):
            parts = oid.split(".")[-4:]
            ip = ".".join(parts)
            if not _is_usable_ipv4(ip):
                continue
            try:
                ip_index[ip] = int(_parse_numeric(val))
            except Exception:
                continue

        for oid, val in await client._async_walk(OID_ipAdEntNetMask):
            parts = oid.split(".")[-4:]
            ip = ".".join(parts)
            if not _is_usable_ipv4(ip):
                continue
            ip_mask[ip] = _normalize_ipv4(val)

    # ---- (2) IP-MIB ipAddressIfIndex ----
    try:
        for oid, val in await client._async_walk(OID_ipAddressIfIndex):
            try:
                suffix = oid[len(OID_ipAddressIfIndex) + 1 :]
                parts = [int(x) for x in suffix.split(".") if x]
                if len(parts) < 6:
                    continue

                ip = None
                for i in range(0, len(parts) - 5):
                    if parts[i] == 1 and parts[i + 1] == 4:
                        a, b, c, d = parts[i + 2 : i + 6]
                        ip = f"{a}.{b}.{c}.{d}"
                        break
                if not ip or not _is_usable_ipv4(ip):
                    continue

                idx = _parse_numeric(val)
                if idx is None:
                    continue
                ip_index[ip] = int(idx)
            except Exception:
                continue
    except Exception:
        pass

    # ---- (3) OSPF-MIB ospfIfIpAddress ----
    try:
        for oid, val in await client._async_walk(OID_ospfIfIpAddress):
            try:
                suffix = oid[len(OID_ospfIfIpAddress) + 1 :]
                parts = [int(x) for x in suffix.split(".")]
                if len(parts) >= 5:
                    a, b, c, d = parts[0], parts[1], parts[2], parts[3]
                    if_index = parts[4]
                    ip = f"{a}.{b}.{c}.{d}"
                    if not _is_usable_ipv4(ip):
                        continue
                    ip_index[ip] = int(if_index)
            except Exception:
                continue
    except Exception:
        pass

    # ---- (4) Derive mask bits from IP-FORWARD-MIB route instances ----
    route_prefixes: List[Tuple[int, int]] = []

    def _bits_to_mask(bits: int) -> str:
        if bits <= 0:
            return "0.0.0.0"
        if bits >= 32:
            return "255.255.255.255"
        mask = (0xFFFFFFFF << (32 - bits)) & 0xFFFFFFFF
        return ".".join(str((mask >> s) & 0xFF) for s in (24, 16, 8, 0))

    def _ip_to_int(ip: str) -> int:
        a, b, c, d = (int(x) for x in ip.split("."))
        return (a << 24) | (b << 16) | (c << 8) | d

    try:
        for oid, _val in await client._async_walk(OID_routeCol):
            try:
                suffix = oid[len(OID_routeCol) + 1 :]
                parts = [int(x) for x in suffix.split(".") if x]

                for i in range(len(parts) - 7):
                    if parts[i] == 1 and parts[i + 1] == 4:
                        a, b, c, d = parts[i + 2 : i + 6]
                        bits = parts[i + 6] if i + 6 < len(parts) else None
                        if bits is None or bits < 0 or bits > 32:
                            continue
                        net_int = _ip_to_int(f"{a}.{b}.{c}.{d}")
                        route_prefixes.append((net_int, bits))
                        break
            except Exception:
                continue
    except Exception:
        pass

    if route_prefixes and ip_index:
        route_prefixes.sort(key=lambda t: t[1], reverse=True)
        for ip in list(ip_index.keys()):
            ip_int = _ip_to_int(ip)
            for net_int, bits in route_prefixes:
                mask_int = (0xFFFFFFFF << (32 - bits)) & 0xFFFFFFFF if bits else 0
                if bits == 0 or (ip_int & mask_int) == (net_int & mask_int):
                    ip_mask[ip] = _bits_to_mask(bits)
                    break

    # Commit maps to cache
    if ip_index:
        client.cache["ipIndex"] = ip_index
    if ip_mask:
        client.cache["ipMask"] = ip_mask

    # Attach to interfaces
    _attach_ipv4_to_interfaces(client)

def _attach_ipv4_to_interfaces(client: SwitchSnmpClient) -> None:
    """Attach resolved IPv4 addresses to interface records."""
    if_table: Dict[int, Dict[str, Any]] = client.cache.get("ifTable", {})
    ip_idx: Dict[str, Optional[int]] = client.cache.get("ipIndex", {})
    ip_mask: Dict[str, str] = client.cache.get("ipMask", {})

    for rec in if_table.values():
        for k in (
            "ipv4", "ip", "netmask", "cidr",
            "ip_address", "ipv4_address", "ipv4_netmask", "ipv4_cidr",
            "ip_cidr_str",
        ):
            rec.pop(k, None)

    def _mask_to_prefix(mask: str | None) -> Optional[int]:
        if not mask:
            return None
        try:
            parts = [int(p) for p in mask.split(".")]
            if len(parts) != 4 or any(p < 0 or p > 255 for p in parts):
                return None
            bits = "".join(f"{p:08b}" for p in parts)
            if "01" in bits:
                return None
            return bits.count("1")
        except Exception:
            return None

    for ip, idx in ip_idx.items():
        if not idx:
            continue
        rec = if_table.get(idx)
        if not rec:
            continue
        mask = ip_mask.get(ip)
        prefix = _mask_to_prefix(mask)
        rec.setdefault("ipv4", []).append({"ip": ip, "netmask": mask, "cidr": prefix})

    for rec in if_table.values():
        addrs = rec.get("ipv4") or []
        if len(addrs) == 1:
            ip = addrs[0]["ip"]
            mask = addrs[0]["netmask"]
            prefix = addrs[0]["cidr"]
            rec["ip"] = ip
            rec["netmask"] = mask
            rec["cidr"] = prefix
            rec["ip_address"] = ip
            rec["ipv4_address"] = ip
            rec["ipv4_netmask"] = mask
            rec["ipv4_cidr"] = prefix
            if prefix is not None:
                rec["ip_cidr_str"] = f"{ip}/{prefix}"

    ip_by_ifindex: Dict[int, str] = {}
    ip_mask_by_ifindex: Dict[int, str] = {}
    for rec in if_table.values():
        try:
            idx = int(rec.get("index"))
        except Exception:
            continue
        ip = rec.get("ip")
        mask = rec.get("netmask")
        if isinstance(ip, str) and ip:
            ip_by_ifindex[idx] = ip
        if isinstance(mask, str) and mask:
            ip_mask_by_ifindex[idx] = mask
    client.cache["ip_by_ifindex"] = ip_by_ifindex
    client.cache["ip_mask_by_ifindex"] = ip_mask_by_ifindex
