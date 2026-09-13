"""Sealed challenge suite for U-004 (satisfies R3).

Unit statement:
    SpendTracker.check returns None at or below the ceiling and raises
    BudgetExceeded above it.

Categories exercised here (stable labels, referee-visible):
    functional/check-empty         -- fresh tracker is within budget
    functional/check-boundary      -- just below / exactly at / just above
    functional/check-return-value  -- returns None literally, not merely falsy
    functional/refusal-attribution -- BudgetExceeded carries total and ceiling
    functional/check-idempotence   -- check is a query, not a state transition

Fixture note: every cost and ceiling below is a dyadic rational (a sum of
powers of two, e.g. 0.5, 0.25, 0.125, 2.0), so the accumulated total lands on
the ceiling EXACTLY under IEEE-754 binary64. No assertion here depends on a
tolerance, and one test re-derives the ceiling from the tracker's own reported
total so that "exactly at the ceiling" is exact by construction rather than by
arithmetic luck.

Written against the interface contract only; the implementation was not read.
"""

import pytest

from demo.spend_tracker import SpendTracker, BudgetExceeded


# ---------------------------------------------------------------------------
# functional/check-empty
# ---------------------------------------------------------------------------

def test_check_on_fresh_tracker_returns_none():
    """A tracker with nothing recorded is within budget."""
    tracker = SpendTracker(1.0)
    assert tracker.check() is None


def test_check_on_fresh_tracker_with_zero_ceiling_returns_none():
    """Zero spend against a zero ceiling is 'at or below', so it passes."""
    tracker = SpendTracker(0.0)
    assert tracker.total() == 0.0
    assert tracker.check() is None


# ---------------------------------------------------------------------------
# functional/check-boundary
# ---------------------------------------------------------------------------

def test_check_below_ceiling_returns_none():
    """Spend strictly under the ceiling does not refuse."""
    tracker = SpendTracker(1.0)
    tracker.record("call-a", 0.5)
    tracker.record("call-b", 0.25)
    assert tracker.total() == 0.75
    assert tracker.check() is None


def test_check_exactly_at_ceiling_does_not_raise():
    """THE boundary case: the ceiling is an inclusive, passing value.

    0.5 + 0.25 + 0.25 is exactly 1.0 in binary64, so "exactly at" is genuine.
    """
    tracker = SpendTracker(1.0)
    tracker.record("call-a", 0.5)
    tracker.record("call-b", 0.25)
    tracker.record("call-c", 0.25)
    assert tracker.total() == 1.0, "fixture drift: total must sit exactly on the ceiling"
    assert tracker.check() is None


def test_check_exactly_at_ceiling_derived_from_reported_total():
    """Same boundary, but the ceiling is taken from the tracker's own total.

    This removes any possibility that the fixture is accidentally just-above:
    the declared ceiling IS the accumulated total, bit for bit.
    """
    probe = SpendTracker(1000000000.0)
    probe.record("c1", 0.125)
    probe.record("c2", 0.375)
    probe.record("c3", 2.0)
    spent = probe.total()

    tracker = SpendTracker(spent)
    tracker.record("c1", 0.125)
    tracker.record("c2", 0.375)
    tracker.record("c3", 2.0)

    assert tracker.total() == tracker.ceiling_usd
    assert tracker.check() is None


def test_check_just_above_ceiling_raises():
    """One representable step past the ceiling refuses."""
    tracker = SpendTracker(1.0)
    tracker.record("call-a", 0.5)
    tracker.record("call-b", 0.25)
    tracker.record("call-c", 0.25)
    tracker.record("call-d", 0.125)
    assert tracker.total() == 1.125
    with pytest.raises(BudgetExceeded):
        tracker.check()


def test_check_raises_when_a_single_call_overshoots():
    """A lone call larger than the whole ceiling refuses immediately."""
    tracker = SpendTracker(0.5)
    tracker.record("whale", 4.0)
    with pytest.raises(BudgetExceeded):
        tracker.check()


def test_crossing_the_ceiling_flips_check_from_pass_to_refuse():
    """The same tracker passes at the ceiling and refuses one step later."""
    tracker = SpendTracker(2.0)
    tracker.record("a", 1.0)
    tracker.record("b", 1.0)
    assert tracker.check() is None
    tracker.record("c", 0.25)
    with pytest.raises(BudgetExceeded):
        tracker.check()


# ---------------------------------------------------------------------------
# functional/check-return-value
# ---------------------------------------------------------------------------

def test_check_returns_none_literally_not_merely_falsy():
    """0, 0.0, False and "" are all falsy; the contract says None."""
    tracker = SpendTracker(1.0)
    tracker.record("a", 0.5)
    result = tracker.check()
    assert result is None
    assert not isinstance(result, bool)


# ---------------------------------------------------------------------------
# functional/refusal-attribution  (the attributability half of R3)
# ---------------------------------------------------------------------------

def test_budget_exceeded_carries_the_actual_total_and_declared_ceiling():
    """The refusal names what was spent and what was declared."""
    tracker = SpendTracker(1.0)
    tracker.record("a", 0.75)
    tracker.record("b", 0.75)
    spent = tracker.total()
    assert spent == 1.5

    with pytest.raises(BudgetExceeded) as excinfo:
        tracker.check()

    assert excinfo.value.total_usd == spent
    assert excinfo.value.ceiling_usd == 1.0


def test_budget_exceeded_is_a_runtime_error():
    """Callers may catch the refusal as a RuntimeError."""
    tracker = SpendTracker(0.5)
    tracker.record("a", 2.0)
    with pytest.raises(RuntimeError):
        tracker.check()


# ---------------------------------------------------------------------------
# functional/check-idempotence  (check is a query, not a transition)
# ---------------------------------------------------------------------------

def test_repeated_check_within_budget_does_not_change_the_total():
    tracker = SpendTracker(4.0)
    tracker.record("a", 1.0)
    tracker.record("b", 0.5)
    before = tracker.total()
    for _ in range(5):
        assert tracker.check() is None
    assert tracker.total() == before


def test_an_over_budget_tracker_keeps_refusing():
    """Refusal is a standing condition, not a one-shot alarm."""
    tracker = SpendTracker(1.0)
    tracker.record("a", 1.0)
    tracker.record("b", 0.5)
    before = tracker.total()

    for _ in range(3):
        with pytest.raises(BudgetExceeded) as excinfo:
            tracker.check()
        assert excinfo.value.total_usd == before
        assert excinfo.value.ceiling_usd == 1.0

    assert tracker.total() == before


def test_check_does_not_disturb_a_later_exact_boundary():
    """Querying below the ceiling leaves the inclusive boundary intact."""
    tracker = SpendTracker(1.0)
    tracker.record("a", 0.5)
    assert tracker.check() is None
    tracker.record("b", 0.5)
    assert tracker.total() == 1.0
    assert tracker.check() is None
