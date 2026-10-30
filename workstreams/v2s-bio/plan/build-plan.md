---
workstream: v2s-bio
artifact: build plan
builds_on: AND.md (approved per approvals row 22; revised in 604b416, filled in 6acf8a3) · PVR.md (CTO-signed per approvals row 21, R1–R24)
status: DRAFT — not grilled, not plan-gate signed
date: 2026-10-30
---

# Build plan — `/v2s:bio`

Every task has the same shape, per `/design`'s decomposition discipline:

> **files → failing test → minimal implementation → verify → commit**

No placeholders, no TODO stubs. Each task is independently verifiable, so a phase is provably complete. Every task carries `satisfies: R<n>` back to a standing requirement.

**On the "failing test" column.** It states *the behaviour the sealed test must assert* — it is the test-author's contract, not a test this plan authors. The sealed tree is written by an author that never sees the implementation, and read by a gate that re-runs it. The implementer never reads it; the `test-seal` hook enforces that half mechanically. A plan that specified sealed-test *contents* would quietly break the discipline it exists to build.

---

## The seal-ordering rule — stated once, as one rule

The CTO asked for this because three seals (predicate, plan, prediction) currently live implicitly across invariants 1, 2 and 6, and nothing states their relationship. It is one rule:

> **For any hypothesis H, all three seals precede H's first confirmatory measurement; the prediction seal precedes the predicate seal; and the predicate and plan seals are mutually blind — neither author may read the other's artifact, and their relative order is therefore unconstrained and must never be relied on.**

```
prediction_sealed_at ──▶ predicate_sealed_at ──┐
   world model              sealed analyst     │
   targets+expectation      targets+expectation├──▶ first confirmatory measurement
                                               │
                         plan_sealed_at ───────┘
                            experimenter
                            TARGETS ONLY  (R2 absolute, AD-7)
```

Two consequences a builder must not miss. **The prediction precedes the predicate** because the predicate formalises the prediction — an analyst writing a threshold the model never committed to is inventing the hypothesis, not testing it. **The predicate and plan are unordered** because ordering them would imply one waits on the other, and waiting is a channel: the register must reject any implementation whose correctness depends on which landed first.

---

## What the first run will NOT exercise — stated at the gate, not discovered after

The proof-of-value quest is protein stability / recombinant expression (A-23). Measured against ClawBio's `catalog.json`: **no entry mentions ESM, AlphaFold, stability, or variant effect.** `struct-predictor` is `maturity_tier: tested`, `status: planned`.

| requirement | built & unit-tested | exercised end-to-end by the PoV quest |
|---|---|---|
| **R18** maturity-tier probe | yes, T3.1 | **no** — the quest calls no ClawBio skill |
| **R23** soft-dependency degradation | yes, T3.1 | **no** — nothing to degrade from |
| R12 wet-lab seam | yes, T5.1 | **no, by design** — it must never execute |

No deliverable from the first run may imply these were proven in use. T3.1 includes the cheap partial the CTO offered: the probe reads `struct-predictor`'s tier even though the quest never calls it, exercising the probe path without pretending the quest exercised the dependency.

---

## Preconditions — both measured, both blocking Phase 1

**P1 — the `v2s` repo does not exist.** A-2 placed the plugin in a new standalone repo. Measured 2026-10-30: no path under `~/github/personal`, no worktree, no repo on `supmo668`. Tasks cannot name files in a repo that has none. T0.1 creates it and **is a principal gate** — creating a public repository is outward-facing and is not mine to do.

**P2 — the sealed-suite runner is unconfigured.** `tests.referee_command` is unset; the sealed directory is configured. v2r-loop's Stage 0 is explicit that a missing sealed-suite runner is a stop, because the gate *is* the loop. T0.3 wires it in the new repo. Until it exists no Phase 1 task can be verified, so no Phase 1 task may be claimed.

---

## Phase 0 — The floor

| # | task | files | the sealed test must fail first on | done when | satisfies |
|---|---|---|---|---|---|
| 0.1 | **Repo skeleton + marketplace manifest.** `v2s` plugin, skill `bio`, so the command is `/v2s:bio` | `.claude-plugin/marketplace.json`, `.claude-plugin/plugin.json`, `skills/bio/SKILL.md` | the resolved command name being anything other than exactly `v2s:bio` | the manifest parses and names one plugin `v2s` with skill `bio` | — (A-2) |
| 0.2 | **Hard dependency on `airdlc`, fails closed.** Version floor asserted against the installed plugin, never read from editable config | `v2s/deps.py` | absent `airdlc` not stopping Stage 0 by name; below-floor not stopping; **any fallback evaluator being constructible** | both conditions stop by name and no code path builds a substitute | **R16** |
| 0.3 | **Sealed-suite runner wired.** Referee command + sealed dir in the new repo | repo `config`, `tools/referee` shim | a suite that collects zero tests being reported as a pass | referee parses junit-xml and requires `tests>0, errors==0, skipped==0, passed>0` | **R4** (precondition) |

---

## Phase 1 — The trust core

Nothing above this phase can be trusted until it closes. Build it first.

| # | task | files | the sealed test must fail first on | done when | satisfies |
|---|---|---|---|---|---|
| 1.1 | **Predicate spec: parse + validate.** Declarative data; no code path | `v2s/predicate.py` | a predicate naming an unknown test being accepted at parse time | unknown test → `OPEN_INFEASIBLE` naming it; no `eval`, no import hook, no escape hatch | **R1 R4** |
| 1.2 | **Test library v1 — the four.** `threshold`, `paired_difference`, `rank_correlation`, `proportion`, each versioned | `v2s/tests_lib/` | each test having a mutant that flips its verdict and survives | four tests, four mutants killed, registry rejects a fifth name | **R4 R18** |
| 1.3 | **Static named-measurement proof — the keystone.** The register proves a predicate names ≥1 measurement *without executing it* | `v2s/register/static.py` | a predicate whose selector resolves nothing reaching evaluation at all | the proof is a pure function of the spec; a fixture where it would pass vacuously fails | **R4** |
| 1.4 | **Evaluation → verdict. Three outcomes and a HALT.** | `v2s/register/evaluate.py` | zero measurements read being reported as REFUTED rather than exit 3 | raising predicate → exit 3; ≥1 measurement → 0 or 1; the vacuous-refutation fixture **fails the suite** | **R3 R4** |
| 1.5 | **Seal hook: `sealed_at` is one-way.** Covers predicates and plans | `hooks/seal.py` | a write to a sealed path succeeding, or a sha mismatch not halting | enforced by hook, not convention; the hook's own absence is itself a HALT | **R1 R2** |
| 1.6 | **`verdict` has exactly one writer.** | `v2s/register/state.py` | an agent transcript asserting a verdict changing the register file | byte-identity after such a transcript; every other mutation path raises | **R3** |
| 1.7 | **Scope freezes at the gate.** | `v2s/register/scope.py` | a hypothesis being addable to an approved register, or a pass prompting instead of halting | no prompt path exists inside a drain | **R20** |

---

## Phase 2 — The blind join

| # | task | files | the sealed test must fail first on | done when | satisfies |
|---|---|---|---|---|---|
| 2.1 | **Plan spec: parse, validate, seal.** | `v2s/plan_spec.py` | a plan sealed after its first confirmatory record not halting | `plan_sealed_at` recorded and immutable | **R1 R20** |
| 2.2 | **Dispatch builder is predicate-blind by construction.** Pure function | `v2s/dispatch.py` | a sentinel string from a predicate appearing anywhere in the rendered payload, its file list, or its environment | the builder takes no predicate argument at all | **R2** |
| 2.3 | **Measurement store: v2s-owned schema, append-only.** From `science.json`: `model_id, revision, weights_sha256, device, seed, provenance`, plus `confirmatory`, `plan_step_id`, span id. ClawBio's `commands.sh` and audit span are embedded fields when present | `v2s/measurement.py` | a record missing its span id or model/tool pins being accepted; an existing record being mutable | append-only enforced; A-25's schema is the only record shape | **R7 R11** |
| 2.4 | **Exploratory / confirmatory split, and `PLAN ∩ PREDICATE`.** | `v2s/register/intersect.py` | a selector resolving an exploratory record; `n_resolved != n_planned` not halting; an off-plan confirmatory record not halting | `confirmatory: false` is permanently unreachable to every predicate | **R24** |
| 2.5 | **The seal-ordering rule, enforced as one check.** | `v2s/register/seal_order.py` | a predicate seal preceding the prediction seal; **and** any implementation whose correctness depends on predicate-vs-plan order | the rule above holds as a single assertion over the run record | **R1 R2 R20** |

---

## Phase 3 — Triage

| # | task | files | the sealed test must fail first on | done when | satisfies |
|---|---|---|---|---|---|
| 3.1 | **Tool probe reads real catalog values.** `maturity_tier ∈ {cli-registered, tested, ci-validated, spec-only, scripted}`, `status ∈ {planned, mvp}` — **`bench-validated` does not exist** | `v2s/tool_probe.py` | a `spec-only` skill yielding `OPEN_FEASIBLE`; a mutant making the probe always-true surviving | probe reads `struct-predictor`'s tier as the cheap partial; absent ClawBio → degrade, never HALT | **R18 R23** |
| 3.2 | **Triage verdict record.** `verdict, tool, preferred, preferred_available, depth, citations` | `v2s/triage/verdict.py` | a verdict produced from abstracts being recorded as `full_text` | `depth` is **derived** — `full_text` iff full-text reading ran over the backing papers; mutation-tested, because a strength label nothing can contradict is not a check | **R5 R6** |
| 3.3 | **Undermind adapter + declared fallback.** Surface measured 2026-10-30: semantic search over a *sample abstract*, async deep search polled for status, batched full-text reading (≤4), bulk metadata lookup (≤300), DOI lookup for citable links | `v2s/triage/undermind.py` | Undermind absent not producing `preferred_available: false`; a draft claiming Undermind-grade triage without it | **the novelty query is written as the abstract of the paper that would already answer the quest** — a keyword query is a lint failure, because it degrades the verdict while `depth` still overstates it | **R6** |
| 3.4 | **Triage terminates the run.** | `v2s/triage/gate.py` | an answered question not returning a resolvable citation, or spending anything | `experiment_spend_usd == 0.0` on ANSWERED; `FOUNDATION` carries its baseline; `OPEN_INFEASIBLE` names the missing tool, tier, or test | **R5 R18** |

---

## Phase 4 — The world model

| # | task | files | the sealed test must fail first on | done when | satisfies |
|---|---|---|---|---|---|
| 4.1 | **Content-addressed ledger, provenance-gated on entry.** `provenance ∈ {literature, measurement, assumption}` | `v2s/world/ledger.py` | a provenance-free claim being insertable | each `vN` content-addressed; the draft cites one specific version | **R11** |
| 4.2 | **Sealed predictions.** `about, expects, credence, basis, sealed_at` | `v2s/world/prediction.py` | a prediction sealed after a confirmatory record for that hypothesis not halting | invariant 6 holds; prediction is the third seal | **R11** |
| 4.3 | **Calibration: Brier, derived, never asserted.** Log rejected — unbounded, infinite at `p=0`, so one zero-credence prediction resolving true destroys the record | `v2s/world/calibration.py` | a calibration figure no resolved prediction supports; a scoring implementation a hedged forecast cannot move | hedging to 0.5 is penalised, which is the whole point | **R11** (AD-8) |
| 4.4 | **Hypothesis generation emits a targets-only statement.** | `v2s/world/hypothesis_gen.py` | a payload containing the expectation or credence, over a fixture where both are present | the experimenter receives targets; expectation and credence never cross | **R2 R20** (AD-7) |
| 4.5 | **Replay is the test.** | — (property over `v2s/world/`) | applying the same results to `vN−1` producing anything other than `vN` byte-for-byte | append-only proven by replay, not asserted | **R11** |

---

## Phase 5 — Boundaries and output

| # | task | files | the sealed test must fail first on | done when | satisfies |
|---|---|---|---|---|---|
| 5.1 | **Wet-lab is a seam, not a capability.** | `v2s/executors/wet.py` | the adapter being callable; a hypothesis closing through it | raises `NotImplementedError`; closing through it HALTs; no execution credential read, referenced or required anywhere | **R12** |
| 5.2 | **Egress guard.** Declared-egress list + the R14 grammar, both probe-proven | `v2s/egress.py` | an undeclared skill being invocable; an identifier-bearing payload leaving; the scan passing without the probe matching | declaring egress is **not** permission to send an identifier — the two checks are independent. Sets the audit-log hide flags and passes relative paths, because ClawBio's audit log writes caller paths verbatim | **R14 R22** |
| 5.3 | **Spend meter the agent cannot write.** | `v2s/spend.py` | a spend-writing tool appearing in the agent's advertised toolset; the ceiling checked inside the tool-error handler | checked **before** each call and **outside** the handler; over-budget raises `BudgetExceeded`, never a tool failure that continues | **R9** |
| 5.4 | **Reporter: every claim resolves, every label holds.** | `v2s/report/claims.py` | a claim with no provenance pointer; an unlabelled unexecuted-source or exploratory value; a draft omitting a REFUTED or INCONCLUSIVE hypothesis | hypothesis count equals the register's closed count; the label check is mutation-tested | **R7 R8 R19 R24** |
| 5.5 | **Decision record built from emitted spans.** | `v2s/report/decisions.py` | a fabricated span id resolving; a fork with no alternatives being given an invented branch | every cited span resolves in the project | **R10** |
| 5.6 | **Citation reachability.** | `v2s/report/citations.py` | a citation to a file outside the deliverable set passing | a DOI-bearing artifact cites nothing its readers cannot reach | **R15** |
| 5.7 | **No internal vocabulary reaches a stranger.** | `v2s/report/lint_vocab.py` | the scan returning zero without the probe term matching | a pass is *a pass*, the register is *the worklist*, a sealed predicate is *a pre-registered analysis* | **R21** |
| 5.8 | **One argument, no flags.** | `skills/bio/SKILL.md`, `v2s/cli.py` | an invocation carrying flags being silently ignored rather than rejected | exactly one declared parameter | **R17** |
| 5.9 | **Reproducibility.** | — (property over the register) | two runs over a recorded fixture with the same quest, seed, instinct pin and predicate shas diverging | identical register transition sequences | **R13** |

---

## Requirement coverage

All 24 standing requirements are carried by at least one task:

```
R1  1.1 1.5 2.1 2.5     R7  2.3 5.4          R13 5.9          R19 5.4
R2  1.5 2.2 2.5 4.4     R8  5.4              R14 5.2          R20 1.7 2.1 2.5 4.4
R3  1.4 1.6             R9  5.3              R15 5.6          R21 5.7
R4  0.3 1.1 1.2 1.3 1.4 R10 5.5              R16 0.2          R22 5.2
R5  3.2 3.4             R11 2.3 4.1-4.3 4.5  R17 5.8          R23 3.1
R6  3.2 3.3             R12 5.1              R18 1.2 3.1 3.4  R24 2.4 5.4
```

## What this plan does not establish

- **Phase ordering is a dependency claim, not a schedule.** No task carries an estimate. `/grill-me` may reorder within a phase but not across the Phase 0 → 1 boundary, because the gate must exist before anything it would gate.
- **T0.1 is a principal gate**, so every downstream task is blocked until a `v2s` repo exists. The plan is written against files that do not yet exist — legitimate for a greenfield repo, and illegitimate to forget.
- **No spend ceiling is declared here.** Ceilings belong to a run's own gate, not to the plan.
- **No sealed test is authored here**, by design. The "must fail first on" column is a contract for the test-author; its contents are not this plan's to write, and the implementer never reads them.
- **Not grilled.** `/grill-me` has not run; no task has been adversarially checked for ambiguity, and no `plan-gate sign` exists.
