"""The paper's §7 simulation study: three experiments, 20 seeds per cell.

E1/H1  Total cost by governance regime across operator archetypes
       (static tiers are U-shaped; AEB tracks the oracle at both ends).
E2/H2  Detection latency for a silent step degradation: AEB burn-rate
       demotion vs periodic human review, across incident volumes.
E3/H3  Asymmetric vs symmetric ladder transitions under noisy SLIs
       (fast-up variants oscillate and cost more).

Run:  python examples/paper_study.py
"""

import statistics
import sys

sys.path.insert(0, "src")

from autonomy_budget.ladder import RUNG_NAMES, SUPERVISED, AUTONOMOUS
from autonomy_budget.sim import (
    SimParams, Operator, run_sim,
    REGIME_STATIC, REGIME_GATE, REGIME_AEB, REGIME_ORACLE,
)

SEEDS = range(20)
REVIEW_CADENCE = 720  # periodic-review baseline: monthly (30 d) track-record review


def cells(op_factory, regime, seeds=SEEDS, static_rung=AUTONOMOUS, **param_kw):
    out = []
    for s in seeds:
        p = SimParams(seed=s, **param_kw)
        out.append(run_sim(op_factory(s), regime, p, static_rung=static_rung))
    return out


def ms(values):
    return statistics.mean(values), (statistics.stdev(values) if len(values) > 1 else 0.0)


def fmt(values, w=7):
    m, s = ms(values)
    return f"{m:{w}.1f} ±{s:5.1f}"


def experiment_1():
    print("=" * 78)
    print("E1/H1 — total cost by regime across operator archetypes")
    print(f"       (horizon 2160 h = 90 d, 0.5 incidents/h, 20 seeds/cell)")
    print("=" * 78)
    archetypes = {
        "reliable (p=0.01)":            lambda s: Operator(0.01),
        "borderline (p=0.05)":          lambda s: Operator(0.05),
        "drifting (0.01→0.15)":         lambda s: Operator(0.01, drift_to=0.15),
        "step-degrading (0.01→0.30)":   lambda s: Operator(0.01, step_at=720, step_to=0.30),
        "unreliable (p=0.20)":          lambda s: Operator(0.20),
    }
    regimes = [
        ("static-autonomous", REGIME_STATIC, dict(static_rung=AUTONOMOUS)),
        ("static-supervised", REGIME_STATIC, dict(static_rung=SUPERVISED)),
        ("per-action gate",   REGIME_GATE,   {}),
        ("AEB + ladder",      REGIME_AEB,    {}),
        ("oracle",            REGIME_ORACLE, {}),
    ]
    header = f"{'operator':<28}" + "".join(f"{name:>16}" for name, _, _ in regimes)
    print(header)
    print("-" * len(header))
    taa_rows = []
    for arch_name, factory in archetypes.items():
        row, taa_row = f"{arch_name:<28}", f"{arch_name:<28}"
        for _, regime, kw in regimes:
            rs = cells(factory, regime, **kw)
            m, s = ms([r.total_cost for r in rs])
            row += f"{m:>10.1f} ±{s:4.1f}"
            tm, _ = ms([r.taa for r in rs])
            taa_row += f"{tm:>16.2f}"
        print(row)
        taa_rows.append(taa_row)
    print("\ntime-at-appropriate-authority (fraction of incident decisions)")
    print("-" * len(header))
    for r in taa_rows:
        print(r)


def experiment_2():
    print("\n" + "=" * 78)
    print("E2/H2 — detection latency for a silent step degradation (p 0.01 → 0.30)")
    print("       AEB burn-rate/exhaustion demotion vs periodic review (30 d cadence)")
    print("       step time jittered uniformly across one review period per seed")
    print("=" * 78)
    print(f"{'incidents/h':>12} {'AEB latency (h)':>22} {'periodic review (h)':>22} {'speedup':>9}")
    print("-" * 70)
    for rate in (0.1, 0.5, 2.0):
        aeb_lat, rev_lat = [], []
        for s in SEEDS:
            step_at = 720 + (s * 36) % REVIEW_CADENCE  # jitter phase over the cadence
            op = Operator(0.01, step_at=step_at, step_to=0.30)
            r = run_sim(op, REGIME_AEB, SimParams(seed=s, horizon=4000, incident_rate=rate))
            if r.detection_latency is not None:
                aeb_lat.append(r.detection_latency)
            # periodic review detects at the first review after the step
            next_review = ((step_at // REVIEW_CADENCE) + 1) * REVIEW_CADENCE
            rev_lat.append(next_review - step_at)
        detected = f"{len(aeb_lat)}/20"
        am, asd = ms(aeb_lat) if aeb_lat else (float('nan'), 0)
        rm, _ = ms(rev_lat)
        print(f"{rate:>12} {am:>14.0f} ±{asd:<5.0f} {rm:>18.0f} {rm/am:>8.1f}x   (detected {detected})")


def experiment_3():
    print("\n" + "=" * 78)
    print("E3/H3 — asymmetric vs symmetric (fast-up) ladder under noisy SLIs")
    print("       borderline operator p=0.045, adjudication noise 2%,")
    print("       horizon 4320 h = 180 d; symmetric: 72 h promotion, no evidence gate")
    print("=" * 78)
    variants = [
        ("asymmetric (720 h + evidence)", dict(promotion_window=720, require_evidence=True)),
        ("symmetric fast-up (72 h)",      dict(promotion_window=72, require_evidence=False)),
    ]
    for label, kw in variants:
        rs = cells(lambda s: Operator(0.045), REGIME_AEB,
                   horizon=4320, adjudication_noise=0.02, **kw)
        trans = [len(r.transitions) for r in rs]
        harm = [r.harm for r in rs]
        total = [r.total_cost for r in rs]
        auto_share = [r.rung_time.get(AUTONOMOUS, 0) / 4320 for r in rs]
        print(f"\n{label}")
        print(f"  transitions: {fmt(trans)}   harm: {fmt(harm)}   "
              f"total cost: {fmt(total)}   time autonomous: {ms(auto_share)[0]:.2f}")
    # same comparison for the step-degrading operator: symmetric re-promotes into damage
    print("\nstep-degrading operator (0.01 → 0.30 at t=1440) under the same variants:")
    for label, kw in variants:
        rs = cells(lambda s: Operator(0.01, step_at=1440, step_to=0.30), REGIME_AEB,
                   horizon=4320, adjudication_noise=0.02, **kw)
        trans = [len(r.transitions) for r in rs]
        harm = [r.harm for r in rs]
        total = [r.total_cost for r in rs]
        print(f"  {label:<32} transitions: {fmt(trans, 5)}  harm: {fmt(harm)}  total: {fmt(total)}")


if __name__ == "__main__":
    experiment_1()
    experiment_2()
    experiment_3()
