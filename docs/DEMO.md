# Demo scripts — BioSim / v2r-loop

Two different things, two different shapes:

- **A · the submission recording** — under 2 minutes, watched alone, no one to ask questions.
- **B · the judging room** — exactly 3 minutes, strictly enforced, demo-heavy, 1–2 slides max, then 1–2 questions.

---

## Pre-flight (do this once, before recording)

```bash
cd /Users/mo/github/personal/bioFM/projects/aviary-biosim
export V2R_TRACE=1
export WANDB_API_KEY=$(grep '^WANDB_API_KEY=' ../../.env | cut -d= -f2-)
export WANDB_PROJECT=3m-m/Aviary-BioSim

# window 1 — terminal, font bumped to ~18pt, cleared
# window 2 — dashboard
uv run --with marimo --with pyyaml --with pandas --with altair --with pyarrow \
  marimo run dashboard/v2r_dashboard.py
# window 3 — browser on the Weave project
# window 4 — browser on github.com/supmo668/Aviary-BioSim
```

Warm the uv cache first so nothing installs on camera:

```bash
uv run --with pyyaml demo/gate_demo.py >/dev/null
```

**Point the dashboard at the real drain, not the seeded fixture**, and say so out loud. "This is the actual run from twenty minutes ago" beats a prettier chart built from fixture data. If the live drain did not finish, use the seeded run and say *that* plainly instead — a judge who catches you presenting fixture data as live has stopped listening.

---

## A · Submission recording — target 1:45

### Shot 1 · 0:00–0:12 — what it is

**Screen:** terminal, one line typed but not run.

```
/v2r-loop "A SpendTracker that records per-call cost, totals it, and refuses to
           exceed a declared budget floor"
```

> "One sentence in. A reviewed branch of working, tested code out. That string is the only parameter — and the loop gets better at this each pass."

### Shot 2 · 0:12–0:42 — the gate *(the shot that matters)*

**Screen:** run it.

```bash
uv run --with pyyaml demo/gate_demo.py
```

> "Most self-improving loops grade their own homework. The agent writes the code, the agent runs the check, the agent reports success.
> Here are three sealed tests. The first genuinely passes. The second is entirely skipped. The third collects nothing.
> Only the first closes a unit. The other two **halt** — because a test that never asserted anything is not a gate. And no agent is trusted to report this: the register re-runs the test itself."

*Let the green/red block sit on screen for a beat. Don't talk over it.*

### Shot 3 · 0:42–1:08 — it actually improves

**Screen:** dashboard, top section, then scroll to the drain chart.

> "Each drain retries only what failed, under a pinned instinct set.
> Drain one to two: three parked units recovered.
> Drain two to three: closed nothing new — so the loop terminates. It stops because it stopped improving, not because a timer ran out."

### Shot 4 · 1:08–1:30 — failure is preserved, not swept

**Screen:** scroll to the parked section, then cut to terminal.

```bash
git log --oneline | head -5
git branch --list 'park/*'
```

> "A unit that can't be built parks. Its attempt is preserved on its own branch, and the tree is reset — so every commit on this branch is green by construction, and the history bisects at behaviour granularity."

### Shot 5 · 1:30–1:45 — traces and close

**Screen:** Weave project, spans visible.

> "Every iteration emits a Weave span — attempt, close, park, halt. Between drains the loop reads its own traces back through the W&B MCP server and captures what it learned.
> Weave, W&B Inference, MCP, marimo. Team BioSim. Repo's public."

---

## B · Judging room — exactly 3:00

Same spine, different opening. **Lead with the story, because it's true and no one else will have one.**

### 0:00–0:30 — the hook *(no slide, just say it)*

> "We built a loop that writes its own code. Halfway through, an independent review found our register declared only `pyyaml` as a dependency — while being invoked with only `pyyaml` available. So `python -m pytest` exited 1. Our own table read exit 1 as 'test failed.'
> Every unit would have burned its attempts and parked, **while the sealed test never ran once.** Our thirty-six test suite passed the entire time.
> That is exactly the failure our project exists to prevent, hiding inside the mechanism meant to prevent it. So we stopped trusting exit codes."

### 0:30–1:10 — the gate

Run `demo/gate_demo.py`. Same narration as Shot 2. Add one line at the end:

> "The gate now parses pytest's own report and requires at least one passing assertion and zero skips. Anything else halts."

### 1:10–1:55 — the loop improving

Dashboard. Same as Shot 3, plus:

> "The implementer never sees its test. The test author never sees the implementation. Neither can weaken the other."

### 1:55–2:25 — the park

Parked section + `git branch --list 'park/*'`. Same as Shot 4.

### 2:25–2:50 — how it's built *(the only slide, if you use one)*

> "Aviary's environment contract as the target. MCP for reading our own traces. Weave for the evidence. W&B Inference — which is also how the loop unblocks GPU access, because serverless takes the GPU off the critical path entirely. marimo for everything you just saw."

### 2:50–3:00 — close

> "One sentence in, reviewed code out, and a gate no agent can talk its way past. Team BioSim."

---

## Questions to expect, and the honest answers

**"Has the full loop run end-to-end autonomously?"**
> The drain has, with real isolated subagents. The full attended head — research, grilling, planning — we compressed for time today. It's in the spec and the README says so.

**"What stops it building the wrong thing really efficiently?"**
> One human gate, before any code. You approve the spec, the register and the interface skeleton. Scope is frozen at that moment — no later drain can add a unit that wasn't in it. That's also the one failure the sealed tests can't catch, which is exactly why a human sits there.

**"Isn't 'the agent can't close its own unit' just a test runner?"**
> The test runner is the easy half. The hard half is that the implementer never sees the test, the author never sees the implementation, and the state transition is owned by 451 lines with no LLM in them. Any one of those missing and the loop drifts.

**"What happens when it gets stuck?"**
> It parks the unit, preserves the attempt on a branch, restores the tree, and keeps going. Parked units get retried next drain under new instincts. When a drain closes nothing new, it stops and hands you the list.

**"Why pin the instincts? Isn't continuous learning the point?"**
> If it adopted instincts mid-drain, unit one and unit twenty-three get built by different agents — same register replayed, different code, no recoverable cause. Learning is adopted between drains, under a recorded pin. It's free: the store is in-repo, so the pin is a git tree SHA.

---

## Cutting for time

If you're over, cut in this order — the gate and the park never get cut, they're the whole argument:

1. The how-it's-built slide (2:25–2:50) — it's in `SUBMISSION.md`, which judges read anyway.
2. Weave traces (Shot 5) — mention it in one sentence over the dashboard instead.
3. The improvement arc (Shot 3) — say "closed nothing new, so it terminated" over a static chart.
