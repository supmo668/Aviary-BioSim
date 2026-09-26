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

A label is a field inside the evidence file, not prose around it.

## Files

| file | task | label | produced by | date |
|---|---|---|---|---|
| `drain1-rerun.json` | A1 | measured | `tools/referee run --sign` via `scripts/sealed_suite_results.sh`, recorded by `scripts/record_referee.py` | — (waiting: the referee command must exist on a commit and be confirmed) |
| `drain1-from-git.csv` | A2 | reconstructed | `scripts/drain1_from_git.py` | — |
| `drain1-record-check.json` | A2b | recovered record; pre-claim chain verified; write-time provenance not established | `scripts/drain1_record_check.py --record <path>` | — |
| `science-input.json` | A3a/b | measured (fresh fetch) | `scripts/science_input.py --inputs <absolute path>` | — |
| `science.json` | A3c | measured (re-run) or reported on mismatch | `scripts/science_rerun.py --inputs <absolute path>` | — |
| `agent-run.json` | A4 | reported (artifact counted) | `scripts/agent_run.py --inputs <absolute path>` | — |
| `weave-count.json` | A4 | queried | recorded by hand from the trace store's count query on the day | — |
| `taxonomy.csv` | A5 | documented | hand-authored; checked by `scripts/taxonomy_check.py` | — |
| `plugin-tests.json` | A6 | measured (re-run) | `scripts/plugin_tests.py` | — |

The **evidence-location rule** applies to every script that reads the published run: it
takes `--inputs <absolute path>`; a missing or empty directory is an error (exit 2) that
names the path checked. The published run's files are not in this repository (`science/out/`
is untracked); the paper says where they were read from.

Plain language: a *pass* of the loop, a *task*, *setting a task aside*, an *independent
test*, the *worklist* — see `docs/CONTEXT.md` § Reader-facing vocabulary for the mapping to
the project's own terms.
