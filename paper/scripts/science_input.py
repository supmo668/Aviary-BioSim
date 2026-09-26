#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["requests"]
# ///
"""A3a/A3b — is the published run's input the record UniProt serves today?

Reads the published input from --inputs (the run's own seqs/ and esm/results.json),
fetches the same record fresh from UniProt with the cache bypassed, and compares the
two sequences by sha256. Records the identifier, the database release, the entry
version, the length and the sequence digests.

The identifier is written IN THE CLEAR here and in the paper's methods, and nowhere
else (coordinator's ruling of 2026-09-26, F33): a digest over an enumerable identifier
grammar is a lookup, not a redaction, and the association between this experiment's
protein and its public record is already published by this repository, so restating
it for reproducibility creates no new association. Tests never carry the value.

The identifier read from the cached file is VALIDATED before it is used to build a URL
(science/esm_tool.py's grammar; F34): cache content is file content, not trusted input.
"""
import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
import _provenance as P  # noqa: E402

UNIPROT = "https://rest.uniprot.org/uniprotkb/{acc}.fasta"


def H(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _valid_accession(value):
    """science/esm_tool.valid_accession, loaded by path so this script needs no torch."""
    src = Path(__file__).resolve().parents[2] / "science" / "esm_tool.py"
    text = src.read_text()
    ns: dict = {}
    # Only the grammar and the validator are needed; execute those definitions alone.
    start = text.index("ACCESSION = re.compile(")
    end = text.index("_model = None")
    exec("import re\n" + text[start:end], ns)
    return ns["valid_accession"](value)


def fetch_fresh(accession: str) -> dict:
    r = requests.get(UNIPROT.format(acc=accession), timeout=30, allow_redirects=False,
                     headers={"Cache-Control": "no-cache", "Accept": "text/plain"})
    r.raise_for_status()
    lines = r.text.strip().splitlines()
    if not lines or not lines[0].startswith(">"):
        sys.exit(f"ERROR: unexpected FASTA body from UniProt ({len(r.text)} bytes)")
    header = lines[0]
    return {"sequence": "".join(lines[1:]),
            "release": r.headers.get("x-uniprot-release", ""),
            "release_date": r.headers.get("x-uniprot-release-date", ""),
            "http_last_modified": r.headers.get("last-modified", ""),
            "entry_version": header.split("SV=")[-1].split()[0] if "SV=" in header else ""}


def published_record(inputs: Path) -> dict:
    res = json.loads((inputs / "esm" / "results.json").read_text())
    human = res["human_sequence"]
    for p in sorted((inputs / "seqs").glob("*.json")):
        rec = json.loads(p.read_text())
        if rec.get("sequence") == human:
            return rec
    print(f"ERROR: no record under {inputs / 'seqs'} carries the published human sequence",
          file=sys.stderr)
    raise SystemExit(2)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", required=True, help="ABSOLUTE path to the published run's science/out")
    ap.add_argument("--out", default="paper/evidence/science-input.json")
    a = ap.parse_args(argv)
    inputs = P.require_inputs(a.inputs)
    rec = published_record(inputs)
    acc = _valid_accession(rec["accession"])            # refuse before any URL is built
    fresh = fetch_fresh(acc)
    published_seq = rec["sequence"]
    out = {
        "label": "measured (fresh fetch, " + P.block(None)["recorded_at"][:10] + ")",
        "identifier": acc,
        "identifier_disclosure": ("recorded in the clear by ruling (2026-09-26): the association is "
                                  "already public in this repository; a digest would be a lookup"),
        "published": {"length": len(published_seq), "sequence_sha256": H(published_seq),
                      "organism_field": rec.get("organism", "")},
        "fresh": {"length": len(fresh["sequence"]), "sequence_sha256": H(fresh["sequence"]),
                  "release": fresh["release"], "release_date": fresh["release_date"],
                  "entry_version": fresh["entry_version"],
                  "http_last_modified": fresh["http_last_modified"]},
        "match": H(published_seq) == H(fresh["sequence"]),
        "provenance": P.block(inputs_path=inputs, modules=("requests",)),
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2))
    print(("MATCH" if out["match"] else "MISMATCH — flag the coordinator before any prose"), a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
