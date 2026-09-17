"""BioSimEnv must ENFORCE its budget, not merely carry a tracker.

Each test targets a way the fix could look done while the refusal is still absent:
a check() swallowed by step()'s generic tool-error handler, a ledger the metered
actor can write to, or a refusal that fires after the next tool has
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
    """check() runs before EVERY call in a batch, not once per batch. No offered tool
    spends today, so a paid tool is simulated: its first call charges past the ceiling
    and the second call in the same batch must not run."""
    env = _env(ceiling=1.0)
    real = env._fns["score_variant"]

    def paid_score_variant(**kwargs):
        env.charge("paid-tool", 5.0)
        return real(**kwargs)

    env._fns["score_variant"] = paid_score_variant
    with pytest.raises(BudgetExceeded):
        _step(env,
              ("score_variant", {"accession": "P01308", "mutation": "A12G"}),
              ("score_variant", {"accession": "P01308", "mutation": "C7S"}))
    assert CALLS == ["score_variant:A12G"], "the call after the crossing one must not run"


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


# --- Principal ruling (#152): the actor being metered must not be able to write the
# ledger that meters it. The agent gets a read-only `spend_remaining`; every write
# goes through the harness's charge().

def _tool_names(env):
    return {t.info.name for t in env.tools}


def test_the_agent_is_offered_no_tool_that_writes_the_ledger():
    env = _env(ceiling=1.0)
    assert _tool_names(env) == {"score_variant", "embed_sequence", "spend_remaining"}


@pytest.mark.parametrize("cost", [-100.0, float("nan"), "nan", float("-inf"), 0.5, 1e9])
def test_a_record_call_from_the_agent_is_not_a_tool_and_cannot_touch_the_ledger(cost):
    """Regression for the bypass: record(cost_usd=-100) or 'nan' used to switch the
    budget off. It must now be refused as an unknown tool, whatever the cost."""
    env = _env(ceiling=1.0)
    env.charge("model-call-1", 5.0)                 # genuinely over budget
    obs, *_ = _step(env, ("record", {"call_id": "agent", "cost_usd": cost}))
    assert "no such tool" in str(obs[0].content)
    assert env.tracker.total() == pytest.approx(5.0)
    with pytest.raises(BudgetExceeded):
        _step(env, ("score_variant", {"accession": "P01308", "mutation": "A12G"}))


def test_spend_remaining_reports_the_ceiling_minus_recorded_spend():
    env = _env(ceiling=2.0)
    env.charge("model-call-1", 0.5)
    obs, *_ = _step(env, ("spend_remaining", {}))
    assert float(obs[0].content) == pytest.approx(1.5)


def test_spend_remaining_is_read_only():
    env = _env(ceiling=2.0)
    env.charge("model-call-1", 0.5)
    for _ in range(3):
        _step(env, ("spend_remaining", {}))
    assert env.tracker.total() == pytest.approx(0.5)


def test_spend_remaining_does_not_overstate_what_is_left():
    """At the ceiling nothing is left, and it must say so rather than round up."""
    env = _env(ceiling=1.0)
    env.charge("model-call-1", 1.0)
    obs, *_ = _step(env, ("spend_remaining", {}))
    assert float(obs[0].content) == pytest.approx(0.0)


@pytest.mark.parametrize("bad_cost", [-1.0, float("nan"), float("-inf"), float("inf"), True, "abc"])
def test_the_harness_ledger_path_rejects_nonsense_loudly(bad_cost):
    env = _env(ceiling=10.0)
    with pytest.raises(ValueError):
        env.charge("model-call-1", bad_cost)
    assert env.tracker.total() == 0.0
