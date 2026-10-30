# A&D — `/v2s:bio` (vision to science)

**Workstream:** `v2s-bio` · **Phase:** and
**Status:** **APPROVED, then REVISED.** Principal approval recorded 2026-10-28 against `867df41c` (aviary approvals row 22). Revised 2026-10-30 under the principal's own decision at row 25 (`/grill-with-res`: A-10 replaced, AD-8 closed to Brier, R18 tier values corrected, `fhaviary` pinned, R22 audit-log constraint added). The revision landed in commit `604b416`; the `triage` row and R6 were then filled in from the Undermind surface measured in-session, in commit `6acf8a3` (agent, no decision authority — approvals row 28). **Pin to those commits, not to a content hash:** the documents are tracked and pushed as of `5ff412e`, and the hash `b659e05f` this line previously carried is not reproducible from any committed state — it named an intermediate that was never committed. *(Pointer form per CTO #751.)*
**Builds on:** [`PVR.md`](PVR.md) — **24** standing requirements R1–R24, CTO-signed at `8d1bcc27`
**Decisions:** [`approvals.md`](approvals.md) — rows marked *(A-n)* below

---

## Human input

| Date | Input | Where |
|---|---|---|
| 2026-10-27 | **D1 — predicate representation:** "Declarative spec + bounded test library" *(A-11)* | `AskUserQuestion` |
| 2026-10-27 | **D2 — store integrity:** "Exploratory / confirmatory split" *(A-12)* | `AskUserQuestion` |
| 2026-10-27 | **D7 — world model:** "Predictive + calibration-scored" *(A-15)*, after questioning whether the alignment sits in subclassing Aviary's `Environment` or adopting ClawBio as the workbench | `AskUserQuestion` |

## Agent assumptions

Choices nobody decided. Each is rejectable; none blocks plan-validity, all must stay visible.

| # | Assumption | Consequence if rejected |
|---|---|---|
| AD-1 | **The PVR needs an amendment.** D2 implies a standing requirement the approved PVR does not contain: *no exploratory measurement may reach a verdict, and every claim derived from exploratory data carries that label.* Raised rather than added quietly — it is requirement-level, so it belongs to the principal, not to me *(A-13)* | Without it the split is a design convention rather than an enforced property, and the attack D2 closes reopens at the first refactor |
| AD-2 | **D3 — seals.** Predicate and plan seals reuse v2r-loop's `test-seal` hook pattern: writable until `sealed_at` is set, immutable after, enforced by hook rather than convention *(A-14)* | A different isolation mechanism means R1 and R2 need their own enforcement, and the airdlc hard dependency buys less |
| ~~AD-3~~ | **REVISED 2026-10-30 after `/grill-with-res` *(A-25)*.** ClawBio's `reproducibility/` bundle is **not** canonical: its README scopes it to *"many skills"* / *"where provided"*, `run_skill()` writes no bundle, `pharmgx-reporter` emits `commands.sh` alone, and `repro-enforcer` is `spec-only`/`planned`. **v2s owns the measurement-record schema**, promoted from `paper/evidence/science.json` (`model_id, revision, weights_sha256, device, seed, provenance`); ClawBio's `commands.sh` and its audit span are fields inside it | The approved text would have had `/plan` decompose R7 against a format that cannot carry R7's span id or model and tool pins |
| AD-4 | **D5 — world model.** Append-only, content-addressed ledger; one version per write-back; every claim carries provenance in `{literature, measurement, assumption}` *(A-14)* | A mutable store makes R11's replay property unprovable |
| AD-5 | **D6 — triage verdict.** One record carrying `verdict`, `tool`, `preferred`, `preferred_available`, `depth`, `citations` *(A-14)* | — |
| AD-6 | The bounded test library ships with `threshold`, `paired_difference`, `rank_correlation` and `proportion` in v1; anything else yields `OPEN_INFEASIBLE` | A larger v1 library widens the surface the sealed analyst can express, and widens what must be tested |
| AD-7 | **The experimenter is shown targets only.** A hypothesis is now a prediction, so its statement carries an expectation — and R2 hands that statement to the experimenter. Expectation and credence stay with the predicate and the world model *(A-16)* | Without the split the experimenter learns the threshold and can bias an under-specified plan toward an outcome, partly reopening D2 |
| AD-8 | **Calibration uses the Brier score** — settled by `/grill-with-res` 2026-10-30: both Brier and log are strictly proper, but log is unbounded and infinite at p=0, so a single zero-credence prediction that resolves true destroys the record; Brier is bounded and symmetric *(A-17, A-26; scoringrules theory, arXiv 2105.12065)* | Scored on accuracy alone, a model that knows it is scored hedges every credence to 0.5 and the track record becomes decorative |

---

## Approaches & decision

### D1 — What is an acceptance predicate, physically? *(By: Human)*

R4 is the requirement everything hangs from: *zero measurements read exits 3, never REFUTED.* Whether that is **structural** or merely **runtime** is decided by what a predicate physically is.

| Option | Verdict |
|---|---|
| Sealed Python module, `evaluate(measurements) -> Verdict` | **Rejected.** Full expressiveness, but the register cannot know what it read without instrumenting the accessor, and a predicate returning REFUTED having read nothing is indistinguishable from one that measured. R4 degrades to a runtime trick |
| Sealed pytest file reusing the v2r referee | **Rejected.** Maximum reuse of machinery we already hard-depend on, but pytest has two outcomes and science has three. A *failing* test means "retry" in v2r-loop and "REFUTED — publish it" here. Mapping three outcomes plus HALT onto pass/fail/error is precisely the lossy encoding that produced F3 |
| **Declarative spec + bounded test library** | **CHOSEN.** The predicate is data. It names its measurements by selector, selects a test from a versioned library of established statistics, and states threshold and verdict map. The register proves it names ≥1 measurement *without executing it* |

**No escape hatch.** A hypothesis needing a test the library lacks yields `OPEN_INFEASIBLE` naming it — reusing R18's existing refusal path. An escape hatch to arbitrary code would re-admit every failure the choice exists to prevent.

The PVR's *"no novel statistics"* out-of-scope line is what makes this viable: it means the test set is enumerable. A constraint written as a limitation turned out to be the enabler.

### D2 — Who controls what reaches the predicate? *(By: Human)*

**The hole this closes.** The predicate selects by *pattern*; the experimenter controls *what enters the store*. R2 keeps the predicate hidden, but the experimenter sees the hypothesis statement, from which the selector shape is largely predictable. So:

- **Dilution** — add records matching the selector but missing the threshold; an `all_of` predicate flips SUPPORTED → REFUTED.
- **Packing** — add records that clear it; an `any_of` or aggregate predicate flips the other way.

Neither requires sight of the predicate. This is the real-world failure pre-registration alone does not fix: committing to the analysis is worthless if the experimenter still controls which data reaches it. The PVR specified F2 for the analyst's side and said nothing about the other half of the join.

**Chosen: an exploratory / confirmatory split**, which restores symmetry — both sides commit before data exists, neither sees the other, and the register intersects them.

```
PHASE E · exploratory                         adaptive, unlimited
  probe → see the real number → choose the next probe
  every record stamped  confirmatory: false
  └─ no predicate can ever resolve these; they ship labelled exploratory
        │
        ↓   the experimenter proposes a confirmatory plan
  plan/H-nnn.yaml          sealed · sha-pinned · predicate-blind (R2)
        │
        ↓
PHASE C · confirmatory                        exactly the plan, nothing else
  register evaluates  PLAN ∩ PREDICATE
     n_resolved ≠ n_planned          → HALT
     a confirmatory record off-plan  → HALT
```

Rejected: **exact-n only** (cheap, keeps full adaptivity, but brittle in the honest direction — a legitimate extra probe that happens to match an unseen selector silently costs the hypothesis); **plan-step binding in one phase** (tight, but loses adaptivity without buying the exploratory record).

Adaptive measurement survives in phase E, where it cannot touch a verdict. `science/run_discovery.py`'s existing adaptive loop maps onto E unchanged.

### D7 — Is the alignment in Aviary's `Environment`, or in ClawBio as a workbench? *(By: Human)*

**Neither — the question exposed that the world model was misnamed.** The schematic says *World Model*; the PVR redefined it as a provenance-gated evidence ledger. A world model is something you can roll **forward** — it tells you the consequence of an action not yet taken. A ledger records what has already been established. R21 forbids exactly that kind of borrowed vocabulary, and the PVR did it anyway.

Why not **subclass `Environment` to hold the world model**, from Aviary's own documentation:

| | |
|---|---|
| Lifetime | `state` is *"the variables that change per step"* — per-episode. The world model must be durable across runs, versioned and content-addressed (R11) |
| Persistence | `export_frame` is documented as optional, *"for visualization or debugging"*. That is a debug hook, not a provenance contract |
| Ownership | An Environment holding the belief store means the thing producing measurements also owns what gets believed — the same merge R11 exists to prevent, and the shape of the D2 attack one level up |
| Reward | `step` returns a scalar. This repo keeps it at 0.0 deliberately and AS-3 puts training out of scope; subclassing imports the RL frame without any RL |

Why not **ClawBio as the workbench**: it has no Environment contract at all — no `reset`/`step`, no observation shape, no state object — so the Environment gets written anyway and ClawBio called from inside it. A-9 already ruled it a tool provider *called by* the loop because its orchestrator has no concept of a sealed predicate. And "RL agent" is borrowed too: no reward, no policy update, no training.

**CHOSEN: the world model earns its name by predicting.** It states what it expects before the confirmatory run, sealed; a hypothesis *is* a prediction; the predicate tests it; the verdict updates the claim store **and** a calibration track record.

```
Aviary        the instrument   episode-scoped apparatus, one measurement
ClawBio       the toolbox      skills called by the loop
world model   the thing that sticks its neck out
```

What it buys, beyond the name: hypothesis generation becomes *"the model predicts X — test X"*, falsifiable by construction; D2's split stops being arbitrary and becomes **uncertain vs committed**; and R11's "articulate fiction" failure gets a real defence, because a fluent fiction that keeps predicting wrong is visible on a scoreboard in a way provenance-on-entry never makes it.

---

## Components & interfaces

| Component | Does | Depends on | Owns requirements |
|---|---|---|---|
| `hypothesis-register` | The trust core. Seals, resolves, intersects, renders verdicts. No LLM, no network in its decision path. Extends airdlc's `register` rather than forking it | `airdlc` (hard, version floor) | R1 R3 R4 R13 R16 R20 R23 |
| `predicate-spec` | Parse + validate a declarative predicate; refuse unknown tests; compute the named-measurement set statically | — | R1 R4 |
| `test-library` | Versioned, bounded set of established statistics. v1: `threshold`, `paired_difference`, `rank_correlation`, `proportion` | — | R4 R18 |
| `plan-spec` | Parse + validate a confirmatory measurement plan; seal it | `test-seal` hook | R1 R20 |
| `seal-hook` | Makes `sealed_at` one-way for both predicates and plans | airdlc hooks | R1 R2 |
| `dispatch-builder` | Pure function rendering the experimenter's payload. Predicate-blind by construction | — | R2 |
| `measurement-store` | Append-only. Every record is a **v2s-owned** schema (from `science.json`: `model_id, revision, weights_sha256, device, seed, provenance`) plus `confirmatory`, `plan_step_id`, span id; ClawBio's `commands.sh` and audit span are embedded fields when present *(A-25)* | ClawBio (soft) | R7 R11 R22 |
| `triage` | Novelty + feasibility. Undermind preferred, declared fallback, records `depth`. **Surface measured in-session 2026-10-30** (user-scope MCP, account `alumni.cmu.edu`): `search_papers(workspace_id, sample_abstract, search_type∈{semantic,library,citations,references}, …)` — takes a 2–3-sentence *sample abstract in the paper's own voice*, not keywords; `launch_deep_search(workspace_id, goal)` — async, 2–5 min, few in parallel, polled by `inspect_deep_searches(status_only=True)`; `read_pdfs(workspace_id, papers[≤4]{cite_key, question})` — one sub-agent per PDF; `lookup_papers_by_metadata(≤300)`; `find_papers_by_author`; `get_paper_info(show_doi=true)` for citable links. All workspace-scoped; cite keys are per-workspace. **R6 `depth` is now concrete:** `full_text` iff `read_pdfs` ran over the papers backing the verdict, else `abstract` | Undermind (soft), consensus/pubmed/biorxiv | R5 R6 R18 |
| `world-model` | Content-addressed ledger of claims **plus sealed predictions and a calibration record**. Refuses a provenance-free claim; scores with a proper rule *(A-17)* | — | R11 |
| `hypothesis-gen` | Derives hypotheses from the model's predictions and its uncertainty. Emits a **targets-only** statement for the experimenter *(A-16)* | `world-model` | R2 R20 |
| `tool-probe` | Capability probe; reads ClawBio `catalog.json` field `maturity_tier` ∈ `{cli-registered, tested, ci-validated, spec-only, scripted}` and `status` ∈ `{planned, mvp}` — **`bench-validated` does not exist** (108/108 checked) | ClawBio (soft) | R18 R23 |
| `egress-guard` | Declared-egress list; scans outbound payloads with the R14 grammar | — | R14 R22 |
| `spend-meter` | Harness-side ledger the agent cannot write | airdlc `spend` | R9 |
| `reporter` | Draft, decision record, review surface. Labels exploratory, unexecuted and fallback-derived values | weave | R7 R8 R10 R15 R19 R21 |

**The one boundary that matters:** `hypothesis-register` is the only writer of `verdict`. Everything above it proposes; only it renders. That is R3, and it is enforced by making `verdict` unreachable from any other module rather than by review.

---

## Data & state

```
.v2s/
  register.yaml            hypotheses, states, seals, verdicts  ← register-only writer
  predicates/H-nnn.yaml    sealed · sha-pinned · analyst-written
  plans/H-nnn.yaml         sealed · sha-pinned · experimenter-written
  measurements/            append-only; one reproducibility bundle per record
  world-model/vN/
    claims/                provenance-gated
    predictions/P-nnn.yaml sealed · targets + expectation + credence + basis
    calibration.json       proper-scoring-rule track record, derived only
  triage/verdict.json      verdict · tool · preferred_available · depth · citations
  run-record-N.json        transitions, spend, span ids
```

**Invariants.**
1. `predicate_sealed_at` precedes every confirmatory measurement timestamp for that hypothesis.
2. `plan_sealed_at` precedes every confirmatory measurement for that hypothesis.
3. A record with `confirmatory: false` is unreachable to every predicate selector, permanently.
4. `verdict` has exactly one writer.
5. The world model is append-only; vN is a pure function of vN−1 plus the results written back.
6. `prediction_sealed_at` precedes every confirmatory measurement for that hypothesis — the **third** seal, alongside the predicate's and the plan's.
7. The statement handed to the experimenter contains targets only; expectation and credence never appear in it.
8. Calibration is **derived** from resolved predictions, never asserted — the same discipline as R6's `depth`.

---

## Failure handling

| PVR failure | Mechanism |
|---|---|
| F1 predicted read as measured | Every value carries provenance; `reporter` refuses an unlabelled unexecuted-source or exploratory value |
| F2 predicate revised after data | `seal-hook` makes `sealed_at` one-way; sha mismatch HALTs |
| F3 the gate silently does not run | Static proof that the predicate names ≥1 measurement, plus `n_resolved == n_planned`. Zero resolved is HALT, never REFUTED |
| F4 weak fallback at full strength | `depth` and `preferred_available` in the verdict; `reporter` cross-checks |
| F5 world model drifts | Provenance required on entry; replay test |
| F6 unreachable citation | Citation resolver over the deliverable set |
| F7 known result as discovery | Triage terminates with `ANSWERED` |
| F8 question inside a pass | The drain HALTs rather than prompting |
| F9 identifier leak | `egress-guard` + R14 scan, both probe-proven |
| **new** — exploratory result reaching a verdict | Invariant 3; see AD-1, which needs a PVR amendment |
| **new** — experimenter biases the plan from a leaked threshold | Invariant 7: targets-only statement *(AD-7)* |
| **new** — the model games its own calibration by hedging | Proper scoring rule penalises hedging and miscalibration together *(AD-8)* |

---

## Per-requirement spec

Each requirement's behavioral contract is its PVR test criteria, carried through unchanged, attached to the owning component in the table above. The four that need design-level sharpening:

- **R4** — the register performs *static* proof (predicate names ≥1 measurement) **and** *dynamic* proof (`n_resolved == n_planned`). Either failing is HALT. A fixture in which an empty evaluation would report REFUTED must fail the suite.
- **R6** — `depth ∈ {abstract, full_text}` is derived from which Undermind call produced the evidence (`read_pdfs` ⇒ `full_text`), never asserted by a model. Measured constraint for the triage prompt: `search_papers` ranks by semantic similarity to a `sample_abstract`, so the novelty query must be written *as the abstract of the paper that would already answer the quest*, not as a question — a keyword query degrades the verdict and R6 would record a `depth` that overstates it.
- **R11** — replay is the test: applying the same results to vN−1 must reproduce vN byte-for-byte under content addressing.
- **R18** — `OPEN_INFEASIBLE` has three distinct causes, each named in the verdict: tool absent, tool present but `maturity_tier: spec-only` or `status: planned`, test absent from the library. The catalog's real values are the five above; the PVR's `bench-validated` was a misreading and is corrected here.
- **R22** — ClawBio's audit log (`~/.clawbio/audit.jsonl`) writes `input.value` / `output.value` exactly as the caller passed them and honours `OPENINFERENCE_HIDE_INPUTS` / `OPENINFERENCE_HIDE_OUTPUTS`. The plan sets both and passes relative paths, or a log v2s does not own violates R22.
- **Pins** — `fhaviary>=0.37.0,<0.38` (PyPI 2026-09-15, Python ≥3.11); both `science/*.py` scripts are currently unpinned. R16 gives `airdlc` a version floor; Aviary gets one too. API reference is `docs.edisonscientific.com/aviary` (self-describes as FutureHouse, `pip install fhaviary`, links `Future-House/aviary`); no rename is established, so the PVR's `futurehouse.org` citation stands.

---

## Open questions

| # | Question | Owner |
|---|---|---|
| ~~AD-1~~ | **CLOSED 2026-10-28** — became **R24** in the PVR; CTO-signed at `8d1bcc27`, aviary approvals row 5 | — |
| ~~AD-9~~ | **CLOSED 2026-10-28** — **R11** amended in place as a dated, visible correction; CTO-signed at `8d1bcc27`, aviary approvals row 5 | — |
| OQ-2 | The proof-of-value quest — still open, still assumed, never to be presented as chosen | Principal |
| OQ-5 | `/v2r-loop` deleted vs deprecated with a pointer | Principal |
| OQ-8 | PVR and A&D durability — both are git-ignored and tracked on zero refs | Principal |
| AD-6 | The v1 test-library contents | Principal or `/plan` |
