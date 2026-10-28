# PVR — `/v2s:bio` (vision to science)

**Workstream:** `v2s-bio` · **Phase:** pvr
**Status:** **APPROVED.** CTO re-signature recorded 2026-10-28 against `8d1bcc27` — aviary approvals row 5, discharging the withheld signature of row 4. The principal's approval (*"approve aviary-biosim PVR for kick-off"*, relayed in dispatch #731, 2026-10-23) was given against the earlier 21-requirement document at `816b5c6e`; this file carries 24 requirements and the CTO's signature covers it at `8d1bcc27`. **This line is the only change since that hash.**
**Decisions:** [`approvals.md`](approvals.md) — every row below marked *(A-n)* is approval-log row n
**Supersedes:** `/v2r-loop`, which is retired by this work (see Open questions OQ-5)

---

## Human input

Each line is something the principal asked for or chose, in their terms, with where they said it.

| Date | Input | Where |
|---|---|---|
| 2026-10-20 | "derive an ambitious yet feasible single skill based on `/v2r-loop`" | `/define` invocation |
| 2026-10-20 | "drop `/v2r-loop` skill and modify it to `/v2s:bio` (vision to science)" | `/define` invocation |
| 2026-10-20 | "`v2s` will be the namespace for the skill series" | `/define` invocation |
| 2026-10-20 | "Focus on AI agent use in science and create the framework of an AI scientist, world model and experimentation loop" based on FutureHouse's Aviary and the four-layer schematic (Human → AI Scientist → AI Science Assistant → AI Tools) | `/define` invocation + attached image |
| 2026-10-20 | "Couple the tool with the use of [Aviary] for building the environment with predefined tools handy for biological sciences / computational biology / data sources" | `/define` invocation |
| 2026-10-20 | "use w&b for AI agent tracing for decision records, interpretability reports, centered around a fully auditable process of turning a hypothesis into a whitepaper or publication draft backed by grounded experimental data and analysis" | `/define` invocation |
| 2026-10-20 | "shipped with appropriate process of research, involving evaluation (pre-existing studies, feasibility…), where if it doesn't pass or a direct existing research exist to answer the question, or a similar research that may be used as foundation" | `/define` invocation |
| 2026-10-20 | "Adopt undermind as the deep research analysis tool as well (mcp use)" | `/define` invocation |
| 2026-10-20 | **Spine:** "Pre-registration as the gate" *(A-1)* | `AskUserQuestion` |
| 2026-10-20 | **Housing:** "New standalone v2s repo" *(A-2)* | `AskUserQuestion` |
| 2026-10-20 | **Substrate:** "include cloud-lab execution boilerplate for future options, but dry-lab only for this PoV (completely computational biology driven research)" *(A-3)* | `AskUserQuestion` |
| 2026-10-20 | **Undermind:** "Preferred, with a declared fallback" *(A-4)* | `AskUserQuestion` |
| 2026-10-20 | **Autonomy:** "One gate, placed after triage" *(A-5)* | `AskUserQuestion` |
| 2026-10-23 | **ClawBio layering:** adopted as the layer-03/04 tool provider called by the loop, NOT as the workspace; integration via the Python API, never the deprecated MCP server *(A-9)* | `AskUserQuestion` |
| 2026-10-23 | **ClawBio depth:** its `reproducibility/` bundle becomes the canonical evidence-record format *(A-10)* | `AskUserQuestion` |
| 2026-10-23 | **Approval:** "approve aviary-biosim PVR for kick-off" | principal, relayed in CTO dispatch #731 |
| 2026-10-22 | **Gate-core dependency:** "proceed with A, should declare hard depedency required by the design of the set-up & platforms" — OQ-1 resolved to a hard dependency on `airdlc`, not vendoring *(A-7)* | mid-turn message |

## Agent assumptions

Gaps filled without a human answer. Each is a claim the principal can reject; each is also an open question until confirmed, and each is copied to the L0's *Decisions needed*.

| # | Assumption | What changes if rejected |
|---|---|---|
| AS-1 | Everything the run learns ships: the draft carries SUPPORTED, REFUTED and INCONCLUSIVE hypotheses alike, and carries the triage verdict even when it reads *"already answered, we stopped"* *(A-6)* | If rejected, the draft becomes a selective report and R7/R8 lose most of their value |
| AS-2 | The primary user is the principal and the bioFM group; a second audience — an external reader holding only the DOI'd artifact — constrains what may be cited (R15) but is not a user to build features for | Widening to external users adds onboarding, packaging and support scope |
| AS-3 | `/v2s:bio` consumes Aviary as an **environment and tool contract** (`fhaviary`). It does not use `ldp` and does not train or fine-tune agents | If training is wanted, this becomes a substantially larger workstream with GPU and dataset scope |
| AS-4 | The proof-of-value quest is in the protein-stability / recombinant-expression area this repo already instruments end to end (ESM-2 masked marginals over real UniProt sequences), not a new domain | A new domain means new tools, new validation and a longer feasibility tail |
| AS-5 | `/v2s:bio` stops at a publication **draft**. Deposit, DOI minting and venue submission stay with the existing n8n academic pipeline | Folding deposit in re-opens an irreversible-publication surface this PVR deliberately excludes |
| AS-6 | The standalone `v2s` repo is public and MIT-licensed, matching Aviary-BioSim | A private repo changes the vendoring calculus in OQ-1 and the citation rules in R15 |

---

## Vision

**One prompt states a quest. `/v2s:bio` returns a publication draft in which every claim resolves to a measurement a non-LLM gate observed, and every hypothesis was written down before the data existed.**

`/v2r-loop` established one property and the rest of it followed: *no agent in the loop can close its own work.* The implementer never sees its test, the test-author never sees the implementation, and a 483-line register with no LLM and no network in its decision path re-runs the test itself and refuses to close on anything less than an observed pass. That is what made an unattended build loop trustworthy — not that the agents were good, but that the agents were structurally unable to grade themselves.

`/v2s:bio` carries that same impossibility into science, where it answers a sharper problem.

The dominant failure of LLM-generated science is not fabricated data. It is **post-hoc rationalisation**: the model runs something, looks at the output, and writes the hypothesis the output happens to support. In the finished artifact that is indistinguishable from discovery, and it is worth nothing. Every soft remedy — asking for honesty, prompting for rigour, reviewing the draft — fails in the same way, because the evidence of the failure is gone by the time anyone reads the paper.

So the transplant is exact:

| `/v2r-loop` | `/v2s:bio` |
|---|---|
| implementer never sees its test | **experimenter never sees the acceptance predicate** |
| test-author writes from the unit statement + skeleton only | **sealed analyst writes the predicate from the hypothesis statement + tool interface only, before any data exists** |
| register re-runs the sealed test | **register evaluates the pre-registered predicate over the measurement record** |
| only `register close` closes a unit | **only `register close-h` renders SUPPORTED / REFUTED / INCONCLUSIVE** |
| a parked unit's code is reverted; history stays green | **a refuted hypothesis is kept and published; the record stays honest** |

That is pre-registration, enforced mechanically rather than promised. The agent that proposes a hypothesis is *incapable* of deciding whether it was confirmed.

### The shape of a run

```
quest  (the only argument)
  │
  │   STAGE 0 · unattended · cheap · may terminate the run
  ├── deep research          undermind (preferred) → consensus · pubmed · biorxiv (declared fallback)
  ├── novelty verdict        ANSWERED │ FOUNDATION │ OPEN+INFEASIBLE │ OPEN+FEASIBLE
  ├── feasibility            are the tools this needs actually reachable from here?
  └── world model v0         a versioned evidence ledger — every claim carries provenance
  │
  │   hypotheses H-001..H-0nn generated from the model's gaps and contradictions
  │   sealed analyst pins one acceptance predicate per hypothesis, sha-recorded
  │
  ⏸   ONE GATE — the verdict, the hypothesis set, the pinned predicates, the ceilings
  │                     scope frozen here; it cannot widen
  │
  │   STAGE 1 · unattended · metered
  ├── drain: experimenter runs the aviary environment, never seeing the predicate
  ├── register evaluates the predicate over the measurements it can name
  │     0 → closed, verdict recorded      1 → retry        3 → HALT, a human looks
  └── world model v0 → vN, each claim written back with its provenance
  │
  │   STAGE 2 · the run is not finished at the data
  ├── publication draft      every claim traceable; refutations included
  ├── decision record        each fork cites a Weave span id that exists
  └── review surface         limitations named before anyone asks
```

### The four layers, mapped

The principal's schematic, with what is built and what is not:

- **01 Human** — the quest. One string, as in `/v2r-loop`.
- **02 AI Scientist** — `/v2s:bio` itself: world model → hypothesis generation → experimentation. **The pre-registration gate lives here and only here.** That placement is the whole reason ClawBio is a tool provider and not the workspace: a route into a tool that bypassed the gate would leave a hypothesis closable without a pinned predicate, and ClawBio's own Bio Orchestrator has no concept of one *(A-9)*.
- **03 AI Science Assistant** — **ClawBio** (`github.com/ClawBio/ClawBio`, MIT): a bioinformatics-native agent skill library of roughly 95 skills — pharmacogenomics, GWAS lookup, polygenic risk scores, ancestry PCA, fine-mapping, scRNA tooling, nf-core and Galaxy wrappers. This layer is consumed, not built.
- **04 AI Tools** — Aviary / `BioSimEnv` as the environment and tool contract (ESM-2 over real UniProt sequences today, structure prediction via API), data APIs (ChEMBL, Open Targets, PubMed, bioRxiv), and **laboratory experiments as a declared seam with no implementation** *(A-3)*.

Aviary is the **environment**, not the world model. Those are separate boxes in the schematic and the PVR keeps them separate: the world model is a provenance-gated ledger *(R11)*, and merging it into the environment that produces the measurements is precisely the failure R11 exists to prevent — nothing external would then check what enters the belief store.

Two things the schematic does not show carry most of the auditability:

- **Stage 0 can end the run.** A quest whose answer already exists returns the answer and stops at zero experiment spend. Refusing to run is a first-class outcome, not a failure.
- **W&B Weave is the substrate of the decision record.** Each stage is a `@weave.op`, so what gets read back afterwards is a span that was emitted during the run — not a narrative the model composed about itself once it knew the ending.

### What this is not

It is not an oracle and it does not discover unaided. It is an instrument that makes a specific class of dishonesty impossible and leaves the rest visible. The decision record shows what an agent *said* its reasons were; it never shows what caused the output, and the deliverable says so in its own voice.

---

## Goals & success metrics

| # | Goal | Metric — how success is measured |
|---|---|---|
| G1 | Every claim in the draft is traceable to a measurement | A claims-check over the finished draft resolves 100% of numeric claims to an evidence record the register wrote; the build fails otherwise |
| G2 | No hypothesis closes on data its proposer could see | For every closed H, `predicate_sha` was recorded before the first measurement timestamp for that H — checked mechanically over the run record, not asserted |
| G3 | The run refuses when the question is already answered | A quest with a known-answered question terminates at `ANSWERED` with ≥1 resolvable citation and `experiment_spend_usd == 0.0` |
| G4 | Refutation ships | A quest seeded with a hypothesis known to be false produces a draft that states it was refuted, with the predicate and the measurements that refuted it |
| G5 | The decision record is reconstructed, not narrated | 100% of forks in the decision record cite a Weave span id that resolves in the project |
| G6 | A run is reproducible | Same quest + seed + instinct pin + predicate shas → identical register transition sequence |
| G7 | The gate cannot silently stop being a gate | The mutant catalogue for the evaluation path is 100% killed; every mutant encodes a distinct way the gate could stop gating |

---

## Out of scope

Cut ruthlessly. Each line is a thing a reasonable reader might expect and will not get.

- **Wet-lab execution.** A documented adapter seam ships; no implementation, no credentials, no protocol execution, and no hypothesis may close through it *(A-3, R12)*.
- **Agent training.** Aviary's `ldp`, RL, fine-tuning, reward modelling. The reward channel stays explicitly unwired rather than filled with a fabricated scalar *(AS-3)*.
- **Domains other than biology.** `v2s:chem`, `v2s:mat` and the rest of the series are why the namespace exists; none are built here.
- **Deposit, DOI minting, venue submission.** The draft is the terminus *(AS-5)*.
- **Novel statistical methodology.** Established tests only; a new estimator inside a pre-registration machine is an unreviewable combination.
- **Multi-quest portfolio management**, scheduling, and any cross-run optimisation.
- **Authoring ClawBio skills.** `/v2s:bio` consumes that layer; it does not extend it. A quest needing a skill ClawBio lacks yields `OPEN_INFEASIBLE` naming it *(R18)*.
- **A hosted service, UI, or API.** This is a skill invoked from Claude Code.
- **Retrofitting the published Aviary-BioSim whitepaper.** That artifact is closed; this work does not reopen it.

---

## Constraints

**Technical**

- Aviary (`fhaviary`) is the environment and tool contract. The existing `science/biosim_env.py` is the reference implementation to generalise from, not to rewrite blind.
- W&B Weave for tracing; W&B Inference as the model endpoint — both already wired in Aviary-BioSim.
- The gate's trust core is `tools/register` (non-LLM, no network in its decision path). It lives in `supmo668/airdlc`, and `v2s` is a standalone repo *(A-2)*, so `v2s` **declares a hard dependency** on `airdlc` rather than vendoring it *(A-7)*. The register is therefore never forked — the one component that must not drift structurally cannot — and `v2s` fails closed when `airdlc` is absent or below its version floor *(R16)*.
- Dry-lab only. Every hypothesis must be closable from inside the run *(A-3)*.
- **ClawBio is integrated through its Python API** (`run_skill()`, `list_skills()`) or its CLI — **never its MCP server**, which ClawBio deprecated in 0.7.0 and removes in 0.8.0 on the stated grounds that MCP addresses connectivity rather than specification. Everything else in this stack is MCP, so MCP was the obvious default and is the wrong one here *(A-9)*.
- ClawBio's `reproducibility/` bundle — `commands.sh`, `environment.yml`, checksums, `runtime-lock.json` — is the canonical evidence-record format the register points at *(A-10, R7, R13)*.
- **ClawBio is a SOFT dependency**, capability-probed, and its absence degrades the run rather than stopping it. This is deliberately the opposite posture to `airdlc` *(R16)*: `airdlc` is the gate's trust core and is ours, while ClawBio is third-party and young (v0.7.1, 31 open PRs, its website repo archived 2026-03-04). A third-party library must never be able to halt the gate, and must never be trusted to be the gate *(R23)*.
- ClawBio's package makes no network calls, but **some of its skills send variants or sequences off-machine** to public annotation APIs. That is an identifier-disclosure path the existing scan does not cover *(R22)*.

**Providers and credentials**

- Undermind (`mcp.undermind.ai/mcp`) is **exposed and authenticated**, verified by measurement in the CTO's session (dispatch #731, 2026-10-23). Surface: `search_papers` (global corpus, workspace library, or the citation graph of seed papers), `launch_deep_search` (agentic, citation-following, re-ranked, 2–5 min), **`read_pdfs` (full-text, batched)**, `lookup_papers_by_metadata`, `find_papers_by_author`. So `preferred_available: true` is the live state and full-text triage is reachable — the fallback (`consensus` / `pubmed` / `biorxiv`) is the contingency, not the operating mode *(A-4, R6)*. It had been exposed at the account level but absent from this agent's own session, which is why the earlier text read it as unverified.
- **bioRxiv has no keyword or full-text search** — its API filters by date and category only. Stage-0 triage must therefore reach preprints through `consensus` or Undermind and use the bioRxiv MCP for category/date sweeps and per-DOI detail, not as a question-answering search. A triage design that assumes keyword search over preprints does not work.
- `benchling` (ELN/LIMS) is deliberately left unconfigured: it is wet-lab tooling, and R12 requires wet-lab to be a seam with no capability behind it.
- Spend is metered by the harness from the provider's own token counts. There is no default price; an operator who declares none gets no budget, because a guessed price makes the guard pass while metering nothing.

**Policy**

- The agent being metered cannot write the ledger. It gets a read-only `spend_remaining` tool and no tool that records spend.
- **F33 identifier hygiene:** the input's identifier, release and digest may appear only in the deliverable's methods section and its evidence directory — never in tests, fixtures or messages *(R14)*.
- One approval gate, after triage. No question may be asked inside a drain: raise it at Stage 0 or at the gate, or halt *(A-5)*.
- Never write the trunk; never land its own PR. Inherited from `/v2r-loop` and non-negotiable.

---

## Failure modes — what must not happen

| Failure | Why it earns a place here |
|---|---|
| F1 — a predicted number read as a measured one | It discredits everything else on the page. Addressed by R8, R12 |
| F2 — a predicate revised after seeing the data | p-hacking. Must be structurally impossible, not discouraged. Addressed by R1 |
| F3 — the gate silently does not run | `/v2r-loop` found exactly this defect in itself: a dependency mismatch meant the sealed test never executed while its own 36-test suite stayed green. Addressed by R4 |
| F4 — a weak fallback reported at the strength of a strong verdict | A novelty claim is only as good as the search behind it. Addressed by R6 |
| F5 — the world model drifts into articulate fiction | Nothing external checks it unless provenance is enforced on entry. Addressed by R11 |
| F6 — the draft cites what its readers cannot reach | The defect just corrected in this repo's own whitepaper. Addressed by R15 |
| F7 — a known result presented as discovery | The whole reason Stage 0 exists. Addressed by R5, R18 |
| F8 — a question asked inside a drain | A drain is unattended by definition, so nobody answers it. Addressed by R20 |
| F9 — an identifier leaking outside methods and evidence | Addressed by R14 |

---

## Requirements

Requirements are **standing** — never closed, enforced across every later refactor. Build units derived in `/design` carry `satisfies: R<n>` back to them.

### R1 — Pre-registration is structural, not procedural
The acceptance predicate for a hypothesis is authored, committed and sha-pinned **before any measurement for that hypothesis exists**, by an agent whose context holds the hypothesis statement and the tool interface and nothing else.
**Test criteria:** given `H-001` sealed, a write to its predicate path is refused by the seal hook; a predicate whose on-disk sha differs from the pinned `predicate_sha` makes the register HALT rather than close; the run record's `predicate_sealed_at` precedes every measurement timestamp for that H, checked over a fixture where it does not.

### R2 — The experimenter never sees the predicate
The subagent that runs an experiment is dispatched with the hypothesis statement and the environment handle only.
**Test criteria:** the dispatch payload builder is a pure function; over a predicate containing a distinctive sentinel string, the sentinel appears nowhere in the rendered payload, its file list, or its environment.

### R3 — Only the register renders a verdict
No LLM output can set a hypothesis to SUPPORTED, REFUTED or INCONCLUSIVE.
**Test criteria:** `register close-h` is the only writer of `verdict`; an agent transcript asserting a verdict leaves the register file byte-identical; any other mutation path raises.

### R4 — The gate refuses when it cannot be trusted to have run
Exit codes are not evidence — the defect `/v2r-loop` found in itself. Evaluation must emit a structured record naming the measurement ids it read; **zero measurements read is a HALT, never a refutation.**
**Test criteria:** a predicate that reads no measurements exits 3; a predicate that raises exits 3; a predicate evaluated over ≥1 named measurement exits 0 or 1. A fixture that would make an empty evaluation report REFUTED fails the suite. *This requirement is the one that keeps the loop from manufacturing negative results.*

### R5 — Triage can terminate the run before any experiment spend
A verdict in `{ANSWERED, FOUNDATION, OPEN_INFEASIBLE, OPEN_FEASIBLE}` is produced with citations. `ANSWERED` and `OPEN_INFEASIBLE` stop the run.
**Test criteria:** a quest whose answer is in the literature returns `ANSWERED` with ≥1 resolvable citation and `experiment_spend_usd == 0.0`; `FOUNDATION` carries the prior work it would use as a baseline; `OPEN_INFEASIBLE` names the specific missing tool or dataset.

### R6 — Triage never overstates its own strength
The verdict names the tool that produced it, whether the preferred tool was reachable, **and the depth of evidence it actually read**. Naming the tool is not enough: triage over abstracts and triage over full text are different strengths, and `read_pdfs` makes both reachable from the same tool, so the tool name alone no longer determines the claim *(CTO #731)*.
**Test criteria:** the verdict record carries `tool`, `preferred`, `preferred_available` and `depth ∈ {abstract, full_text}`. With Undermind reachable the record reads `preferred_available: true`; with it absent, `tool: consensus`, `preferred_available: false`. A verdict produced from abstracts but recorded as `full_text` fails; a draft claiming full-text triage over a verdict whose `depth` is `abstract` fails. Both checks are mutation-tested, because a strength label that is never contradicted is not a check.

### R7 — Every claim in the draft resolves to a measurement
The evidence record a claim points at carries the Weave span id and the pinned model and tool versions that produced it. Where a ClawBio skill produced the measurement, its `reproducibility/` bundle **is** that record *(A-10)*.
**Test criteria:** the claims-check exits non-zero when any numeric claim lacks a provenance pointer into an evidence record the register wrote; a claim pointing at a record that does not exist fails; a claim pointing at a record written outside the run fails; a record missing its span id or its model/tool pins fails.

### R8 — A predicted number is never presented as a measured one
**Test criteria:** any value whose provenance is not an executed run carries an explicit label; a draft containing an unlabelled unexecuted-source value fails the check; the check is mutation-tested.

### R9 — Spend is metered, and the metered party cannot write the ledger
**Test criteria:** the agent's advertised toolset contains no spend-writing tool; the ceiling is checked **before** each tool call and outside the tool-error handler, so an over-budget rollout stops with `BudgetExceeded` rather than reporting it as a tool failure and continuing.

### R10 — The decision record is built from spans that were emitted
**Test criteria:** every Weave span id cited in the decision record resolves in the project; a record citing a fabricated id fails; a fork presented with no alternatives is stated as having had none rather than given an invented rejected branch.

### R11 — The world model is predictive and calibration-scored
> **Corrected 2026-10-28** *(A-15)*. As approved on 2026-10-23 this requirement read: *"The world model is a versioned evidence ledger, not a free-text belief blob."* `/design` established that a ledger only records what was already settled, while a world model is something you can roll **forward** — so the approved text borrowed the schematic's word for a weaker object, which R21 forbids. The provenance half below is unchanged; the predictive half is new.

Every claim carries provenance, evidence strength and the run that produced it, and a claim without provenance cannot enter. **In addition**, the model states what it expects *before* the confirmatory run, sealed and sha-pinned, and carries a calibration record derived from how its resolved predictions actually turned out. Calibration is scored with a **proper scoring rule** (Brier or log), never accuracy, because a model scored on accuracy alone hedges every credence toward 0.5 and the record becomes decorative.
**Test criteria:** inserting a provenance-free claim is refused; each `world-model.vN` is content-addressed; the draft cites one specific version; replaying the same results onto `vN-1` reproduces `vN` exactly. `prediction_sealed_at` precedes every confirmatory measurement for that hypothesis. Calibration is **derived** from resolved predictions and never asserted — a calibration figure that no resolved prediction supports fails the check. A scoring implementation that cannot be moved by a hedged forecast fails its mutant.

### R12 — Wet-lab is a seam, not a capability
**Test criteria:** the adapter interface exists, is documented and raises `NotImplementedError`; a register asked to close a hypothesis whose executor is the wet adapter HALTs; no credential for any execution provider is read, referenced or required anywhere in the package.

### R13 — A run is reproducible
**Test criteria:** two runs over a recorded fixture with the same quest, seed, instinct pin and predicate shas produce identical register transition sequences.

### R14 — Identifier hygiene (F33)
**Test criteria:** a scan of tests, fixtures and message bodies with the published accession grammar returns 0 matches, with the grammar proven live in the same run by an invented probe that must match; real identifiers and release strings appear only in the methods section and the evidence directory.

### R15 — The reader can reach everything the deliverable cites
**Test criteria:** every path and document cited by the draft resolves inside the deliverable set; a citation to a file outside it fails the check. *A DOI-bearing artifact must not cite a document its readers cannot reach.*

### R16 — The dependency on the gate's trust core fails closed
`v2s` declares a hard dependency on `airdlc` with an explicit version floor *(A-7)*. A missing, unreadable or below-floor `airdlc` must stop the run at Stage 0 with a named blocker — never degrade to a local substitute, and never let a hypothesis close.
**Test criteria:** with `airdlc` absent, Stage 0 exits non-zero naming the missing dependency and its required floor; with `airdlc` present but below floor, the same; no code path constructs a fallback evaluator; a hypothesis cannot reach a verdict in either condition. The version floor is asserted against the installed plugin, not read from a config the run could edit.

### R17 — One argument, no flags
Everything else is derived, or declared at the single gate.
**Test criteria:** exactly one declared parameter; an invocation carrying flags is rejected rather than silently ignored.

### R18 — Feasibility is a capability probe, not a judgement
Whether a hypothesis is testable is decided by probing the tools that would have to run it, not by a model's opinion that it seems doable. ClawBio's `catalog.json` carries a maturity tier per skill (`spec-only` → `bench-validated`), so the probe distinguishes *absent* from *present but unvalidated*.
**Test criteria:** a hypothesis needing an absent tool yields `OPEN_INFEASIBLE` naming that tool; a hypothesis resting on a `spec-only` skill yields `OPEN_INFEASIBLE` naming the tier, not `OPEN_FEASIBLE`; a mutant that makes the probe always return true is killed.

### R19 — Refutations ship
Every hypothesis that reached a verdict appears in the draft with that verdict *(A-6)*.
**Test criteria:** the draft's hypothesis count equals the register's closed count; a draft omitting a REFUTED or INCONCLUSIVE hypothesis fails the check.

### R20 — One gate, and scope freezes at it
No hypothesis may be added after approval, and no question may be raised inside a drain.
**Test criteria:** adding a hypothesis to an approved register is refused; a drain that reaches a decision it cannot make HALTs rather than prompting.

### R21 — No internal vocabulary reaches a stranger
The glossary exists so the loop stays precise; nobody outside it agreed to learn the words. A drain is *a pass*, a hypothesis unit is *a hypothesis*, the register is *the worklist*, a sealed predicate is *a pre-registered analysis*.
**Test criteria:** a term scan over the draft, the decision record and the review surface returns zero internal terms; the scan is proven live by a probe term that must match.

### R22 — Third-party egress is declared, and never carries the input identifier
Some ClawBio skills send variants or sequences to public annotation APIs. Any skill that leaves the machine is declared before it runs, and what it sends is scanned by the same grammar that guards R14.
**Test criteria:** a skill not on the declared-egress list cannot be invoked; an egress payload carrying the input identifier, release or digest is refused before the request is made; the scan is proven live by an invented probe that must match. Declaring egress is not permission to send an identifier — the two checks are independent.

### R23 — A third-party tool layer can neither halt the gate nor be the gate
ClawBio is a soft, capability-probed dependency. Its absence degrades the run with a named reduction in capability; it never stops the gate and never renders a verdict.
**Test criteria:** with ClawBio absent, Stage 0 completes and marks the affected hypotheses `OPEN_INFEASIBLE` naming the missing skill — it does not HALT; no ClawBio return value can set a verdict; contrast R16, where a missing `airdlc` must stop the run.

### R24 — No exploratory measurement may reach a verdict
> **Added 2026-10-28** *(A-13)*. This requirement did not exist in the document approved on 2026-10-23. It emerged from `/design`: the experimenter controls what enters the measurement store, so on an under-specified hypothesis it can move a verdict by dilution or packing **without ever seeing the predicate** — the failure pre-registration alone does not fix.

Measurement is split. Exploratory measurement is adaptive and unlimited, permanently stamped `confirmatory: false`, and no predicate may ever resolve against it. The confirmatory phase runs a sealed measurement plan the experimenter declares before the run. R2 is absolute and unqualified here — the experimenter **never** sees the predicate, at any point — and the plan's seal is a second, independent lock: it fixes the measurement set before any data exists, so neither side can be shaped around the other even in principle. Every claim derived from exploratory data carries that label wherever a reader meets it.
**Test criteria:** a predicate selector that resolves an exploratory record HALTs rather than evaluating; `n_resolved != n_planned` HALTs; a confirmatory record outside the sealed plan HALTs; a draft figure sourced from exploratory data without the label fails the check. The statement handed to the experimenter carries targets only — a payload containing the expectation or credence fails, over a fixture where it is present.

---

## Open questions

| # | Question | Why it is open | Who resolves |
|---|---|---|---|
| OQ-2 | What is the proof-of-value quest? | AS-4 proposes the protein-stability area this repo already instruments; not yet chosen or stated | Principal |
| OQ-3 | Does `/v2s:bio` reuse Aviary's shipped environments (LitQA, SeqQA, molecular cloning) or only custom ones? | Reuse buys validated tasks and a comparison baseline; it also imports their assumptions | `/design`, after reading the Aviary repo |
| OQ-5 | Is `/v2r-loop` **deleted** or **deprecated with a pointer**? | "drop" was the word used. The published whitepaper names `v2r-loop`; deleting leaves it citing a command that does not exist. A dated note in `SUBMIT.md` is the honest form either way | Principal |
| OQ-6 | Weave span retention | R10 makes the decision record depend on spans still resolving when someone reads the draft. If retention expires before that, the record degrades to prose | `/design` |
| OQ-7 | Each of AS-1 … AS-6 above | Assumptions stand until confirmed; none blocks plan-validity, all must stay visible | Principal |
| OQ-8 | How does the PVR become durable? `workstreams/` is git-ignored (`.gitignore:13`) and tracked on zero refs, so this approval is pinned to a content hash of a file on one disk rather than to a commit. Three options: track `workstreams/` in Aviary-BioSim as bioFM does; force-add the PVR as a deliberate exception; or accept that the approval rests on one disk. Overturning the repo's own ignore policy is a decision, not a correction, so it is not mine | Principal |
