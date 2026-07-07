"""Authority Ladder: the asymmetric fast-down/slow-up authority state machine.

Implements paper §5: demotion is immediate and mechanical (budget exhaustion
or fast-burn alert drops one rung, on the rising edge of the condition);
promotion is slow and evidence-gated (a full healthy window, affirmative
evidence at the target rung, and a dwell time since the last transition).
The asymmetry is hysteresis: it prevents authority oscillation under noisy
SLIs (evaluated as H3 in the paper's simulation study).
"""

DISABLED, ADVISORY, SUPERVISED, AUTONOMOUS = 0, 1, 2, 3
RUNG_NAMES = {0: "disabled", 1: "advisory", 2: "supervised", 3: "autonomous"}


class AuthorityLadder:
    def __init__(self, budget, initial_rung, promotion_window, require_evidence=True):
        self.budget = budget
        self.rung = initial_rung
        self.promotion_window = int(promotion_window)
        self.require_evidence = require_evidence
        self.transitions = []       # (t, from_rung, to_rung)
        self._last_transition = -1
        self._prev_exhausted = False
        self._prev_fast_alert = False

    def _move(self, now, to_rung):
        self.transitions.append((now, self.rung, to_rung))
        self.rung = to_rung
        self._last_transition = now

    def tick(self, now, evidence_ok):
        exhausted = self.budget.exhausted(now)
        fast_alert = self.budget.fast_burn_alert(now)
        demote = (exhausted and not self._prev_exhausted) or \
                 (fast_alert and not self._prev_fast_alert)
        self._prev_exhausted, self._prev_fast_alert = exhausted, fast_alert

        if demote and self.rung > DISABLED:
            self._move(now, self.rung - 1)
            return self.rung

        if (self.rung < AUTONOMOUS
                and self.budget.healthy_for(now) >= self.promotion_window
                and now - self._last_transition >= self.promotion_window
                and (evidence_ok or not self.require_evidence)):
            self._move(now, self.rung + 1)
        return self.rung
