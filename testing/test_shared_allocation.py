"""Tests for the shared integer-allocation helper."""

from __future__ import annotations

from simulation.allocation import allocate_proportional_integers
from simulation.rebalancing import allocate_targets_from_weights


def test_shared_allocator_matches_rebalancing_wrapper():
    weights = {1: 4.0, 2: 3.0, 3: 1.0}
    expected = allocate_proportional_integers(weights, total_units=13, min_per_key=1)
    observed = allocate_targets_from_weights(weights, total_units=13, min_per_hub=1)
    assert observed == expected


def test_shared_allocator_preserves_exact_total():
    allocation = allocate_proportional_integers({1: 2.0, 2: 1.0}, total_units=5)
    assert allocation == {1: 3, 2: 2}
    assert sum(allocation.values()) == 5
