# §risk

<!-- HACP L1 · local source; the Notion Section row mirrors this file. -->

**Tag:** `§risk` · **Layer:** L1 · **Holds:** known gaps, proxies, anything unverified · **Reaches:** the deferred-findings list, the pass-1 notes, the decision records

**TL;DR** — Every gap below has the same shape, and the project says so about itself: a mechanism ran, returned, and looked right while the property it exists to guarantee was absent. Six are open.

## Known gaps

| # | Gap | What it means for a reader | Status | Where recorded |
|---|---|---|---|---|
| 1 | **The demo seeder overwrote the live run state.** `dashboard/seed_demo_run.py` writes a made-up 23-task, 3-pass story into the same `.v2r/` directory the real loop writes to, and did so in the main checkout, over pass 1's own record. | Any pass-to-pass improvement seen on a dashboard fed from that directory is fiction. The public dashboard page discloses this ([`artifacts/dashboard.html`](../../artifacts/dashboard.html)); pass 1 is reconstructed from version control instead. | Open — fix planned as the white paper's first build item: the seeder must refuse a live directory | [`dashboard/seed_demo_run.py`](../../dashboard/seed_demo_run.py); [§build](build.md) |
| 2 | **The lessons pin moves when nothing was learned.** It is a hash over a store that background hooks rewrite, so two passes with identical lessons can carry different pins, and the store can change mid-pass. | Comparing pins cannot attribute a difference between passes to lessons, which is the pin's only job. Pass 1 was immune by accident — the store did not yet exist. | Open — three fixes ranked, none chosen | [ADR-0003](../adr/0003-instincts-pinned-per-drain.md) § Correction; [`docs/CONTEXT.md`](../CONTEXT.md) § Flagged ambiguities |
| 3 | **Budget enforcement has never run end to end.** The discovery loop refuses to start without a declared token price, and none has been supplied. | The budget guard is built and tested, not exercised in anger. The 66-measurement run predates it. | Open — a decision the principal owns | [`SUBMISSION.md`](../../SUBMISSION.md) § Status |
| 4 | **F31 — a held security finding** about the integrity of the sequence cache's read path. | The published science numbers were computed where the cache had no integrity check, so their provenance is not verifiable from the repo. Detail is withheld because the repo is public. | Open — held | [`docs/deferred-findings.md`](../deferred-findings.md) row F31 |
| 5 | **The two per-task prompts are not pinned.** The worklist pins the seed, the worklist digest and (approximately) the lessons; not the prompts that brief the test author and the implementer. | The same worklist replayed by a different driver can close and set aside different tasks with every declared input identical. The documented claim is attribution, not reproduction. | Open — prompt templating is the known path to the stronger claim | [`docs/CONTEXT.md`](../CONTEXT.md) § Flagged ambiguities; [`docs/drain-1-notes.md`](../drain-1-notes.md) § The park that didn't happen |
| 6 | **Earlier mutation counts are unverified.** Two earlier gates measured broken-copy detection without clearing compiled bytecode, so a stale compiled file could run while the source on disk looked correct. | Those figures appear in no published document and are recorded rather than re-run; the fixes they accompanied were reviewed independently. Any future publication must re-earn them. | Recorded, binding on future gates | [`docs/deferred-findings.md`](../deferred-findings.md) § Method notes |

## Also unverified, stated plainly

- The protein model has certainly seen insulin; the science result is recovery of a known constraint, not new biology. No wet experiment has been run. ([`SUBMISSION.md`](../../SUBMISSION.md) § Not claimed)
- Self-improvement across passes is a mechanism, not a measured result: one pass ran, it closed everything, and nothing was set aside for a second pass to improve on.
- The 75 independent component tests from pass 1 have not been re-run since ([§eval](eval.md)).

## Read the source

- [`docs/deferred-findings.md`](../deferred-findings.md) — findings judged real and not fixed in the PR that raised them (2026-09-25)
- [`docs/drain-1-notes.md`](../drain-1-notes.md) — the three pass-1 findings, all caught by hand (2026-09-17)

Back to the [index](index.md).
