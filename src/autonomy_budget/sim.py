"""Simulation of governance regimes for the paper's §7 study.

One tick = one hour. Incidents arrive stochastically; the operator proposes
one action per incident, wrong with probability given by its (possibly
time-varying) trajectory. Blast radius is drawn from a three-class mix
(minor 0.2 / moderate 1.0 / major 5.0). Costs: harm accrues when a wrong
action executes; toil accrues for human review (supervised / gated actions)
or full manual handling (advisory, disabled).

Regimes:
  REGIME_STATIC -- authority frozen at deployment (the status quo).
  REGIME_GATE   -- per-action gating only: major-class actions always
                   require approval; no longitudinal adjustment.
  REGIME_AEB    -- per-action gate + Autonomy Error Budget / Authority
                   Ladder (the paper's proposal, composed via the min rule).
"""

import random
from collections import deque
from dataclasses import dataclass, field

from .budget import AutonomyBudget
from .ladder import AuthorityLadder, DISABLED, ADVISORY, SUPERVISED, AUTONOMOUS

REGIME_STATIC = "static"
REGIME_GATE = "gate"
REGIME_AEB = "aeb"
REGIME_ORACLE = "oracle"  # full-knowledge cost floor for the study

SEVERITY_CLASSES = ((0.70, 0.2), (0.25, 1.0), (0.05, 5.0))  # (probability, weight)
EXPECTED_SEVERITY = sum(p * w for p, w in SEVERITY_CLASSES)
MAJOR_WEIGHT = 5.0


@dataclass
class SimParams:
    horizon: int = 2160                # ticks (hours); 90 days default
    incident_rate: float = 0.5         # incidents per tick
    seed: int = 0
    review_toil: float = 0.02          # cost of one human review
    manual_toil: float = 0.3           # cost of humans handling one incident
    catch_prob: float = 0.9            # human catches a wrong proposal
    adjudication_noise: float = 0.0    # SLI mislabel probability
    slo_miss: float = 0.03             # autonomy SLO miss rate (1 - SLO)
    allowance: float | None = None     # harm units / window; None = SLO-derived
    window: int = 720                  # budget window (30 days)
    fast_burn_window: int = 24
    fast_burn_multiplier: float = 10.0
    promotion_window: int = 720        # healthy time + dwell required to promote
    require_evidence: bool = True
    evidence_window: int = 720
    evidence_threshold: float = 0.97   # trailing concordance required to promote
    evidence_min: int = 50             # minimum adjudicated proposals


@dataclass
class Operator:
    base_rate: float
    step_at: int | None = None         # silent model update: rate steps at this tick
    step_to: float | None = None
    drift_to: float | None = None      # context rot: linear drift over the horizon

    def wrong_rate(self, t, horizon):
        if self.step_at is not None and t >= self.step_at:
            return self.step_to
        if self.drift_to is not None:
            return self.base_rate + (self.drift_to - self.base_rate) * (t / horizon)
        return self.base_rate


@dataclass
class SimResult:
    harm: float = 0.0
    toil: float = 0.0
    transitions: list = field(default_factory=list)
    detection_latency: int | None = None
    taa: float = 0.0                   # time-at-appropriate-authority
    rung_time: dict = field(default_factory=dict)

    @property
    def total_cost(self):
        return self.harm + self.toil


def derived_allowance(params):
    """Budget allowance = (1 - SLO) x expected weighted action volume per window.

    Denominating the allowance in expected volume is load-bearing: a fixed
    absolute allowance makes the same per-action reliability exhaust the
    budget N x faster at N x the action volume.
    """
    if params.allowance is not None:
        return params.allowance
    return params.slo_miss * params.incident_rate * params.window * EXPECTED_SEVERITY


def oracle_rung(p, params):
    """Rung a full-knowledge oracle assigns for true wrong-action rate p."""
    costs = {
        AUTONOMOUS: p * EXPECTED_SEVERITY,
        SUPERVISED: params.review_toil + p * (1 - params.catch_prob) * EXPECTED_SEVERITY,
        ADVISORY: params.manual_toil,
    }
    # min cost; ties resolve to the higher (cheaper-to-run) rung
    return max((rung for rung in costs), key=lambda r: (-costs[r], r))


def _draw_severity(rng):
    x, acc = rng.random(), 0.0
    for prob, weight in SEVERITY_CLASSES:
        acc += prob
        if x < acc:
            return weight
    return SEVERITY_CLASSES[-1][1]


def _incident_count(rng, rate):
    n = int(rate)
    if rng.random() < rate - n:
        n += 1
    return n


def run_sim(op, regime, params, static_rung=AUTONOMOUS):
    rng = random.Random(params.seed)
    res = SimResult()
    budget = AutonomyBudget(derived_allowance(params), params.window,
                            params.fast_burn_window, params.fast_burn_multiplier)
    ladder = AuthorityLadder(budget, initial_rung=AUTONOMOUS,
                             promotion_window=params.promotion_window,
                             require_evidence=params.require_evidence)
    evidence = deque()  # (t, observed_good) adjudicated proposals
    incident_ticks = 0
    appropriate_ticks = 0

    def adjudicate(wrong):
        if params.adjudication_noise and rng.random() < params.adjudication_noise:
            return not wrong
        return wrong

    def supervised_handle(t, wrong, sev):
        """Human reviews the proposal; uncaught wrong proposals execute.

        Supervised-mode wrongness enters the evidence stream (gating
        promotion), NOT the budget: the executing authority is the human,
        and burning human-approved actions creates a demotion spiral in
        which the budget can never recover at any rung below autonomous.
        """
        res.toil += params.review_toil
        caught = wrong and rng.random() < params.catch_prob
        observed_wrong = adjudicate(wrong)  # one verdict per action
        if wrong and not caught:
            res.harm += sev
        evidence.append((t, not observed_wrong))

    def autonomous_handle(t, wrong, sev, gated):
        if gated and sev == MAJOR_WEIGHT:
            supervised_handle(t, wrong, sev)
            return
        if wrong:
            res.harm += sev
        observed_wrong = adjudicate(wrong)
        if observed_wrong:
            budget.record_wrong_action(t, sev)
        else:
            budget.record_correct_action(t)
        evidence.append((t, not observed_wrong))

    for t in range(params.horizon):
        p = op.wrong_rate(t, params.horizon)

        if regime == REGIME_AEB:
            while evidence and evidence[0][0] <= t - params.evidence_window:
                evidence.popleft()
            good = sum(1 for _, g in evidence if g)
            evidence_ok = (len(evidence) >= params.evidence_min
                           and good / len(evidence) >= params.evidence_threshold)
            rung = ladder.tick(t, evidence_ok)
        elif regime == REGIME_GATE:
            rung = AUTONOMOUS
        elif regime == REGIME_ORACLE:
            rung = oracle_rung(p, params)
        else:
            rung = static_rung

        res.rung_time[rung] = res.rung_time.get(rung, 0) + 1

        for _ in range(_incident_count(rng, params.incident_rate)):
            incident_ticks += 1
            if rung == oracle_rung(p, params):
                appropriate_ticks += 1
            wrong = rng.random() < p
            sev = _draw_severity(rng)
            if rung == AUTONOMOUS:
                gated = regime in (REGIME_GATE, REGIME_AEB)
                autonomous_handle(t, wrong, sev, gated)
            elif rung == SUPERVISED:
                supervised_handle(t, wrong, sev)
            else:  # ADVISORY / DISABLED: humans handle; operator shadows for evidence
                res.toil += params.manual_toil
                evidence.append((t, not adjudicate(wrong)))

    res.transitions = list(ladder.transitions)
    if op.step_at is not None:
        demotions = [tt for (tt, old, new) in res.transitions
                     if new < old and tt >= op.step_at]
        res.detection_latency = (demotions[0] - op.step_at) if demotions else None
    res.taa = appropriate_ticks / incident_ticks if incident_ticks else 0.0
    return res
