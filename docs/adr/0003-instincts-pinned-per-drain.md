# Instincts are pinned for the duration of a drain

_Amended after drain 1: the mechanism below does not enforce what this paragraph intends.
See **Correction, after drain 1**._

The loop is intended to improve across **drains** and to refuse to improve during one. The
instinct set is hashed at drain start and written to the **run record**, and it is *intended*
not to change until the drain ends — even though aiadlc's Stop hook keeps reinforcing
instincts throughout. That intent is currently **not enforced**: the same Stop hook rewrites
the store, so the pin can move with nothing learned, including mid-drain.

The learning substrate is **aiadlc's existing instinct layer**, not a second system. It
stores at `.aiadlc/instincts`, surfaces via the SessionStart hook, reinforces via the Stop
hook against touched-file triggers, and is configured under `agency.yaml instincts.*`. A
parallel store would mean two sets of instincts, two confidence semantics and two SessionStart
surfaces, with neither authoritative.

Because that store is in-repo and not gitignored, the pin was taken to need **no new
machinery at all**:

    instinct_pin = $(git rev-parse HEAD:.aiadlc/instincts)

a tree SHA, already versioned.

**Correction, after drain 1 — this decision was cheaper than it was correct, and the opening
paragraph above overstates what happens.** The instinct set is read at drain start and written
to the run record, but it does **not** "not change until the drain ends", because nothing
enforces that. The same Stop hook named above rewrites `confidence` and `last_reinforced` on
any instinct whose triggers match touched files, and `instinct decay` rewrites `confidence` on
a timer. Both move the tree SHA. Therefore:

- The pin changes when **nothing was learned**, so identical instinct sets can carry different
  pins and a pin comparison cannot attribute a divergence to instincts.
- `cmd_close` runs `git add -A`, so hook-mutated instinct files can be committed **inside a
  drain**, against this ADR's central claim.

Drain 1 was unaffected only because `.aiadlc/instincts` did not exist until its stage 4. Drain
2 is the first drain with a non-null pin and the first that can drift.

The decision itself stands — pinning per drain is still right, and the aiadlc store is still
the correct substrate. What is withdrawn is "needs no new machinery". Ranked candidates: hash
instinct *bodies* excluding volatile frontmatter; or snapshot the store at drain start and
build against the snapshot; or have `close` stage explicit paths. Deferred to the gate, since
the pin is computed inside the trusted component.

A reader will assume continuous learning is the entire point of a self-improving loop and try
to remove this. The reason it is here: ChipSim's **replay test** in its PoC form requires that
the same config and seed reproduce the same result exactly, and that has a build-layer
analogue. A loop adopting instincts mid-drain builds `U-001` and `U-023` with materially
different agents. The same register replayed then produces different code, and when the result
is stylistically incoherent across a single run the cause is unrecoverable — the evidence is
spread across a mutating store with no version. This is the same discipline as the audit's R2,
"pre-registration frozen before the first complex".

## Consequences

The cost is learning latency: a lesson from `U-003` cannot help `U-004`, only the next drain.
That was judged cheap, because a drain is the natural improvement unit anyway — the outer loop
retries parked units under a fresh pin, which is precisely where a lesson pays off.
