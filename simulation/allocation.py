"""Shared integer allocation helpers for fleet and rebalancing logic."""

from __future__ import annotations

from math import floor
from typing import Dict, Mapping, TypeVar

KeyT = TypeVar("KeyT")


def allocate_proportional_integers(
    weights: Mapping[KeyT, float],
    total_units: int,
    *,
    min_per_key: int = 0,
) -> Dict[KeyT, int]:
    """
    Allocate an exact integer total proportionally using largest remainders.

    `min_per_key` reserves a minimum integer allocation for every key before
    proportional distribution is applied to the remainder.
    """
    if not weights:
        raise ValueError("weights cannot be empty")
    if total_units < 0:
        raise ValueError("total_units must be non-negative")
    if min_per_key < 0:
        raise ValueError("min_per_key must be non-negative")

    keys = list(weights)
    required_minimum = min_per_key * len(keys)
    if total_units < required_minimum:
        raise ValueError(
            f"total_units={total_units} is too small for min_per_key={min_per_key} "
            f"across {len(keys)} keys"
        )

    totals: Dict[KeyT, int] = {key: min_per_key for key in keys}
    remaining = total_units - required_minimum
    if remaining == 0:
        return totals

    total_weight = sum(float(weight) for weight in weights.values())
    if total_weight <= 0:
        raise ValueError("weights must sum to a positive value")

    exact = {
        key: (float(weight) / total_weight) * remaining
        for key, weight in weights.items()
    }
    base = {key: floor(value) for key, value in exact.items()}
    remainder = remaining - sum(base.values())

    ranked = sorted(
        keys,
        key=lambda key: (exact[key] - base[key], float(weights[key])),
        reverse=True,
    )
    for key in ranked[:remainder]:
        base[key] += 1

    for key in keys:
        totals[key] += base[key]

    if sum(totals.values()) != total_units:
        raise AssertionError("allocated integers did not sum to total_units")

    return totals


__all__ = ["allocate_proportional_integers"]
