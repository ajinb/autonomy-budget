"""E4: what adjudication latency does to detection latency (§7, v0.3).

The budget acts on adjudicated outcomes, and adjudication lags reality. Two
questions, separated on purpose:

  1. A CONSTANT lag L translates the burn process the budget sees by exactly
     L, so every threshold crossing — and therefore detection — should shift
     by exactly L, per seed, not just on average. (Constant-lag runs consume
     an identical RNG stream to the lag-0 baseline, so this is checkable
     seed-by-seed.)
  2. A JITTERED lag at the same mean is a different animal: spreading
     verdicts in time smears the burst concentration the fast-burn window
     alerts on, so detection should fall back from fast-burn to window
     exhaustion — later, by more than the mean lag.

Setup mirrors E2: silent step degradation p 0.01 -> 0.30, phase jittered
across a 30 d review period, 0.5 incidents/h, 20 seeds.

Usage: python examples/adjudication_study.py
"""

import statistics
import sys

sys.path.insert(0, "src")

from autonomy_budget.sim import SimParams, Operator, run_sim, REGIME_AEB

SEEDS = range(20)
REVIEW_CADENCE = 720
HORIZON = 4400  # slack for the longest lag row
RATE = 0.5

ROWS = [
    ("0 (baseline)",            0.0,   0.0),
    ("24 h constant",           24.0,  0.0),
    ("72 h constant",           72.0,  0.0),
    ("168 h constant",          168.0, 0.0),
    ("72 h jittered (sd~26 h)", 72.0,  0.35),
    ("72 h jittered (sd~68 h)", 72.0,  0.75),
]


def latencies(lag, jitter, fast_burn=True):
    """Detection latency per seed; fast_burn=False disables the fast-burn
    alert (multiplier -> effectively infinite) so the residual latency
    isolates window exhaustion as the only detector."""
    out = {}
    for s in SEEDS:
        step_at = 720 + (s * 36) % REVIEW_CADENCE
        op = Operator(0.01, step_at=step_at, step_to=0.30)
        r = run_sim(op, REGIME_AEB,
                    SimParams(seed=s, horizon=HORIZON, incident_rate=RATE,
                              adjudication_lag=lag, adjudication_lag_jitter=jitter,
                              fast_burn_multiplier=10.0 if fast_burn else 1e9))
        out[s] = r.detection_latency
    return out


def main():
    print("=" * 78)
    print("E4 — detection latency vs adjudication lag (step p 0.01 -> 0.30, "
          f"{RATE} incidents/h, 20 seeds)")
    print("=" * 78)
    base = latencies(0.0, 0.0)
    base_mean = statistics.mean([v for v in base.values() if v is not None])
    print(f"{'adjudication lag':<26}{'detected':>9}{'full AEB (h)':>15}"
          f"{'exhaustion-only':>17}{'per-seed shift vs baseline':>28}")
    print("-" * 96)
    for label, lag, jitter in ROWS:
        lats = base if (lag == 0 and jitter == 0) else latencies(lag, jitter)
        noburst = latencies(lag, jitter, fast_burn=False)
        got = [v for v in lats.values() if v is not None]
        m = statistics.mean(got)
        sd = statistics.stdev(got) if len(got) > 1 else 0.0
        nb = [v for v in noburst.values() if v is not None]
        nbm = statistics.mean(nb)
        nbsd = statistics.stdev(nb) if len(nb) > 1 else 0.0
        if jitter == 0 and lag > 0:
            shifts = sorted((lats[s] - base[s])
                            for s in SEEDS if lats[s] is not None and base[s] is not None)
            n_exact = sum(1 for d in shifts if d == lag - 1)
            detail = f"{n_exact}/20 at exactly +{lag - 1:.0f}; outliers {[d for d in shifts if d != lag - 1]}"
        else:
            detail = f"mean {m - base_mean:+.0f}"
        # Per-seed fast-burn advantage: how much earlier the full budget
        # detects than exhaustion alone. Zero means the fast-burn alert
        # contributed nothing for that seed.
        adv = [noburst[s] - lats[s] for s in SEEDS
               if lats[s] is not None and noburst[s] is not None]
        fb_dead = sum(1 for a in adv if a <= 0)
        q = sorted(got)
        p50, p90, worst = q[len(q) // 2], q[int(len(q) * 0.9)], q[-1]
        print(f"{label:<26}{len(got):>6}/20{m:>10.0f} ±{sd:<4.0f}"
              f"{nbm:>11.0f} ±{nbsd:<5.0f}{detail:>28}")
        print(f"{'':<26}{'':>9}  p50/p90/max {p50:.0f}/{p90:.0f}/{worst:.0f} h"
              f"   fast-burn advantage {statistics.mean(adv):.0f} h mean, "
              f"dead in {fb_dead}/20 seeds")


if __name__ == "__main__":
    main()
