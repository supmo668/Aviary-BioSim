#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///
"""A5 — every taxonomy row either cites a regression test that exists or says it has none.

Columns: id, symptom, why_it_passed_review, found_by, regression_test, label,
comp_bio_analogue, source. A `regression_test` may list several paths separated by `;`.
Paths under tests/ that do not exist in this repository are looked up under
--plugin-root. A row with no test must carry the label `documented, no test`; a row
with a test must not. Exit 1 listing every failure.
"""
import argparse
import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REQUIRED = ["id", "symptom", "why_it_passed_review", "found_by", "regression_test",
            "label", "comp_bio_analogue", "source"]


def check(csv_path: Path, plugin_root: Path | None) -> tuple[list[str], dict]:
    failures, stats = [], {"rows": 0, "with_tests": 0, "documented_only": 0}
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != REQUIRED:
            return [f"columns are {reader.fieldnames}, expected {REQUIRED}"], stats
        ids = set()
        for row in reader:
            stats["rows"] += 1
            rid = row["id"]
            if rid in ids:
                failures.append(f"{rid}: duplicate id")
            ids.add(rid)
            for col in ("symptom", "why_it_passed_review", "comp_bio_analogue", "source", "label"):
                if not row[col].strip():
                    failures.append(f"{rid}: empty {col}")
            tests = [t.strip() for t in row["regression_test"].split(";") if t.strip()]
            if tests:
                stats["with_tests"] += 1
                if row["label"] == "documented, no test":
                    failures.append(f"{rid}: cites a test but is labelled 'documented, no test'")
                for t in tests:
                    here = REPO / t
                    there = (plugin_root / t) if plugin_root else None
                    if not here.exists() and not (there and there.exists()):
                        failures.append(f"{rid}: regression test not found: {t}")
            else:
                stats["documented_only"] += 1
                if row["label"] != "documented, no test":
                    failures.append(f"{rid}: no test cited; label must be 'documented, no test' (is {row['label']!r})")
    return failures, stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="paper/evidence/taxonomy.csv")
    ap.add_argument("--plugin-root", default=None)
    a = ap.parse_args(argv)
    failures, stats = check(Path(a.csv), Path(a.plugin_root) if a.plugin_root else None)
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"ok: {stats['rows']} rows, {stats['with_tests']} with tests, {stats['documented_only']} documented-only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
