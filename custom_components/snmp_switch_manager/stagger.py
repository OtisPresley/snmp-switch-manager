"""Give each switch its own slot in the polling interval.

Home Assistant schedules a coordinator's next poll a whole number of seconds
after the last one. Every switch is set up in the same second at startup, so
with the same interval they poll in the same second for as long as Home
Assistant runs, and their SNMP replies are decoded on the event loop back to
back: four switches measured as a 100-430 ms stall of the whole of Home
Assistant once a minute, where one switch at a time costs a fraction of that.

Each switch gets a fixed slot - its place among the loaded switches, spread
evenly over the interval - on the event loop's clock, and is refreshed once
when that slot next comes round, which re-anchors its schedule there. The
slot is absolute rather than "some seconds after setup", so a switch that is
reloaded later (an options change) goes back to its own slot instead of
landing on another switch's.

Only public coordinator API is used: ``async_refresh()`` reschedules the
coordinator from the moment it completes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.update_coordinator import DataUpdateCoordinator


def slot_delay(now: float, interval: float, index: int, count: int) -> float:
    """Seconds from ``now`` until the loop clock next reaches this switch's slot.

    The slot is ``index / count`` of the way through the interval; the delay
    is always in ``[0, interval)``.
    """
    slot = interval * index / count
    return (slot - now) % interval


@callback
def async_stagger_switch(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: DataUpdateCoordinator
) -> float | None:
    """Schedule the refresh that moves this switch to its slot.

    Returns the delay in seconds, or None when there is nothing to spread
    (a single switch, or polling switched off).
    """
    interval = coordinator.update_interval
    if interval is None:
        return None
    switches = sorted(
        e.entry_id
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.disabled_by is None
    )
    if len(switches) < 2 or entry.entry_id not in switches:
        return None
    delay = slot_delay(
        hass.loop.time(),
        interval.total_seconds(),
        switches.index(entry.entry_id),
        len(switches),
    )

    @callback
    def _refresh(_now: Any) -> None:
        entry.async_create_background_task(
            hass, coordinator.async_refresh(), f"{DOMAIN} stagger {entry.title}"
        )

    entry.async_on_unload(async_call_later(hass, delay, _refresh))
    return delay
