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
