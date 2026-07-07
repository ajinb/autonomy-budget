"""Autonomy Error Budget (AEB): blast-radius-weighted burn over a rolling window (paper §4)."""

from autonomy_budget.budget import AutonomyBudget


def make_budget(**kw):
    defaults = dict(allowance=10.0, window=720, fast_burn_window=24, fast_burn_multiplier=10.0)
    defaults.update(kw)
    return AutonomyBudget(**defaults)


def test_new_budget_is_healthy_with_full_allowance():
    b = make_budget()
    assert b.remaining(now=0) == 10.0
    assert not b.exhausted(now=0)


def test_wrong_action_burns_in_proportion_to_severity_not_count():
    b = make_budget()
    b.record_wrong_action(t=1, severity=3.0)
    b.record_wrong_action(t=2, severity=0.5)
    assert b.remaining(now=3) == 10.0 - 3.5


def test_correct_actions_burn_nothing():
    b = make_budget()
    b.record_correct_action(t=1)
    assert b.remaining(now=2) == 10.0


def test_budget_exhausts_when_burn_exceeds_allowance():
    b = make_budget(allowance=2.0)
    b.record_wrong_action(t=1, severity=2.5)
    assert b.exhausted(now=2)


def test_burn_ages_out_of_rolling_window():
    b = make_budget(window=100)
    b.record_wrong_action(t=0, severity=5.0)
    assert b.remaining(now=50) == 5.0
    assert b.remaining(now=101) == 10.0  # t=0 event outside (now-window, now]


def test_fast_burn_alert_fires_when_short_window_burn_exceeds_multiplier():
    # nominal rate = allowance/window = 10/720; over fast window of 24 ticks
    # nominal fast-window burn = 24 * 10/720 = 0.333; 10x threshold = 3.33
    b = make_budget()
    b.record_wrong_action(t=100, severity=4.0)
    assert b.fast_burn_alert(now=101)


def test_no_fast_burn_alert_at_nominal_burn():
    b = make_budget()
    b.record_wrong_action(t=100, severity=0.2)
    assert not b.fast_burn_alert(now=101)


def test_healthy_since_tracks_uninterrupted_health_streak():
    b = make_budget(allowance=2.0, window=100)
    b.record_wrong_action(t=10, severity=2.5)  # exhausted at t=10
    assert b.exhausted(now=11)
    # event ages out at t=110; exhausted through tick 109, healthy from 110
    assert not b.exhausted(now=111)
    assert b.healthy_for(now=150) == 150 - 109


def test_partial_reset_on_evidence_invalidating_event():
    # model/prompt update: healthy history no longer funds authority (paper §4.4)
    b = make_budget(window=100)
    b.record_wrong_action(t=10, severity=1.0)
    b.evidence_invalidating_event(t=50)
    assert b.healthy_for(now=60) <= 10
