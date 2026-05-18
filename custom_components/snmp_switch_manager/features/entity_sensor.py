"""ENTITY-SENSOR-MIB cross-vendor fallback for temps, fans, and power."""
from __future__ import annotations
import asyncio
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..snmp import SwitchSnmpClient

from ..helpers import _parse_numeric, _entity_sensor_value_to_float

# entPhySensorType table OIDs
_OID_TYPE = "1.3.6.1.2.1.99.1.1.1.1"    # entPhySensorType
_OID_PREC = "1.3.6.1.2.1.99.1.1.1.2"    # entPhySensorPrecision
_OID_SCALE = "1.3.6.1.2.1.99.1.1.1.3"   # entPhySensorScale
_OID_VALUE = "1.3.6.1.2.1.99.1.1.1.4"   # entPhySensorValue
_OID_OPER = "1.3.6.1.2.1.99.1.1.1.5"    # entPhySensorOperStatus

# entPhySensorType enum values of interest
_TYPE_WATTS = 6
_TYPE_CELSIUS = 8
_TYPE_RPM = 10

# oper-status -> fan_status mapping  (ok=1→2, unavailable=2→1, nonoperational=3→3)
_OPER_TO_FAN_STATUS = {1: 2, 2: 1, 3: 3}


def _rows_to_int_dict(rows: list) -> dict[int, int]:
    """Walk rows [(oid, val), …] → {last_oid_component: int(val)}."""
    result: dict[int, int] = {}
    for oid, val in rows:
        try:
            idx = int(str(oid).split(".")[-1])
        except Exception:
            continue
        n = _parse_numeric(val)
        if n is not None:
            result[idx] = int(n)
    return result


def _rows_to_any_dict(rows: list) -> dict[int, Any]:
    """Walk rows [(oid, val), …] → {last_oid_component: val}."""
    result: dict[int, Any] = {}
    for oid, val in rows:
        try:
            idx = int(str(oid).split(".")[-1])
        except Exception:
            continue
        result[idx] = val
    return result


async def poll_entity_sensor_fallback(client: "SwitchSnmpClient") -> None:
    """Fill missing temperature, fan, and power readings via ENTITY-SENSOR-MIB.

    Only runs when at least one category is absent from the cache.
    """
    need_temps = client.cache.get("env_temps_c") in (None, {})
    need_fans = client.cache.get("env_fans_rpm") in (None, {})
    need_power = float(client.cache.get("env_power_mw_total") or 0.0) == 0.0

    if not (need_temps or need_fans or need_power):
        return

    try:
        types = _rows_to_int_dict(await client._async_walk(_OID_TYPE))
        if not types:
            return

        value_rows, scale_rows, prec_rows, oper_rows = await asyncio.gather(
            client._async_walk(_OID_VALUE),
            client._async_walk(_OID_SCALE),
            client._async_walk(_OID_PREC),
            client._async_walk(_OID_OPER),
        )

        values = _rows_to_any_dict(value_rows)
        scales = _rows_to_int_dict(scale_rows)
        precs = _rows_to_int_dict(prec_rows)
        opers = _rows_to_int_dict(oper_rows)

        temps_c: dict[int, int] = dict(client.cache.get("env_temps_c") or {})
        fans_rpm: dict[int, int] = dict(client.cache.get("env_fans_rpm") or {})
        fans_status: dict[int, int] = dict(client.cache.get("env_fans_status") or {})
        watts_mw_total = 0.0
        watts_found = False

        for idx, sensor_type in types.items():
            v = _entity_sensor_value_to_float(values.get(idx), scales.get(idx), precs.get(idx))
            if v is None:
                continue

            if sensor_type == _TYPE_CELSIUS and -50.0 <= v <= 150.0:
                temps_c.setdefault(idx, int(round(v)))

            elif sensor_type == _TYPE_RPM and 0.0 <= v <= 50000.0:
                fans_rpm.setdefault(idx, int(round(v)))
                fans_status.setdefault(idx, _OPER_TO_FAN_STATUS.get(opers.get(idx, 2), 3))

            elif sensor_type == _TYPE_WATTS and 0.0 <= v <= 100000.0:
                watts_found = True
                watts_mw_total += v * 1000.0

        if temps_c:
            client.cache["env_temps_c"] = temps_c
        if fans_rpm:
            client.cache["env_fans_rpm"] = fans_rpm
        if fans_status:
            client.cache["env_fans_status"] = fans_status
        if watts_found and float(client.cache.get("env_power_mw_total") or 0.0) == 0.0:
            client.cache["env_power_mw_total"] = watts_mw_total

    except Exception:
        pass
