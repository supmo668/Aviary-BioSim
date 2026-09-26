"""The frozen mutant catalogue must stay applicable to the code it describes.

Running all 31 mutants takes minutes (each is a pytest subprocess against its own
copy of the tree), so the full sweep lives in mutants/run_mutants.py and is the
acceptance gate for changing the guard. What runs here on every suite is the cheap
half: that each mutant's `find` string still matches its target exactly once.

That is the property that rots. A catalogue entry whose anchor has drifted silently
stops testing anything, which is the same failure the catalogue exists to prevent.
"""
import ast
import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load_catalogue():
    """Load by path rather than `sys.path.insert` + `import catalogue`.

    conftest.py states the rule this module used to break: a test module must never
    write global import state at import time. The old form left science/tests/mutants
    on sys.path and the very generic name `catalogue` in sys.modules for the whole
    session, and escaped the guard only because that directory is not in _OURS.
    """
    spec = importlib.util.spec_from_file_location(
        "aviary_mutant_catalogue", Path(__file__).parent / "mutants" / "catalogue.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CATALOGUE = _load_catalogue()
MUTANTS = _CATALOGUE.MUTANTS
RETIRED = _CATALOGUE.RETIRED


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
    # Superset, not equality: a later review pass adds entries, and demanding equality
    # made adding pass 5 turn the suite red for no reason. Every earlier pass must still
    # be represented — that is the property — but the set is open at the top.
    assert {"1", "2", "3", "4"} <= passes, f"a review pass lost all its mutants: {passes}"
    targets = {m["target"] for m in MUTANTS}
    for required in ("science/biosim_env.py", "science/esm_tool.py",
                     "science/run_discovery.py", "science/tests/conftest.py"):
        assert required in targets, f"no frozen mutant targets {required}"
    assert len({m["id"] for m in MUTANTS}) == len(MUTANTS), "duplicate mutant id"


@pytest.mark.parametrize("mutant", MUTANTS, ids=lambda m: m["id"])
def test_every_mutant_would_actually_be_applied_and_checked(mutant):
    """The anchor check alone is not enough: an entry can rot in three more ways that
    all read as healthy. A `check` pointing at a file that no longer exists makes pytest
    exit 4, which the runner used to score as a kill. A `replace` equal to `find` mutates
    nothing. A `replace` that breaks the syntax kills every test for the wrong reason."""
    check_file = REPO / mutant["check"].split("::")[0]
    assert check_file.exists(), (
        f"{mutant['id']}: check {mutant['check']} does not exist — a run against it "
        "would exit 4, which is not evidence of anything")
    assert "test_mutant_catalogue" not in mutant["check"], (
        f"{mutant['id']}: this file is a spec-rot detector, not a behavioural test. "
        "Applying any mutant drives its own anchor count to 0, so including it here "
        "would make the mutant kill itself.")
    assert mutant["replace"] != mutant["find"], f"{mutant['id']}: replace is a no-op"

    target = REPO / mutant["target"]
    if target.suffix == ".py":
        mutated = target.read_text().replace(mutant["find"], mutant["replace"], 1)
        try:
            ast.parse(mutated)
        except SyntaxError as exc:
            pytest.fail(f"{mutant['id']}: the mutation leaves {mutant['target']} "
                        f"unparseable ({exc.msg}), so every test dies at import and the "
                        "kill says nothing about the property")


def test_the_live_count_is_asserted_so_the_catalogue_cannot_quietly_shrink():
    """Lowering this is a deliberate act that shows up in review.

    Without it the coverage test above is satisfied by as few as four entries — four
    passes x four target files — so 30 could become 4 with the suite green. That is the
    same hole test_every_name_the_guard_must_watch_is_watched exists to close for
    WATCHED, and it was open here while this file policed everything else.
    """
    assert len(MUTANTS) == 48, (
        f"{len(MUTANTS)} live mutants, expected 48. Adding is free; REMOVING one means "
        "retiring it into RETIRED with a reason and updating this number.")
    assert len(RETIRED) == 1
    for entry in RETIRED:
        assert entry["why_retired"].strip(), f"{entry['id']}: retired with no reason"
        assert entry["id"] not in {m["id"] for m in MUTANTS}
