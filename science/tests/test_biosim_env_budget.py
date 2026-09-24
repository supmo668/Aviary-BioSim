"""BioSimEnv must ENFORCE its budget, not merely carry a tracker.

Each test targets a way the fix could look done while the refusal is still absent:
a check() swallowed by step()'s generic tool-error handler, a ledger the metered
actor can write to, or a refusal that fires after the next tool has already run.
Assertions are about whether the rollout STOPS and whether the tool RAN — never
about a string appearing in a response.

The fake tool, the call recorder and the env/step helpers live in conftest.py as
per-test fixtures (`bio`), so nothing is installed into sys.modules at import time.
"""
import pytest


def _tool_names(env):
    return {t.info.name for t in env.tools}


def test_within_budget_the_step_runs_the_tool(bio):
    env = bio.env(ceiling=1.0)
    obs, reward, done, truncated = bio.step(env, ("score_variant", {"accession": "P01308", "mutation": "A12G"}))
    assert bio.calls == ["score_variant:A12G"]
    assert not done


def test_spend_exactly_at_the_ceiling_still_runs(bio):
    env = bio.env(ceiling=1.0)
    env.charge("model-call-1", 1.0)
    bio.step(env, ("score_variant", {"accession": "P01308", "mutation": "A12G"}))
    assert bio.calls == ["score_variant:A12G"]


def test_over_budget_the_rollout_stops_and_the_tool_never_runs(bio):
    env = bio.env(ceiling=1.0)
    env.charge("model-call-1", 1.5)
    with pytest.raises(bio.BudgetExceeded) as refused:
        bio.step(env, ("score_variant", {"accession": "P01308", "mutation": "A12G"}))
    assert bio.calls == [], "a refused step must not spend on the tool it refused"
    assert refused.value.total_usd == pytest.approx(1.5)
    assert refused.value.ceiling_usd == pytest.approx(1.0)


def test_the_refusal_is_not_converted_into_a_tool_error_string(bio):
    """The trap: check() inside step()'s `except Exception` would return
    'tool error: bio.BudgetExceeded: ...' and let the rollout continue."""
    env = bio.env(ceiling=1.0)
    env.charge("model-call-1", 2.0)
    try:
        result = bio.step(env, ("score_variant", {"accession": "P01308", "mutation": "A12G"}))
    except bio.BudgetExceeded:
        return
    pytest.fail(f"step returned instead of refusing: {result!r}")


def test_env_side_charge_records_without_the_agent_reporting_anything(bio):
    env = bio.env(ceiling=10.0)
    env.charge("model-call-1", 0.75)
    env.charge("model-call-2", 0.25)
    assert env.tracker.total() == pytest.approx(1.0)
    assert bio.calls == []


def test_crossing_the_ceiling_mid_batch_refuses_the_remaining_calls(bio):
    """check() runs before EVERY call in a batch, not once per batch. No offered tool
    spends today, so a paid tool is simulated: its first call charges past the ceiling
    and the second call in the same batch must not run."""
    env = bio.env(ceiling=1.0)
    real = env._fns["score_variant"]

    def paid_score_variant(**kwargs):
        env.charge("paid-tool", 5.0)
        return real(**kwargs)

    env._fns["score_variant"] = paid_score_variant
    with pytest.raises(bio.BudgetExceeded):
        bio.step(env,
              ("score_variant", {"accession": "P01308", "mutation": "A12G"}),
              ("score_variant", {"accession": "P01308", "mutation": "C7S"}))
    assert bio.calls == ["score_variant:A12G"], "the call after the crossing one must not run"


def test_once_over_budget_every_later_step_keeps_refusing(bio):
    env = bio.env(ceiling=1.0)
    env.charge("model-call-1", 3.0)
    for _ in range(3):
        with pytest.raises(bio.BudgetExceeded):
            bio.step(env, ("score_variant", {"accession": "P01308", "mutation": "A12G"}))
    assert bio.calls == []


def test_an_ordinary_tool_failure_is_still_reported_not_raised(bio):
    env = bio.env(ceiling=10.0)
    obs, reward, done, truncated = bio.step(env, ("embed_sequence", {"accession": "P01308"}))
    assert bio.calls == ["embed_sequence"]
    assert "tool error" in str(obs[0].content)


# --- Principal ruling (#152): the actor being metered must not be able to write the
# ledger that meters it. The agent gets a read-only `spend_remaining`; every write
# goes through the harness's charge().

def _tool_names(env):
    return {t.info.name for t in env.tools}


def test_the_agent_is_offered_no_tool_that_writes_the_ledger(bio):
    env = bio.env(ceiling=1.0)
    assert _tool_names(env) == {"score_variant", "embed_sequence", "spend_remaining"}


@pytest.mark.parametrize("cost", [-100.0, float("nan"), "nan", float("-inf"), 0.5, 1e9])
def test_a_record_call_from_the_agent_is_not_a_tool_and_cannot_touch_the_ledger(bio, cost):
    """Regression for the bypass: record(cost_usd=-100) or 'nan' used to switch the
    budget off. It must now be refused as an unknown tool, whatever the cost."""
    env = bio.env(ceiling=1.0)
    env.charge("model-call-1", 5.0)                 # genuinely over budget
    obs, *_ = bio.step(env, ("record", {"call_id": "agent", "cost_usd": cost}))
    assert "no such tool" in str(obs[0].content)
    assert env.tracker.total() == pytest.approx(5.0)
    with pytest.raises(bio.BudgetExceeded):
        bio.step(env, ("score_variant", {"accession": "P01308", "mutation": "A12G"}))


def test_spend_remaining_reports_the_ceiling_minus_recorded_spend(bio):
    env = bio.env(ceiling=2.0)
    env.charge("model-call-1", 0.5)
    obs, *_ = bio.step(env, ("spend_remaining", {}))
    assert float(obs[0].content) == pytest.approx(1.5)


def test_spend_remaining_is_read_only(bio):
    env = bio.env(ceiling=2.0)
    env.charge("model-call-1", 0.5)
    for _ in range(3):
        bio.step(env, ("spend_remaining", {}))
    assert env.tracker.total() == pytest.approx(0.5)


def test_spend_remaining_does_not_overstate_what_is_left(bio):
    """At the ceiling nothing is left, and it must say so rather than round up."""
    env = bio.env(ceiling=1.0)
    env.charge("model-call-1", 1.0)
    obs, *_ = bio.step(env, ("spend_remaining", {}))
    assert float(obs[0].content) == pytest.approx(0.0)


@pytest.mark.parametrize("bad_cost", [-1.0, float("nan"), float("-inf"), float("inf"), True, "abc"])
def test_the_harness_ledger_path_rejects_nonsense_loudly(bio, bad_cost):
    env = bio.env(ceiling=10.0)
    with pytest.raises(ValueError):
        env.charge("model-call-1", bad_cost)
    assert env.tracker.total() == 0.0


# --- Re-gate test findings: spend_remaining must stay read-only however it is called,
# and must be refused past the ceiling like every other tool.

def _spend_remaining_tool(env):
    return next(t for t in env.tools if t.info.name == "spend_remaining")


def test_spend_remaining_takes_no_arguments(bio):
    """Pins the schema: a spend_remaining that grew a cost parameter would reintroduce
    the record bypass under a name the agent is allowed to call."""
    env = bio.env(ceiling=10.0)
    params = _spend_remaining_tool(env).info.parameters
    assert not (params.properties or {}), params
    assert not (params.required or []), params


@pytest.mark.parametrize("cost", [-100.0, float("nan"), "nan", 1e9])
def test_arguments_to_spend_remaining_cannot_write_the_ledger(bio, cost):
    """Under budget, so check() cannot mask a write that did happen."""
    env = bio.env(ceiling=10.0)
    env.charge("model-call-1", 0.5)
    obs, *_ = bio.step(env, ("spend_remaining", {"cost_usd": cost}))
    assert env.tracker.total() == 0.5
    assert "tool error" in str(obs[0].content)


def test_a_record_call_under_budget_is_still_not_a_tool(bio):
    """The earlier record regression runs over budget, where check() would stop even a
    restored record tool before it ran. Under budget, only its absence refuses it."""
    env = bio.env(ceiling=10.0)
    env.charge("model-call-1", 0.5)
    obs, *_ = bio.step(env, ("record", {"call_id": "agent", "cost_usd": -100.0}))
    assert "no such tool" in str(obs[0].content)
    assert env.tracker.total() == 0.5


def test_spend_remaining_never_calls_the_ledger_write_path(bio, monkeypatch):
    env = bio.env(ceiling=10.0)
    env.charge("model-call-1", 0.5)
    monkeypatch.setattr(env.tracker, "record",
                        lambda *a, **k: pytest.fail("spend_remaining wrote the ledger"))
    for _ in range(3):
        bio.step(env, ("spend_remaining", {}))
    assert env.tracker.total() == 0.5


def test_over_budget_spend_remaining_is_refused_and_does_not_run(bio):
    env = bio.env(ceiling=1.0)
    env.charge("model-call-1", 1.5)
    ran = []
    real = env._fns["spend_remaining"]
    env._fns["spend_remaining"] = lambda: ran.append(1) or real()
    with pytest.raises(bio.BudgetExceeded):
        bio.step(env, ("spend_remaining", {}))
    assert ran == []


def test_spend_remaining_is_exact_and_never_rounded_or_clamped(bio):
    env = bio.env(ceiling=1.0)
    env.charge("model-call-1", 0.123)
    obs, *_ = bio.step(env, ("spend_remaining", {}))
    assert float(obs[0].content) == pytest.approx(0.877, abs=1e-9)

    over = bio.env(ceiling=1.0)
    over.charge("model-call-1", 1.5)
    assert over.spend_remaining() == pytest.approx(-0.5)
