"""GETBULK walks against a simulated agent: same rows as GETNEXT, far fewer requests.

Loads snmp_compat on its own (the package __init__ needs Home Assistant) and
swaps pysnmp's bulk_cmd / next_cmd for an in-memory agent, so these run with
nothing on the network.
"""
import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1] / "custom_components" / "snmp_switch_manager"


def _load():
    pkg = types.ModuleType("ssm_pkg")
    pkg.__path__ = [str(PKG)]
    sys.modules["ssm_pkg"] = pkg
    for name in ("const", "snmp_compat"):
        spec = importlib.util.spec_from_file_location(f"ssm_pkg.{name}", PKG / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
    return sys.modules["ssm_pkg.snmp_compat"]


compat = _load()


class EndOfMibView:  # the class NAME is what the walk checks, as with pysnmp's
    pass


class Agent:
    """A sorted MIB and the request behaviour of the agents met in practice."""

    def __init__(self, mib, *, too_big_above=None, truncate_to=None, no_bulk=False, stuck_after=None):
        self.mib = sorted(mib.items(), key=lambda kv: tuple(int(x) for x in kv[0].split(".")))
        self.too_big_above, self.truncate_to = too_big_above, truncate_to
        self.no_bulk, self.stuck_after = no_bulk, stuck_after
        self.bulk_requests = self.next_requests = 0

    def _after(self, oid):
        key = tuple(int(x) for x in oid.split("."))
        for o, v in self.mib:
            if tuple(int(x) for x in o.split(".")) > key:
                if self.stuck_after and o > self.stuck_after:
                    return self.stuck_after, "again"      # never advances past this point
                return o, v
        return oid, EndOfMibView()

    async def bulk(self, _e, _c, _t, _x, non_rep, reps, *objs, **_k):
        self.bulk_requests += 1
        if self.no_bulk or (self.too_big_above and reps * len(objs) > self.too_big_above):
            return None, 1, 0, []                         # errStat tooBig / genErr
        cols = [str(o[0]) for o in objs]
        out = []
        for _ in range(reps):
            row = []
            for i, cur in enumerate(cols):
                oid, val = self._after(cur)
                row.append((oid, val))
                cols[i] = oid
            out.extend(row)
        if self.truncate_to is not None:
            out = out[: self.truncate_to]                  # cut mid-row, as agents do
        return None, 0, 0, out

    async def next(self, _e, _c, _t, _x, obj, **_k):
        self.next_requests += 1
        return None, 0, 0, [self._after(str(obj[0]))]


def _objs(monkeypatch, agent):
    monkeypatch.setattr(compat, "bulk_cmd", agent.bulk)
    monkeypatch.setattr(compat, "next_cmd", agent.next)
    monkeypatch.setattr(compat, "ObjectIdentity", lambda oid: oid)
    monkeypatch.setattr(compat, "ObjectType", lambda ident: (ident,))


class Engine:
    pass


IF = "1.3.6.1.2.1.2.2.1"


def _iftable(ports=188):
    mib = {}
    for col in (5, 7, 8):
        for i in range(1, ports + 1):
            mib[f"{IF}.{col}.{i}"] = col * 1000 + i
    for i in range(1, ports + 1):
        mib[f"1.3.6.1.2.1.31.1.1.1.15.{i}"] = 1000
    mib[f"{IF}.10.1"] = "a neighbouring column: .10 must not leak into a walk of .1"
    mib[f"{IF}.1.1"] = 1
    return mib


def walk(bases, engine=None):
    return asyncio.run(compat._do_bulk_walk(engine or Engine(), None, None, None, bases))


def slow(bases):
    """The same MIB walked one row per request: the reference answer."""
    out = {}
    for b in bases:
        out[b] = asyncio.run(compat._do_next_walk_one(Engine(), None, None, None, b))
    return out


COLS = [f"{IF}.7", f"{IF}.8", f"{IF}.5", "1.3.6.1.2.1.31.1.1.1.15"]


def test_same_rows_as_one_row_per_request_for_a_188_port_switch(monkeypatch):
    agent = Agent(_iftable())
    _objs(monkeypatch, agent)
    fast = walk(COLS)
    expected = slow(COLS)
    assert fast == expected and sum(len(v) for v in fast.values()) == 4 * 188
    assert agent.bulk_requests <= 13          # vs 756 GETNEXTs


def test_a_reply_cut_mid_row_loses_nothing(monkeypatch):
    agent = Agent(_iftable(), truncate_to=7)  # not a multiple of 4 columns
    _objs(monkeypatch, agent)
    assert walk(COLS) == slow(COLS)


def test_an_agent_that_says_toobig_is_asked_for_less_and_remembered(monkeypatch):
    agent = Agent(_iftable(), too_big_above=30)
    _objs(monkeypatch, agent)
    engine = Engine()
    assert walk(COLS, engine) == slow(COLS)
    assert engine._ssm_bulk_budget <= 30 and not getattr(engine, "_ssm_no_bulk", False)
    before = agent.bulk_requests
    walk(COLS, engine)
    per_walk = agent.bulk_requests - before
    assert per_walk <= 4 * 188 // 28 + 2      # the learned size is used straight away, no refusals


def test_an_agent_without_getbulk_is_walked_the_old_way_and_not_asked_again(monkeypatch):
    agent = Agent(_iftable(), no_bulk=True)
    _objs(monkeypatch, agent)
    engine = Engine()
    assert walk(COLS, engine) == slow(COLS)
    assert engine._ssm_no_bulk is True
    before = agent.bulk_requests
    walk(COLS, engine)
    assert agent.bulk_requests == before      # it has learned


def test_the_end_of_the_mib_ends_the_walk(monkeypatch):
    agent = Agent({"1.3.6.1.9.1": 1, "1.3.6.1.9.2": 2})   # the walked subtree is the last in the MIB
    _objs(monkeypatch, agent)
    assert walk(["1.3.6.1.9"]) == {"1.3.6.1.9": [("1.3.6.1.9.1", 1), ("1.3.6.1.9.2", 2)]}


def test_a_neighbouring_subtree_is_not_taken_along(monkeypatch):
    """The old walk matched with startswith(base) and no dot, so walking .1
    would also have taken .10 had .2 to .9 been missing."""
    agent = Agent({f"{IF}.1.1": 1, f"{IF}.10.1": "neighbour"})
    _objs(monkeypatch, agent)
    assert walk([f"{IF}.1"]) == {f"{IF}.1": [(f"{IF}.1.1", 1)]}


def test_an_agent_that_stops_advancing_cannot_loop_the_walk(monkeypatch):
    agent = Agent({f"{IF}.7.{i}": i for i in range(1, 50)}, stuck_after=f"{IF}.7.20")
    _objs(monkeypatch, agent)
    rows = walk([f"{IF}.7"])[f"{IF}.7"]
    assert [o for o, _ in rows][-1] == f"{IF}.7.20" and agent.bulk_requests < 10


def test_columns_of_different_lengths_each_end_on_their_own(monkeypatch):
    mib = {f"{IF}.7.{i}": i for i in range(1, 100)}
    mib.update({f"{IF}.8.{i}": i for i in range(1, 4)})
    agent = Agent(mib)
    _objs(monkeypatch, agent)
    got = walk([f"{IF}.7", f"{IF}.8"])
    assert len(got[f"{IF}.7"]) == 99 and len(got[f"{IF}.8"]) == 3


def test_asking_for_the_same_base_twice_is_harmless(monkeypatch):
    agent = Agent(_iftable(3))
    _objs(monkeypatch, agent)
    got = asyncio.run(compat._do_bulk_walk(Engine(), None, None, None, [f"{IF}.7", f"{IF}.7"]))
    assert len(got[f"{IF}.7"]) == 3


def test_the_single_column_entry_point_keeps_its_old_name_and_shape(monkeypatch):
    agent = Agent(_iftable(5))
    _objs(monkeypatch, agent)
    rows = asyncio.run(compat._do_next_walk(Engine(), None, None, None, f"{IF}.8"))
    assert rows == [(f"{IF}.8.{i}", 8000 + i) for i in range(1, 6)]
