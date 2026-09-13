---
name: v2r-implementer-prompt-is-an-uncontrolled-variable
confidence: 0.800
created: 2026-09-13T18:49:54Z
last_reinforced: 2026-09-13T18:49:54Z
ttl_days: 30
triggers: [.claude/skills/v2r-loop/SKILL.md, .v2r/register.yaml]
tags: [v2r-loop, replay, methodology]
---

The register pins the instinct set, the seed and the register hash so a drain is replayable and attributable to one builder. It does NOT capture the implementer and test-author PROMPTS, which is where most of the difficulty actually lives. On drain 1 the unit expected to park (crash-atomic persist) closed on attempt 0 because the implementer prompt named the staging-and-atomic-rename pattern outright; a neutral prompt very plausibly parks. So 'same register, same pin, same seed reproduces the same closes and parks' is only true if the prompts are also fixed, and nothing currently fixes them. Either template the two prompts per unit and hash them into the run record, or stop claiming replay.
