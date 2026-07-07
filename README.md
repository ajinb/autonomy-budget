# autonomy-budget

Reference implementation and simulation study for **"Error Budgets for Autonomy:
SLO-Driven Authority Management for Autonomous AI Operators"** (Ajin Baby, 2026).

AI operators are being granted standing authority over production
infrastructure. This library transplants SRE error-budget semantics onto that
authority:

- **`AutonomyBudget`** — a blast-radius-weighted error budget: wrong actions
  burn budget in proportion to realized severity over a rolling window, with
  fast-burn alerting and evidence-invalidating events (model/prompt updates)
  that reset the health streak.
- **`AuthorityLadder`** — the asymmetric fast-down/slow-up authority state
  machine (autonomous → supervised → advisory → disabled): demotion is
  immediate and mechanical on budget exhaustion or fast-burn; promotion
  requires a full healthy window, a dwell time, and affirmative concordance
  evidence.
- **`sim`** — the paper's §7 study: governance regimes (static tier,
  per-action gating, AEB + ladder, full-knowledge oracle) over operator
  populations with step degradations (silent model updates) and gradual
  drifts (context rot).

## Run the study

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest            # 30 tests
.venv/bin/python examples/paper_study.py
```

## Headline results (20 seeds/cell)

- **Static tiers are U-shaped; the budget tracks the oracle at both ends.**
  Static-autonomous costs 3.9x the budget-governed regime under a silent step
  degradation; static-supervised costs 3.9x under a reliable operator. AEB
  governance stays within ~8% of the full-knowledge oracle at both extremes.
- **Burn-rate demotion detects silent degradation 2.7–5.1x faster than
  monthly track-record review** (20/20 detected), with latency set by action
  volume and budget geometry rather than review cadence.
- **The fast-down/slow-up asymmetry is load-bearing:** a symmetric (fast-up)
  ladder oscillates under 2% adjudication noise (16 vs 1.4 transitions) and
  more than doubles realized harm.

Two design rules the simulation surfaced (§4/§5 of the paper):

1. **Denominate the allowance in expected action volume** (`(1 − SLO) ×
   volume × expected severity`), or the same per-action reliability exhausts
   a fixed budget N× faster at N× traffic.
2. **Supervised-mode wrongness enters the evidence stream, not the budget.**
   The executing authority for an approved action is the human; burning
   human-approved executions creates a demotion spiral in which the budget
   can never recover at any rung below autonomous.

MIT license.
