import logging
from pathlib import Path

try:
    from homeassistant.components.http import StaticPathConfig

    HAS_STATIC_PATH_CONFIG = True
except ImportError:
    HAS_STATIC_PATH_CONFIG = False

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

URL_BASE = "/snmp-switch-manager-frontend"
CARD_FILENAME = "snmp-switch-manager-card.js"


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Register the frontend resources."""
    # 1. Register the static path
    frontend_dir = Path(__file__).parent / "frontend"
    if not frontend_dir.exists():
        _LOGGER.warning("Frontend directory not found at %s", frontend_dir)
        return

    if HAS_STATIC_PATH_CONFIG:
        # Use the async path registration
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    url_path=f"{URL_BASE}/{CARD_FILENAME}",
                    path=str(frontend_dir / CARD_FILENAME),
                    cache_headers=False,
                )
            ]
        )
    else:
        # Fallback for older HA versions (like those in test environments)
        hass.http.register_static_path(
            f"{URL_BASE}/{CARD_FILENAME}",
            str(frontend_dir / CARD_FILENAME),
            False,
        )

    # 2. Register the Lovelace resource
    # To avoid the lazy loading data loss bug, we ensure the resources are loaded first.
    lovelace = hass.data.get("lovelace")
    if not lovelace:
        _LOGGER.debug("Lovelace not loaded, cannot register resource")
        return

    lovelace_mode = getattr(
        lovelace, "resource_mode", getattr(lovelace, "mode", "storage")
    )
    if lovelace_mode != "storage":
        _LOGGER.debug(
            "Lovelace is in %s mode, skipping automatic resource registration",
            lovelace_mode,
        )
        return

    resources = lovelace.resources
    if not resources:
        _LOGGER.debug("Lovelace resources collection not found")
        return

    if not resources.loaded:
        await resources.async_load()

    # Find the version dynamically from the integration manifest
    try:
        from homeassistant.loader import async_get_integration

        from .const import DOMAIN

        integration = await async_get_integration(hass, DOMAIN)
        version = integration.version
    except Exception as err:
        _LOGGER.warning("Could not retrieve integration version: %s", err)
        version = "0.6.0"

    url = f"{URL_BASE}/{CARD_FILENAME}?v={version}"

    # Check if resource already exists (checking url prefix to handle version changes)
    existing = None
    for item in resources.async_items():
        item_url = item.get("url", "")
        if item_url.startswith(f"{URL_BASE}/{CARD_FILENAME}"):
            existing = item
            break

    if existing:
        if existing.get("url") != url:
            _LOGGER.info(
                "Updating Lovelace resource from %s to %s",
                existing.get("url"),
                url,
            )
            await resources.async_update_item(
                existing.get("id"),
                {
                    "res_type": "module",
                    "url": url,
                },
            )
    else:
        _LOGGER.info("Registering Lovelace resource: %s", url)
        await resources.async_create_item(
            {
                "res_type": "module",
                "url": url,
            }
        )
