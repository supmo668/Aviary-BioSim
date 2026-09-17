---
name: v2r-loop
description: Vision to reality. Takes a single free-text vision and carries it to a reviewed branch of working, individually-tested code. An attended head aligns the vision - researching open questions, grilling it until its boundary is decided, fixing the domain language, writing the spec, planning the implementation, and emitting a committed interface skeleton - which you approve once, declaring the ceilings the run may spend. An unattended body then drains it one build unit at a time, each written by an implementer that never sees its test and tested by an author that never sees the implementation, each close earned by a gate that re-runs the test itself. Failed units are reverted out of the tree and preserved on a branch, so the drain never leaves broken code behind. Between drains it reads its own execution traces, captures what it learned, and retries only what failed, stopping when it stops improving. It then turns the run into three human-readable deliverables: the domain document the vision asked for, an interpretability report reconstructing every decision and what it cost, and a navigable presentation deck with speaker notes. Never writes the trunk, never lands its own PR, and cannot widen its scope after approval. Use when a vision needs building out end to end and you want to be involved once rather than continuously.
argument-hint: "<vision>"
---

# /v2r-loop — vision to reality

**Input:** `$ARGUMENTS` — the vision. The only parameter. No flags.

Spec: `docs/spec.md` · Glossary: `docs/CONTEXT.md` (use its vocabulary exactly) · Decisions: `docs/adr/0001`–`0004`.

```bash
R="uv run --with pyyaml --with weave --with fhaviary .claude/skills/v2r-loop/scripts/register.py"
```

## Stage 0 — Preflight and unblock

Resolve access from available credentials and MCP servers. Report any blocker you cannot
resolve and **stop before the gate** — never work around one, never ask mid-drain.

| Blocker | Where it resolves |
|---|---|
| Inference compute | W&B Inference (serverless — no GPU on the critical path) |
| `WANDB_API_KEY` | Infisical `biofm/dev`, or `.env` |
| Trace read | `wandb` MCP server (`query_weave_traces_tool`) |
| Trace write | `weave.init(WANDB_PROJECT)` + `@weave.op` on every stage |
| Spend meter | `spend record` / `spend check --cap` — halts on exit 3 |

```bash
export V2R_TRACE=1                       # without it every span is dropped
export WANDB_API_KEY=...                 # Infisical biofm/dev, or .env
export WANDB_PROJECT=<team>/<project>
```

**`@weave.op`, never `weave.publish`.** `publish` writes an *object*, not a call: it
succeeds, prints a confident URL, and is invisible to the trace query that Stage 4 and D2
both depend on. Verify by querying the traces back, not by reading the code — instrumented
and readable are different properties, and this exact drift has already happened once.

Confirm you are **not** on the trunk branch. If you are, stop.

`weave` must be in the register's own environment whenever `V2R_TRACE=1`. `emit_span`
imports it lazily, so without it every span is dropped — one warning on stderr, then a
drain that looks perfect and a stage 4 with nothing to read. Add `fhaviary` likewise once
a sealed test imports `aviary.core`. Both belong in the `$R` invocation, not in a project
requirements file: the gate runs under the interpreter `uv` builds for `register.py`.

## Stage 1 — Alignment (attended)

A vision is not a specification. Close that gap in order:

1. **`/research`** — ground the open questions. Skip when the vision stands on
   well-understood ground.
2. **`/grill-with-docs`** — one question at a time until the boundary is decided and every
   fuzzy term is sharpened against the glossary. Update `CONTEXT.md` inline; write an ADR
   when a decision is hard to reverse, surprising, and a real trade-off. **Terminology
   collisions caught here cost a sentence; caught in the register they cost a drain.**
3. **`spec.md`** — standing requirements `R<n>`. Never closed.
4. **`/writing-plans`** — the ordered implementation plan.
5. **`register.yaml` + `skeleton/`** — decompose the plan into build units `U-nnn`, each
   carrying `satisfies: R<n>`; emit real modules with real signatures and
   `NotImplementedError` bodies, one stub per unit. Commit the skeleton.

## Stage 2 — The gate (the last human checkpoint)

Present the aligned set and stop. Approval fixes scope permanently, declares the ceilings,
and grants standing authorization to push the branch and open a PR. **Do not proceed without
it.**

## Stage 3 — Drain (unattended)

```bash
START=$(date +%s)
$R drain-start --drain "$N" --seed 1337
while unit=$($R next); do
  $R check --started-at "$START" || break          # exit 3 = halt the drain
  $R claim "$unit"
  # test-author subagent: sealed test from the unit statement + skeleton ONLY
  $R seal "$unit"
  # implementer subagent: fill the stub; never shown the sealed test
  $R close "$unit"                                 # 0 closed · 1 retry · 3 HALT
done
$R drain-end --outcome completed
```

- Dispatch **two separate subagents** per unit. The test-author gets the unit statement and
  the skeleton; the implementer gets the unit statement and the stub. Neither sees the
  other's output.
- `close` returning **1** means retry, up to `max_attempts`, then
  `$R park "$unit" --evidence <pytest output>`.
- `close` returning **3** is a **halt**, not a park. Stop the drain.
- A park is local. Do not infer that any other unit is blocked. Do not add `blocked_by`.

At drain end, push the branch and `gh pr create`. **Never write the trunk. Never land the
PR.**

## Stage 4 — Between drains

1. `query_weave_traces_tool` over this drain's spans (`unit.attempt`, `unit.close`,
   `unit.park`, `unit.halt`) — which units parked, at which attempt, on what failure.
2. `instinct capture` per durable lesson, with the drain's touched paths as `--triggers`.
3. Commit `.aiadlc/instincts`; the new pin is `$R pin`.
4. Drain *n+1* retries **only parked units**.

Stop when a drain closes zero new units, or `max_drains` is reached. Report the parked list.

Then go to **Stage 5** — the run is not finished until all three deliverables exist.

## Stage 5 — Deliverables (the run must produce all three)

A drain that leaves only a branch has not finished. Every run ends in three artifacts,
each built **only** from what the run actually produced. No figure may show a number the
run did not compute, and no label may be written from your guess when the source says
otherwise — check it against the data that came back.

### D1 · The domain document

Whatever the vision asked for, written properly for its field. A scientific vision yields
a paper-shaped document — abstract, introduction, hypothesis, methods, expected results,
discussion, references. A software vision yields a design document. Match the field's own
conventions; the vision names the domain, not you.

**Every figure comes from a run that happened.** If the vision admits a computable check —
a model, a dataset, a benchmark — run it and chart the real output. State plainly what was
executed and what was not. A predicted result presented as a finding is the one failure
that discredits everything else on the page.

### D2 · The interpretability report

Reconstruct the decision tree from the traces, not from memory:

```bash
# the traces are already there — every stage is a @weave.op
query_weave_traces_tool   # which calls ran, in what order, at what cost
$R pin                    # the instinct set this drain ran under
```

For **each fork**: the options that existed, which was taken, and — side by side — why
each rejected branch lost, in the agent's own stated terms. Against every layer put the
**running cost to that point**, in completion tokens or metered spend. A fork with no
alternatives is not a fork; say so and move on rather than inventing a branch.

Close with what the report does *not* establish. A trace shows what an agent said its
reasons were, never what caused the output, and that distinction belongs on the page.

### D3 · The presentation deck

Scientific structure, one idea per slide:

| | |
|---|---|
| 1 | Title — the claim in one line |
| 2 | **Problem / hypothesis** |
| 3 | **Solution & methods** — what was reasoned, what was adopted |
| 4–5 | **Product** — the figures, from real runs |
| 6 | **Conclusion** |
| 7 | **Discussion** — limitations, stated before anyone asks |

Required behaviour: one slide visible at a time, `←` / `→` to navigate, **`n` toggles
speaker notes**, a clickable progress rail and a slide counter. Terse on the slide, full
technical detail in the notes — every slide carries notes, always. The notes are where the
mechanism, the exact numbers, and the answers to the obvious challenges live.

### Deliverable rules

- **No internal vocabulary on a deliverable.** The glossary exists so *this loop* stays
  precise; it is not language a reader has agreed to learn. Terms like **drain**, **build
  unit**, **register**, **park**, **sealed test** and **instinct pin** belong in the code and
  the design docs, never on a slide or in a report a stranger reads. Say what the thing does:
  a drain is *a pass*, a build unit is *a task*, parking is *setting work aside*, the register
  is *the worklist*, a sealed test is *an independent test*. If a term genuinely has no plain
  equivalent, define it once, in the sentence where it first appears.
- **The deck ships a `?present` mode.** Speaker notes forced off and un-toggleable, the notes
  hint hidden, navigation unchanged — so one link is safe to hand to a stranger and another
  keeps the notes for the person presenting.
- **Schematics over paragraphs.** A flow, a tree, a chart or a labelled table beats prose
  wherever it can carry the same content.
- **Both themes, one gutter, phone width.** These get read on someone else's screen.
- **Every chart drawn to its scale**, with the axis labelled in the units the run produced.
- **Name the limitations yourself.** Whatever a reader would object to, say it first.

## Never

- Write the trunk, or land a PR.
- Present a predicted or seeded number as a measured one.
- Label a figure from your own assumption when the source data says otherwise.
- Add a build unit that was not in the approved register.
- Assert a close. Only `register.py close` closes a unit.
- Show the implementer the sealed test, or the test-author the implementation.
