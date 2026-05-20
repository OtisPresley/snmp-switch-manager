from __future__ import annotations
from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from ..snmp import SwitchSnmpClient

try:
    from ..helpers import _parse_numeric
except ImportError:
    from custom_components.snmp_switch_manager.helpers import _parse_numeric

async def poll_power(client: SwitchSnmpClient, vendor: str) -> None:
    """Poll Power metrics."""
    power_items = client._get_database_oids("power", vendor)
    env_power_mw: Dict[int, float] = {}
    for item in power_items:
        oid = item.get("oid")
        scale = float(item.get("scale", 1.0))
        if item.get("method") == "walk":
            rows = await client._async_walk(oid)
            for o, val in rows:
                try:
                    env_idx = int(str(o).split(".")[-1])
                except Exception:
                    continue
                mw = _parse_numeric(val)
                if mw is None:
                    continue
                env_power_mw[env_idx] = float(mw) * scale
                
    client.cache["env_power_mw"] = env_power_mw
    client.cache["env_power_mw_total"] = float(sum(env_power_mw.values())) if env_power_mw else 0.0
