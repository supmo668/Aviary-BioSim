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
| F08 | gate #151, promoted #213 | **high** | **yes** (2026-09-24) | **fixed (unlanded)** | 2026-09-24 | Test isolation depends on pytest collection order. `science/tests/test_biosim_env_budget.py` installs a fake `esm_tool` into `sys.modules` at import time and never restores it, and a sibling imports that module as a library to reuse the stub. Under `--import-mode=importlib` two tests fail; but the default mode's green is not evidence of isolation either, only of a favourable ordering — a test that imports the real `esm_tool`, `torch` or `requests` can pass while silently exercising a stub. Live repro: `test_esm_tool_accession.py` passed alone and failed 50 in the suite until it was made to load its module by path. FIXED in the gate of 2026-09-24: the fakes, the recorder and the env/step helpers are per-test fixtures in `science/tests/conftest.py` installed with `monkeypatch.setitem`; no test module imports another; `pytest_configure` snapshots `sys.modules` and `sys.path` before collection and the hooks fail any test that does not match, reporting an import-time write at collection rather than blaming the first test to run. Detection is by identity rather than by a marker, so a stub written by someone who never heard of this file is caught too. UPDATED 2026-09-25 (pass 5): authentication is now by OBJECT IDENTITY against a pre-collection snapshot, not by inspecting a module's own attributes. Passes 2, 3 and 4 each found the same defect in different clothes — a marker, then `__file__`, then `__spec__.origin` — because every attribute a module has is one a fake can set. Pass 5 also found that five of the guard's own tests could not fail, that two of its three enforcement halves could be deleted with the suite green, and that the mutation gate credited a kill on any non-zero exit; all fixed. Known limits are recorded as F23-F26. |
| S-001 | gate #215 | **security** | — | held — detail withheld while open | 2026-09-24 | Held. Detail in the private bioFM workstream. |
| F22 | gate #215 | low | no | open | 2026-09-24 | `science/esm_tool.py` `position_logprobs(seq[:position] + seq[position:])` is a no-op slice-concat. It is *correct* for masked-marginal scoring, which needs the wild-type sequence, so there is no defect in the number today. The risk is future behaviour: it reads as if it applies the mutation, so the next person to "fix" the no-op will change the scoring semantics, and no test currently objects. Worth a row precisely because it is presently harmless. |
| F16 | gate #151 | low | no | open | 2026-09-17 | A mid-batch budget refusal in `BioSimEnv.step` discards the responses of calls that already ran, so the transcript's "refused" entry lists requests with no results while `audit_trail` holds them — the two records disagree. No data is lost. |
| F09 | gate #151 | low | no | open | 2026-09-17 | `science/run_discovery.py` uses `BioSimEnv`'s default `ceiling_usd` silently while requiring the token price to be declared; the sealed-tested `load_ceiling` goes unused. The e2e test has to monkeypatch `BioSimEnv.__init__.__defaults__` positionally, which is brittle. |
| F13 | gate #151 | low | no | open | 2026-09-17 | If the provider omits `resp.usage`, or returns `None` token counts, `agent_turn` raises after the call was billed and before `charge()`, so that call is never metered and `discovery.json` is never written. Fails closed today; becomes an under-metering path the moment a retry wrapper is added. |
| F14 | gate #151 | low | no | open | 2026-09-17 | A single blended `BIOSIM_USD_PER_1M_TOKENS` under-meters output-heavy calls, because providers price output tokens above input. Either split input/output prices, or document that the declared price must be the output rate and the ledger an upper bound. |
| F05 | gate #151 | low | no | **withdrawn** | 2026-09-24 | "No test that `record` itself is refused when over budget." Moot: principal ruling #152 removed the agent-facing `record` tool entirely, and `test_a_record_call_from_the_agent_is_not_a_tool_and_cannot_touch_the_ledger` now pins its absence. |
| F23 | gate pass 5 | med | no | open | 2026-09-25 | `pytest_collection_finish` is session-global while `_path_leaks` was narrowed to this project's own directories. A sibling test root that fakes a watched third-party name at import time therefore aborts the WHOLE session, and `_repair()` overwrites that suite's deliberate state before raising. The sys.path half of this lesson was learned and fixed; the sys.modules half was not. `test_collecting_alongside_another_test_root_is_not_treated_as_a_leak` covers only the path half. |
| F24 | gate pass 5 | med | no | open | 2026-09-25 | The baseline is self-certifying. `importlib.import_module` returns an existing `sys.modules` entry, so anything that runs before `pytest_configure` — a conftest in an ancestor directory, a `.pth` file, a `pytest11` entry-point plugin, `sitecustomize`, `-p mod` — has its fake recorded as ground truth and then defended by the guard for the whole session. Latent: there is no root conftest today. The fix is not free (it means re-introducing origin checking for the pre-existing case), which is why it is deferred rather than done. |
| F25 | gate pass 5 | med | no | open | 2026-09-25 | Identity authenticates the BINDING, not the contents. `import yaml; yaml.safe_load = evil` at import time leaves the object identical, so no hook fires and `_repair()` cannot undo it. Same for rebinding the `core` attribute on the `aviary` package object without touching `sys.modules["aviary.core"]`. Outside the file's stated rule ("never assign `sys.modules`"), but the surrounding language reads as if the class were closed. The conftest docstring now says plainly that this is the one leak shape the guard cannot see. |
| F26 | gate pass 5 | low | no | open | 2026-09-25 | `stub_contract.baseline` hands tests the live mutable `_BASELINE` dict; one assignment re-certifies a fake for the session AND makes `_repair()` install it. `MappingProxyType` would cost nothing — the single consumer only does a lookup. |
| F27 | gate pass 5 | low | no | open | 2026-09-25 | `pytest_runtest_teardown` is correctly `trylast`, but pluggy aborts the multicall when an earlier impl raises, so a test whose fixture finalizer raises AND leaks is not reported by teardown. The next test's `tryfirst` setup still detects and repairs, so detection is not lost — only misattributed, except for the last test in a session. (The original form of this finding claimed detection was lost; that was wrong and is corrected here.) Separately, `tryfirst` on setup places the guard ahead of `_pytest.skipping`, so a skipped test in a dirty session reports FAILED rather than SKIPPED. |
| F28 | gate pass 5 | low | no | **partly fixed (unlanded)** — see note | 2026-09-26 | `science/esm_tool.py` — `position` reaches operator-facing text with neither `operator_safe` nor a length cap, while `organism` and `length` were given both. Escape injection is unreachable through the JSON tool path (the `1 <= position` comparison raises TypeError on a str first), but a multi-thousand-digit integer still produces a multi-kilobyte line. |
| F29 | gate pass 5 | low | no | **partly fixed (unlanded)** — see note | 2026-09-26 | `science/esm_tool.py` — the fetch is unbounded: `r.text` is read with no size limit, `allow_redirects` is left at its default of True, and `lines[0]` raises IndexError on an empty body before the guarded `split("OS=")`. The 30s timeout is present and correct. |
| F30 | gate pass 5 | low | no | open | 2026-09-25 | `science/esm_tool.py` — the cache directory is created with default permissions and records are written non-atomically (truncate-then-write, no tmp+rename), so a crash or a concurrent reader can observe a partial record. Feeds F31. |
| F31 | gate pass 5 | **security** | no | held — detail withheld while open | 2026-09-25 | Security. Cache read path integrity. Detail withheld from this public repo per the rule above; filed in full in the private bioFM workstream. |
| F32 | gate pass 5 | low | no | open | 2026-09-25 | `science/run_discovery.py` — the `"tool error: no response"` fallback in `measure()` has no behavioural test; changing the string is noticed only by the catalogue's anchor check, which is spec-rot detection, not behaviour. |
| F28/F29 note | F08 re-gate | — | — | — | 2026-09-26 | Re-gate of 2026-09-26 (findings C4/T11, T6): `position` and `mutant` are now type-checked and refused before any text is built, and `valid_accession`'s echo is capped and stripped (F28's echo half). An empty, blank or headerless UniProt body is refused with a ValueError and nothing is cached (F29's empty-body half). Still open from those rows: the unbounded `r.text` read and the default `allow_redirects=True` (F29). |
| F33 | F08 re-gate (S1) | **med** | n/a | open — plan content, escalated | 2026-09-26 | The #272 plan's G2 mechanism records `sha256(accession)` and `sha256(sequence)` as if a digest withheld the identifier. It does not: the accession grammar (`science/esm_tool.py` `ACCESSION`) is small enough to enumerate offline, and a sequence digest is a lookup against any public sequence store. The evidence file would disclose what the paper claims is withheld. Not fixable here — the plan is signed; the CTO re-rules G2 (record no digest, or a keyed digest whose key is never published, or publish openly). |
| F34 | F08 re-gate (S2/D4) | low | n/a | open — plan content, build note | 2026-09-26 | The #272 plan's Task 4 draft passes `rec["accession"]`, read from a cached JSON file, straight into a UniProt URL. This branch's `valid_accession` exists for exactly that path. The Task 4 implementation will validate before building the URL and add a refusal test; the plan text is unchanged. |
| F35 | F08 re-gate (D17) | low | no | open — approved design doc | 2026-09-26 | `docs/spec.md` gives the unit state shape as `open \| closed \| parked`; `register.py` and `docs/hacp/design.md` also have `claimed`. The spec is the stale one. Not edited here: it is the approved design; flagged to the CTO. |

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
