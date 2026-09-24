# Deferred findings

Findings raised by a quality gate, judged real, and **not fixed in the PR that raised
them**. A finding leaves this register in one direction only: it is fixed, or it is
withdrawn with a reason.

It exists because the full text of a gate's findings used to live in scratch files under
`/tmp` that were deleted, while the QGR receipt's Hash B and Hash C went on attesting to
them. The only durable trace of a deferred finding was a token in a dispatch. When the CTO
asked "where is F08 recorded, so I can promote it", the answer was: nowhere.

## How to read it

**Live repro** is the field that makes promotion mechanical rather than a judgement call.
A deferred finding that acquires a reproduction is scheduled — no further argument needed.

**Security rows are held.** This repository is public, and a register of unfixed findings
is a disclosure surface. A security-severity row carries only its id, severity and status
here; the description, reproduction and fix shape live in the private bioFM workstream
until the fix ships, at which point the full row moves here. If a severity is arguable it
is treated as security and held — the cost of over-holding is a thin row, the cost of
under-holding is a published exploit path.

**Disposition date** is the last time someone decided about the row. A finding deferred
repeatedly is visibly a finding nobody wants to fix.

**When a row closes.** At the gate that fixes it, not at merge — the row is written by the
same agent in the same commit range as the fix, so deferring the edit to merge is how a
register starts drifting from the code it describes. `fixed (unlanded)` means the fix is
gated and submitted but not yet on trunk; it becomes `fixed` when the CTO lands it.

| id | raised | severity | live repro | status | disposition | finding |
|---|---|---|---|---|---|---|
| F08 | gate #151, promoted #213 | **high** | **yes** (2026-09-24) | **fixed (unlanded)** | 2026-09-24 | Test isolation depends on pytest collection order. `science/tests/test_biosim_env_budget.py` installs a fake `esm_tool` into `sys.modules` at import time and never restores it, and a sibling imports that module as a library to reuse the stub. Under `--import-mode=importlib` two tests fail; but the default mode's green is not evidence of isolation either, only of a favourable ordering — a test that imports the real `esm_tool`, `torch` or `requests` can pass while silently exercising a stub. Live repro: `test_esm_tool_accession.py` passed alone and failed 50 in the suite until it was made to load its module by path. FIXED in the gate of 2026-09-24: the fakes, the recorder and the env/step helpers are per-test fixtures in `science/tests/conftest.py` installed with `monkeypatch.setitem`; no test module imports another; `pytest_configure` snapshots `sys.modules` and `sys.path` before collection and the hooks fail any test that does not match, reporting an import-time write at collection rather than blaming the first test to run. Detection is by identity rather than by a marker, so a stub written by someone who never heard of this file is caught too. |
| S-001 | gate #215 | **security** | — | held — detail withheld while open | 2026-09-24 | Held. Detail in the private bioFM workstream. |
| F22 | gate #215 | low | no | open | 2026-09-24 | `science/esm_tool.py` `position_logprobs(seq[:position] + seq[position:])` is a no-op slice-concat. It is *correct* for masked-marginal scoring, which needs the wild-type sequence, so there is no defect in the number today. The risk is future behaviour: it reads as if it applies the mutation, so the next person to "fix" the no-op will change the scoring semantics, and no test currently objects. Worth a row precisely because it is presently harmless. |
| F16 | gate #151 | low | no | open | 2026-09-17 | A mid-batch budget refusal in `BioSimEnv.step` discards the responses of calls that already ran, so the transcript's "refused" entry lists requests with no results while `audit_trail` holds them — the two records disagree. No data is lost. |
| F09 | gate #151 | low | no | open | 2026-09-17 | `science/run_discovery.py` uses `BioSimEnv`'s default `ceiling_usd` silently while requiring the token price to be declared; the sealed-tested `load_ceiling` goes unused. The e2e test has to monkeypatch `BioSimEnv.__init__.__defaults__` positionally, which is brittle. |
| F13 | gate #151 | low | no | open | 2026-09-17 | If the provider omits `resp.usage`, or returns `None` token counts, `agent_turn` raises after the call was billed and before `charge()`, so that call is never metered and `discovery.json` is never written. Fails closed today; becomes an under-metering path the moment a retry wrapper is added. |
| F14 | gate #151 | low | no | open | 2026-09-17 | A single blended `BIOSIM_USD_PER_1M_TOKENS` under-meters output-heavy calls, because providers price output tokens above input. Either split input/output prices, or document that the declared price must be the output rate and the ledger an upper bound. |
| F05 | gate #151 | low | no | **withdrawn** | 2026-09-24 | "No test that `record` itself is refused when over budget." Moot: principal ruling #152 removed the agent-facing `record` tool entirely, and `test_a_record_call_from_the_agent_is_not_a_tool_and_cannot_touch_the_ledger` now pins its absence. |

## Method notes

Not findings about the product, but about evidence for it.

**Mutation counts from the #152 gate and its re-gate are UNVERIFIED.** They were produced
with a mutate/run/restore-by-`cp` loop that did not clear `__pycache__`. A `.pyc` whose
recorded `(mtime, size)` still validates is reused, so a run can execute the *mutant* while
the file on disk is correct; `inspect.getsource` reads the source file and `cmp` compares
the source, so both instruments pass while the stale bytecode runs. This is recorded rather
than re-run, on the CTO's ruling: the affected figure (notably "eight false fixes, all
caught") appears in no repository document, so re-running would verify a sentence in
dispatch prose rather than a published claim. **The fixes themselves are not in doubt** —
each was independently reviewed and the suites are green. Only the metric is.

Two consequences, both binding: run all future mutation under `python -B` with
`__pycache__` cleared between mutants; and if that figure is ever about to be published —
a deck, `SUBMISSION.md`, a paper — it must be re-earned first.
