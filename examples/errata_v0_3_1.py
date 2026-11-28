"""Errata to paper v0.3 (published as v0.3.1): every number in the correction.

Runs against the unchanged v0.3 simulator. Four checks:

  1. E4 jitter at 400 seeds. v0.3 reported jittered-lag effects on the
     median, p90 and spread from 20 seeds. Re-run the identical setup at 400
     seeds with seed-paired bootstrap 95% CIs against the 72 h constant row.
  2. Allowance denomination. derived_allowance() sizes the allowance on the
     expected severity of ALL actions, but the per-action gate routes the
     major class to review, so those actions never reach the budget. Report
     the looseness factor, then re-run E1-E3 with the allowance denominated
     over the governed (non-major) volume only.
  3. Lag-0 delivery convention. A lag-0 verdict is applied after that tick's
     rung decision; a lagged verdict is applied before the decision on its
     due tick. Compare constant-lag runs against lag 1 instead of lag 0.
  4. Dead-time overshoot. With a constant lag, verdicts already in flight
     when the ladder demotes keep burning the budget. Count runs that fall
     below supervised after the step, and the cost relative to lag 0.

Usage: python examples/errata_v0_3_1.py [N_SEEDS]   (default 400; E1-E3 use 20)
"""

import random
import statistics
import sys

sys.path.insert(0, "src")

from autonomy_budget import sim
from autonomy_budget.ladder import SUPERVISED, AUTONOMOUS
from autonomy_budget.sim import (
    SimParams, Operator, run_sim, SEVERITY_CLASSES, MAJOR_WEIGHT, EXPECTED_SEVERITY,
    REGIME_STATIC, REGIME_GATE, REGIME_AEB, REGIME_ORACLE,
)

N = int(sys.argv[1]) if len(sys.argv) > 1 else 400
SEEDS = range(N)
PAPER_SEEDS = range(20)
CADENCE = 720
HORIZON = 4400
RATE = 0.5
BOOT = 2000


def q(xs, f):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * f))]


def step_op(s):
    return Operator(0.01, step_at=720 + (s * 36) % CADENCE, step_to=0.30)


def e4_run(s, lag, jitter=0.0, fast_burn=True):
    return run_sim(step_op(s), REGIME_AEB,
                   SimParams(seed=s, horizon=HORIZON, incident_rate=RATE,
                             adjudication_lag=lag, adjudication_lag_jitter=jitter,
                             fast_burn_multiplier=10.0 if fast_burn else 1e9))


def boot_ci(pairs, stat):
    rng = random.Random(0)
    vals = sorted(stat([pairs[rng.randrange(len(pairs))] for _ in pairs]) for _ in range(BOOT))
    return vals[int(0.025 * BOOT)], vals[int(0.975 * BOOT)]


# ---------------------------------------------------------------- check 1
def check_jitter():
    print("=" * 78)
    print(f"1. E4 jitter at {N} seeds (72 h mean lag; v0.3 used 20 seeds)")
    print("=" * 78)
    rows = [("72 h constant", 0.0), ("72 h jittered sd~26 h", 0.35), ("72 h jittered sd~68 h", 0.75)]
    full = {}
    for label, j in rows:
        f = {s: e4_run(s, 72.0, j).detection_latency for s in SEEDS}
        x = {s: e4_run(s, 72.0, j, fast_burn=False).detection_latency for s in SEEDS}
        full[label] = f
        got = [v for v in f.values() if v is not None]
        dead = sum(1 for s in SEEDS if f[s] is not None and x[s] is not None and x[s] - f[s] <= 0)
        print(f"  {label:<22} detected {len(got)}/{N}  mean {statistics.mean(got):6.1f}  "
              f"sd {statistics.stdev(got):5.1f}  p50 {q(got, .5):4.0f}  p90 {q(got, .9):4.0f}  "
              f"fast-burn adds nothing in {dead}/{N} ({100 * dead / N:.0f}%)")
    base = full["72 h constant"]
    stats = (
        ("mean", lambda p: statistics.mean(b for _, b in p) - statistics.mean(a for a, _ in p), "h"),
        ("median", lambda p: q([b for _, b in p], .5) / q([a for a, _ in p], .5) - 1, "%"),
        ("p90", lambda p: q([b for _, b in p], .9) / q([a for a, _ in p], .9) - 1, "%"),
        ("sd", lambda p: statistics.stdev(b for _, b in p) / statistics.stdev(a for a, _ in p) - 1, "%"),
    )
    for label, _ in rows[1:]:
        pairs = [(base[s], full[label][s]) for s in SEEDS
                 if base[s] is not None and full[label][s] is not None]
        parts = []
        for name, f, unit in stats:
            pt, (lo, hi) = f(pairs), boot_ci(pairs, f)
            if unit == "%":
                parts.append(f"{name} {100 * pt:+.1f}% [{100 * lo:+.1f}, {100 * hi:+.1f}]")
            else:
                parts.append(f"{name} {pt:+.1f} h [{lo:+.1f}, {hi:+.1f}]")
        print(f"  {label} vs constant: " + "; ".join(parts))


# ---------------------------------------------------------------- check 2
GOVERNED_SEVERITY = sum(p * w for p, w in SEVERITY_CLASSES if w != MAJOR_WEIGHT)


def governed_allowance(params):
    if params.allowance is not None:
        return params.allowance
    return params.slo_miss * params.incident_rate * params.window * GOVERNED_SEVERITY


def study(label):
    def cost(factory, regime, **kw):
        static = kw.pop("static_rung", AUTONOMOUS)
        rs = [run_sim(factory(s), regime, SimParams(seed=s, **kw), static_rung=static) for s in PAPER_SEEDS]
        return statistics.mean(r.total_cost for r in rs)

    print(f"\n  [{label}]")
    arch = {
        "reliable": lambda s: Operator(0.01),
        "borderline": lambda s: Operator(0.05),
        "drifting": lambda s: Operator(0.01, drift_to=0.15),
        "step": lambda s: Operator(0.01, step_at=720, step_to=0.30),
        "unreliable": lambda s: Operator(0.20),
    }
    print("  E1 total cost   static-auto  static-sup   gate    AEB   oracle  AEB/oracle")
    for name, f in arch.items():
        c = [cost(f, REGIME_STATIC, static_rung=AUTONOMOUS), cost(f, REGIME_STATIC, static_rung=SUPERVISED),
             cost(f, REGIME_GATE), cost(f, REGIME_AEB), cost(f, REGIME_ORACLE)]
        print(f"  {name:<14}" + "".join(f"{v:>9.1f}" for v in c) + f"{c[3] / c[4]:>10.2f}")
    print("  E2 detection (h)  rate  mean  p50   speedup vs 378 h review")
    for rate in (0.1, 0.5, 2.0):
        lat = [run_sim(step_op(s), REGIME_AEB, SimParams(seed=s, horizon=4000, incident_rate=rate)).detection_latency
               for s in PAPER_SEEDS]
        got = [v for v in lat if v is not None]
        print(f"  {'':<16}{rate:>5}{statistics.mean(got):>6.0f}{q(got, .5):>5.0f}   "
              f"{378 / statistics.mean(got):.1f}x  ({len(got)}/20 detected)")
    print("  E3 (p=0.045, 2% noise)   transitions  harm   total")
    for vlabel, kw in (("asymmetric", dict(promotion_window=720, require_evidence=True)),
                       ("symmetric", dict(promotion_window=72, require_evidence=False))):
        rs = [run_sim(Operator(0.045), REGIME_AEB,
                      SimParams(seed=s, horizon=4320, adjudication_noise=0.02, **kw)) for s in PAPER_SEEDS]
        print(f"  {vlabel:<24}{statistics.mean(len(r.transitions) for r in rs):>9.1f}"
              f"{statistics.mean(r.harm for r in rs):>8.1f}{statistics.mean(r.total_cost for r in rs):>8.1f}")


def check_denomination():
    print("\n" + "=" * 78)
    print("2. Allowance denomination")
    print("=" * 78)
    print(f"  E[severity] all actions {EXPECTED_SEVERITY:.2f}; governed (non-major) {GOVERNED_SEVERITY:.2f}; "
          f"v0.3 allowance is {EXPECTED_SEVERITY / GOVERNED_SEVERITY:.2f}x the governed SLO")
    original = sim.derived_allowance
    study("v0.3 denomination (as published)")
    sim.derived_allowance = governed_allowance
    try:
        study("governed-volume denomination")
    finally:
        sim.derived_allowance = original


# ---------------------------------------------------------------- checks 3 + 4
def check_delivery_and_overshoot():
    print("\n" + "=" * 78)
    print(f"3. Lag-0 delivery convention and 4. dead-time overshoot ({N} seeds)")
    print("=" * 78)
    lags = (0.0, 1.0, 24.0, 72.0, 168.0)
    runs = {lag: {s: e4_run(s, lag) for s in SEEDS} for lag in lags}
    for lag in lags[2:]:
        vs0 = sum(1 for s in SEEDS if runs[lag][s].detection_latency - runs[0.0][s].detection_latency == lag - 1)
        vs1 = sum(1 for s in SEEDS if runs[lag][s].detection_latency - runs[1.0][s].detection_latency == lag - 1)
        print(f"  {lag:>5.0f} h lag: shift exactly L-1 vs lag 0 in {vs0}/{N}; vs lag 1 in {vs1}/{N}")
    base_cost = statistics.mean(r.total_cost for r in runs[0.0].values())
    for lag in lags:
        below = 0
        for s, r in runs[lag].items():
            step_at = 720 + (s * 36) % CADENCE
            if any(new < SUPERVISED and t >= step_at for (t, _, new) in r.transitions):
                below += 1
        c = statistics.mean(r.total_cost for r in runs[lag].values())
        print(f"  {lag:>5.0f} h lag: falls below supervised after the step in {below}/{N} "
              f"({100 * below / N:.0f}%); total cost {c:.1f} ({c / base_cost:.2f}x lag 0)")


if __name__ == "__main__":
    check_jitter()
    check_denomination()
    check_delivery_and_overshoot()
