"""Sealed challenge suite — build unit U-001.

Satisfies R1: every model call's cost is recorded against the call that
incurred it, and the total spent so far is available at any time.

Unit statement under test:
    SpendTracker.record accumulates each call's cost and SpendTracker.total
    returns the running sum, 0.0 before anything is recorded.

Scope: SpendTracker.__init__, SpendTracker.record, SpendTracker.total only.
Nothing here calls load_ceiling, check, persist, restore, or BudgetExceeded,
and nothing here touches a private attribute — the contract is exercised
purely through record() and total().

Category: functional/spend-accumulation

Ambiguities recorded for the principal (deliberately NOT asserted here,
because the spec does not settle them):
  1. Recording the same call_id twice — replace the prior cost, sum both, or
     refuse? Undefined by the unit statement, so this suite only ever uses
     distinct call_ids.
  2. Whether a zero or negative cost is admissible, and whether record()
     itself is expected to refuse once the ceiling is passed (the skeleton
     assigns refusal to check(), so every ceiling here is set far above the
     recorded spend to keep the two concerns separate).
"""

from __future__ import annotations

import pytest

from demo.spend_tracker import SpendTracker


CEILING = 1_000_000.0


def test_fresh_tracker_totals_zero() -> None:
    """Before anything is recorded the running sum is 0.0, not None/absent."""
    tracker = SpendTracker(CEILING)

    total = tracker.total()

    assert total == pytest.approx(0.0)
    assert isinstance(total, float)


def test_constructor_keeps_ceiling_as_float() -> None:
    """The declared ceiling is retained as a float and is not the spend."""
    tracker = SpendTracker(25)

    assert tracker.ceiling_usd == pytest.approx(25.0)
    assert isinstance(tracker.ceiling_usd, float)
    assert tracker.total() == pytest.approx(0.0)


def test_single_recorded_call_is_reflected_in_total() -> None:
    """One record() shows up in total()."""
    tracker = SpendTracker(CEILING)

    assert tracker.record("call-1", 0.25) is None
    assert tracker.total() == pytest.approx(0.25)


def test_several_distinct_calls_accumulate() -> None:
    """Costs from distinct call_ids add up rather than overwrite."""
    tracker = SpendTracker(CEILING)

    tracker.record("call-a", 1.0)
    assert tracker.total() == pytest.approx(1.0)

    tracker.record("call-b", 2.0)
    assert tracker.total() == pytest.approx(3.0)

    tracker.record("call-c", 4.5)
    assert tracker.total() == pytest.approx(7.5)


def test_fractional_costs_sum_correctly() -> None:
    """Sub-cent per-call costs accumulate to the right running sum."""
    tracker = SpendTracker(CEILING)

    for index in range(1000):
        tracker.record(f"call-{index}", 0.001)

    assert tracker.total() == pytest.approx(1.0)


def test_mixed_magnitude_costs_sum_correctly() -> None:
    """Mixing large and tiny costs still yields the arithmetic sum."""
    tracker = SpendTracker(CEILING)
    costs = [0.000_01, 12.5, 0.3, 7.25, 0.000_004]

    for index, cost in enumerate(costs):
        tracker.record(f"mixed-{index}", cost)

    assert tracker.total() == pytest.approx(sum(costs))


def test_total_is_a_query_not_a_consumer() -> None:
    """Reading total() repeatedly neither drains nor re-counts the spend."""
    tracker = SpendTracker(CEILING)
    tracker.record("call-1", 3.0)
    tracker.record("call-2", 1.5)

    first = tracker.total()
    second = tracker.total()
    third = tracker.total()

    assert first == pytest.approx(4.5)
    assert second == pytest.approx(4.5)
    assert third == pytest.approx(4.5)


def test_trackers_do_not_share_recorded_spend() -> None:
    """Each tracker accumulates its own spend — no shared/class-level state."""
    first = SpendTracker(CEILING)
    second = SpendTracker(CEILING)

    first.record("call-1", 5.0)

    assert first.total() == pytest.approx(5.0)
    assert second.total() == pytest.approx(0.0)

    second.record("call-2", 2.0)

    assert first.total() == pytest.approx(5.0)
    assert second.total() == pytest.approx(2.0)


def test_integer_costs_are_accumulated_as_numbers() -> None:
    """An int cost is summed numerically, not concatenated or coerced away."""
    tracker = SpendTracker(CEILING)

    tracker.record("call-int", 3)
    tracker.record("call-float", 0.5)

    assert tracker.total() == pytest.approx(3.5)
