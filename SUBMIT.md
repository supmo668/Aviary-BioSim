# Where each thing goes

Work top to bottom. Item 2 blocks the submission from closing, so start it first if others are joining.

---

## 1 · AGI House platform — the submission itself

**Where:** the same site you checked in on → **"create project"** button.
**Who:** one teammate submits for the whole team, but every member must be signed in and listed.

Paste these fields:

| Field | Value |
|---|---|
| Team name | `BioSim` |
| Project name | `v2r-loop — agents that measure` |
| Members | Mangyin Mo |
| GitHub | `https://github.com/supmo668/Aviary-BioSim` (public) |
| Track | Best Use of Weave · Best Use of marimo · Best Loop Design |
| X | `@mattmo_668` |
| LinkedIn | `linkedin.com/in/matthew-mo` |

**Description** — paste from `SUBMISSION.md`. It already contains the 2–3 sentence summary, what it does, how it's built (RL environment, orchestration protocol, agent framework), the sponsor table, and the honest-limitations section. The rules call the sponsor list *critical for both sponsor and grand prizes*, so do not trim that table.

**Demo links** — three artifacts, all must be **shared**, not private:

```
Deck              https://claude.ai/code/artifact/67e77477-8d04-4984-8178-7849152bab06
Pre-registration  https://claude.ai/code/artifact/df564d0d-8a96-41e0-9107-047b33d0c5e9
Interpretability  https://claude.ai/code/artifact/1514a892-2eaa-4cce-9385-8bd17303d9aa
```

---

## 2 · Participant survey — blocks submission

**Where:** the AGI House platform, same place as check-in. Not in your email — I searched; the only recent AGI House message is an unrelated newsletter.

**Every team member must complete it** or the submission cannot be finalised. If anyone else is on the team, send it to them now rather than at the end.

---

## 3 · The screen recording — under 2 minutes

**Where:** upload to the submission form, or link it (YouTube unlisted / Loom).

Shot list with exact commands and narration: [`docs/DEMO.md`](docs/DEMO.md). Seven shots, 1:45.

Before recording:
```bash
cd ~/github/personal/bioFM/projects/aviary-biosim
export V2R_TRACE=1
export WANDB_API_KEY=$(grep '^WANDB_API_KEY=' ../../.env | cut -d= -f2-)
export WANDB_PROJECT=3m-m/Aviary-BioSim
uv run --with pyyaml demo/gate_demo.py >/dev/null   # warm the cache
```

**The HeyGen presenter video is a companion, not this.** The rules ask for a screen recording of what you built; HeyGen cannot capture your terminal or the Weave UI. Attach it as the explanatory video if the form allows a second link.

---

## 4 · The live presentation — 3 minutes, strictly enforced

**Where:** your assigned room, via **Zoom**. Install it, or confirm https://share.zoom.us works in your browser.

One or two slides maximum, heavy emphasis on the demo. The deck is built for this: `←` / `→` to move, **`n`** to show speaker notes if a judge asks for depth mid-answer.

Running order and the prepared answers to expected questions are in [`docs/DEMO.md`](docs/DEMO.md) under "Judging room".

---

## Pre-flight

- [ ] All three artifact links open in a private window (proves they are shared)
- [ ] `github.com/supmo668/Aviary-BioSim` loads while signed out
- [ ] Survey completed by every member
- [ ] Recording under 2:00
- [ ] Zoom installed or share.zoom.us reachable
- [ ] `uv run --with pyyaml demo/gate_demo.py` runs clean on the machine you will present from
