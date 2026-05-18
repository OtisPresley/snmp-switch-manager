"""PySNMP engine bootstrap and MIB preloading, offloaded to the executor."""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..snmp import SwitchSnmpClient

_LOGGER = logging.getLogger(__name__)


def _build_engine_and_preload_mibs():
    """Build a SnmpEngine and preload all MIBs synchronously (runs in executor)."""
    from ..snmp_compat import SnmpEngine, ObjectIdentity  # local import avoids circular

    eng = SnmpEngine()
    try:
        if hasattr(eng, "get_mib_builder"):
            mib_builder = eng.get_mib_builder()
        elif hasattr(eng, "getMibBuilder"):
            mib_builder = eng.getMibBuilder()
        elif hasattr(eng, "mibBuilder"):
            mib_builder = eng.mibBuilder
        elif hasattr(eng, "msgAndPduDsp"):
            mib_builder = eng.msgAndPduDsp.mibInstrumController.mibBuilder
        else:
            raise RuntimeError("Could not extract MibBuilder from SnmpEngine")

        # Pre-load ALL MIB modules used by this integration off the event loop.
        # Home Assistant flags synchronous FS access (os.listdir/open) from pysnmp's
        # MIB loader when it occurs on the asyncio loop thread. Preloading here
        # ensures pysnmp will not hit the filesystem during async polling/walks.
        #
        # Modules covered:
        #   - Core SMI / ASN.1 machinery (SNMPv2-SMI, SNMPv2-TC, …)
        #   - SNMPv3 USM / framework (needed for v3 auth/priv negotiation)
        #   - IF-MIB types (OctetString counters, ifType enumerations)
        #   - ENTITY-MIB, HOST-RESOURCES-MIB, BRIDGE-MIB, Q-BRIDGE-MIB
        #   - IP-MIB, POWER-ETHERNET-MIB
        mibs_to_load = [
            # Core / SMI
            "SNMPv2-SMI",
            "SNMPv2-TC",
            "SNMPv2-CONF",
            "SNMPv2-MIB",
            "__SNMPv2-MIB",
            "instances.__SNMPv2-MIB",
            # SNMPv3
            "SNMP-FRAMEWORK-MIB",
            "SNMP-COMMUNITY-MIB",
            "SNMP-TARGET-MIB",
            "SNMP-NOTIFICATION-MIB",
            "SNMP-USER-BASED-SM-MIB",
            "SNMP-VIEW-BASED-ACM-MIB",
            "SNMPv2-TM",
            "PYSNMP-USM-MIB",
            "PYSNMP-MPD-MIB",
            "PYSNMP-SOURCE-MIB",
            # Interface MIBs
            "IF-MIB",
            "IANAifType-MIB",
            # Entity / hardware inventory
            "ENTITY-MIB",
            # IP address tables
            "IP-MIB",
            # Bridge / VLAN MIBs
            "BRIDGE-MIB",
            "Q-BRIDGE-MIB",
            # Host resources (CPU / memory fallback)
            "HOST-RESOURCES-MIB",
            "HOST-RESOURCES-TYPES",
            # PoE
            "POWER-ETHERNET-MIB",
        ]

        for mib in mibs_to_load:
            try:
                if hasattr(mib_builder, "load_modules"):
                    mib_builder.load_modules(mib)
                else:
                    mib_builder.loadModules(mib)
            except Exception as e:
                _LOGGER.debug("Failed to preload MIB %s: %s", mib, e)
    except Exception as e:
        _LOGGER.error("Fatal error during PySNMP preload initialization: %s", e)

    # Force PySNMP to evaluate and cache the internal instances required by the
    # protocol engine. If not explicitly imported here, the protocol engine
    # (rfc3412/USM) will lazily trigger import_symbols on the very first received
    # packet, hitting the filesystem during the event loop.
    try:
        if hasattr(mib_builder, "import_symbols"):
            mib_builder.import_symbols("SNMPv2-SMI", "iso", "zeroDotZero", "snmpModules")
            mib_builder.import_symbols("SNMPv2-MIB", "snmpInPkts", "snmpInBadVersions", "snmpInBadCommunityNames", "snmpInBadCommunityUses", "snmpInASNParseErrs", "snmpSilentDrops", "snmpProxyDrops")
            mib_builder.import_symbols("__PYSNMP-USM-MIB", "pysnmpUsmKeyType")
        else:
            mib_builder.importSymbols("SNMPv2-SMI", "iso", "zeroDotZero", "snmpModules")
            mib_builder.importSymbols("SNMPv2-MIB", "snmpInPkts", "snmpInBadVersions", "snmpInBadCommunityNames", "snmpInBadCommunityUses", "snmpInASNParseErrs", "snmpSilentDrops", "snmpProxyDrops")
            mib_builder.importSymbols("__PYSNMP-USM-MIB", "pysnmpUsmKeyType")

        from pysnmp.smi.view import MibViewController
        vc = MibViewController(mib_builder)
        eng._vc = vc  # cache MibViewController on engine immediately!
        eng.cache["mibViewController"] = vc  # PySNMP v7 requires it in the internal cache dictionary

        if hasattr(ObjectIdentity("1.3.6.1.2.1.1.1.0"), "resolve_with_mib"):
            ObjectIdentity("1.3.6.1.2.1.1.1.0").resolve_with_mib(vc)
        else:
            ObjectIdentity("1.3.6.1.2.1.1.1.0").resolveWithMib(vc)
    except Exception as e:
        _LOGGER.warning("PySNMP warmup failed (this is harmless but may cause FS logs): %s", e)

    return eng


async def ensure_engine(client: "SwitchSnmpClient") -> None:
    """Lazily build the SnmpEngine (runs MIB preloading in executor)."""
    if client.engine is not None:
        return
    client.engine = await client.hass.async_add_executor_job(_build_engine_and_preload_mibs)
