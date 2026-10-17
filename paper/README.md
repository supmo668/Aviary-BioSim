# The paper

| | |
|---|---|
| source | `main.tex`, built with `tectonic -X compile main.tex` |
| numbers | `claims.yaml` → `claims.py` → `claims.tex`; the build refuses an unmapped number |
| evidence | **[`evidence/README.md`](evidence/README.md)** — one row per evidence file: the task, the label, and the exact command that produced it |
| figures | `figures/make_figures.py`, which writes only into the evidence directory |
| deposit | `publish.yml` declares the payload; `../orchestration/n8n/README.md` describes the pipeline |

The evidence documentation deliberately lives **in `evidence/`**, not here. `evidence/` is a
declared artifact of the deposit and this file is not, so documentation kept here would be
unreachable to a reader who has the DOI but not the repository — the same defect as citing a
document that ships somewhere else.
