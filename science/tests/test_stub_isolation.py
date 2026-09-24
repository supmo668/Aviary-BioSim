"""The isolation contract itself, asserted rather than assumed.

conftest's hooks FAIL any test whose sys.modules no longer matches the snapshot
taken before collection. These tests state the contract from the other side, so it
survives a hook refactor, and pin the fixture wiring the rest of the suite trusts.

This is the regression guard for F08. Without it the fix decays the first time
someone adds a module that installs a global stub — which is how F08 arrived.
"""
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

    Asserted on sys.path itself, not via find_spec: find_spec answers from
    sys.modules for anything already imported, so it reports a module the suite
    legitimately imported and says nothing about the search path.
    """
    assert stub_contract.demo_dir not in sys.path
    assert stub_contract.science_dir not in sys.path


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

def _run(pytester, module_source):
    conftest = pathlib.Path(__file__).parent / "conftest.py"
    pytester.makeconftest(CONFTEST_SHIM.format(conftest=str(conftest)))
    pytester.makepyfile(test_probe=module_source)
    return pytester.runpytest_subprocess("-q")


def test_the_guard_catches_an_unmarked_stub_installed_at_import_time(pytester):
    """The original F08 shape, and the one a marker-based guard misses: a plain
    ModuleType written by someone who never heard of our marker."""
    result = _run(pytester, """
        import sys, types
        sys.modules["esm_tool"] = types.ModuleType("esm_tool")

        def test_harmless():
            assert True
    """)
    result.assert_outcomes(errors=1)
    assert "esm_tool" in result.stdout.str()


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
    """The in-file sys.path assertion above runs before any `bio` test, so alone it
    passes trivially. This orders the two explicitly: load by path, then check."""
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
