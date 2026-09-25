"""The frozen mutant catalogue must stay applicable to the code it describes.

Running all 31 mutants takes minutes (each is a pytest subprocess against its own
copy of the tree), so the full sweep lives in mutants/run_mutants.py and is the
acceptance gate for changing the guard. What runs here on every suite is the cheap
half: that each mutant's `find` string still matches its target exactly once.

That is the property that rots. A catalogue entry whose anchor has drifted silently
stops testing anything, which is the same failure the catalogue exists to prevent.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "mutants"))
from catalogue import MUTANTS  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("mutant", MUTANTS, ids=lambda m: m["id"])
def test_every_frozen_mutant_still_applies_exactly_once(mutant):
    target = REPO / mutant["target"]
    assert target.exists(), f"{mutant['target']} is gone; the catalogue entry is stale"
    occurrences = target.read_text().count(mutant["find"])
    assert occurrences == 1, (
        f"{mutant['id']}: anchor occurs {occurrences}x in {mutant['target']} — the code "
        "moved and this mutant no longer probes what it claims to. Fix the anchor."
    )


def test_the_catalogue_covers_every_pass_and_every_guarded_file():
    passes = {m["pass_"] for m in MUTANTS}
    assert passes == {"1", "2", "3", "4"}, f"missing a review pass: {passes}"
    targets = {m["target"] for m in MUTANTS}
    for required in ("science/biosim_env.py", "science/esm_tool.py",
                     "science/run_discovery.py", "science/tests/conftest.py"):
        assert required in targets, f"no frozen mutant targets {required}"
    assert len({m["id"] for m in MUTANTS}) == len(MUTANTS), "duplicate mutant id"
