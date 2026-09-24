"""The isolation contract itself, asserted rather than assumed.

conftest's hooks FAIL any test whose sys.modules no longer matches the snapshot
taken before collection. These tests state the contract from the other side, so it
survives a hook refactor, and pin the fixture wiring the rest of the suite trusts.

This is the regression guard for F08. Without it the fix decays the first time
someone adds a module that installs a global stub — which is how F08 arrived.
"""
import importlib.util
import pathlib
import sys

import pytest

pytest_plugins = ["pytester"]

# `from conftest import *` would resolve to pytester's OWN conftest, silently
# registering nothing — the probe then runs unguarded and the meta-test passes for
# the wrong reason. Load this suite's conftest by path instead.
CONFTEST_SHIM = """
import importlib.util, sys
_spec = importlib.util.spec_from_file_location("aviary_science_conftest", {conftest!r})
_mod = importlib.util.module_from_spec(_spec)
sys.modules["aviary_science_conftest"] = _mod
_spec.loader.exec_module(_mod)
globals().update({{k: v for k, v in vars(_mod).items() if not k.startswith("__")}})
"""


# --- the contract, from the test side -------------------------------------------

def test_a_test_that_did_not_ask_for_a_stub_sees_no_stub(stub_contract):
    assert stub_contract.stubbed() == []


def test_the_real_requests_is_importable_when_no_fixture_faked_it(stub_contract):
    import requests
    assert not getattr(requests, stub_contract.marker, False)
    assert hasattr(requests, "Session"), "this should be the real library"


def test_a_test_that_did_not_ask_for_bio_has_a_clean_sys_path(stub_contract):
    """The sys.path half of the contract. The modules under test insert their own
    directories at import; if that is not unwound, what a later bare import resolves
    to depends on what ran first — the same order-dependence, moved to sys.path.

    Asserted as a DELTA against the pre-collection baseline, not as "this directory is
    absent from sys.path": the absolute form depended on how the suite was launched
    (`cd science && python -m pytest tests` puts science on the path before pytest
    starts), making the suite's colour a property of the invocation rather than of the
    code — the inverse of the defect this unit removes.
    """
    assert stub_contract.path_leaks() == []


def test_the_fake_tool_is_visible_only_while_a_fixture_holds_it(esm_stub, stub_contract):
    assert stub_contract.stubbed() == ["esm_tool"]
    assert sys.modules["esm_tool"] is esm_stub


def test_the_heavy_stubs_are_visible_only_while_the_esm_fixture_holds_them(esm, stub_contract):
    assert sorted(stub_contract.stubbed()) == ["requests", "torch", "transformers"]
    assert esm.valid_accession("P01308") == "P01308"


# --- the wiring the rest of the suite trusts ------------------------------------

def test_the_bundle_exposes_the_same_objects_the_code_under_test_uses(bio, esm_stub):
    """Without this, widening bio.BudgetExceeded to Exception leaves every
    'the rollout must STOP' assertion green while asserting only 'raises anything'."""
    import aviary.core
    import spend_tracker

    assert bio.BudgetExceeded is spend_tracker.BudgetExceeded
    assert issubclass(bio.BudgetExceeded, RuntimeError)
    assert bio.BudgetExceeded is not Exception
    assert bio.module.SpendTracker is spend_tracker.SpendTracker
    assert bio.ToolCall is aviary.core.ToolCall
    assert bio.ToolRequestMessage is aviary.core.ToolRequestMessage
    assert bio.calls is esm_stub.calls is sys.modules["esm_tool"].calls
    assert bio.module.esm_tool is sys.modules["esm_tool"]


def test_the_harness_shares_the_environment_the_bundle_built(disc, bio):
    assert disc.BioSimEnv is bio.module.BioSimEnv
    assert disc.BudgetExceeded is bio.BudgetExceeded
    assert sys.modules["biosim_env"] is bio.module


# --- the guard, exercised end to end ---------------------------------------------
# Run as their own pytest sessions, so the assertions do not depend on this file's
# collection order the way a "runs after the one above" test would.

def _shadow_dir(pytester, module_name):
    """A directory that would answer to a watched name — what makes a path entry
    dangerous. An added directory shadowing nothing cannot change any resolution."""
    directory = pytester.mkdir(f"shadow_{module_name}")
    (directory / f"{module_name}.py").write_text("FAKE = True\n")
    return directory


def _run(pytester, module_source):
    conftest = pathlib.Path(__file__).parent / "conftest.py"
    pytester.makeconftest(CONFTEST_SHIM.format(conftest=str(conftest)))
    pytester.makepyfile(test_probe=module_source)
    return pytester.runpytest_subprocess("-q")


def test_the_guard_catches_an_unmarked_stub_installed_at_import_time(pytester):
    """The original F08 shape, and the one a marker-based guard misses: a plain
    ModuleType written by someone who never heard of our marker.

    Reported at COLLECTION, before any test runs — an import-time write is caused by
    collection, so blaming whichever test happened to run first marks an innocent file
    red and hides the real offender.
    """
    result = _run(pytester, """
        import sys, types
        sys.modules["esm_tool"] = types.ModuleType("esm_tool")

        def test_harmless():
            assert True
    """)
    assert result.ret != 0
    result.assert_outcomes(passed=0, failed=0, errors=0)
    out = result.stdout.str() + result.stderr.str()
    assert "esm_tool" in out
    assert "COLLECTED" in out


def test_the_guard_catches_a_sys_path_write_at_import_time(pytester):
    """The sys.path half of the same shape — previously invisible to the guard."""
    result = _run(pytester, """
        import sys
        sys.path.insert(0, SHADOW)

        def test_harmless():
            assert True
    """.replace("SHADOW", repr(str(_shadow_dir(pytester, "yaml")))))
    assert result.ret != 0
    out = result.stdout.str() + result.stderr.str()
    assert "shadow_yaml" in out


def test_the_guard_catches_a_sys_path_leak_from_a_test_body(pytester):
    result = _run(pytester, """
        import sys

        def test_leaks_a_path():
            sys.path.insert(0, SHADOW)

        def test_next():
            assert True
    """.replace("SHADOW", repr(str(_shadow_dir(pytester, "requests")))))
    result.assert_outcomes(errors=1, passed=2)
    assert "shadow_requests" in result.stdout.str()


def test_the_guard_catches_a_stub_leaked_by_a_test_body(pytester):
    result = _run(pytester, """
        import sys, types

        def test_leaks():
            sys.modules["torch"] = types.ModuleType("torch")
    """)
    result.assert_outcomes(errors=1, passed=1)
    assert "torch" in result.stdout.str()


def test_a_fixture_stub_does_not_leak_to_the_next_test(pytester):
    """Both halves in one session, so a reordering cannot make this vacuous."""
    result = _run(pytester, """
        import sys

        def test_asks_for_the_fake(esm_stub):
            assert sys.modules["esm_tool"] is esm_stub

        def test_does_not_ask(stub_contract):
            assert stub_contract.stubbed() == []
            assert "esm_tool" not in sys.modules
    """)
    result.assert_outcomes(passed=2)


def test_sys_path_is_restored_after_a_fixture_loaded_a_module_by_path(pytester):
    """Orders the two explicitly: load by path, then check.

    The in-file assertion above cannot carry this on its own — whether a `bio` test has
    already run depends on how the suite was invoked (trivially true for this file alone,
    false in a full run). An assertion whose meaning depends on collection order is the
    defect this unit exists to remove, so the ordered version lives here.
    """
    result = _run(pytester, """
        import sys

        def test_loads_modules_by_path(bio, stub_contract):
            assert bio.module.BioSimEnv is not None
            assert stub_contract.demo_dir in sys.path      # while the fixture holds it

        def test_sys_path_came_back(stub_contract):
            assert stub_contract.demo_dir not in sys.path
            assert stub_contract.science_dir not in sys.path
    """)
    result.assert_outcomes(passed=2)


def test_load_by_path_restores_sys_path(stub_contract, tmp_path):
    """Pins the loader's own sys.path restore, which was previously commented as
    untestable. The `esm` fixture never calls monkeypatch.syspath_prepend, so for that
    fixture this `finally` is the only thing unwinding a module's sys.path write."""
    module = tmp_path / "writes_sys_path.py"
    module.write_text("import sys\nsys.path.insert(0, '/inserted-by-the-loaded-module')\n")
    before = list(sys.path)

    stub_contract.load_by_path("loaded_under_test", module)

    assert sys.path == before
    assert "/inserted-by-the-loaded-module" not in sys.path


def test_the_bundle_imports_its_classes_rather_than_reading_sys_modules(bio, stub_contract, monkeypatch):
    """Distinguishes an import from a sys.modules lookup, which are otherwise
    indistinguishable: with the entry removed, an import re-imports and a lookup raises
    KeyError. That latent dependency on another function's imports is why this changed."""
    monkeypatch.delitem(sys.modules, "spend_tracker", raising=False)
    monkeypatch.delitem(sys.modules, "aviary.core", raising=False)

    rebuilt = stub_contract.bio_class(bio.module, [])

    import spend_tracker
    assert rebuilt.BudgetExceeded is spend_tracker.BudgetExceeded
    assert rebuilt.BudgetExceeded is not Exception


def test_the_setup_hook_fails_a_test_that_starts_with_dirty_state(stub_contract, tmp_path):
    """The sibling hooks repair before failing, so this one cannot fire through the
    suite and no suite-level test can pin it. Called directly instead: without this,
    deleting it entirely leaves the suite green."""
    class _Item:
        nodeid = "probe::item"

    shadow = tmp_path / "shadowing"
    shadow.mkdir()
    (shadow / "torch.py").write_text("FAKE = True\n")
    sys.path.insert(0, str(shadow))
    try:
        # pytest.fail raises Failed, which derives from BaseException, not Exception.
        with pytest.raises(BaseException) as refused:
            stub_contract.runtest_setup(_Item())
    finally:
        while str(shadow) in sys.path:
            sys.path.remove(str(shadow))
    message = str(refused.value)
    assert str(shadow) in message
    assert "not necessarily the one that caused it" in message, \
        "the hook must not assert a cause it cannot know"


def test_a_fabricated_dunder_file_does_not_make_a_fake_look_real(bio, stub_contract):
    """__file__ is one line to set and comes free from spec_from_file_location, so it
    is not evidence. Identity is checked against where the module must actually live."""
    import types

    fake = types.ModuleType("esm_tool")
    fake.__file__ = "/not/a/real/file.py"
    assert not stub_contract.is_the_real_module("esm_tool", fake)

    import spend_tracker
    assert stub_contract.is_the_real_module("spend_tracker", spend_tracker)


def test_the_guard_catches_a_file_backed_fake_at_import_time(pytester, tmp_path):
    """The other half: a fake loaded exactly the way conftest loads modules, which gets
    a real __spec__ and a real __file__ for free."""
    fake = tmp_path / "esm_tool.py"
    fake.write_text("def score_variant(**kwargs):\n    return 'fabricated'\n")
    result = _run(pytester, f"""
        import importlib.util, sys
        _spec = importlib.util.spec_from_file_location("esm_tool", {str(fake)!r})
        _m = importlib.util.module_from_spec(_spec)
        sys.modules["esm_tool"] = _m
        _spec.loader.exec_module(_m)

        def test_harmless():
            assert True
    """)
    assert result.ret != 0
    assert "esm_tool" in result.stdout.str() + result.stderr.str()


def test_collecting_alongside_another_test_root_is_not_treated_as_a_leak(pytester):
    """pytest inserts each collected file's directory into sys.path during collection
    in prepend mode. Treating that as a leak aborted the whole run and blamed a test
    module for pytest's own behaviour."""
    pytester.makepyfile(test_probe="def test_one():\n    assert True\n")
    other = pytester.mkdir("second_root")
    (other / "test_second.py").write_text("def test_two():\n    assert True\n")
    conftest = pathlib.Path(__file__).parent / "conftest.py"
    pytester.makeconftest(CONFTEST_SHIM.format(conftest=str(conftest)))
    result = pytester.runpytest_subprocess("-q", ".", str(other))
    result.assert_outcomes(passed=2)


@pytest.mark.parametrize("name", ["esm_tool", "biosim_env", "run_discovery",
                                  "spend_tracker", "aviary", "aviary.core", "torch",
                                  "transformers", "requests", "openai", "weave", "yaml"])
def test_every_name_the_guard_must_watch_is_watched(name, stub_contract):
    """WATCHED could be cut from twelve names to four with the suite green: it was the
    guard's entire reach, pinned by nothing. Each name here is either swapped by a
    fixture or imported for real by a module under test."""
    assert name in stub_contract.watched


def test_a_fake_at_a_dotted_watched_name_is_caught(pytester, tmp_path):
    """aviary.core is where the Environment and Tool classes come from; substituting it
    makes a budget-enforcement test pass while measuring a stub. Dotted names were
    exempted outright."""
    fake = tmp_path / "core.py"
    fake.write_text("Environment = object\n")
    result = _run(pytester, """
        import importlib.util, sys
        _spec = importlib.util.spec_from_file_location("aviary.core", FAKE)
        _m = importlib.util.module_from_spec(_spec)
        sys.modules["aviary.core"] = _m
        _spec.loader.exec_module(_m)

        def test_harmless():
            assert True
    """.replace("FAKE", repr(str(fake))))
    assert result.ret != 0
    assert "aviary.core" in result.stdout.str() + result.stderr.str()


def test_a_shadowing_directory_cannot_validate_its_own_fake(pytester):
    """The composed bypass: drop yaml.py beside the test file and insert that directory.
    A guard resolving against the CURRENT sys.path finds the shadow and agrees with
    itself; resolution happens against the pre-collection baseline instead."""
    result = _run(pytester, """
        import os, sys
        _here = os.path.dirname(__file__)
        with open(os.path.join(_here, "yaml.py"), "w") as fh:
            fh.write("FAKE = True\\n")
        sys.path.insert(0, _here)
        import yaml

        def test_harmless():
            assert getattr(yaml, "FAKE", False)
    """)
    assert result.ret != 0, "a fake resolved through a directory it inserted itself"


def test_a_dotted_name_that_did_not_resolve_at_configure_is_still_checked(
        stub_contract, tmp_path, monkeypatch):
    """The dotted-name branch is only reachable when the name was unresolvable before
    collection — an optional dependency that is not installed. aviary IS installed here,
    so the origin baseline answers first and the branch would otherwise go unexercised.
    """
    monkeypatch.setitem(stub_contract.baseline_origin, "aviary.core", (None, False))

    fake_file = tmp_path / "core.py"
    fake_file.write_text("Environment = object\n")
    spec = importlib.util.spec_from_file_location("aviary.core", fake_file)
    fake = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fake)
    assert not stub_contract.is_the_real_module("aviary.core", fake)

    import aviary.core
    assert stub_contract.is_the_real_module("aviary.core", aviary.core)
