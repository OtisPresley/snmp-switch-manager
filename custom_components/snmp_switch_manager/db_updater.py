import logging
import os
import json
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN, GITHUB_BRANCH

_LOGGER = logging.getLogger(__name__)

DB_FILES = [
    "cpu.json",
    "device_info.json",
    "fans.json",
    "interface_classification.json",
    "interface_filters.json",
    "memory.json",
    "poe.json",
    "power.json",
    "psu.json",
    "rename_rules.json",
    "temperature.json",
    "vendors.json"
]

RAW_URL_ROOT = f"https://raw.githubusercontent.com/OtisPresley/snmp-switch-manager/{GITHUB_BRANCH}/custom_components/snmp_switch_manager/database/"


async def async_check_and_update_db(hass: HomeAssistant) -> bool:
    """Download updated database files from GitHub and save them if changed."""
    session = async_get_clientsession(hass)
    db_path = os.path.join(os.path.dirname(__file__), "database")
    
    updated_any = False
    
    for filename in DB_FILES:
        url = f"{RAW_URL_ROOT}{filename}"
        local_path = os.path.join(db_path, filename)
        
        try:
            async with session.get(url, timeout=10) as response:
                if response.status != 200:
                    _LOGGER.debug("Skipping update check for %s: HTTP %s", filename, response.status)
                    continue
                
                content = await response.text()
                # Parse to ensure it is valid JSON
                new_data = json.loads(content)
                new_str = json.dumps(new_data, indent=2, sort_keys=True)
                
                # Load current local file
                old_str = None
                if os.path.exists(local_path):
                    def read_local() -> str | None:
                        try:
                            with open(local_path, "r", encoding="utf-8") as f:
                                return json.dumps(json.load(f), indent=2, sort_keys=True)
                        except Exception:
                            return None
                    old_str = await hass.async_add_executor_job(read_local)
                
                if old_str != new_str:
                    _LOGGER.info("Updating local database file: %s", filename)
                    
                    def write_local(path: str, data_str: str) -> None:
                        os.makedirs(os.path.dirname(path), exist_ok=True)
                        with open(path, "w", encoding="utf-8") as f:
                            f.write(data_str)
                            
                    await hass.async_add_executor_job(
                        write_local, 
                        local_path, 
                        json.dumps(new_data, indent=2)
                    )
                    updated_any = True
                    
        except Exception as e:
            _LOGGER.error("Failed to check database update for %s: %s", filename, e)
            
    return updated_any


async def async_setup_db_updater(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up the periodic background database updater."""
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
        
    # Store entry reference
    entries = hass.data[DOMAIN].setdefault("entries", {})
    entries[entry.entry_id] = entry
    
    if "db_updater_timer" in hass.data[DOMAIN]:
        return
        
    async def run_update(now: Any = None) -> None:
        _LOGGER.debug("Starting background database update check...")
        updated = await async_check_and_update_db(hass)
        if updated:
            _LOGGER.info("Database updated! Reloading all active SNMP Switch Manager config entries...")
            for active_entry in list(entries.values()):
                hass.async_create_task(
                    hass.config_entries.async_reload(active_entry.entry_id)
                )

    # Schedule periodic checks every 6 hours
    hass.data[DOMAIN]["db_updater_timer"] = async_track_time_interval(
        hass,
        run_update,
        timedelta(hours=6)
    )
    
    # Run immediate check shortly after start to avoid blocking initialization
    def deferred_start(_: Any) -> None:
        hass.add_job(run_update())
        
    from homeassistant.helpers.event import async_call_later
    async_call_later(hass, 10, deferred_start)


def async_unload_db_updater(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clean up and remove background updater if no entries remain."""
    if DOMAIN not in hass.data:
        return
        
    entries = hass.data[DOMAIN].get("entries", {})
    entries.pop(entry.entry_id, None)
    
    if not entries:
        timer = hass.data[DOMAIN].pop("db_updater_timer", None)
        if timer:
            timer()
            _LOGGER.debug("Cancelled background database updater timer")
