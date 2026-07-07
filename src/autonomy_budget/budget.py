"""Autonomy Error Budget (AEB): blast-radius-weighted burn over a rolling window.

Implements paper §4: wrong actions burn budget in proportion to realized
severity (harm allowance, not error count); burn ages out of a rolling
window; fast-burn alerting compares short-window burn against a multiple
of the nominal rate; evidence-invalidating events (model/prompt updates)
reset the health streak that funds promotion.

Time is a monotonically non-decreasing integer tick supplied by the caller.
"""

from collections import deque


class AutonomyBudget:
    def __init__(self, allowance, window, fast_burn_window, fast_burn_multiplier):
        self.allowance = float(allowance)
        self.window = int(window)
        self.fast_burn_window = int(fast_burn_window)
        self.fast_burn_multiplier = float(fast_burn_multiplier)
        self._events = deque()       # (t, burn) within the rolling window
        self._fast_events = deque()  # (t, burn) within the fast-burn window
        self._window_burn = 0.0
        self._fast_burn = 0.0
        self._scanned = -1           # last tick health was evaluated
        self._last_unhealthy = -1    # last tick exhausted or invalidated

    # -- internal ---------------------------------------------------------

    def _prune(self, now):
        while self._events and self._events[0][0] <= now - self.window:
            self._window_burn -= self._events.popleft()[1]
        while self._fast_events and self._fast_events[0][0] <= now - self.fast_burn_window:
            self._fast_burn -= self._fast_events.popleft()[1]

    def _advance(self, now):
        """Advance the health scan tick by tick so streaks are exact."""
        for t in range(self._scanned + 1, now + 1):
            self._prune(t)
            if self._window_burn >= self.allowance:
                self._last_unhealthy = t
        self._scanned = max(self._scanned, now)

    # -- recording --------------------------------------------------------

    def record_wrong_action(self, t, severity):
        self._advance(t)
        self._events.append((t, float(severity)))
        self._fast_events.append((t, float(severity)))
        self._window_burn += severity
        self._fast_burn += severity
        if self._window_burn >= self.allowance:
            self._last_unhealthy = t

    def record_correct_action(self, t):
        self._advance(t)

    def evidence_invalidating_event(self, t):
        self._advance(t)
        self._last_unhealthy = t

    # -- queries ----------------------------------------------------------

    def remaining(self, now):
        self._advance(now)
        return self.allowance - self._window_burn

    def exhausted(self, now):
        return self.remaining(now) <= 0.0

    def fast_burn_alert(self, now):
        self._advance(now)
        nominal_fast = self.fast_burn_window * self.allowance / self.window
        return self._fast_burn >= self.fast_burn_multiplier * nominal_fast

    def healthy_for(self, now):
        self._advance(now)
        return now - self._last_unhealthy
