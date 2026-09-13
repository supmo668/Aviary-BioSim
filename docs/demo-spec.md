# Proving run — SpendTracker

The vision, as stated:

> A SpendTracker that records per-call cost, totals it, loads a declared floor from
> config, raises BudgetExceeded above the floor, and survives a process restart.

This is a **proving run** for `/v2r-loop`: a register small enough to drain in one sitting,
whose purpose is to exercise the loop end-to-end with real sealed tests and real
implementers. It is not the aviary environment.

## Requirements

Requirements are **standing**. None of them is ever closed; the build units derived from
them are. (`docs/CONTEXT.md` → Requirement, Build unit.)

**R1 — Spend is observable.**
Every model call's cost is recorded against the call that incurred it, and the total spent
so far is available at any time.

**R2 — The ceiling is declared, not coded.**
The spend ceiling is read from configuration. A build that hard-codes it violates R2 even
if every unit below is closed.

**R3 — The run refuses to proceed past the ceiling.**
Once recorded spend has passed the declared ceiling, the tracker refuses to continue, and
the refusal is attributable: it carries what was spent and what the ceiling was.

**R4 — Spend survives a restart.**
Recorded spend is durable across a process restart, so a resumed run cannot silently
reset its budget back to zero. Durability includes crash-atomicity: a reader must never
observe a partially written state file.

## Boundary

In scope: recording, totalling, ceiling configuration, refusal, durable state.
Out of scope: pricing tables, provider APIs, concurrency across processes, retry policy.
