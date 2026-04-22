"""
M/G/k queuing model — Erlang-C core with Whitt's heavy-traffic approximation.

Model
-----
Arrivals   : Poisson at rate λ (the M)
Service    : General with mean E[S] and c_s² = Var[S]/E[S]² (the G)
Servers    : k identical landing pads (the k)

Key quantities
--------------
a  = λ × E[S]           Offered load (Erlangs) — total work arriving per unit time
ρ  = a / k              Per-pad utilisation     — must be < 1 for stable queue
C  = Erlang_C(k, a)     Probability a drone must WAIT (M/M/k exact)
P_cran ≈ C × (1 + c_s²) / 2   M/G/k P(wait) via Whitt (1992) approximation

We solve for the minimum k such that:
  (1) P_cran ≤ P_CRAN_TARGET   (default 5%)
  (2) ρ      ≤ UTIL_CAP        (default 85%)

Erlang-C implementation
-----------------------
Computed in log-space to stay numerically stable for large k.
Uses iterative summation rather than scipy to keep the module dependency-free.

References
----------
Whitt (1992) "Approximations for the GI/G/m queue" — Production and Operations Management
Erlang (1917) — original C formula
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from settings.hub_sizing import (
    MGK_MAX_K_SEARCH,
    MGK_P_CRAN_TARGET,
    MGK_UTIL_CAP,
)

# ── Targets ──────────────────────────────────────────────────────────────────

P_CRAN_TARGET: float = MGK_P_CRAN_TARGET
UTIL_CAP: float = MGK_UTIL_CAP
MAX_K_SEARCH: int = MGK_MAX_K_SEARCH


# ── Core Erlang-C ─────────────────────────────────────────────────────────────

def erlang_c(k: int, a: float) -> float:
    """
    Exact Erlang-C formula: P(arriving drone must wait) in an M/M/k queue.

    Parameters
    ----------
    k : int   number of servers (pads)
    a : float offered load = λ × E[S]  (must satisfy a < k for stability)

    Returns
    -------
    float in [0, 1]
    """
    if a <= 0:
        return 0.0
    rho = a / k
    if rho >= 1.0:
        return 1.0   # unstable — queue grows without bound

    # Log-space Poisson sum for the denominator terms n = 0 … k-1
    # log(a^n / n!) = n*log(a) - log(n!)
    log_a = math.log(a)
    log_terms = []
    log_factorial = 0.0
    for n in range(k):
        if n > 0:
            log_factorial += math.log(n)
        log_terms.append(n * log_a - log_factorial)

    # The k-th term × k/(k-a)
    log_factorial += math.log(k)
    log_kth = k * log_a - log_factorial + math.log(k) - math.log(k - a)

    # Numerator = kth term
    # Denominator = sum of all terms (0..k-1) + kth term
    max_log = max(max(log_terms), log_kth)
    num = math.exp(log_kth - max_log)
    den = sum(math.exp(t - max_log) for t in log_terms) + num

    return num / den


def mgk_p_wait(k: int, a: float, cv_squared: float) -> float:
    """
    M/G/k P(wait) via Whitt (1992) heavy-traffic approximation.

    P_wait(M/G/k) ≈ Erlang_C(k, a) × (1 + c_s²) / 2

    Exact when c_s² = 1 (exponential service = M/M/k).
    Conservative (upper bound) for c_s² < 1.
    """
    c_mm_k = erlang_c(k, a)
    return c_mm_k * (1.0 + cv_squared) / 2.0


# ── Solver ───────────────────────────────────────────────────────────────────

@dataclass
class MGKResult:
    hub_id: int
    lambda_per_min: float     # λ (arrivals per minute)
    mean_service_min: float   # E[S] in minutes
    cv_squared: float         # c_s²
    offered_load: float       # a = λ × E[S]
    k: int                    # recommended pad count
    utilisation: float        # ρ = a / k
    p_cran: float             # P(craning) with this k
    p_cran_k_minus_1: float   # P(craning) one pad short — shows urgency of the Nth pad
    binding_constraint: str   # "p_cran" or "utilisation"


def solve_k(
    hub_id: int,
    lambda_per_min: float,
    mean_service_min: float,
    cv_squared: float,
    p_cran_target: float = P_CRAN_TARGET,
    util_cap: float = UTIL_CAP,
) -> MGKResult:
    """
    Find the minimum k that satisfies both the craning probability and
    utilisation constraints.

    Parameters
    ----------
    hub_id         : int
    lambda_per_min : float   arrivals per minute at this hub (from demand.py)
    mean_service_min: float  E[S] in minutes (from service.py)
    cv_squared     : float   c_s² (from service.py)
    p_cran_target  : float   max P(craning), default 5%
    util_cap       : float   max pad utilisation, default 85%
    """
    a = lambda_per_min * mean_service_min   # offered load (Erlangs)

    # Minimum k for stability: a/k < 1, so k > a
    k_min = max(1, math.ceil(a) + 1)

    result_k: Optional[int] = None
    binding: str = "none"

    p_prev = 1.0   # P(craning) with k-1 pads, initialise to worst case

    for k in range(k_min, MAX_K_SEARCH + 1):
        rho    = a / k
        p_cran = mgk_p_wait(k, a, cv_squared)

        util_ok  = rho <= util_cap
        cran_ok  = p_cran <= p_cran_target

        if util_ok and cran_ok:
            result_k = k
            binding  = "p_cran" if p_cran >= rho / util_cap * p_cran_target else "utilisation"
            # Determine which constraint was binding at k-1
            if not (a / (k - 1) <= util_cap):
                binding = "utilisation"
            else:
                binding = "p_cran"
            break
        p_prev = p_cran

    if result_k is None:
        result_k = MAX_K_SEARCH   # capped — shouldn't happen with reasonable inputs

    final_rho    = a / result_k
    final_p_cran = mgk_p_wait(result_k, a, cv_squared)
    p_k_minus_1  = mgk_p_wait(result_k - 1, a, cv_squared) if result_k > 1 else 1.0

    return MGKResult(
        hub_id            = hub_id,
        lambda_per_min    = lambda_per_min,
        mean_service_min  = mean_service_min,
        cv_squared        = cv_squared,
        offered_load      = a,
        k                 = result_k,
        utilisation       = final_rho,
        p_cran            = final_p_cran,
        p_cran_k_minus_1  = p_k_minus_1,
        binding_constraint= binding,
    )
