"""Sealed challenge suite for build unit U-003.

Category: functional/budget-exceeded
Spec:     R3 -- once recorded spend has passed the declared ceiling the tracker
          refuses to continue, and the refusal is attributable: it carries what
          was spent and what the ceiling was.
Unit:     BudgetExceeded carries the total and the ceiling as attributes and
          names both in its message.

Scope note: this file exercises BudgetExceeded by direct construction only.
It never calls check(), persist(), restore() or as_tool() -- those belong to
other build units and are out of scope here.

Open question for the principal (recorded, not assumed): the spec does not fix
a rendering for the two numbers in the message (bare float, two decimals,
currency-prefixed). These tests therefore assert only that each number is
*discoverable* in the message, not how it is formatted.
"""

import math
import re

import pytest

from demo.spend_tracker import BudgetExceeded


# A number as a human would write one in a message: optional sign, digits with
# optional thousands separators, optional decimal part. Maximal munch, so
# "10.50" is one token rather than "10" and "50".
_NUMBER_RE = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")

# Tolerance wide enough to accept "10", "10.0", "10.00" and "$10.00" for the
# same value, narrow enough that a different number never counts as a match.
_ABS_TOL = 0.01


def _numbers_in(text):
    """Every number a human could read out of ``text``, as floats."""
    found = []
    for token in _NUMBER_RE.findall(text):
        try:
            found.append(float(token.replace(",", "")))
        except ValueError:  # pragma: no cover - the regex already constrains this
            continue
    return found


def _names_number(text, value):
    """True when ``text`` renders ``value`` in some readable form."""
    return any(
        math.isclose(found, value, rel_tol=0.0, abs_tol=_ABS_TOL)
        for found in _numbers_in(text)
    )


def test_number_detector_is_sound():
    """The message assertions below can actually fail.

    Guards the helper itself: it must find a number that is present under any
    ordinary rendering, and must NOT find one that was omitted.
    """
    for rendering in ("12.5", "12.50", "$12.50", "spent $12.50 so far", "12.5000"):
        assert _names_number(rendering, 12.5), rendering
    assert not _names_number("budget exceeded: ceiling was 10.00", 12.5)
    assert not _names_number("budget exceeded", 10.0)


def test_carries_total_and_ceiling_as_attributes():
    exc = BudgetExceeded(12.5, 10.0)
    assert exc.total_usd == pytest.approx(12.5)
    assert exc.ceiling_usd == pytest.approx(10.0)


def test_constructor_accepts_the_documented_keyword_names():
    exc = BudgetExceeded(total_usd=7.75, ceiling_usd=5.0)
    assert exc.total_usd == pytest.approx(7.75)
    assert exc.ceiling_usd == pytest.approx(5.0)


@pytest.mark.parametrize(
    ("total", "ceiling"),
    [
        (12.5, 10.0),
        (125.0, 100.0),
        (3.0, 1.0),
    ],
)
def test_message_names_both_numbers(total, ceiling):
    """str(exc) must let a human reading a crashed run see both numbers."""
    message = str(BudgetExceeded(total, ceiling))
    assert message, "BudgetExceeded produced an empty message"
    assert _names_number(message, total), (
        "message does not name the spent total {0!r}: {1!r}".format(total, message)
    )
    assert _names_number(message, ceiling), (
        "message does not name the ceiling {0!r}: {1!r}".format(ceiling, message)
    )


def test_is_a_runtime_error():
    assert issubclass(BudgetExceeded, RuntimeError)
    assert isinstance(BudgetExceeded(1.0, 0.5), RuntimeError)


def test_raises_and_is_catchable_as_a_runtime_error_with_attributes_intact():
    with pytest.raises(RuntimeError) as caught:
        raise BudgetExceeded(20.0, 15.0)
    exc = caught.value
    assert isinstance(exc, BudgetExceeded)
    assert exc.total_usd == pytest.approx(20.0)
    assert exc.ceiling_usd == pytest.approx(15.0)
    assert _names_number(str(exc), 20.0)
    assert _names_number(str(exc), 15.0)


def test_catchable_by_its_own_type():
    caught = None
    try:
        raise BudgetExceeded(2.0, 1.0)
    except BudgetExceeded as exc:
        caught = exc
    assert caught is not None, "BudgetExceeded was not catchable by its own type"
    assert caught.total_usd == pytest.approx(2.0)
    assert caught.ceiling_usd == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("total", "ceiling"),
    [
        (1.0, 100.0),   # total below the ceiling
        (10.0, 10.0),   # exactly at the ceiling
        (0.0, 25.0),    # nothing spent yet
    ],
)
def test_is_a_carrier_not_a_validator(total, ceiling):
    """The class must not police the relationship between the two numbers."""
    exc = BudgetExceeded(total, ceiling)
    assert exc.total_usd == pytest.approx(total)
    assert exc.ceiling_usd == pytest.approx(ceiling)
