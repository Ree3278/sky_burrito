"""
Dispatcher — decides when to create a new payload order on a corridor.

Each simulated tick, the dispatcher samples from a Poisson process at the
aggregate λ for the current sim-time window and assigns the order to a
corridor weighted by demand_weight.

This is the stub NHPP: λ is held flat at the peak rate for the entire
sim window. A real NHPP would vary λ(t) by 15-minute bucket.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from corridor_pruning.pruning import ScoredCorridor

if TYPE_CHECKING:
    from corridor_pruning.corridors import Corridor


@dataclass(frozen=True)
class DispatchRequest:
    """A payload order that needs a physical drone assignment."""

    request_id: int
    corridor: "Corridor"

    @property
    def origin_hub_id(self) -> int:
        return self.corridor.origin.id

    @property
    def destination_hub_id(self) -> int:
        return self.corridor.destination.id


# Global counter for unique request IDs
_request_counter = 0


def _next_id() -> int:
    global _request_counter
    _request_counter += 1
    return _request_counter


class Dispatcher:
    """
    Creates payload order requests on shortlisted corridors according to demand weights.

    Parameters
    ----------
    shortlist : list of ScoredCorridor
    lambda_per_sim_s : float
        Total network arrival rate in orders per simulation-second.
        Derived from hub_sizing demand (200 orders/hr → 200/3600 ≈ 0.056/s).
    cruise_altitude_m : float
        Passed through to launched Drone objects downstream.
    """

    def __init__(
        self,
        shortlist: "List[ScoredCorridor]",
        lambda_per_sim_s: float = 200 / 3600,
        cruise_altitude_m: float = 120.0,
    ):
        self.shortlist = shortlist
        self.lambda_per_sim_s = lambda_per_sim_s
        self.cruise_altitude_m = cruise_altitude_m

        # Precompute normalised weights for weighted-random corridor selection
        total_w = sum(sc.demand_weight for sc in shortlist)
        self._weights = [sc.demand_weight / total_w for sc in shortlist]

        self._leftover: float = 0.0   # fractional arrivals carried over between ticks

    def tick(self, dt_sim_s: float) -> List[DispatchRequest]:
        """
        Generate payload order requests for this time step.

        Uses a Poisson approximation: expected arrivals = λ × dt.
        For small dt, P(≥1 arrival) ≈ λ × dt, so we draw from Poisson(λ × dt).

        Returns a list of new order requests (may be empty).
        """
        expected = self.lambda_per_sim_s * dt_sim_s + self._leftover
        n_arrivals = int(expected)
        self._leftover = expected - n_arrivals

        # Stochastic rounding: spawn the fractional drone probabilistically
        if random.random() < self._leftover:
            n_arrivals += 1
            self._leftover = 0.0

        new_requests: List[DispatchRequest] = []
        for _ in range(n_arrivals):
            corridor = self._pick_corridor()
            request = DispatchRequest(
                request_id=_next_id(),
                corridor=corridor,
            )
            new_requests.append(request)

        return new_requests

    def _pick_corridor(self) -> "ScoredCorridor.__class__":  # returns Corridor
        sc = random.choices(self.shortlist, weights=self._weights, k=1)[0]
        return sc.corridor


__all__ = ["DispatchRequest", "Dispatcher"]
