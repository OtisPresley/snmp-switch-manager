"""Each switch gets its own slot in the polling interval.

Four switches set up in the same second polled in the same second forever
after, and their replies were decoded on the event loop back to back.
"""
import importlib.util
import sys
import types
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

PKG = Path(__file__).resolve().parents[1] / "custom_components" / "snmp_switch_manager"


def _load():
    pkg = types.ModuleType("ssm_stagger_pkg")
    pkg.__path__ = [str(PKG)]
    sys.modules["ssm_stagger_pkg"] = pkg
    for name in ("const", "stagger"):
        spec = importlib.util.spec_from_file_location(f"ssm_stagger_pkg.{name}", PKG / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
    return sys.modules["ssm_stagger_pkg.stagger"]


stagger = _load()


@pytest.mark.parametrize("now", [0.0, 7.3, 59.9, 123456.789])
def test_four_switches_land_a_quarter_of_the_interval_apart(now):
    phases = [(now + stagger.slot_delay(now, 60.0, i, 4)) % 60.0 for i in range(4)]
    assert phases == pytest.approx([0.0, 15.0, 30.0, 45.0], abs=1e-6)
    assert all(0 <= stagger.slot_delay(now, 60.0, i, 4) < 60.0 for i in range(4))


def test_a_reloaded_switch_goes_back_to_its_own_slot():
    """The slot is on the loop clock, not relative to setup: reloading switch 2
    at any moment still puts it at 30 s past the minute."""
    for reloaded_at in (1000.0, 1017.4, 1044.9):
        delay = stagger.slot_delay(reloaded_at, 60.0, 2, 4)
        assert (reloaded_at + delay) % 60.0 == pytest.approx(30.0, abs=1e-6)


class _Entry:
    def __init__(self, entry_id, disabled_by=None):
        self.entry_id, self.disabled_by, self.title = entry_id, disabled_by, entry_id
        self.unloads, self.tasks = [], []

    def async_on_unload(self, func):
        self.unloads.append(func)

    def async_create_background_task(self, hass, coro, name):
        self.tasks.append(name)
        coro.close()


def _hass(entries, now=100.0):
    return SimpleNamespace(
        config_entries=SimpleNamespace(async_entries=lambda domain: entries),
        loop=SimpleNamespace(time=lambda: now),
    )


def _coordinator(seconds=60):
    async def _refresh():
        return None

    return SimpleNamespace(
        update_interval=None if seconds is None else timedelta(seconds=seconds),
        async_refresh=_refresh,
    )


def test_each_switch_schedules_one_refresh_for_its_slot(monkeypatch):
    scheduled = []

    def fake_call_later(hass, delay, action):
        scheduled.append((delay, action))
        return lambda: None

    monkeypatch.setattr(stagger, "async_call_later", fake_call_later)
    entries = [_Entry(e) for e in ("d", "b", "a", "c")] + [_Entry("z", disabled_by="user")]
    hass = _hass(entries, now=100.0)
    delays = {e.entry_id: stagger.async_stagger_switch(hass, e, _coordinator()) for e in entries[:4]}
    # Sorted a, b, c, d -> slots 0, 15, 30, 45 s past the loop-clock minute; 100 s is 40 s past.
    assert delays == pytest.approx({"a": 20.0, "b": 35.0, "c": 50.0, "d": 5.0})
    assert all(len(e.unloads) == 1 for e in entries[:4])      # cancelled if unloaded first
    scheduled[0][1](None)                                       # the timer fires
    assert entries[0].tasks == ["snmp_switch_manager stagger d"]


def test_nothing_to_spread(monkeypatch):
    monkeypatch.setattr(stagger, "async_call_later", lambda *a: pytest.fail("must not schedule"))
    one = _Entry("a")
    assert stagger.async_stagger_switch(_hass([one]), one, _coordinator()) is None
    two = [_Entry("a"), _Entry("b")]
    assert stagger.async_stagger_switch(_hass(two), two[0], _coordinator(None)) is None
