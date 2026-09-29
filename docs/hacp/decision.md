# §decision

<!-- HACP L1 · local source; the Notion Section row mirrors this file. -->

**Tag:** `§decision` · **Layer:** L1 · **Holds:** open questions the principal owns · **Reaches:** —

Each item is a choice, not a request for prose. The options are the ones the source documents already price; where the source ranks them, the ranking is the source's, not this page's.

## Open

### 1. How to fix the lessons pin *(raised 2026-09-17)*

The pin moves when nothing was learned ([§risk](risk.md) row 2). [ADR-0003](../adr/0003-instincts-pinned-per-drain.md) ranks three fixes, cheapest first:

| Option | What it does | What it forecloses |
|---|---|---|
| **A** — hash the lesson bodies, excluding the volatile header fields | The pin stops moving on reinforcement alone | Does not stop the store changing mid-pass |
| **B** — snapshot the store at the start of a pass and build against the snapshot | Enforces the rule instead of documenting it | More machinery inside the trusted tool |
| **C** — have the close step stage explicit paths instead of everything | Narrowest change | Touches how an implementer's work is committed at all |

The change lives inside the trusted tool, so whichever is chosen needs its own gate. Not started; not authorised.

### 2. Whether to run a second pass *(raised 2026-09-17)*

A second pass would be the first with a non-empty lessons pin and the first that could drift. It is out of scope for the white paper, which states the preconditions for measuring improvement without executing them.

| Option | Consequence |
|---|---|
| **A** — after decision 1 is fixed | The pass is attributable; the paper still reports no measured improvement |
| **B** — now, under the approximate pin | Any improvement seen could not be attributed to lessons |
| **C** — not before the paper ships | The paper's limitations section stands as written |

### 3. The token price for the discovery loop *(raised 2026-09-17)*

`BIOSIM_USD_PER_1M_TOKENS` has no default and the loop refuses to start without it ([`science/run_discovery.py`](../../science/run_discovery.py)). Until a provider price is supplied, budget enforcement has never run end to end, and [`SUBMISSION.md`](../../SUBMISSION.md) says so. A single blended price under-meters output-heavy calls ([`docs/deferred-findings.md`](../deferred-findings.md) row F14) — supply one number and document it as an upper bound, or supply two.

### 4. A capability with no caller *(raised 2026-09-17)*

Requirement R5 in [`docs/demo-spec.md`](../demo-spec.md) exposes the spend meter as an agent-callable tool. The agent-facing record tool was later removed on a principal ruling — the agent is the party being metered, so it is offered nothing that writes the ledger ([`docs/deferred-findings.md`](../deferred-findings.md) row F05). The capability remains, tested and unused. Keep it (a standing requirement is never closed) or withdraw R5.

Back to the [index](index.md).
