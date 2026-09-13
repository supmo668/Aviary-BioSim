---
name: v2r-loop
description: Vision to reality. Takes a single free-text vision and carries it to a reviewed branch of working, individually-tested code. An attended head aligns the vision - researching open questions, grilling it until its boundary is decided, fixing the domain language, writing the spec, planning the implementation, and emitting a committed interface skeleton - which you approve once, declaring the ceilings the run may spend. An unattended body then drains it one build unit at a time, each written by an implementer that never sees its test and tested by an author that never sees the implementation, each close earned by a gate that re-runs the test itself. Failed units are reverted out of the tree and preserved on a branch, so the drain never leaves broken code behind. Between drains it reads its own execution traces, captures what it learned, and retries only what failed, stopping when it stops improving. Never writes the trunk, never lands its own PR, and cannot widen its scope after approval. Use when a vision needs building out end to end and you want to be involved once rather than continuously.
argument-hint: "<vision>"
---

# /v2r-loop — vision to reality

**Input:** `$ARGUMENTS` — the vision. The only parameter. No flags.

Spec: `docs/spec.md` · Glossary: `docs/CONTEXT.md` (use its vocabulary exactly) · Decisions: `docs/adr/0001`–`0004`.

```bash
R="uv run --with pyyaml .claude/skills/v2r-loop/scripts/register.py"
```

## Stage 0 — Preflight and unblock

Resolve access from available credentials and MCP servers. Report any blocker you cannot
resolve and **stop before the gate** — never work around one, never ask mid-drain.

| Blocker | Where it resolves |
|---|---|
| Inference compute | W&B Inference (serverless — no GPU on the critical path) |
| `WANDB_API_KEY` | Infisical `biofm/dev`, or `.env` |
| Trace read | `wandb` MCP server |

Confirm you are **not** on the trunk branch. If you are, stop.

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

## Never

- Write the trunk, or land a PR.
- Add a build unit that was not in the approved register.
- Assert a close. Only `register.py close` closes a unit.
- Show the implementer the sealed test, or the test-author the implementation.
