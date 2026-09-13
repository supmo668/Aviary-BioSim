# Drain 1 — what the proving run actually showed

Run record: `.v2r/run-record-1.yaml` (untracked; `.v2r/` is run state).
Outcome: **6 closed, 0 parked**, every unit on attempt 0.

| Unit | satisfies | closed |
|---|---|---|
| U-001 `record` + `total` | R1 | attempt 0 |
| U-002 `load_ceiling` | R2 | attempt 0 |
| U-003 `BudgetExceeded` carries its numbers | R3 | attempt 0 |
| U-004 `check` boundary | R3 | attempt 0 |
| U-005 `persist`/`restore`, crash-atomic | R4 | attempt 0 |
| U-006 `as_tool` → `aviary.core.Tool` | R5 | attempt 0 |

## The shape all of these share

Every finding below is one failure mode, and it is the honest limitation of this design:

> **A mechanism reports success while the property it exists to guarantee is absent.**

`weave.publish` succeeded and printed a confident URL while writing evidence nothing could
read. The register pins the instinct set, the seed and the register digest, but not the two
per-unit prompts where the difficulty actually lives. The instinct pin is computed exactly and
does not identify what it names. In each case the mechanism ran, returned, and looked right.

The sealed gate is built to catch a **build unit** that FAILS, and it is very good at that —
`close` re-runs the test itself and refuses anything short of an observed pass. It is blind to
a mechanism that PASSES FOR THE WRONG REASON, because passing is the only signal it reads.
All three findings below were caught by hand; none of them would have parked a unit, and drain
1 closed 6 of 6 with all three present.

The practical rule: verify a mechanism by observing the property it promises, from the outside,
not by confirming the mechanism ran. The Weave fix was verified by querying the trace back
rather than by reading `emit_span`, and that is the only reason it is known to work.

## The park that didn't happen

U-005 was chosen to be genuinely hard — crash-atomicity is difficult to implement and
difficult to test black-box — and the drain was expected to park it. It closed first try.

The honest reason is not that the unit was easy. It is that the implementer prompt named
the durable-write pattern outright ("serialise elsewhere, then put it into place with a
single operation that either fully happens or does not"). That is most of the answer. A
neutral prompt stating only the requirement would very plausibly have parked.

This is the drain's most useful finding, and it is about the loop rather than about
SpendTracker: **the register pins the instinct set, the seed and the register hash, but
nothing pins the two prompts**, and the prompts are where the difficulty actually lives.
`docs/CONTEXT.md` claims a drain is replayable — "the same register, the same instinct pin
and the same seed must reproduce the same closes and parks". That claim does not hold while
the prompts are free variables. Either template them per unit and hash them into the run
record, or narrow the claim.

No `park/U-nnn` branch exists for this drain. One was not manufactured.

## Two decomposition defects, caught at the gate

The register was re-gated before the first claim. The original 6 units contained two that
were not independently testable:

- `record` had no observable surface until `total` closed.
- `check raises BudgetExceeded` was ordered before the unit that filled
  `BudgetExceeded.__init__`, so constructing the exception raised `NotImplementedError`.

Both would have exhausted `max_attempts` and parked for reasons having nothing to do with
the implementer. In the register such a park is **indistinguishable** from one earned by
hard work — which would have made it the centrepiece of a demo about a gate that works.
Fixed by merging the first pair and ordering the carrier before its raiser.

The general rule: every unit must be testable using only the units ordered before it.

## Stage 4 cannot read stage 3's evidence

`SKILL.md` stage 4 says to query the drain's spans with `query_weave_traces_tool`. For this
drain that returns **zero** — while six `unit.close` records sit in the project.

`emit_span` calls `weave.publish(payload, name=name)`, which writes a weave **object**, not
a call/trace span. Objects and traces are different stores and the trace query never sees
the former. Note also that the six closes are six **versions of one object** named
`unit.close`, not six separate objects.

Reading them requires the object API instead:

```python
c = weave.init("3m-m/Aviary-BioSim")
for o in c._objects():
    if o.object_id == "unit.close":
        weave.ref(f"weave:///3m-m/Aviary-BioSim/object/unit.close:{o.digest}").get()
```

So a drain can be perfectly instrumented and still be unreadable by its own documented
procedure. Instrumented and readable are different properties.

**Fixed after drain 1.** `emit_span` now calls a `@weave.op`-decorated function named for the
transition, so each span is a real traced call. Verified by querying it back rather than by
reading the code: `count_weave_traces_tool` went from 0 to non-zero, and a filter on the op
name returns the call with its attributes as inputs and output.

Worth noting `docs/spec.md` "Known gaps" already prescribed `@weave.op` spans — *"`register.py`
must emit its own `@weave.op` spans per iteration"*. The implementation reached for
`weave.publish` instead and nothing caught the divergence, because publishing succeeded and
printed a confident URL. The spec was right and the code drifted from it silently.

**Drain 1's evidence still needs the object API.** Its six closes were published as object
versions before the fix and are deliberately left as they are — re-emitting them now as calls
would fabricate trace evidence with the wrong timestamps, asserted by me rather than observed
by the gate. Drain 2 onward is queryable as calls.

## Why the instrumentation gap was visible at all

`emit_span` prints its first failure to stderr rather than swallowing it. Without that, the
missing `weave` dependency in the register's environment would have dropped every span in
silence: all six units would still have closed, the run record would have looked perfect,
and the Weave project would have been empty — discovered at the demo rather than at the
drain. The `$R` invocation needs `--with weave --with fhaviary`; `SKILL.md` now says so.

## The instinct pin does not mean what it claims

Found immediately after the drain, while verifying the tree was clean: four instinct files
had changed on their own. A Stop hook reinforces any instinct whose triggers match files
just touched — confidence `+0.05`, `last_reinforced` rewritten — and `instinct decay`
rewrites confidence on a timer. No learning was adopted; the store simply moved.

The pin is `git rev-parse HEAD:.aiadlc/instincts`, a tree SHA, so:

1. **Two drains can carry different pins with an identical instinct set.** A divergence
   can no longer be attributed to instincts by comparing pins — which is the pin's entire
   job, and which matters more now that the surrounding claim has been narrowed to
   attribution.
2. **The store can change *during* a drain.** `cmd_close` runs `git add -A`, so
   hook-mutated instinct files are swept into unit commits mid-drain. `CONTEXT.md` states
   that learned behaviour is "only ever *adopted* between drains, never during one"; nothing
   currently enforces that. Drain 1 was immune only because `.aiadlc/instincts` did not exist
   until stage 4.

Candidate fixes, cheapest first: hash the instinct *bodies* and exclude the volatile
frontmatter (`confidence`, `last_reinforced`) from the pin; or snapshot the store at
drain-start and build against the snapshot; or have `close` stage explicit paths rather than
`git add -A`. Not fixed here — it is register-level work and wants its own gate.
