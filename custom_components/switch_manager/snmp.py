# custom_components/switch_manager/snmp.py
from __future__ import annotations

from typing import Iterable, Tuple, Any

__all__ = [
    "SnmpError",
    "SnmpDependencyError",
    "SwitchSnmpClient",
    "ensure_snmp_available",
    "validate_environment_or_raise",
    "snmp_get",
    "snmp_walk",
    "snmp_set_octet_string",
]


# -----------------------------------------------------------------------------
# Exceptions (backward compatible)
# -----------------------------------------------------------------------------

class SnmpError(RuntimeError):
    """Base SNMP error for this integration."""


class SnmpDependencyError(SnmpError):
    """Raised when pysnmp cannot be imported/used."""


# -----------------------------------------------------------------------------
# Lazy HLAPI import (works with pysnmp-lextudio>=5 and pysnmp 4.x)
# -----------------------------------------------------------------------------

def _imports():
    """
    Lazy-import pysnmp HLAPI so HA can install requirements first.

    We intentionally avoid the legacy CommandGenerator API; both pysnmp 4.x and
    pysnmp-lextudio 5.x provide the HLAPI we use here.
    """
    try:
        from pysnmp.hlapi import (  # type: ignore
            SnmpEngine,
            CommunityData,
            UdpTransportTarget,
            ContextData,
            ObjectType,
            ObjectIdentity,
            getCmd,
            nextCmd,
            setCmd,
        )
    except Exception as e:  # pragma: no cover
        # Keep raw reason in logs; UI shows a generic dependency error.
        raise SnmpDependencyError(f"pysnmp.hlapi import failed: {e}")

    return (
        SnmpEngine,
        CommunityData,
        UdpTransportTarget,
        ContextData,
        ObjectType,
        ObjectIdentity,
        getCmd,
        nextCmd,
        setCmd,
    )


# -----------------------------------------------------------------------------
# Public helpers
# -----------------------------------------------------------------------------

def ensure_snmp_available() -> None:
    """Used by config_flow to verify HLAPI availability once."""
    _imports()  # raises SnmpDependencyError on failure


def validate_environment_or_raise() -> None:
    """
    Backward-compatible alias used by older code paths.

    Prior versions called this to validate pysnmp availability. Keep it to
    avoid import errors from modules that haven't been updated yet.
    """
    ensure_snmp_available()


def snmp_get(host: str, community: str, port: int, oid: str) -> Any:
    """Perform a single GET and return the value for the OID."""
    (
        SnmpEngine,
        CommunityData,
        UdpTransportTarget,
        ContextData,
        ObjectType,
        ObjectIdentity,
        getCmd,
        _nextCmd,
        _setCmd,
    ) = _imports()

    iterator = getCmd(
        SnmpEngine(),
        CommunityData(community, mpModel=1),  # SNMP v2c
        UdpTransportTarget((host, int(port))),
        ContextData(),
        ObjectType(ObjectIdentity(oid)),
    )

    error_indication, error_status, error_index, var_binds = next(iterator)
    if error_indication:
        raise SnmpError(error_indication)
    if error_status:
        where = var_binds[int(error_index) - 1][0] if error_index else "?"
        raise SnmpError(f"{error_status.prettyPrint()} at {where}")
    # Return the value part of the first var-bind
    return var_binds[0][1]


def snmp_walk(
    host: str, community: str, port: int, base_oid: str
) -> Iterable[Tuple[str, Any]]:
    """Walk (nextCmd) starting at base_oid and yield (oid, value) pairs."""
    (
        SnmpEngine,
        CommunityData,
        UdpTransportTarget,
        ContextData,
        ObjectType,
        ObjectIdentity,
        _getCmd,
        nextCmd,
        _setCmd,
    ) = _imports()

    for (err_ind, err_stat, err_idx, var_binds) in nextCmd(
        SnmpEngine(),
        CommunityData(community, mpModel=1),
        UdpTransportTarget((host, int(port))),
        ContextData(),
        ObjectType(ObjectIdentity(base_oid)),
        lexicographicMode=False,
    ):
        if err_ind:
            raise SnmpError(err_ind)
        if err_stat:
            where = var_binds[int(err_idx) - 1][0] if err_idx else "?"
            raise SnmpError(f"{err_stat.prettyPrint()} at {where}")

        for name, val in var_binds:
            yield (str(name), val)


def snmp_set_octet_string(
    host: str, community: str, port: int, oid: str, value
) -> None:
    """Set an OCTET STRING (or compatible) value."""
    (
        SnmpEngine,
        CommunityData,
        UdpTransportTarget,
        ContextData,
        ObjectType,
        ObjectIdentity,
        _getCmd,
        _nextCmd,
        setCmd,
    ) = _imports()

    err_ind, err_stat, err_idx, var_binds = next(
        setCmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            UdpTransportTarget((host, int(port))),
            ContextData(),
            ObjectType(ObjectIdentity(oid), value),
        )
    )
    if err_ind:
        raise SnmpError(err_ind)
    if err_stat:
        where = var_binds[int(err_idx) - 1][0] if err_idx else "?"
        raise SnmpError(f"{err_stat.prettyPrint()} at {where}")


# -----------------------------------------------------------------------------
# Backward-compatible client wrapper (used elsewhere in the integration)
# -----------------------------------------------------------------------------

class SwitchSnmpClient:
    """
    Thin wrapper preserved for compatibility with existing modules.

    Provides simple get/walk/set methods bound to a host/community/port.
    """

    def __init__(self, host: str, community: str, port: int = 161) -> None:
        self._host = host
        self._community = community
        self._port = int(port)

    # Optional classmethod so callers can force dependency check explicitly
    @classmethod
    def ensure_available(cls) -> None:
        ensure_snmp_available()

    # Instance helpers used by the integration
    def get(self, oid: str) -> Any:
        return snmp_get(self._host, self._community, self._port, oid)

    def walk(self, base_oid: str) -> Iterable[Tuple[str, Any]]:
        return snmp_walk(self._host, self._community, self._port, base_oid)

    def set_octet_string(self, oid: str, value) -> None:
        snmp_set_octet_string(self._host, self._community, self._port, oid, value)
