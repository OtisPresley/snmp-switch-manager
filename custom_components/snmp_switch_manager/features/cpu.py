"""CPU usage polling."""
from __future__ import annotations
import re
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..snmp import SwitchSnmpClient

from ..helpers import _parse_numeric

_OID_HR_CPU = "1.3.6.1.2.1.25.3.3.1.2"  # HOST-RESOURCES-MIB hrProcessorLoad


def _parse_cpu_string(cpu_val) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Extract up to three CPU percentages (5s, 60s, 300s) from a value string.

    Handles:
    - Cisco-style: "5%/60%/300%"
    - Plain numeric: "42"
    - Averaged float from walk
    """
    if cpu_val is None:
        return None, None, None

    cpu_s = str(cpu_val)
    nums = re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*%", cpu_s)
    if len(nums) >= 3:
        return float(nums[0]), float(nums[1]), float(nums[2])

    try:
        f = float(cpu_val)
        return f, f, f
    except Exception:
        return None, None, None


async def poll_cpu(client: "SwitchSnmpClient", vendor: str) -> None:
    """Poll CPU utilisation metrics."""
    cpu_items = client._get_database_oids("cpu", vendor)
    cpu_val = None

    for item in cpu_items:
        oid = item.get("oid")
        if item.get("method") == "get":
            cpu_val = await client._async_get_one(oid)
        elif item.get("method") == "walk":
            rows = await client._async_walk(oid)
            vals = [float(v) for _, v in rows if _parse_numeric(v) is not None]
            if vals:
                cpu_val = sum(vals) / len(vals)

    v5s, v60s, v300s = _parse_cpu_string(cpu_val)
    client.cache["env_cpu_raw"] = str(cpu_val) if cpu_val is not None else None
    client.cache["env_cpu_5s"] = v5s
    client.cache["env_cpu_60s"] = v60s
    client.cache["env_cpu_300s"] = v300s

    # HOST-RESOURCES-MIB fallback (only fills missing values)
    if v5s is None and v60s is None and v300s is None:
        try:
            cpu_vals = [
                float(n)
                for _, val in await client._async_walk(_OID_HR_CPU)
                if (n := _parse_numeric(val)) is not None and 0.0 <= float(n) <= 100.0
            ]
            if cpu_vals:
                avg = sum(cpu_vals) / len(cpu_vals)
                client.cache["env_cpu_5s"] = avg
                client.cache["env_cpu_60s"] = avg
                client.cache["env_cpu_300s"] = avg
        except Exception:
            pass
