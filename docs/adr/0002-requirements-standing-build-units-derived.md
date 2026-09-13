# Requirements are standing; build units are derived and closed once

`R<n>` and `U-nnn` are two namespaces with a parent/child relation, not one namespace with
two spellings. A **requirement** is a standing claim enforced for the life of the project and
is never closed. A **build unit** is derived from one, carries `satisfies: R<n>`, and is
closed exactly once.

The temptation to merge them is strong and specific: `workstreams/chipsim-lbm-audit/PVR.md`
already numbers requirements `R1`–`R10`, and several read like single iterations of work —
R1's preflight gate, R9's budget guard. That invites treating the PVR as a runnable register.

It is the wrong reading. R9 is never done. A budget guard is a property the system must keep
satisfying across every later refactor and every new call site; marking it closed stops it
being enforced at the exact moment someone adds a second submission path that bypasses the
tracker. Conversely, if register rows are standing, they never drain and the loop never
terminates.

## Consequences

Traceability survives — every unit points at the claim that motivated it — and the loop still
has a termination condition. A regression against a standing requirement opens a *new* build
unit under the same `satisfies:`, rather than reopening anything.
