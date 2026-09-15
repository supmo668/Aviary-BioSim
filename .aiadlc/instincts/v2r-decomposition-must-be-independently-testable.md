---
name: v2r-decomposition-must-be-independently-testable
confidence: 1.000
created: 2026-09-13T18:49:54Z
last_reinforced: 2026-09-13T19:51:59Z
ttl_days: 30
triggers: [.v2r/register.yaml, docs/CONTEXT.md]
tags: [v2r-loop, register, decomposition]
---

Before draining, check every build unit is testable using ONLY the units ordered before it. A unit whose observable surface is filled by a LATER unit cannot be tested and will burn its whole attempt budget and park — and in the register that park is indistinguishable from one earned by genuinely hard work. Caught two on drain 1 pre-gate: 'record accumulates' had no reader until 'total' closed, and 'check raises BudgetExceeded' preceded the unit that filled BudgetExceeded.__init__. Fix is mechanical: merge the pair, or order the carrier before its raiser. A rigged park is worse than no park because it looks like evidence.
