---
name: v2r-instinct-pin-drifts-under-hooks
confidence: 0.900
created: 2026-09-13T19:50:47Z
last_reinforced: 2026-09-13T19:50:47Z
ttl_days: 30
triggers: [.aiadlc/instincts, .claude/skills/v2r-loop/scripts/register.py, docs/adr/0003-instincts-pinned-per-drain.md]
tags: [v2r-loop, register, pin, defect]
---

The instinct pin is 'git rev-parse HEAD:.aiadlc/instincts' — a TREE SHA. But the store is not inert: a Stop hook reinforces any instinct whose triggers match the files just touched, bumping confidence and rewriting last_reinforced, and 'instinct decay' rewrites confidence on a timer. Observed live: four instinct files changed confidence +0.05 and timestamps minutes after capture, with no learning adopted. Two consequences. (1) The pin stops meaning what it claims — two drains can carry different pins with an identical instinct SET, so a divergence cannot be attributed to instincts by comparing pins. (2) Worse, it breaks 'within a drain nothing about the builder changes': cmd_close runs 'git add -A', so hook-mutated instinct files get swept into UNIT COMMITS mid-drain, meaning the tracked store genuinely changes during a drain and the drain-start pin no longer describes the tree at drain-end. CONTEXT.md says learned behaviour is 'only ever adopted between drains, never during one'; the mechanism does not currently enforce that. Fix options: pin a hash of instinct BODIES excluding volatile frontmatter (confidence, last_reinforced); or snapshot the store at drain-start and build against the snapshot; or have close stage explicit paths instead of 'git add -A'. Until then, treat the pin as an approximate label, not an identity.
