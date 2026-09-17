"""BioSimEnv must ENFORCE its budget, not merely carry a tracker.

Each test targets a way the fix could look done while the refusal is still absent:
a check() swallowed by step()'s generic tool-error handler, a ledger only the
metered actor can write to, or a refusal that fires after the next tool has
already run. Assertions are about whether the rollout STOPS and whether the tool
RAN — never about a string appearing in a response.
"""
import asyncio
import sys
import types
from pathlib import Path

import pytest

SCIENCE = Path(__file__).resolve().parents[1]
CALLS: list[str] = []


def _stub_esm_tool() -> None:
    """Stand in for esm_tool so the tests never import torch or load ESM-2."""
    mod = types.ModuleType("esm_tool")

    def score_variant(accession: str, mutation: str) -> float:
        """Score a substitution.

        Args:
            accession: UniProt accession.
            mutation: Substitution such as A12G.
        """
        CALLS.append(f"score_variant:{mutation}")
        return -1.25

    def embed_sequence(accession: str) -> int:
        """Embed a sequence.

        Args:
            accession: UniProt accession.
        """
        CALLS.append("embed_sequence")
        raise ValueError("instrument fault")

    mod.score_variant = score_variant
    mod.embed_sequence = embed_sequence
    sys.modules["esm_tool"] = mod


_stub_esm_tool()
sys.path.insert(0, str(SCIENCE))
import biosim_env  # noqa: E402
import spend_tracker  # noqa: E402  same module object biosim_env imported
from aviary.core import ToolCall, ToolRequestMessage  # noqa: E402

BudgetExceeded = spend_tracker.BudgetExceeded


def _env(ceiling: float = 1.0) -> biosim_env.BioSimEnv:
    CALLS.clear()
    env = biosim_env.BioSimEnv("objective", ceiling_usd=ceiling, max_rounds=10)
    asyncio.run(env.reset())
    return env


def _step(env, *calls):
    action = ToolRequestMessage(content=None, tool_calls=[
        ToolCall.from_name(name, **args) for name, args in calls])
    return asyncio.run(env.step(action))


def test_within_budget_the_step_runs_the_tool():
    env = _env(ceiling=1.0)
    obs, reward, done, truncated = _step(env, ("score_variant", {"accession": "P01308", "mutation": "A12G"}))
    assert CALLS == ["score_variant:A12G"]
    assert not done


def test_spend_exactly_at_the_ceiling_still_runs():
    env = _env(ceiling=1.0)
    env.charge("model-call-1", 1.0)
    _step(env, ("score_variant", {"accession": "P01308", "mutation": "A12G"}))
    assert CALLS == ["score_variant:A12G"]


def test_over_budget_the_rollout_stops_and_the_tool_never_runs():
    env = _env(ceiling=1.0)
    env.charge("model-call-1", 1.5)
    with pytest.raises(BudgetExceeded) as refused:
        _step(env, ("score_variant", {"accession": "P01308", "mutation": "A12G"}))
    assert CALLS == [], "a refused step must not spend on the tool it refused"
    assert refused.value.total_usd == pytest.approx(1.5)
    assert refused.value.ceiling_usd == pytest.approx(1.0)


def test_the_refusal_is_not_converted_into_a_tool_error_string():
    """The trap: check() inside step()'s `except Exception` would return
    'tool error: BudgetExceeded: ...' and let the rollout continue."""
    env = _env(ceiling=1.0)
    env.charge("model-call-1", 2.0)
    try:
        result = _step(env, ("score_variant", {"accession": "P01308", "mutation": "A12G"}))
    except BudgetExceeded:
        return
    pytest.fail(f"step returned instead of refusing: {result!r}")


def test_env_side_charge_records_without_the_agent_reporting_anything():
    env = _env(ceiling=10.0)
    env.charge("model-call-1", 0.75)
    env.charge("model-call-2", 0.25)
    assert env.tracker.total() == pytest.approx(1.0)
    assert CALLS == []


def test_crossing_the_ceiling_mid_batch_refuses_the_remaining_calls():
    env = _env(ceiling=1.0)
    with pytest.raises(BudgetExceeded):
        _step(env,
              ("record", {"call_id": "agent-reported", "cost_usd": 5.0}),
              ("score_variant", {"accession": "P01308", "mutation": "A12G"}))
    assert CALLS == [], "the call after the one that crossed the ceiling must not run"


def test_once_over_budget_every_later_step_keeps_refusing():
    env = _env(ceiling=1.0)
    env.charge("model-call-1", 3.0)
    for _ in range(3):
        with pytest.raises(BudgetExceeded):
            _step(env, ("score_variant", {"accession": "P01308", "mutation": "A12G"}))
    assert CALLS == []


def test_an_ordinary_tool_failure_is_still_reported_not_raised():
    env = _env(ceiling=10.0)
    obs, reward, done, truncated = _step(env, ("embed_sequence", {"accession": "P01308"}))
    assert CALLS == ["embed_sequence"]
    assert "tool error" in str(obs[0].content)


# --- QG finding: the agent-facing `record` tool must not be able to lower or poison
# the ledger. The agent is the metered party and its tool arguments are untrusted.

@pytest.mark.parametrize("bad_cost", [-100.0, float("nan"), "nan", float("-inf"), float("inf"), True, "abc"])
def test_the_agent_cannot_lower_or_poison_the_ledger_through_record(bad_cost):
    env = _env(ceiling=1.0)
    env.charge("model-call-1", 5.0)          # genuinely over budget
    before = env.tracker.total()
    obs, *_ = _step_unchecked(env, ("record", {"call_id": "agent", "cost_usd": bad_cost}))
    assert env.tracker.total() == before, f"record({bad_cost!r}) changed the ledger"
    with pytest.raises(BudgetExceeded):     # still refused afterwards
        _step(env, ("score_variant", {"accession": "P01308", "mutation": "A12G"}))


@pytest.mark.parametrize("bad_cost", [-1.0, float("nan"), float("-inf"), float("inf")])
def test_the_harness_ledger_path_rejects_nonsense_loudly(bad_cost):
    env = _env(ceiling=10.0)
    with pytest.raises(ValueError):
        env.charge("model-call-1", bad_cost)
    assert env.tracker.total() == 0.0


def test_a_valid_agent_report_still_counts_and_zero_is_allowed():
    env = _env(ceiling=10.0)
    _step(env, ("record", {"call_id": "agent-1", "cost_usd": 0.5}),
               ("record", {"call_id": "agent-2", "cost_usd": 0}))
    assert env.tracker.total() == pytest.approx(0.5)


def _step_unchecked(env, *calls):
    """Run a step whose single record call happens while already over budget.

    step() refuses before every tool, so to reach record's own validation the
    tracker must be under budget at the moment of the call: lift the ceiling for
    the duration of the step, then restore it.
    """
    ceiling = env.tracker.ceiling_usd
    env.tracker.ceiling_usd = float("inf")
    try:
        return _step(env, *calls)
    finally:
        env.tracker.ceiling_usd = ceiling
