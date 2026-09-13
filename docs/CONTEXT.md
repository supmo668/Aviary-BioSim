# V2R Loop

The loop that turns one stated vision into working code — aligning the vision into a
bounded specification, then discharging it one independently-testable behaviour at a time. This glossary fixes the language of the register and its gate, where
several terms are already spoken for by the ChipSim context and must not be borrowed
loosely.

## Language

### The work

**Vision**:
The single free-text statement the user authors, and the loop's only parameter. Not yet a
specification: it states an intent whose boundary, vocabulary and open questions are all
still undecided.
_Avoid_: objective, goal, prompt (each suggests something already bounded)

**Alignment**:
The attended phase that turns a **vision** into a bounded specification — research, then
adversarial interview, then requirements, then a plan. It is a conversation and it is the
only place a human is involved besides the approval gate.
_Avoid_: preamble, planning (the first understates it, the second names one of its four moves)

**Requirement**:
A standing claim about what the system must do, authored by a human in a PVR or A&D and
identified `R<n>`. Enforced for the life of the project; **never closed**. R9 ("Modal spend
is tracked and the run halts before exceeding the declared credit") stays true across every
later refactor, so no amount of completed work discharges it.
_Avoid_: using this for a unit of work

**Build unit**:
One atomic, independently-testable behaviour derived from a **requirement**, identified
`U-nnn` and carrying `satisfies: R<n>`. Discharged by its **sealed test** and closed exactly
once. One requirement yields one-to-many build units; the relation is the only coupling
between a spec and the loop.
_Avoid_: task (spoken for by aviary's `TaskDataset` and aiadlc's plan decomposition), slice
(spoken for by the build plans, and implies the tracer-bullet model this loop rejects),
obligation (ADR-0002 uses it for a standing duty, the opposite sense)

**Interface skeleton**:
Real modules with real signatures and `NotImplementedError` bodies, committed before a
**drain** starts. The one artifact both the sealed **test-author** and the implementer read,
so the symbols they each bind to cannot disagree. Each stub names the **build unit** that
fills it.
_Avoid_: stubs, scaffolding (both suggest throwaway code; the skeleton is the contract and
survives)

**Approved artifact**:
What the single human gate actually covers: the spec, the **register**, and the **interface
skeleton** together. Approving it fixes the scope of every subsequent **drain** permanently —
no later drain may add a **build unit** that was not in it.

**Register**:
The durable, ordered set of **build units** and their states. It is the loop's entire
memory — there is no second state file. Every transition is made by the register CLI, never
by an agent editing the file.

**Iteration**:
One pass of the inner loop: claim the next open **build unit**, build it, run its **sealed
test**, then **close** or **park** it.

**Drain**:
One complete pass over a **register** under a single pinned **instinct set** — every
**iteration** from the first claim until no open **build unit** remains. The unit of replay:
the same register, the same instinct pin and the same seed must reproduce the same closes and
parks. Successive drains are how the loop improves; within a drain nothing about the builder
changes.
_Avoid_: run (ChipSim already uses "run" for a lung-on-chip run, the thing a curated chip
record records), pass, cycle

**Run record**:
The artifact that makes a **drain** reproducible — the register hash, the **instinct pin**,
the seed, and the resulting closed and parked lists. Written once per drain.

**Instinct pin**:
The hash of the instinct set, frozen at the start of a **drain** and recorded in the **run
record**. Learned behaviour accumulates continuously via hooks but is only ever *adopted*
between drains, never during one.
_Avoid_: treating the live instinct store as the builder's configuration

### The gate

**Sealed test**:
The test that discharges a **build unit**, written from the unit's text alone by an author
that never sees the implementation, and never shown to the implementer. Named by analogy
with ChipSim's **sealed allocation**: fixed before the actor it constrains gets to see it.
_Avoid_: acceptance test, unit test (the sealing is the whole point; a name that omits it
invites someone to let the implementer write it)

**Close**:
The transition of a **build unit** to its terminal satisfied state. Performed only by the
register CLI, and only after the CLI has itself run the **sealed test** and observed a pass.
An agent cannot assert a close.
_Avoid_: done, complete, pass

**Park**:
The transition of a **build unit** to blocked, carrying the failure evidence, after its
attempt budget is spent. The loop simply continues to the next unit. Parking is a normal
outcome, not an error — a single stubborn unit must not stall a build-out.

A park is **local**: it says nothing about any other unit. There is no dependency graph, no
cascade, and no inference about what else the failure might block. A unit that needed the
parked work fails on its own terms and parks on its own terms, and the resulting parked list
is triaged by a human in one pass. This is deliberate — the cascade machinery was priced and
declined, because it would be built against a predicted cost before the loop has run once.
_Avoid_: fail, skip, defer, blocked_by

**Halt**:
The abandonment of a **drain** when a declared ceiling is breached — drains, attempts,
wall-clock or spend. Distinct from **park**: a park retires one **build unit** and the drain
continues; a halt ends the drain with every unit left as it stood. The **register**, the
`park/*` branches and the **run record** all survive a halt, so a halted drain is resumable.
_Avoid_: stop, abort, fail (each loses the park/halt distinction)

## Standing rules

**The actor that does the work never records that the work passed.**

This is the same principle as ChipSim's **frozen evaluator** — "immutable, versioned, outside
the agent's write scope" — one altitude up, and the A&D's warning that "the ratchet is the
thing that overfits" is the reason. An agent that has just spent three attempts on `U-014` is
the worst-placed actor in the system to decide `U-014` is closed. Three independent
precedents in this repo's tooling already encode it: ChipSim's frozen evaluator, prp-loop's
`VALIDATION: GREEN` sentinel and `--validate` command, and aiadlc's QGR receipts.

The practical consequence is that the register CLI, not the model, owns every transition,
and `close` re-runs the sealed test rather than trusting a report of it.

**A drain is attributable to exactly one builder.**

ChipSim's **replay test** in its PoC form — *same config and seed reproduces the same scores
exactly* — has a build-layer analogue, and the **instinct pin** is what preserves it. A loop
that adopted new instincts mid-drain would build `U-001` and `U-023` with materially
different agents, so the same register replayed would produce different code and the
incoherence would have no recoverable cause. This is the same discipline as the audit's R2,
"pre-registration frozen before the first complex".

## Flagged ambiguities

**"Ratchet" names two different mechanisms.** ChipSim's ratchet is *keep-if-better on a gate
scalar* — the same goal re-attempted, the attempt retained only when the scalar improves. The
V2R Loop's register is *monotonic state progression* — a unit moves open → closed or
open → parked and never moves back, with no comparison and no scalar. Both are called
ratchets in ordinary speech and they share no mechanism. **Use "the register is monotonic"
for this context and reserve "ratchet" for ChipSim.**

**"Requirement" collided across contexts and the collision was load-bearing.** The chipsim
PVR's `R1`–`R10` read like build units — R1 and R9 especially — which invites treating the
PVR as a runnable register. Doing so marks standing properties closed and stops enforcing
them. **Resolved: requirements are standing and are never closed; build units are derived,
backlinked, and closed exactly once.**

## Example dialogue

> **Dev:** R9 is done — the budget guard is in, spend is tracked, it halts at the floor.
>
> **Domain expert:** R9 isn't a thing that gets done. It's a standing requirement. What you
> closed is three build units that satisfy it.
>
> **Dev:** Practically, though — the code's written. What's the difference?
>
> **Domain expert:** The difference shows up in six weeks when someone adds a second
> submission path that doesn't go through the tracker. R9 is still true as a claim, and now
> it's violated. If we'd marked R9 closed, nothing would be watching it. The build units are
> closed; the requirement is standing.
>
> **Dev:** So a new unit gets opened against the same R9.
>
> **Domain expert:** Right — `satisfies: R9`, same as the first three. And it gets its own
> sealed test, written by someone who hasn't seen your new path.
>
> **Dev:** Can I not just write that one myself? I know exactly what's broken.
>
> **Domain expert:** That's precisely why you can't. You'd write the test that your fix
> passes.
