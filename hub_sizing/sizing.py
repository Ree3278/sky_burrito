"""
Apply M/G/k to each active hub in the corridor shortlist.

Produces a per-hub sizing report:
  - Minimum pad count k to keep P(craning) ≤ 5%
  - Pad utilisation at that k
  - What P(craning) would be with one fewer pad (urgency of the last pad)
  - Battery bay count (equal to k — one bay per pad)
  - Tier classification: LIGHT / MODERATE / HEAVY based on offered load

Output
------
list of HubSizingResult, sorted by offered load descending (busiest hubs first).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, TYPE_CHECKING

from .demand import estimate_demand, HubDemand
from .service import ServiceSpec, default_service_spec
from .mgk import solve_k, MGKResult

if TYPE_CHECKING:
    from corridor_pruning.pruning import ScoredCorridor

# One battery bay per landing pad (simplest configuration)
BATTERY_BAYS_PER_PAD: int = 1

# Hub tier thresholds (offered load a = λ × E[S])
TIER_HEAVY_A    = 2.0
TIER_MODERATE_A = 1.0


@dataclass
class HubSizingResult:
    hub_id: int
    lambda_per_hour: float
    offered_load: float         # Erlangs
    k_pads: int                 # landing pads
    k_bays: int                 # battery bays
    utilisation_pct: float
    p_cran_pct: float           # P(craning) with k pads
    p_cran_minus1_pct: float    # P(craning) one pad short
    tier: str                   # LIGHT / MODERATE / HEAVY
    binding_constraint: str
    service_spec: ServiceSpec
    is_stub: bool = True

    def __str__(self):
        stub_flag = " [stub]" if self.is_stub else ""
        return (
            f"Hub {self.hub_id:2d}  λ={self.lambda_per_hour:5.1f}/hr  "
            f"a={self.offered_load:.2f} E  "
            f"k={self.k_pads} pads + {self.k_bays} bays  "
            f"ρ={self.utilisation_pct:.0f}%  "
            f"P(cran)={self.p_cran_pct:.1f}%  "
            f"[{self.tier}]{stub_flag}"
        )


def _tier(offered_load: float) -> str:
    if offered_load >= TIER_HEAVY_A:
        return "HEAVY"
    if offered_load >= TIER_MODERATE_A:
        return "MODERATE"
    return "LIGHT"


def size_hubs(
    shortlist: "List[ScoredCorridor]",
    service_spec: ServiceSpec = None,
) -> List[HubSizingResult]:
    """
    Size every active hub in the shortlist using M/G/k queuing.

    Parameters
    ----------
    shortlist : list of ScoredCorridor
        Output of corridor_pruning.prune_corridors().
    service_spec : ServiceSpec, optional
        Pad service time parameters. Defaults to manual kiosk spec.

    Returns
    -------
    list of HubSizingResult, sorted by offered load descending.
    """
    if service_spec is None:
        service_spec = default_service_spec()

    demands: Dict[int, HubDemand] = estimate_demand(shortlist)
    results: List[HubSizingResult] = []

    for hub_id, demand in demands.items():
        mgk: MGKResult = solve_k(
            hub_id          = hub_id,
            lambda_per_min  = demand.lambda_per_min,
            mean_service_min= service_spec.mean_min,
            cv_squared      = service_spec.cv_squared,
        )

        results.append(HubSizingResult(
            hub_id              = hub_id,
            lambda_per_hour     = demand.lambda_per_hour,
            offered_load        = mgk.offered_load,
            k_pads              = mgk.k,
            k_bays              = mgk.k * BATTERY_BAYS_PER_PAD,
            utilisation_pct     = mgk.utilisation * 100,
            p_cran_pct          = mgk.p_cran * 100,
            p_cran_minus1_pct   = mgk.p_cran_k_minus_1 * 100,
            tier                = _tier(mgk.offered_load),
            binding_constraint  = mgk.binding_constraint,
            service_spec        = service_spec,
            is_stub             = demand.is_stub or service_spec.is_stub,
        ))

    results.sort(key=lambda r: r.offered_load, reverse=True)
    _print_report(results, service_spec)
    return results


def _print_report(results: List[HubSizingResult], spec: ServiceSpec) -> None:
    stub_flag = " [ALL STUBS — see hub_sizing/demand.py + service.py]" if any(r.is_stub for r in results) else ""

    print(f"\n{'='*80}")
    print(f"  M/G/k HUB SIZING REPORT{stub_flag}")
    print(f"  Service spec: E[S]={spec.mean_s:.0f}s ({spec.mean_min:.1f} min)  "
          f"c_s²={spec.cv_squared}  P(cran) target ≤ 5%  util cap ≤ 85%")
    print(f"{'='*80}")
    print(f"  {'Hub':<6} {'λ/hr':>6} {'Load(E)':>8} {'Pads':>5} {'Bays':>5} "
          f"{'Util%':>6} {'P(cran)%':>9} {'@k-1%':>7} {'Tier':<10} {'Binding'}")
    print(f"  {'-'*78}")

    for r in results:
        print(
            f"  Hub {r.hub_id:<2}  "
            f"{r.lambda_per_hour:>6.1f}  "
            f"{r.offered_load:>8.2f}  "
            f"{r.k_pads:>5}  "
            f"{r.k_bays:>5}  "
            f"{r.utilisation_pct:>6.1f}  "
            f"{r.p_cran_pct:>8.1f}  "
            f"{r.p_cran_minus1_pct:>7.1f}  "
            f"{r.tier:<10}  "
            f"{r.binding_constraint}"
        )

    total_pads = sum(r.k_pads for r in results)
    total_bays = sum(r.k_bays for r in results)

    print(f"  {'-'*78}")
    print(f"  NETWORK TOTAL:  {total_pads} landing pads  +  {total_bays} battery bays")
    print()

    heavy   = [r for r in results if r.tier == "HEAVY"]
    moderate= [r for r in results if r.tier == "MODERATE"]
    light   = [r for r in results if r.tier == "LIGHT"]

    if heavy:
        print(f"  🔴 HEAVY hubs (≥2 E):  {', '.join(f'Hub {r.hub_id}' for r in heavy)}")
        print(f"     → Priority build-out. P(cran) drops sharply if one pad is unavailable.")
    if moderate:
        print(f"  🟡 MODERATE hubs (1–2 E): {', '.join(f'Hub {r.hub_id}' for r in moderate)}")
    if light:
        print(f"  🟢 LIGHT hubs (<1 E):  {', '.join(f'Hub {r.hub_id}' for r in light)}")
        print(f"     → Single pad may suffice; second pad is insurance only.")

    print(f"\n  Key: P(@k-1%) = craning probability if you remove one pad — shows")
    print(f"       how much that last pad is worth. Jump from 5% → 40%+ = critical pad.")
    print(f"{'='*80}\n")
