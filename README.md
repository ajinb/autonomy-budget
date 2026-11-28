# autonomy-budget

Reference implementation and simulation study for **["Error Budgets for Autonomy:
SLO-Driven Authority Management for Autonomous AI Operators"](https://cloudandsre.com/research/error-budgets-for-autonomy/)** (Ajin Baby, 2026).

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

## E4: adjudication latency (v0.3)

The budget acts on adjudicated outcomes, and adjudication lags reality.
`examples/adjudication_study.py` measures what the lag costs (`adjudication_lag`
/ `adjudication_lag_jitter` on `SimParams`):

- a **constant** lag translates detection latency by **exactly the lag**,
  seed-for-seed (constant-lag runs consume an identical RNG stream to lag-0
  runs, so this is checked per seed, not on average), and the fast-burn
  alert's ~40 h advantage over window exhaustion survives intact;
- a **jittered** pipeline at the same 72 h mean: v0.3 reported a 15% median
  and 36% spread penalty from 20 seeds. At 400 seeds neither holds (see
  Errata below).

## Errata (paper v0.3.1)

`examples/errata_v0_3_1.py` reproduces every number in the paper's v0.3.1
correction against this unchanged simulator (about two minutes):

1. The E4 jitter effects on median, p90 and spread are not distinguishable
   from zero at 400 seeds.
2. `derived_allowance()` denominates the allowance over all actions, including
   the major class the per-action gate routes to review, so the budget is
   1.64x looser than its SLO. E1–E3 still confirm H1–H3 with the governed
   denomination; detection is about 2x faster than v0.3 reported.
3. A lag-0 verdict is applied after the tick's rung decision, a lagged one
   before it. Against a 1 h pipeline, constant lag L shifts detection by
   exactly L − 1 h in 400/400 seeds.
4. With 24–168 h of lag, in-flight verdicts push the ladder below supervised
   after the step in 42–98% of runs, at 3.5–6.6x the lag-0 cost.

```bash
.venv/bin/python examples/errata_v0_3_1.py
```

## Paper

This repository is the companion code for the preprint **[Error Budgets for Autonomy: SLO-Driven Authority Management for Autonomous AI Operators](https://cloudandsre.com/research/error-budgets-for-autonomy/)**
(Ajin Baby, September 2026, v0.3.1 with a correction dated 28 November 2026, not peer reviewed).
Full text: [PDF](https://ajinb.github.io/research/error-budgets-for-autonomy/error-budgets-for-autonomy.pdf) · [paper page](https://ajinb.github.io/research/error-budgets-for-autonomy/) ·
[all papers](https://ajinb.github.io/research/).

```bibtex
@techreport{baby2026error,
  title       = {Error Budgets for Autonomy: SLO-Driven Authority Management for Autonomous AI Operators},
  author      = {Ajin Baby},
  year        = {2026},
  institution = {cloudandsre.com},
  type        = {Preprint},
  url         = {https://cloudandsre.com/research/error-budgets-for-autonomy/}
}
```

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
  governance stays within 9% of the full-knowledge oracle at both extremes.
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

[Apache-2.0](LICENSE).
