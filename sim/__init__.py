"""Offline Bazaar (M6a/M6b): FakeGame with its own oracle, HTTP front on 127.0.0.1, faults, invariants and bots."""
from __future__ import annotations

from sim.world import FakeGame, VirtualClock, Model, deal_delta, venue_fee  # noqa: F401
