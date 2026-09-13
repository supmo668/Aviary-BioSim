# A park reverts the tree and says nothing about any other unit

Two deliberate choices, both surprising, recorded together because they are the same
judgement about what a failed **build unit** is allowed to affect.

**The tree reverts.** When a unit exhausts its attempt budget, the last attempt is preserved
on `park/U-nnn` and the working tree is reset to its pre-claim state. Nothing a failed unit
wrote survives in the branch. This is what makes "every commit on the branch is green" true by
construction and the history bisectable at behaviour granularity. The alternative — keeping
partial work — means the branch contains code no sealed test ever passed, and the loop cannot
distinguish rubble from foundation. Nothing is lost: the attempt is a real branch, resumable,
not a patch file that may no longer apply.

**The park does not cascade.** There is no `blocked_by`, no dependency graph, and no inference
about what else the failure might block. A unit needing the parked work fails on its own terms
and parks on its own terms.

## Considered options

Cascade mechanisms were priced. Learning the missing symbol once and auto-parking later units
that die on it would bound the waste at one attempt budget per foundational park. It was
declined as machinery built against a predicted cost before the loop has run even once. If the
waste proves real, it can be added with evidence — and a foundational unit failing is a
situation worth stopping to look at anyway.

## Consequences

Worst case, a foundational park causes every dependent unit to spend its full budget
rediscovering the same fact. That cost is bounded, visible in the run record, and accepted.
