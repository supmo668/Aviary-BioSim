"""Sealed challenge suite for U-005 (satisfies R4).

Contract under test (taken from the interface skeleton only -- the
implementation was not read):

    SpendTracker.persist(path)               -> writes recorded spend to
                                                `path`, durably.
    SpendTracker.restore(path, ceiling_usd)  -> rebuilds a tracker from state
                                                previously written to `path`.

Categories
----------
functional/persistence-roundtrip
    State written by `persist` and read back by `restore` reconstructs the
    recorded spend, and the restored tracker is a working tracker carrying the
    ceiling the *caller* handed to `restore`.
integration/crash-atomicity
    A reader must never observe a partially written state file, even when a
    later `persist` dies part-way through writing.

Questions for the principal (spec ambiguities, deliberately NOT assumed here)
----------------------------------------------------------------------------
1. The on-disk format, file extension and encoding are unspecified, so nothing
   here inspects file contents -- durability is only ever observed through
   `restore`.
2. The spec does not say whether a `persist` that dies mid-write must leave the
   *previous* state or may leave the *new* complete state. Both satisfy "never
   partially written", so the atomicity tests accept either complete state and
   fail only on a truncated, emptied, missing or unreadable file.
3. Whether `persist` must create missing parent directories is unspecified;
   these tests only persist to paths whose parent already exists.
"""

import builtins
import importlib
import io
import os

import pytest

from demo.spend_tracker import SpendTracker


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _budget_error():
    """The refusal type raised by `check`, looked up lazily so that a rename
    can never turn this suite into a collection-time error."""
    module = importlib.import_module("demo.spend_tracker")
    return getattr(module, "BudgetExceeded", Exception)


class _FailingHandle:
    """Behaves exactly like the file object it wraps, except that every write
    raises -- standing in for a process that dies part-way through a write."""

    def __init__(self, wrapped):
        self._wrapped = wrapped

    def write(self, *args, **kwargs):
        raise OSError("simulated crash part-way through writing")

    def writelines(self, *args, **kwargs):
        raise OSError("simulated crash part-way through writing")

    def __getattr__(self, name):
        return getattr(self._wrapped, name)

    def __iter__(self):
        return iter(self._wrapped)

    def __enter__(self):
        self._wrapped.__enter__()
        return self

    def __exit__(self, *exc_info):
        return self._wrapped.__exit__(*exc_info)


def _crashing_open(real_open):
    """Wrap an `open` so that handles opened for writing refuse bytes.

    Handles opened for reading are passed straight through untouched, so
    nothing but the act of writing is disturbed.
    """

    def _open(file, mode="r", *args, **kwargs):
        handle = real_open(file, mode, *args, **kwargs)
        if isinstance(mode, str) and any(ch in mode for ch in "wax+"):
            return _FailingHandle(handle)
        return handle

    return _open


def _refusing_os_write(fd, data, *args, **kwargs):
    raise OSError("simulated crash part-way through writing")


def _install_write_crash(monkeypatch):
    """Make every stdlib route from Python bytes to the filesystem fail.

    Whatever strategy a writer uses, it reaches the disk through
    `builtins.open`, through `io.open` (where `pathlib.Path.open`,
    `Path.write_text`, `Path.write_bytes`, `os.fdopen` and `tempfile` all
    funnel), or through the raw `os.write` syscall wrapper. Patching those
    three assumes no particular temp-file name, call sequence or format: a
    writer that opens the real path directly is left with a truncated file,
    while a writer that stages bytes elsewhere and swaps them in atomically
    leaves the real path untouched.
    """
    monkeypatch.setattr(builtins, "open", _crashing_open(builtins.open))
    monkeypatch.setattr(io, "open", _crashing_open(io.open))
    monkeypatch.setattr(os, "write", _refusing_os_write)


def _persist_through_a_crash(monkeypatch, tracker, path):
    """Attempt one `persist` with all writes failing, then fully restore the
    stdlib. Whether the failure propagates or is swallowed is the
    implementer's call; only the file left behind is asserted on."""
    _install_write_crash(monkeypatch)
    try:
        tracker.persist(path)
    except Exception:
        pass
    finally:
        monkeypatch.undo()


# --------------------------------------------------------------------------
# functional/persistence-roundtrip
# --------------------------------------------------------------------------

def test_persist_then_restore_reconstructs_recorded_spend(tmp_path):
    """functional/persistence-roundtrip"""
    state = tmp_path / "spend-state"
    assert not state.exists()

    tracker = SpendTracker(10.0)
    tracker.record("call-a", 1.25)
    tracker.record("call-b", 2.50)
    tracker.record("call-c", 0.75)
    expected = tracker.total()

    tracker.persist(state)

    restored = SpendTracker.restore(state, 10.0)

    # The failure this guards against above all others: a resumed run whose
    # budget has silently gone back to zero.
    assert restored.total() != 0.0
    assert restored.total() == pytest.approx(expected)
    assert restored.total() == pytest.approx(4.50)


def test_persist_accepts_a_path_that_does_not_exist_yet(tmp_path):
    """functional/persistence-roundtrip"""
    state = tmp_path / "brand-new-state"
    assert not state.exists()

    tracker = SpendTracker(5.0)
    tracker.record("only", 0.10)
    tracker.persist(state)

    assert state.exists()
    assert state.stat().st_size > 0
    assert SpendTracker.restore(state, 5.0).total() == pytest.approx(0.10)


def test_restore_of_an_empty_ledger_round_trips_as_zero(tmp_path):
    """functional/persistence-roundtrip"""
    state = tmp_path / "empty-state"

    SpendTracker(3.0).persist(state)

    assert SpendTracker.restore(state, 3.0).total() == pytest.approx(0.0)


def test_persisting_twice_leaves_the_later_state(tmp_path):
    """functional/persistence-roundtrip"""
    state = tmp_path / "state"

    tracker = SpendTracker(20.0)
    tracker.record("first", 1.00)
    tracker.persist(state)

    tracker.record("second", 3.00)
    tracker.persist(state)

    assert SpendTracker.restore(state, 20.0).total() == pytest.approx(4.00)


def test_restored_tracker_keeps_accumulating_on_top_of_restored_spend(tmp_path):
    """functional/persistence-roundtrip"""
    state = tmp_path / "state"

    first_process = SpendTracker(100.0)
    first_process.record("before-restart", 6.00)
    first_process.persist(state)

    second_process = SpendTracker.restore(state, 100.0)
    second_process.record("after-restart", 4.00)

    assert second_process.total() == pytest.approx(10.00)

    # ... and that continued spend is itself durable.
    second_process.persist(state)
    assert SpendTracker.restore(state, 100.0).total() == pytest.approx(10.00)


def test_restored_tracker_uses_the_ceiling_it_was_handed(tmp_path):
    """functional/persistence-roundtrip"""
    state = tmp_path / "state"

    tracker = SpendTracker(50.0)
    tracker.record("spend", 8.00)
    tracker.persist(state)

    # The ceiling is an argument to `restore`, so it comes from the caller and
    # not from the file: the same state file under a generous ceiling is fine,
    # under a stingy one it is a refusal.
    generous = SpendTracker.restore(state, 50.0)
    assert generous.total() == pytest.approx(8.00)
    assert generous.check() is None

    stingy = SpendTracker.restore(state, 2.00)
    assert stingy.total() == pytest.approx(8.00)
    with pytest.raises(_budget_error()):
        stingy.check()


# --------------------------------------------------------------------------
# integration/crash-atomicity
# --------------------------------------------------------------------------

def test_a_persist_that_dies_mid_write_never_leaves_a_partial_file(
    tmp_path, monkeypatch
):
    """integration/crash-atomicity"""
    state = tmp_path / "state"

    tracker = SpendTracker(100.0)
    tracker.record("committed", 7.00)
    tracker.persist(state)

    # Sanity: a complete, readable state exists on disk before the crash.
    assert SpendTracker.restore(state, 100.0).total() == pytest.approx(7.00)

    tracker.record("in-flight", 5.00)
    _persist_through_a_crash(monkeypatch, tracker, state)

    # Whatever happened inside `persist`, a reader must still see a complete
    # state file: present, non-empty, readable, and holding one of the two
    # complete totals -- never a truncated or half-written file, and never a
    # silent reset to zero.
    assert state.exists(), "the previously persisted state file was removed"
    assert state.stat().st_size > 0, "the state file was truncated to nothing"

    reader = SpendTracker.restore(state, 100.0)
    observed = reader.total()
    assert observed != 0.0, "recorded spend was silently reset to zero"
    assert observed == pytest.approx(7.00) or observed == pytest.approx(12.00), (
        "a reader observed neither the old nor the new complete state "
        "(total was %r)" % (observed,)
    )


def test_state_survives_a_mid_write_crash_well_enough_to_keep_running(
    tmp_path, monkeypatch
):
    """integration/crash-atomicity"""
    state = tmp_path / "state"

    tracker = SpendTracker(10.0)
    tracker.record("committed", 9.00)
    tracker.persist(state)

    tracker.record("in-flight", 0.50)
    _persist_through_a_crash(monkeypatch, tracker, state)

    # A resumed run reads the surviving state and is still budget-aware: the
    # spend it recovers is close enough to the ceiling that the next big call
    # must be refused.
    resumed = SpendTracker.restore(state, 10.0)
    assert resumed.total() >= 9.00
    assert resumed.check() is None

    resumed.record("next", 5.00)
    with pytest.raises(_budget_error()):
        resumed.check()
