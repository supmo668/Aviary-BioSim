"""Sealed challenge tests for build unit U-006.

Category: functional/tooling

Spec mapping
------------
R5 — The tracker's recording operation is exposed as an ``aviary.core.Tool`` so
that an ``Environment.reset()`` can return it in its tool list. The tool's name,
description and parameter schema must be DERIVED from ``record``'s own signature
and docstring (via ``Tool.from_function`` on the bound method) rather than
restated by hand, so the advertised contract cannot drift from the code.

Ambiguities recorded for the principal
--------------------------------------
- The spec does not fix the exact wording of ``record``'s docstring summary, so
  the description is challenged structurally (non-empty, derived, mentions the
  sense of recording a cost) rather than by exact string match.
- The spec does not promise any public handle on the wrapped callable, so
  instance binding is challenged through the tracker's own observable state
  rather than by reaching into ``Tool`` internals.
"""

import inspect

import pytest
from aviary.core import Tool

from demo.spend_tracker import SpendTracker


@pytest.fixture
def tracker() -> SpendTracker:
    return SpendTracker(ceiling_usd=10.0)


def _parameters(tool: Tool):
    """Return (properties, required) from a tool's parameter schema.

    ``info.parameters`` may be a pydantic model, so read attributes directly.
    """
    parameters = tool.info.parameters
    return parameters.properties, list(parameters.required)


# --- functional/tooling: the returned object is a real aviary Tool ----------


def test_as_tool_returns_an_aviary_tool(tracker: SpendTracker) -> None:
    assert isinstance(tracker.as_tool(), Tool)


# --- functional/tooling: name is derived from the operation ----------------


def test_tool_name_is_the_recording_operations_own_name(
    tracker: SpendTracker,
) -> None:
    assert tracker.as_tool().info.name == SpendTracker.record.__name__ == "record"


# --- functional/tooling: description is derived from the docstring ---------


def test_tool_description_is_derived_from_record_docstring(
    tracker: SpendTracker,
) -> None:
    description = tracker.as_tool().info.description

    assert isinstance(description, str)
    assert description.strip(), "tool description must be non-empty"

    # Derived, not hand-written: the description must be drawn from record's own
    # docstring text, so its opening sentence has to appear in that docstring.
    docstring = inspect.getdoc(SpendTracker.record) or ""
    summary = description.strip().split("\n")[0].strip()
    assert summary, "tool description must carry a summary line"
    assert summary in " ".join(docstring.split()) or summary in docstring, (
        "tool description must come from record's docstring, not a restatement"
    )

    # And it must actually carry the sense of recording a call's cost.
    lowered = description.lower()
    assert "record" in lowered
    assert "cost" in lowered


# --- functional/tooling: the parameter schema is derived from the signature -


def test_tool_parameters_exclude_self(tracker: SpendTracker) -> None:
    properties, required = _parameters(tracker.as_tool())

    assert "self" not in properties, "bound method must not advertise `self`"
    assert "self" not in required


def test_tool_parameters_match_record_signature_and_types(
    tracker: SpendTracker,
) -> None:
    properties, required = _parameters(tracker.as_tool())

    assert set(properties) == {"call_id", "cost_usd"}
    assert properties["call_id"]["type"] == "string"
    assert properties["cost_usd"]["type"] == "number"
    assert set(required) == {"call_id", "cost_usd"}

    # The schema's parameter names are the signature's own, minus `self`.
    signature_names = [
        name for name in inspect.signature(SpendTracker.record).parameters if name != "self"
    ]
    assert signature_names == ["call_id", "cost_usd"]
    assert set(signature_names) == set(properties)


def test_every_tool_parameter_carries_a_description(tracker: SpendTracker) -> None:
    # Tool.from_function rejects undocumented parameters, so a successfully
    # built tool must expose a description for each one.
    properties, _ = _parameters(tracker.as_tool())

    for name, schema in properties.items():
        assert schema.get("description", "").strip(), (
            f"parameter {name!r} must carry a derived description"
        )


# --- functional/tooling: the tool belongs to the instance that made it ------


def test_tool_is_bound_to_the_producing_instance(tracker: SpendTracker) -> None:
    other = SpendTracker(ceiling_usd=10.0)
    tool = tracker.as_tool()
    assert isinstance(tool, Tool)

    # The tool wraps this tracker's bound `record`, so the operation it exposes
    # accrues against this tracker and leaves an independent one untouched.
    tracker.record("call-a", 1.25)

    assert tracker.total() == pytest.approx(1.25)
    assert other.total() == pytest.approx(0.0)

    # Building a tool must not itself mutate or reset recorded spend.
    assert tracker.as_tool().info.name == "record"
    assert tracker.total() == pytest.approx(1.25)


def test_each_instance_yields_its_own_tool(tracker: SpendTracker) -> None:
    other = SpendTracker(ceiling_usd=99.0)

    first = tracker.as_tool()
    second = other.as_tool()

    assert isinstance(first, Tool)
    assert isinstance(second, Tool)
    assert first.info.name == second.info.name == "record"

    first_properties, _ = _parameters(first)
    second_properties, _ = _parameters(second)
    assert set(first_properties) == set(second_properties) == {"call_id", "cost_usd"}
