"""
Dispatcher — decides when to create a new payload order on a corridor.

Each simulated tick, the dispatcher samples from a non-homogeneous Poisson
process (NHPP) whose arrival rate λ(t) is modulated by time-of-day to match
real food-delivery demand patterns:

  - Off-peak baseline: 10 % of peak λ
  - Breakfast peak  (~ 08:00): 40 % of peak λ
  - Lunch peak      (~ 12:30): 100 % of peak λ
  - Afternoon snack (~ 15:30): 30 % of peak λ
  - Dinner peak     (~ 19:00): 100 % of peak λ

``lambda_per_sim_s`` is the peak (maximum) arrival rate.  At each tick the
effective rate is  λ(t) = lambda_per_sim_s × demand_multiplier(sim_hour).

This replaces the original flat-λ stub that ran at peak rate all day and put
the system under permanent stress, causing slow but persistent queue drift.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, List

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

    def tick(self, dt_sim_s: float, sim_hour: float = 12.0) -> List[DispatchRequest]:
        """
        Generate payload order requests for this time step.

        Uses a non-homogeneous Poisson process: the effective arrival rate is
        ``lambda_per_sim_s × demand_multiplier(sim_hour)``.  This means demand
        naturally troughs overnight and peaks at lunch/dinner, matching the
        M/G/k sizing assumptions (which were calibrated to the peak rate only).

        Parameters
        ----------
        dt_sim_s : float
            Length of this tick in simulated seconds.
        sim_hour : float
            Current simulated hour in [0, 24).  Defaults to noon if not supplied.

        Returns a list of new order requests (may be empty).
        """
        lambda_t = self.lambda_per_sim_s * self._demand_multiplier(sim_hour)
        expected = lambda_t * dt_sim_s + self._leftover
        n_arrivals = int(expected)
        self._leftover = expected - n_arrivals

        # Stochastic rounding: carry the fractional arrival probabilistically.
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

    @staticmethod
    def _demand_multiplier(hour: float) -> float:
        """
        Return a scale factor ∈ [0.10, 1.00] representing relative demand at
        the given hour.

        The envelope is built from four Gaussian-shaped meal-time windows
        (matching the RL observation features) plus a flat off-peak baseline.
        Peak λ is reached at lunch (~12:30) and dinner (~19:00).

        Why this shape?
            Food-delivery platforms see ~10× swing between 3 AM and peak dinner.
            Running at constant peak-rate all day is equivalent to assuming
            customers order as frequently at midnight as at 7 PM, which leads
            to permanent fleet stress and slow but persistent queue drift.
        """
        base       = 0.10
        breakfast  = max(0.0, 1.0 - abs(hour -  8.0) / 1.0) * 0.40
        lunch      = max(0.0, 1.0 - abs(hour - 12.5) / 1.5) * 1.00
        snack      = max(0.0, 1.0 - abs(hour - 15.5) / 1.0) * 0.30
        dinner     = max(0.0, 1.0 - abs(hour - 19.0) / 1.5) * 1.00
        return base + max(breakfast, lunch, snack, dinner)

    def _pick_corridor(self) -> "ScoredCorridor.__class__":  # returns Corridor
        sc = random.choices(self.shortlist, weights=self._weights, k=1)[0]
        return sc.corridor


__all__ = ["DispatchRequest", "Dispatcher"]
