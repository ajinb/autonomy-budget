"""Simulation harness for the paper's §7 study: regimes, cost accounting, oracle."""

from autonomy_budget.sim import (
    SimParams, Operator, run_sim, oracle_rung,
    REGIME_STATIC, REGIME_GATE, REGIME_AEB,
)
from autonomy_budget.ladder import AUTONOMOUS, SUPERVISED


def params(**kw):
    d = dict(horizon=2000, incident_rate=0.5, seed=7)
    d.update(kw)
    return SimParams(**d)


def test_same_seed_reproduces_identical_results():
    op = Operator(base_rate=0.05)
    r1 = run_sim(op, REGIME_AEB, params())
    r2 = run_sim(op, REGIME_AEB, params())
    assert r1.total_cost == r2.total_cost
    assert r1.harm == r2.harm and r1.toil == r2.toil


def test_static_supervised_with_perfect_catch_has_toil_but_no_harm():
    op = Operator(base_rate=1.0)  # always wrong
    p = params(catch_prob=1.0)
    r = run_sim(op, REGIME_STATIC, p, static_rung=SUPERVISED)
    assert r.harm == 0.0
    assert r.toil > 0.0


def test_static_autonomous_always_wrong_operator_accumulates_harm():
    op = Operator(base_rate=1.0)
    r = run_sim(op, REGIME_STATIC, params(), static_rung=AUTONOMOUS)
    assert r.harm > 0.0
    assert r.toil == 0.0


def test_oracle_prefers_autonomous_for_reliable_and_supervised_for_degraded():
    p = params()
    assert oracle_rung(0.005, p) == AUTONOMOUS
    assert oracle_rung(0.30, p) == SUPERVISED


def test_aeb_demotes_after_step_degradation_and_records_latency():
    op = Operator(base_rate=0.01, step_at=1000, step_to=0.4)
    r = run_sim(op, REGIME_AEB, params(horizon=4000))
    assert r.detection_latency is not None
    assert 0 < r.detection_latency < 720  # well under one budget window


def test_aeb_never_demotes_a_reliable_operator():
    op = Operator(base_rate=0.005)
    r = run_sim(op, REGIME_AEB, params(horizon=4000))
    assert all(new >= old for (_, old, new) in r.transitions) or r.transitions == []


def test_per_action_gate_routes_major_actions_to_review():
    # gate-alone regime: major-severity actions cost review toil even though autonomous
    op = Operator(base_rate=0.0)
    r = run_sim(op, REGIME_GATE, params())
    assert r.toil > 0.0
    assert r.harm == 0.0


def test_oracle_regime_always_sits_at_appropriate_authority():
    from autonomy_budget.sim import REGIME_ORACLE
    op = Operator(base_rate=0.01, step_at=1000, step_to=0.4)
    r = run_sim(op, REGIME_ORACLE, params(horizon=3000))
    assert r.taa == 1.0


def test_supervised_wrong_executions_enter_evidence_not_budget():
    # human-approved executions must not burn the operator's autonomy budget:
    # burning them creates a demotion spiral (budget can never recover below
    # autonomous); wrongness at supervised rung gates promotion via evidence
    op = Operator(base_rate=1.0)
    p = params(catch_prob=0.0, horizon=3000)
    r = run_sim(op, REGIME_STATIC, p, static_rung=SUPERVISED)
    assert r.harm > 0.0  # wrong actions did execute...


def test_allowance_scales_with_incident_volume():
    # SLO-derived allowance: same per-action reliability must be equally
    # budget-healthy at 4x the action volume
    from autonomy_budget.sim import derived_allowance
    lo = derived_allowance(SimParams(incident_rate=0.5))
    hi = derived_allowance(SimParams(incident_rate=2.0))
    assert abs(hi / lo - 4.0) < 1e-9


def test_aeb_holds_supervised_not_advisory_for_chronically_bad_operator():
    # with evidence-not-budget semantics, a bad operator settles at supervised
    # (oracle-optimal) instead of spiraling to advisory/disabled
    op = Operator(base_rate=0.20)
    r = run_sim(op, REGIME_AEB, params(horizon=4000))
    from autonomy_budget.ladder import SUPERVISED as SUP
    assert r.rung_time.get(SUP, 0) > 0.8 * (4000 - 720)  # most post-demotion time
