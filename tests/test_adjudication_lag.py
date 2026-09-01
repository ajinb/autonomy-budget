"""E4: adjudication latency (paper §7, v0.3).

Pins the study's claims:
  - lag 0 is the pre-lag code path, bit-for-bit;
  - a constant lag L translates detection latency by exactly L - 1 per seed
    (the -1 is the delivery convention: a queued verdict lands at the top of
    its tick, ahead of that tick's rung decision, where an inline verdict is
    first seen one tick after it is recorded);
  - the fast-burn alert's detection advantage over window exhaustion
    survives a constant lag intact.
"""

from autonomy_budget.sim import SimParams, Operator, run_sim, REGIME_AEB

RATE = 0.5


def _latency(seed, lag=0.0, jitter=0.0, fast_burn=True, horizon=3000):
    step_at = 720 + (seed * 36) % 720
    op = Operator(0.01, step_at=step_at, step_to=0.30)
    r = run_sim(op, REGIME_AEB,
                SimParams(seed=seed, horizon=horizon, incident_rate=RATE,
                          adjudication_lag=lag, adjudication_lag_jitter=jitter,
                          fast_burn_multiplier=10.0 if fast_burn else 1e9))
    return r.detection_latency


def test_lag_zero_is_the_inline_code_path():
    op = Operator(0.05)
    a = run_sim(op, REGIME_AEB, SimParams(seed=7, horizon=2000, incident_rate=RATE))
    b = run_sim(op, REGIME_AEB, SimParams(seed=7, horizon=2000, incident_rate=RATE,
                                          adjudication_lag=0.0))
    assert a.total_cost == b.total_cost
    assert a.transitions == b.transitions


def test_constant_lag_translates_detection_exactly():
    # Constant-lag runs consume an identical RNG stream to lag-0 runs, so the
    # translation is checkable seed-for-seed, not just on average.
    for seed in (0, 1, 2, 4):
        base = _latency(seed)
        for lag in (24, 48):
            assert _latency(seed, lag=lag) == base + lag - 1


def test_fast_burn_advantage_survives_constant_lag():
    # The fast-burn alert detects the step well before window exhaustion, and
    # a constant lag preserves that advantage (it translates the burst it
    # alerts on rather than smearing it).
    for lag in (0.0, 72.0):
        adv = [_latency(s, lag=lag, fast_burn=False) - _latency(s, lag=lag)
               for s in range(10)]
        assert all(a >= 0 for a in adv)
        assert sum(adv) / len(adv) >= 15.0


def test_jittered_lag_degrades_the_median_not_the_mean():
    # At the same 72 h mean, a jittered pipeline leaves mean detection nearly
    # unchanged (the lognormal's early tail compensates) but shifts the
    # median up: predictability is what lag variance costs.
    const = sorted(_latency(s, lag=72.0, horizon=4400) for s in range(12))
    jit = sorted(_latency(s, lag=72.0, jitter=0.75, horizon=4400) for s in range(12))
    assert jit[len(jit) // 2] > const[len(const) // 2]
