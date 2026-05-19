"""H3C (HP Comware) environmental polling module."""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..snmp import SwitchSnmpClient

from ..helpers import _parse_numeric
from ..const import (
    OID_entPhysicalName,
    OID_entPhysicalDescr,
)


async def poll_h3c_environment(client: SwitchSnmpClient) -> None:
    """Fetch environmental statistics for H3C devices cleanly and efficiently."""
    physical_names: dict[int, str] = {}

    # Retrieve vendor-specific OIDs dynamically from the JSON database
    # with local fallbacks to keep other files completely clean.
    cpu_items = client._get_database_oids("cpu", "H3C")
    oid_h3c_cpu = cpu_items[0].get("oid") if cpu_items else "1.3.6.1.4.1.25506.2.6.1.1.1.1.6"

    mem_items = client._get_database_oids("memory", "H3C")
    oid_h3c_mem = mem_items[0].get("oid") if mem_items else "1.3.6.1.4.1.25506.2.6.1.1.1.1.8"

    temp_items = client._get_database_oids("temperature", "H3C")
    oid_h3c_temp = temp_items[0].get("oid") if temp_items else "1.3.6.1.4.1.25506.2.6.1.1.1.1.12"

    psu_items = client._get_database_oids("psu", "H3C")
    oid_h3c_error_status = psu_items[0].get("oid_status") if psu_items else "1.3.6.1.4.1.25506.2.6.1.1.1.1.19"
    
    # Try entPhysicalName first
    try:
        for oid, val in await client._async_walk(OID_entPhysicalName):
            try:
                idx = int(str(oid).split(".")[-1])
                name_str = ""
                if hasattr(val, "asOctets"):
                    name_str = val.asOctets().decode("utf-8", "ignore")
                elif hasattr(val, "prettyPrint"):
                    name_str = val.prettyPrint()
                else:
                    name_str = str(val)
                if name_str:
                    physical_names[idx] = name_str.strip()
            except Exception:
                continue
    except Exception:
        pass
    
    # Fallback to entPhysicalDescr
    if not physical_names:
        try:
            for oid, val in await client._async_walk(OID_entPhysicalDescr):
                try:
                    idx = int(str(oid).split(".")[-1])
                    desc_str = ""
                    if hasattr(val, "asOctets"):
                        desc_str = val.asOctets().decode("utf-8", "ignore")
                    elif hasattr(val, "prettyPrint"):
                        desc_str = val.prettyPrint()
                    else:
                        desc_str = str(val)
                    if desc_str:
                        physical_names[idx] = desc_str.strip()
                except Exception:
                    continue
        except Exception:
            pass

    # CPU Walk
    try:
        cpu_by_idx = {}
        for oid, val in await client._async_walk(oid_h3c_cpu):
            try:
                idx = int(str(oid).split(".")[-1])
                n = _parse_numeric(val)
                if n is not None and 0 <= n <= 100:
                    cpu_by_idx[idx] = float(n)
            except Exception:
                continue

        # Find index corresponding to "board", "chassis", "main", "mpu", or "cpu" (case-insensitive)
        board_cpu = None
        for idx, cpu_val in cpu_by_idx.items():
            name = physical_names.get(idx, "").lower()
            if any(x in name for x in ("board", "chassis", "main", "mpu", "cpu")):
                board_cpu = cpu_val
                break

        # Fallback: if not found, use index 212, or average non-zeros, or max non-zero
        if board_cpu is None:
            board_cpu = cpu_by_idx.get(212)
        if board_cpu is None:
            non_zero = [v for v in cpu_by_idx.values() if v > 0]
            board_cpu = max(non_zero) if non_zero else 0.0

        client.cache["env_cpu_5s"] = board_cpu
        client.cache["env_cpu_60s"] = board_cpu
        client.cache["env_cpu_300s"] = board_cpu
    except Exception:
        client.cache["env_cpu_5s"] = None
        client.cache["env_cpu_60s"] = None
        client.cache["env_cpu_300s"] = None

    # Memory Walk
    try:
        mem_by_idx = {}
        for oid, val in await client._async_walk(oid_h3c_mem):
            try:
                idx = int(str(oid).split(".")[-1])
                n = _parse_numeric(val)
                if n is not None and 0 <= n <= 100:
                    mem_by_idx[idx] = float(n)
            except Exception:
                continue

        board_mem = None
        for idx, mem_val in mem_by_idx.items():
            name = physical_names.get(idx, "").lower()
            if any(x in name for x in ("board", "chassis", "main", "mpu", "cpu")):
                board_mem = mem_val
                break

        if board_mem is None:
            board_mem = mem_by_idx.get(212)
        if board_mem is None:
            non_zero = [v for v in mem_by_idx.values() if v > 0]
            board_mem = max(non_zero) if non_zero else 0.0

        client.cache["env_mem_total_kb"] = 1000000
        client.cache["env_mem_free_kb"] = int(1000000.0 * (100.0 - board_mem) / 100.0)
    except Exception:
        client.cache["env_mem_total_kb"] = None
        client.cache["env_mem_free_kb"] = None

    # Temperature Walk
    temps_c: dict[int, int] = {}
    try:
        for oid, val in await client._async_walk(oid_h3c_temp):
            try:
                idx = int(str(oid).split(".")[-1])
                n = _parse_numeric(val)
                if n is not None and n != 65535 and -50 <= n <= 200:
                    temps_c[idx] = int(n)
            except Exception:
                continue
    except Exception:
        pass

    # Fans & PSUs Walk via ErrorStatus
    raw_fans_status: dict[int, int] = {}
    raw_psus_status: dict[int, int] = {}
    try:
        for oid, val in await client._async_walk(oid_h3c_error_status):
            try:
                idx = int(str(oid).split(".")[-1])
                st_n = _parse_numeric(val)
                if st_n is not None:
                    st_n = int(st_n)
                    if st_n in (1, 4):
                        continue
                    name_str = physical_names.get(idx, "")
                    name_lower = name_str.lower()
                    is_fan = "fan" in name_lower
                    is_psu = "power" in name_lower or "psu" in name_lower
                    mapped_status = 2 if st_n == 2 else 3
                    
                    if is_fan:
                        raw_fans_status[idx] = mapped_status
                    elif is_psu:
                        raw_psus_status[idx] = mapped_status
            except Exception:
                continue
    except Exception:
        pass

    # Sequential Index Mapping
    sorted_temp_idxs = sorted(temps_c.keys())
    sorted_fan_idxs = sorted(raw_fans_status.keys())
    sorted_psu_idxs = sorted(raw_psus_status.keys())

    mapped_temps_c = {}
    mapped_temp_labels = {}
    for seq_idx, raw_idx in enumerate(sorted_temp_idxs):
        mapped_temps_c[seq_idx] = temps_c[raw_idx]
        raw_label = physical_names.get(raw_idx, f"SENSOR {seq_idx + 1}")
        mapped_temp_labels[seq_idx] = raw_label
    client.cache["env_temps_c"] = mapped_temps_c
    client.cache["env_temp_labels"] = mapped_temp_labels

    mapped_fans_status = {}
    for seq_idx, raw_idx in enumerate(sorted_fan_idxs):
        mapped_fans_status[seq_idx] = raw_fans_status[raw_idx]
    client.cache["env_fans_status"] = mapped_fans_status

    mapped_psus_status = {}
    for seq_idx, raw_idx in enumerate(sorted_psu_idxs):
        mapped_psus_status[seq_idx] = raw_psus_status[raw_idx]
    client.cache["env_psu_status"] = mapped_psus_status
