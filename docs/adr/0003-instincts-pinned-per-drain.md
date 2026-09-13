# Instincts are pinned for the duration of a drain

The loop improves across **drains** and refuses to improve during one. The instinct set is
hashed at drain start, written to the **run record**, and does not change until the drain
ends — even though aiadlc's Stop hook keeps reinforcing instincts throughout.

The learning substrate is **aiadlc's existing instinct layer**, not a second system. It
stores at `.aiadlc/instincts`, surfaces via the SessionStart hook, reinforces via the Stop
hook against touched-file triggers, and is configured under `agency.yaml instincts.*`. A
parallel store would mean two sets of instincts, two confidence semantics and two SessionStart
surfaces, with neither authoritative.

Because that store is in-repo and not gitignored, the **pin needs no new machinery at all**:

    instinct_pin = $(git rev-parse HEAD:.aiadlc/instincts)

an exact tree SHA, already versioned, already replayable.

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
