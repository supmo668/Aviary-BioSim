# Evidence for the white paper

Every number the paper carries maps to one file in `evidence/` with a **label**, and every
file was produced by one script in `scripts/` that wrote its exact run configuration beside
the numbers (`scripts/_provenance.py`: git SHA, timestamp, the inputs path as passed, Python
and package versions, and — where a model ran — model id, revision, weights digest, device
and seed). `claims.py` refuses to build the paper if a number has no file, a file is missing,
a value disagrees, or a claim that was only *reported* is phrased as *measured*.

## Labels

| label | meaning |
|---|---|
| **measured** | re-run for this paper, on the date given, with its configuration recorded |
| **reconstructed** | rebuilt from version control, not from a run's own record |
| **reported** | taken from the published run's artifact, not re-derived |
| **documented** | a taxonomy row that cites its source |
| **queried** | an external store answered on the date given |
| **recovered record** | a copy found after the fact; checked for consistency against history, its time of writing not established |

A label is a field inside the evidence file, not prose around it. `claims.py` refuses a claim whose
label the evidence file does not itself carry, and any file labelled `NOT …` or `MISMATCH …`.

## The sealed-suite referee

The sealed suite is re-run by the plugin's `referee`, which resolves its command from the project
configuration key `tests.referee_command` (per module: `tests.referee_command_<module>`, read first).
For this paper the key was `tests.referee_command_aviary-biosim`, set in the parent repository's
`agency.yaml`, to

```
sh paper/scripts/sealed_suite_results.sh
```

The script's exit-code contract is in its header; `paper/scripts/record_referee.py` records the run.

## Files

Run every command below **from the repository root**. The scripts anchor their git calls and default output paths to the repository themselves, so the working directory only matters for paths you type (`HF_HOME`, `--inputs`).

| file | task | label | produced by | date |
|---|---|---|---|---|
| `drain1-rerun.json` | A1 | measured (re-run) | `tools/referee run --sign` via `paper/scripts/sealed_suite_results.sh`, recorded by `paper/scripts/record_referee.py --referee <tools/referee> --sign` | 2026-09-26 |
| `drain1-from-git.csv` | A2 | reconstructed | `paper/scripts/drain1_from_git.py` | 2026-09-26 |
| `drain1-record-check.json` | A2b | recovered record; pre-claim chain verified; write-time provenance not established | `paper/scripts/drain1_record_check.py --record <absolute path to the recovered .v2r>` | 2026-09-26 |
| `science-input.json` | A3a/b | measured (fresh fetch) | `paper/scripts/science_input.py --inputs <absolute path>` | 2026-09-26 |
| `science.json` | A3c | measured (re-run) — every field matched | `HF_HOME=$PWD/paper/.hf-cache uv run --with torch --with transformers --with requests --with numpy paper/scripts/science_rerun.py --inputs <absolute path>` | 2026-09-26 |
| `agent-run.json` | A4 | reported (artifact counted) | `paper/scripts/agent_run.py --inputs <absolute path>/discovery` | 2026-09-26 |
| `weave-count.json` | A4 | queried | recorded by hand from the trace store's count query on the day | 2026-09-26 |
| `taxonomy.csv` | A5 | documented | hand-authored; checked by `paper/scripts/taxonomy_check.py --plugin-root <plugin checkout>` | 2026-09-26 |
| `plugin-tests.json` | A6 | measured (re-run) | `paper/scripts/plugin_tests.py --plugin-repo <plugin checkout> --tag v0.64.0` | 2026-09-26 |
| `repo-tests.json` | — | measured (re-run) | `paper/scripts/repo_tests.py` (this repository's suites and the full mutant sweep) | 2026-10-02 |
| `candidate-record/` | A2b | copies | written by `paper/scripts/drain1_record_check.py`; digests in `drain1-record-check.json` | 2026-09-26 |

The **evidence-location rule** applies to every script that reads the published run: it
takes `--inputs <absolute path>`; a missing or empty directory is an error (exit 2) that
names the path checked. The published run's files are not in this repository (`science/out/`
is untracked); the paper says where they were read from.

Plain language: a *pass* of the loop, a *task*, *setting a task aside*, an *independent
test*, the *worklist* — see `docs/CONTEXT.md` § Reader-facing vocabulary for the mapping to
the project's own terms.

## Why the science identifier is recorded in the clear

`science-input.json` and the paper's methods name the database record the experiment
used. A digest of it would not hide it: the identifier grammar is small enough to
enumerate offline, and a digest of the sequence is a lookup against any public sequence
store. The project's rule against new identifier-to-substance associations is
prospective; the association between this experiment's protein and its public record is
already published by this repository (the run's own prompt and the submission text), so
restating it for reproducibility creates no new one. Ruled by the coordinator on
2026-09-26 (F33), with the principal told so they can override before submission. The
values (identifier, release, digest) are printed in the methods and stored in the evidence
file only; `claims.yaml` and the generated `claims.tex` carry them to the methods, and they
are kept out of the appendix table (`table: false`). Never in tests, fixtures or messages.
