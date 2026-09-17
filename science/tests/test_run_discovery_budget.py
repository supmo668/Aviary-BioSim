"""The discovery harness meters model calls itself and stops at the ceiling.

The model is stubbed; nothing here reaches the network or loads ESM-2.
"""
import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_biosim_env_budget as envtests  # noqa: E402  installs the esm_tool stub

os.environ.setdefault("WANDB_API_KEY", "test-not-a-real-key")
import run_discovery  # noqa: E402

BudgetExceeded = envtests.BudgetExceeded


@pytest.mark.parametrize("raw", [None, "0", "-1", "abc", "inf", "nan"])  # F12: inf/nan too
def test_an_undeclared_or_meaningless_price_refuses_to_start(monkeypatch, raw):
    if raw is None:
        monkeypatch.delenv("BIOSIM_USD_PER_1M_TOKENS", raising=False)
    else:
        monkeypatch.setenv("BIOSIM_USD_PER_1M_TOKENS", raw)
    with pytest.raises(SystemExit):
        run_discovery.usd_per_1m_tokens()


@pytest.mark.parametrize("raw", ["", "   "])
def test_an_empty_price_is_reported_as_undeclared_not_as_malformed(monkeypatch, capsys, raw):
    """The documented command passes BIOSIM_USD_PER_1M_TOKENS="$PRICE"; with PRICE
    unset that is an empty string, and the operator must be told to declare a price."""
    monkeypatch.setenv("BIOSIM_USD_PER_1M_TOKENS", raw)
    with pytest.raises(SystemExit) as refused:
        run_discovery.usd_per_1m_tokens()
    assert "is not set" in str(refused.value.code)


def test_a_declared_price_is_used(monkeypatch):
    monkeypatch.setenv("BIOSIM_USD_PER_1M_TOKENS", "2.5")
    assert run_discovery.usd_per_1m_tokens() == 2.5


def _turn(calls=None):
    return {"content": "thinking", "prompt_tokens": 600_000, "completion_tokens": 400_000,
            "tool_calls": calls or []}


def test_each_model_call_is_charged_from_the_providers_token_counts(monkeypatch):
    env = envtests._env(ceiling=100.0)
    monkeypatch.setattr(run_discovery, "agent_turn", lambda m, t: _turn())
    run_discovery.paid_turn(env, 3.0, "round-1", [], [])
    assert env.tracker.total() == pytest.approx(3.0)  # 1M tokens at $3 / 1M


def test_over_budget_the_harness_refuses_before_paying_for_another_call(monkeypatch):
    env = envtests._env(ceiling=1.0)
    env.charge("earlier", 5.0)
    paid = []
    monkeypatch.setattr(run_discovery, "agent_turn", lambda m, t: paid.append(1) or _turn())
    with pytest.raises(BudgetExceeded):
        run_discovery.paid_turn(env, 3.0, "round-2", [], [])
    assert paid == []


def test_a_real_rollout_stops_at_the_ceiling(monkeypatch):
    """End to end: an agent that would measure forever is stopped by spend."""
    monkeypatch.setenv("BIOSIM_USD_PER_1M_TOKENS", "1.0")
    monkeypatch.setattr(run_discovery.BioSimEnv.__init__, "__defaults__", (2.5, 5))
    call = {"id": "c1", "name": "score_variant",
            "arguments": '{"accession": "P01308", "mutation": "C7S"}'}
    model_calls = []
    monkeypatch.setattr(run_discovery, "agent_turn",
                        lambda m, t: model_calls.append(1) or _turn([call]))
    envtests.CALLS.clear()

    result = asyncio.run(run_discovery.run_discovery())

    assert result["stopped"], "the rollout must record why it stopped"
    assert result["conclusion"] is None
    # $1 per model call against a $2.50 ceiling: calls 1-3 are paid, the third crosses,
    # so its measurement is refused and no further model call is made.
    assert len(model_calls) == 3
    assert envtests.CALLS == ["score_variant:C7S"] * 2
    refused = result["rounds"][-1]
    assert refused["round"] == 3 and "refused" in refused, \
        "the refused measurement must be visible in the transcript, not silently skipped"
    assert result["spend_usd"] == pytest.approx(3.0)
    assert result["ceiling_usd"] == pytest.approx(2.5)


# --- QG findings on the harness: refusal branches that no test exercised (F06, F07)
# and two defects in how the harness hands tool calls to the environment (F17, F18).

def _rollout(monkeypatch, ceiling, turns):
    """Run run_discovery with a scripted model. `turns` is a list of tool-call lists;
    once exhausted the model stops calling tools. Returns (result, model_calls)."""
    monkeypatch.setenv("BIOSIM_USD_PER_1M_TOKENS", "1.0")        # $1 per model call
    monkeypatch.setattr(run_discovery.BioSimEnv.__init__, "__defaults__", (ceiling, 5))
    script = list(turns)
    model_calls = []

    def fake_turn(messages, tools):
        model_calls.append(1)
        return _turn(script.pop(0) if script else [])

    monkeypatch.setattr(run_discovery, "agent_turn", fake_turn)
    envtests.CALLS.clear()
    return asyncio.run(run_discovery.run_discovery()), model_calls


def test_the_conclusion_call_is_refused_when_already_over_budget(monkeypatch):
    """F06: round 1 costs $1 against a $0.50 ceiling and requests no tools, so the
    only thing left is the conclusion — which must not be paid for."""
    result, model_calls = _rollout(monkeypatch, ceiling=0.5, turns=[])
    assert len(model_calls) == 1
    assert result["conclusion"] is None
    assert result["stopped"]
    assert result["spend_usd"] == pytest.approx(1.0)


def test_under_budget_the_conclusion_is_paid_for_and_returned(monkeypatch):
    """Control for F06."""
    result, model_calls = _rollout(monkeypatch, ceiling=10.0, turns=[])
    assert len(model_calls) == 2
    assert result["conclusion"] == "thinking"
    assert not result["stopped"]


def test_the_loop_head_refuses_when_step_never_had_a_tool_to_refuse(monkeypatch):
    """F07: every call names a tool that does not exist, so step() runs nothing and
    never checks the budget. The refusal must come from the next paid turn, and
    must end the rollout cleanly rather than crash it."""
    bogus = [{"id": "x", "name": "nope", "arguments": "{}"}]
    result, model_calls = _rollout(monkeypatch, ceiling=2.5, turns=[bogus] * 5)
    assert len(model_calls) == 3
    assert result["stopped"]
    assert result["conclusion"] is None
    assert result["spend_usd"] == pytest.approx(3.0)
    assert "no such tool" in result["rounds"][-1]["results"][0]


def test_results_are_paired_with_the_calls_that_produced_them(monkeypatch):
    """F17: step() answers valid calls first and invalid ones after, so pairing by
    position hands the real score to the call that named a nonexistent tool."""
    batch = [{"id": "bad", "name": "nosuch", "arguments": "{}"},
             {"id": "good", "name": "score_variant",
              "arguments": '{"accession": "P01308", "mutation": "C7S"}'}]
    result, _ = _rollout(monkeypatch, ceiling=10.0, turns=[batch])
    results = result["rounds"][0]["results"]
    assert "no such tool" in results[0], results
    assert results[1] == "-1.25", results


def test_malformed_tool_arguments_do_not_crash_the_rollout(monkeypatch):
    """F18: a model emitting truncated JSON must get a tool error for that call; the
    rest of the batch still runs and the rollout still returns a result."""
    batch = [{"id": "broken", "name": "score_variant", "arguments": '{"accession": "P0130'},
             {"id": "list", "name": "score_variant", "arguments": "[1, 2]"},
             {"id": "good", "name": "score_variant",
              "arguments": '{"accession": "P01308", "mutation": "C7S"}'}]
    result, _ = _rollout(monkeypatch, ceiling=10.0, turns=[batch])
    results = result["rounds"][0]["results"]
    assert "tool error" in results[0], results
    assert "tool error" in results[1], results
    assert results[2] == "-1.25", results
    assert envtests.CALLS == ["score_variant:C7S"]


def test_tool_arguments_that_collide_with_the_call_constructor_do_not_crash_the_rollout(monkeypatch):
    """Re-gate own finding: ToolCall.from_name(name, id=..., **args) raises TypeError when
    the model's arguments include `id` or `function_name`. That escaped the per-call
    ValueError handler added for F18 and crashed the rollout the same way."""
    batch = [{"id": "c1", "name": "score_variant", "arguments": '{"id": 1}'},
             {"id": "c2", "name": "score_variant", "arguments": '{"function_name": "x"}'},
             {"id": "c3", "name": "score_variant",
              "arguments": '{"accession": "P01308", "mutation": "C7S"}'}]
    result, _ = _rollout(monkeypatch, ceiling=10.0, turns=[batch])
    results = result["rounds"][0]["results"]
    assert "tool error" in results[0], results
    assert "tool error" in results[1], results
    assert results[2] == "-1.25", results
