"""Authority Ladder: asymmetric fast-down/slow-up authority state machine (paper §5)."""

from autonomy_budget.budget import AutonomyBudget
from autonomy_budget.ladder import AuthorityLadder, AUTONOMOUS, SUPERVISED, ADVISORY, DISABLED


def make(rung=AUTONOMOUS, allowance=10.0, promotion_window=720, require_evidence=True):
    b = AutonomyBudget(allowance=allowance, window=720, fast_burn_window=24, fast_burn_multiplier=10.0)
    lad = AuthorityLadder(budget=b, initial_rung=rung, promotion_window=promotion_window,
                          require_evidence=require_evidence)
    return b, lad


def test_starts_at_initial_rung():
    _, lad = make(rung=SUPERVISED)
    assert lad.rung == SUPERVISED


def test_demotes_one_rung_on_fast_burn_alert():
    b, lad = make(rung=AUTONOMOUS)
    b.record_wrong_action(t=100, severity=5.0)  # >> 10x nominal in fast window
    lad.tick(now=100, evidence_ok=False)
    assert lad.rung == SUPERVISED


def test_demotes_on_budget_exhaustion_and_keeps_demoting_while_burning():
    b, lad = make(rung=AUTONOMOUS, allowance=2.0)
    b.record_wrong_action(t=50, severity=3.0)
    lad.tick(now=50, evidence_ok=False)
    assert lad.rung == SUPERVISED
    # quiet interval: still exhausted, but no new demotion without a new burn edge
    lad.tick(now=120, evidence_ok=False)
    assert lad.rung == SUPERVISED
    # a further wrong action while exhausted drives it down again
    b.record_wrong_action(t=200, severity=3.0)
    lad.tick(now=200, evidence_ok=False)
    assert lad.rung == ADVISORY


def test_demotion_floor_is_disabled():
    b, lad = make(rung=ADVISORY, allowance=1.0)
    b.record_wrong_action(t=10, severity=5.0)
    lad.tick(now=10, evidence_ok=False)
    lad.tick(now=11, evidence_ok=False)
    assert lad.rung == DISABLED
    lad.tick(now=12, evidence_ok=False)
    assert lad.rung == DISABLED


def test_no_promotion_before_healthy_window_elapses():
    _, lad = make(rung=SUPERVISED, promotion_window=720)
    for t in range(0, 700, 100):
        lad.tick(now=t, evidence_ok=True)
    assert lad.rung == SUPERVISED


def test_promotes_after_healthy_window_with_evidence():
    _, lad = make(rung=SUPERVISED, promotion_window=100)
    lad.tick(now=200, evidence_ok=True)
    assert lad.rung == AUTONOMOUS


def test_no_promotion_without_evidence_even_when_healthy():
    _, lad = make(rung=SUPERVISED, promotion_window=100, require_evidence=True)
    lad.tick(now=500, evidence_ok=False)
    assert lad.rung == SUPERVISED


def test_promotion_requires_dwell_time_since_last_transition():
    b, lad = make(rung=AUTONOMOUS, promotion_window=100)
    # fast-burn demotion at t=200, but budget itself stays healthy
    b.record_wrong_action(t=200, severity=5.0)
    lad.tick(now=200, evidence_ok=True)
    assert lad.rung == SUPERVISED
    # immediately after, budget healthy_for is long -- must NOT bounce right back
    lad.tick(now=201, evidence_ok=True)
    assert lad.rung == SUPERVISED
    # after dwell + healthy window it may return
    lad.tick(now=320, evidence_ok=True)
    assert lad.rung == AUTONOMOUS


def test_ceiling_is_autonomous():
    _, lad = make(rung=AUTONOMOUS, promotion_window=10)
    lad.tick(now=100, evidence_ok=True)
    assert lad.rung == AUTONOMOUS


def test_transition_log_records_moves():
    b, lad = make(rung=AUTONOMOUS)
    b.record_wrong_action(t=100, severity=5.0)
    lad.tick(now=100, evidence_ok=False)
    assert lad.transitions == [(100, AUTONOMOUS, SUPERVISED)]
