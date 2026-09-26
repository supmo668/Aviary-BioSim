"""The isolation contract itself, asserted rather than assumed.

conftest's hooks FAIL any test whose sys.modules no longer matches the snapshot
taken before collection. These tests state the contract from the other side, so it
survives a hook refactor, and pin the fixture wiring the rest of the suite trusts.

This is the regression guard for F08. Without it the fix decays the first time
someone adds a module that installs a global stub — which is how F08 arrived.
"""
import pathlib
import sys
import textwrap
import types

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
    assert requests is stub_contract.baseline["requests"], "not the module we started with"
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

# Phrases ONLY the guard emits. Asserting a module name instead is worthless: the probe
# source is echoed in any traceback, so "yaml" appears whether the guard fired or the
# probe simply failed to parse.
GUARD_PHRASES = (
    "while being COLLECTED",
    "ran with global import state already dirty",
    "left global import state dirty",
)


def _run(pytester, module_source):
    """Run a throwaway suite under THIS suite's conftest.

    The probe source is compiled HERE first. Without that, a typo in a probe produces a
    collection error, the owning test sees a non-zero exit, and it passes while the guard
    never ran. That is not hypothetical: the four-way forgery test below was written with
    a placeholder collision ("REAL" also rewrote the REAL inside REAL_YAML), so every
    probe was a SyntaxError and all four parametrisations passed against a guard that had
    been deleted outright.
    """
    compile(textwrap.dedent(module_source), "<probe>", "exec")
    conftest = pathlib.Path(__file__).parent / "conftest.py"
    pytester.makeconftest(CONFTEST_SHIM.format(conftest=str(conftest)))
    pytester.makepyfile(test_probe=module_source)
    return pytester.runpytest_subprocess("-q")


def _assert_the_guard_refused(result, *, expect=None):
    """The oracle every probe test must use.

    `ret != 0` alone is satisfied by ANY probe-side error, which is why five tests in
    this file passed against a completely disabled guard. Require instead that the probe
    produced no test outcomes at all (the run was stopped before tests ran) and that the
    output carries something only the guard says.
    """
    out = result.stdout.str() + result.stderr.str()
    assert result.ret != 0, "the probe suite passed; the guard did not refuse it"
    assert any(phrase in out for phrase in GUARD_PHRASES), (
        "the probe run failed, but not with anything the guard emits — so this test "
        "would pass on a typo in the probe. Tail of output:\n" + out[-1500:])
    if expect is not None:
        assert expect in out, f"expected {expect!r} in the guard's message"
    return out


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
    result.assert_outcomes(passed=0, failed=0, errors=0)
    _assert_the_guard_refused(result, expect="esm_tool")


def test_the_guard_catches_a_sys_path_write_at_import_time(pytester):
    """The sys.path half of the same shape.

    Only THIS project's directories are policed now: every watched name is imported at
    configure, so a later path entry cannot change what one resolves to, and treating
    another suite's entries as leaks once aborted whole sessions over other people's
    code. A fixture that forgets to unwind OUR directory is still a real defect.
    """
    result = _run(pytester, """
        import sys
        sys.path.insert(0, OURS)

        def test_harmless():
            assert True
    """.replace("OURS", repr(str(pathlib.Path(__file__).resolve().parents[1]))))
    out = _assert_the_guard_refused(result)
    # _describe always prints BOTH halves, so "sys.path" alone would not show which
    # half fired. Name the directory, which only appears when the path half found it.
    assert repr(str(pathlib.Path(__file__).resolve().parents[1])).strip("'") in out



def test_the_guard_catches_a_sys_path_leak_from_a_test_body(pytester):
    result = _run(pytester, """
        import sys

        def test_leaks_a_path():
            sys.path.insert(0, OURS)

        def test_next():
            assert True
    """.replace("OURS", repr(str(pathlib.Path(__file__).resolve().parents[1]))))
    result.assert_outcomes(errors=1, passed=2)
    assert "sys.path" in result.stdout.str()


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
            # Relative to the baseline, not absolute. Asserting `"esm_tool" not in
            # sys.modules` made this suite's colour depend on whether torch happened to
            # be installed on the machine running it.
            assert sys.modules.get("esm_tool") is stub_contract.baseline["esm_tool"]
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


def test_the_setup_hook_fails_a_test_that_starts_with_dirty_state(stub_contract):
    """The sibling hooks repair before failing, so this one cannot fire through the
    suite and no suite-level test can pin it. Called directly instead: without this,
    deleting it entirely leaves the suite green."""
    class _Item:
        nodeid = "probe::item"

    ours = stub_contract.demo_dir
    sys.path.insert(0, ours)
    try:
        # pytest.fail raises Failed, which derives from BaseException, not Exception.
        with pytest.raises(BaseException) as refused:
            stub_contract.runtest_setup(_Item())
    finally:
        while ours in sys.path:
            sys.path.remove(ours)
    message = str(refused.value)
    assert "sys.path" in message
    assert "not necessarily the one that caused it" in message, \
        "the hook must not assert a cause it cannot know"


def test_the_setup_hook_fails_a_test_that_starts_with_a_faked_module(stub_contract,
                                                                     monkeypatch):
    """The setup hook has two halves and only the sys.path one was pinned.

    Mutating `leaked, paths = _leaked(), _path_leaks()` to `[], _path_leaks()` — the hook
    blind to substituted modules, which is the entire point of the file — left all 38
    tests passing. Called directly, because the hook repairs before it fails, so no
    suite-level test can observe it.
    """
    class _Item:
        nodeid = "probe::item"

    fake = types.ModuleType("torch")
    monkeypatch.setitem(sys.modules, "torch", fake)
    with pytest.raises(BaseException) as refused:      # pytest.fail raises Failed
        stub_contract.runtest_setup(_Item())
    message = str(refused.value)
    assert "torch" in message, "the hook did not name the substituted module"
    assert "sys.modules" in message
    assert sys.modules.get("torch") is stub_contract.baseline["torch"], \
        "the hook must repair before failing, or one leak fails every later test"


def test_one_leak_fails_one_test_and_the_rest_of_the_session_survives(pytester):
    """_repair's docstring promises 'ONE leak fails ONE test instead of every test after
    it'. Only the sys.path half of that promise was tested: deleting the sys.modules
    restore loop entirely left all 38 tests passing.

    Three tests, the first of which leaks. With repair: one teardown error, three passes.
    Without it, the two later tests die at setup too — which is the cascade.
    """
    result = _run(pytester, """
        import sys, types

        def test_leaks():
            sys.modules["torch"] = types.ModuleType("torch")

        def test_after_one():
            assert True

        def test_after_two():
            assert True
    """)
    assert result.ret != 0, "the leak was not reported at all"
    result.assert_outcomes(passed=3, errors=1)
    assert "left global import state dirty" in result.stdout.str() + result.stderr.str()


@pytest.mark.parametrize("forgery", [
    'fake.__file__ = "/not/a/real/file.py"',
    'fake.__spec__ = importlib.util.spec_from_file_location("yaml", __REAL_PATH__)',
    'fake.__spec__ = importlib.machinery.ModuleSpec("yaml", None, origin="built-in")',
    'fake.__spec__ = importlib.machinery.ModuleSpec("yaml", None, is_package=True)',
], ids=["dunder-file", "forged-origin", "built-in-origin", "package-shaped"])
def test_no_attribute_a_fake_can_set_makes_it_look_authentic(pytester, forgery):
    """Every earlier version of this guard authenticated a module from its OWN
    attributes — first __file__, then __spec__.origin — and each was defeated by a
    three-line fake that simply set the attribute. Identity cannot be forged.

    The forged-origin case points the spec at the REAL yaml file: that is the strongest
    attack on origin-based authentication, and it and built-in-origin are pinned nowhere
    else in this file.

    This test was itself vacuous when written: the placeholder was "REAL", which
    str.replace also rewrote inside "REAL_YAML", so every probe was a SyntaxError and all
    four parametrisations passed against a deleted guard. _run now compiles the probe.
    """
    import yaml as real_yaml
    source = """
        import importlib.machinery, importlib.util, sys, types
        fake = types.ModuleType("yaml")
        __FORGERY__
        fake.safe_load = lambda *a, **k: {"pwned": True}
        sys.modules["yaml"] = fake

        def test_harmless():
            assert True
    """.replace("__FORGERY__", forgery).replace("__REAL_PATH__", repr(real_yaml.__file__))
    _assert_the_guard_refused(_run(pytester, source), expect="yaml")


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
    _assert_the_guard_refused(result, expect="esm_tool")


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
    _assert_the_guard_refused(result, expect="aviary.core")


def test_a_shadow_beside_the_conftest_is_not_recorded_as_the_baseline(pytester):
    """The docstring said third-party names resolve on a CLEAN sys.path. They did not:
    pytest's prepend import mode puts the conftest's own directory at the front of
    sys.path before configure runs, and `python -m pytest` adds the working directory.
    A yaml.py in either place was imported at configure, recorded as the genuine
    baseline, and then defended by the guard for the whole session — the guard
    poisoning its own ground truth, the shape the docstring claimed was closed.

    The probe asserts the shadow file really exists beside the conftest, so the test
    cannot pass by the shadow never being in play."""
    pytester.makepyfile(yaml="FAKE = True\ndef safe_load(*a, **k): return {}\n")
    result = _run(pytester, """
        import pathlib

        def test_the_baseline_is_the_real_library(stub_contract):
            assert (pathlib.Path(__file__).parent / "yaml.py").exists()
            base = stub_contract.baseline["yaml"]
            assert not getattr(base, "FAKE", False), f"shadow recorded as baseline: {base.__file__}"
            assert hasattr(base, "safe_dump"), "not the real library"
    """)
    result.assert_outcomes(passed=1)


def test_a_shadowing_directory_cannot_validate_its_own_fake(pytester):
    """A directory placed on sys.path that answers to a watched name.

    The probe must drop the cached module first: every watched name is pre-imported at
    configure, so a bare `import yaml` is a cache hit and the shadow never loads. Without
    the pop this test passed against a deleted guard — the probe's own assertion failed,
    the run exited non-zero, and `ret != 0` was satisfied by that instead.

    The probe asserts the shadow really loaded, so the scenario cannot silently stop
    happening again.
    """
    result = _run(pytester, """
        import sys, pathlib
        here = pathlib.Path(__file__).parent
        (here / "yaml.py").write_text("FAKE = True\\ndef safe_load(*a, **k): return {}\\n")
        sys.path.insert(0, str(here))
        sys.modules.pop("yaml", None)
        import yaml
        assert yaml.FAKE is True, "the shadow did not load; this probe proves nothing"

        def test_harmless():
            assert True
    """)
    _assert_the_guard_refused(result, expect="yaml")


def test_a_package_shaped_fake_at_a_dotted_name_is_caught(pytester):
    """aviary.core is where the Environment and Tool classes come from. A spec built
    with is_package=True used to exempt it outright — the shape that makes a budget
    enforcement test pass while measuring a stub."""
    result = _run(pytester, """
        import importlib.machinery, importlib.util, sys
        spec = importlib.machinery.ModuleSpec("aviary.core", None, is_package=True)
        fake = importlib.util.module_from_spec(spec)
        fake.Environment = object
        sys.modules["aviary.core"] = fake

        def test_harmless():
            assert True
    """)
    _assert_the_guard_refused(result, expect="aviary.core")


def test_a_sourceless_pyc_shadow_is_caught(pytester, tmp_path):
    """A .pyc with no source imports happily, and the old shadow heuristic looked only
    for <name>.py and <name>/ so it could not see one.

    The probe asserts it really loaded the .pyc. Without that this test passed with the
    shadow directory never placed on sys.path and the .pyc never compiled — it was
    exercising pop-and-reimport and nothing else.
    """
    import py_compile
    src = tmp_path / "yaml.py"
    src.write_text("FAKE = True\n")
    shadow = pytester.mkdir("pyc_shadow")
    py_compile.compile(str(src), cfile=str(shadow / "yaml.pyc"), doraise=True)
    result = _run(pytester, """
        import sys
        sys.path.insert(0, __SHADOW__)
        sys.modules.pop("yaml", None)
        import yaml
        assert yaml.FAKE is True, "the .pyc shadow did not load; this probe proves nothing"
        assert yaml.__file__.endswith(".pyc"), yaml.__file__

        def test_harmless():
            assert True
    """.replace("__SHADOW__", repr(str(shadow))))
    _assert_the_guard_refused(result, expect="yaml")


@pytest.mark.parametrize("name", [
    "yaml", "requests", "openai", "weave", "aviary", "aviary.core", "spend_tracker"])
def test_every_preimported_name_really_holds_the_real_module(name, stub_contract):
    """Without this, the guard degrades silently.

    A PREIMPORT name that stops importing gets baseline None, and its check quietly drops
    from identity to presence — still safe, but no longer the property the file claims,
    and nothing would say so. Measured before this test existed: five of twelve watched
    names had no baseline at all and every test was green.
    """
    assert name in stub_contract.preimport
    assert stub_contract.baseline[name] is not None, (
        f"{name} did not import at configure "
        f"({stub_contract.import_failures.get(name, 'no reason recorded')}), so its check "
        "silently degraded from identity to presence")


def test_no_preimported_name_failed_to_import(stub_contract):
    """The reason is recorded rather than swallowed — `except Exception: pass` is why the
    degradation above was invisible for four review passes."""
    assert stub_contract.import_failures == {}, stub_contract.import_failures


def test_the_modules_under_test_are_not_imported_by_collecting_the_suite(stub_contract):
    """run_discovery's module body builds an openai client from os.environ["WANDB_API_KEY"].
    Collecting a test suite must not execute that, and must not depend on a secret."""
    for name in ("esm_tool", "biosim_env", "run_discovery"):
        assert stub_contract.baseline[name] is None, (
            f"{name} was imported at configure; collecting this suite now runs production "
            "code and, for run_discovery, reads a credential from the environment")
