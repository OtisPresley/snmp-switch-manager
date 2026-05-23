import asyncio
import sys
import os
import types

PROJECT = "/home/jamie/Documents/Projects/snmp-switch-manager"
sys.path.insert(0, PROJECT)

class FakeHass:
    def __init__(self):
        self.loop = asyncio.get_event_loop()
    async def async_add_executor_job(self, fn, *args):
        return await asyncio.get_event_loop().run_in_executor(None, fn, *args)

_ha = types.ModuleType("homeassistant")
_ha_core = types.ModuleType("homeassistant.core")
_ha_core.HomeAssistant = FakeHass
_ha.core = _ha_core
sys.modules["homeassistant"] = _ha
sys.modules["homeassistant.core"] = _ha_core

for mod in [
    "homeassistant.config_entries",
    "homeassistant.exceptions",
    "homeassistant.helpers",
    "homeassistant.helpers.update_coordinator",
    "homeassistant.helpers.config_validation",
    "homeassistant.helpers.selector",
    "homeassistant.const",
    "homeassistant.data_entry_flow",
]:
    sys.modules[mod] = types.ModuleType(mod)

sys.modules["homeassistant.config_entries"].ConfigEntry = object
sys.modules["homeassistant.exceptions"].ConfigEntryAuthFailed = Exception
sys.modules["homeassistant.helpers.update_coordinator"].DataUpdateCoordinator = object
sys.modules["homeassistant.const"].CONF_HOST = "host"
sys.modules["homeassistant.const"].CONF_PORT = "port"

from custom_components.snmp_switch_manager.snmp import SwitchSnmpClient

async def main():
    hass = FakeHass()
    settings = {
        "host": "10.0.11.102",
        "port": 161,
        "version": "v3",
        "snmpv3_username": "snmpv3user",
        "snmpv3_auth_protocol": "sha",
        "snmpv3_auth_password": "OtisPresley1983",
        "snmpv3_priv_protocol": "none",
        "snmpv3_priv_password": "",
    }
    client = SwitchSnmpClient(hass, "10.0.11.102", settings)
    await client.async_initialize()
    
    print("\n[A] Walking standard actual power: 1.3.6.1.2.1.105.1.1.1.15")
    std_rows = await client._async_walk("1.3.6.1.2.1.105.1.1.1.15")
    print(f"  Returned {len(std_rows)} rows. First 5:")
    for oid, val in std_rows[:5]:
        print(f"    {oid} = {val}")

    print("\n[B] Walking typoed actual power: 1.3.6.1.2.1.105.1.1.1.1.15")
    typo_rows = await client._async_walk("1.3.6.1.2.1.105.1.1.1.1.15")
    print(f"  Returned {len(typo_rows)} rows. First 5:")
    for oid, val in typo_rows[:5]:
        print(f"    {oid} = {val}")

    print("\n[C] Walking Dell private actual power: 1.3.6.1.4.1.674.10895.5000.2.6132.1.1.15.1.1.1.2.1")
    dell_rows = await client._async_walk("1.3.6.1.4.1.674.10895.5000.2.6132.1.1.15.1.1.1.2.1")
    print(f"  Returned {len(dell_rows)} rows. First 5:")
    for oid, val in dell_rows[:5]:
        print(f"    {oid} = {val}")

    await client.async_close()

if __name__ == "__main__":
    asyncio.run(main())
