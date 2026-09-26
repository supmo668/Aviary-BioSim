#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["matplotlib"]
# ///
"""A8 — every figure is drawn from paper/evidence/ and nothing else.

Refuses any --evidence directory that is not paper/evidence (resolved), so a figure can
never be drawn from a run directory or a cache. Every figure carries a footer naming the
evidence file it was drawn from and the commit it was drawn at. No number appears in a
plot title or annotation that is not also a claim macro in the text.
"""
import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PAPER = Path(__file__).resolve().parents[1]
EVIDENCE = PAPER / "evidence"


def guard(evidence: str) -> Path:
    p = Path(evidence).resolve()
    if p != EVIDENCE.resolve():
        print(f"ERROR: figures are drawn from {EVIDENCE} only, not {p}", file=sys.stderr)
        raise SystemExit(2)
    return p


def sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()


def footer(fig, source: str):
    fig.text(0.01, 0.01, f"generated from paper/evidence/{source} at {sha()}", fontsize=6, color="0.4")


def timeline(ev: Path, out: Path):
    rows = list(csv.DictReader((ev / "drain1-from-git.csv").open()))
    times = [datetime.fromisoformat(r["committed_at"]) for r in rows]
    t0 = times[0]
    minutes = [(t - t0).total_seconds() / 60 for t in times]
    fig, ax = plt.subplots(figsize=(6.4, 1.9))
    ax.scatter(minutes, [0] * len(rows), s=60, zorder=3)
    for m, r in zip(minutes, rows):
        ax.annotate(f'{r["unit"]}\n{r["requirement"]}', (m, 0), textcoords="offset points",
                    xytext=(0, 9), ha="center", fontsize=7)
    ax.set_yticks([])
    ax.set_xlabel("minutes after the first task closed")
    ax.set_title("The first pass: one glyph per task, at the time its independent test passed", fontsize=8)
    for s in ("left", "right", "top"):
        ax.spines[s].set_visible(False)
    footer(fig, "drain1-from-git.csv")
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(out / "timeline.pdf")
    plt.close(fig)


def cysteines(ev: Path, out: Path):
    d = json.loads((ev / "science.json").read_text())
    means = d["per_position_mean"]
    cys = set(d["headline"]["cysteine_positions"])
    pos = list(range(1, len(means) + 1))
    colors = ["#c0392b" if p in cys else "#7f8c8d" for p in pos]
    fig, ax = plt.subplots(figsize=(6.4, 2.6))
    ax.bar(pos, means, color=colors, width=0.9)
    ax.axhline(d["headline"]["cysteine_mean_mature"], color="#c0392b", lw=0.8, ls="--")
    ax.axhline(d["headline"]["other_mean_mature"], color="#7f8c8d", lw=0.8, ls="--")
    ax.axvspan(0.5, d["headline"]["mature_from_position"] - 0.5, color="0.92", zorder=0)
    ax.set_xlabel("residue position")
    ax.set_ylabel("mean substitution score")
    ax.set_title("Per-position sensitivity. Cysteines highlighted; dashed lines: the two mature-protein means",
                 fontsize=7, loc="left")
    for s in ("right", "top"):
        ax.spines[s].set_visible(False)
    footer(fig, "science.json")
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(out / "cysteines.pdf")
    plt.close(fig)


def taxonomy(ev: Path, out: Path):
    rows = list(csv.DictReader((ev / "taxonomy.csv").open()))
    cells = [[r["id"], _wrap(r["symptom"], 62), _wrap(r["comp_bio_analogue"], 44),
              "yes" if r["regression_test"].strip() else "no"] for r in rows]
    fig, ax = plt.subplots(figsize=(8.5, 0.34 * len(rows) + 0.8))
    ax.axis("off")
    tbl = ax.table(cellText=cells, colLabels=["id", "what happened", "the lab analogue", "test?"],
                   colWidths=[0.06, 0.52, 0.36, 0.06], loc="upper center", cellLoc="left")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(6)
    for (r, c), cell in tbl.get_celld().items():
        cell.set_height(0.31 / (0.34 * len(rows) + 0.8) * 1.0 if r else 0.03)
        cell.set_edgecolor("0.8")
        if r == 0:
            cell.set_text_props(weight="bold")
    footer(fig, "taxonomy.csv")
    fig.savefig(out / "taxonomy.pdf", bbox_inches="tight")
    plt.close(fig)


def _wrap(text: str, width: int) -> str:
    import textwrap
    return "\n".join(textwrap.wrap(text, width)[:3])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", default=str(EVIDENCE))
    ap.add_argument("--out", default=str(PAPER / "figures"))
    a = ap.parse_args(argv)
    ev = guard(a.evidence)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    timeline(ev, out)
    cysteines(ev, out)
    taxonomy(ev, out)
    print("wrote", ", ".join(f"{out / n}.pdf" for n in ("timeline", "cysteines", "taxonomy")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
