# The register CLI owns every state transition

A 150-line `register.py` exists, rather than letting the loop's model read and write
`register.yaml` directly, because the actor that does the work may never be the actor that
records the work passed. `close` independently re-runs the **sealed test** and refuses unless
it observes a pass; the model cannot assert a close in prose.

This is ChipSim's **frozen evaluator** rule one altitude up — "immutable, versioned, outside
the agent's write scope" — and the A&D's warning that "the ratchet is the thing that
overfits" is the reason. An agent that has just spent three attempts on `U-014` is the
worst-placed actor in the system to judge whether `U-014` is done.

## Considered options

Letting the model own the file was genuinely simpler and needs no CLI at all. It was rejected
because the register's whole value is being trustworthy without a human reading it, and a
register maintained by an interested party drifts optimistic in exactly the unattended
conditions where nobody is checking.

## Consequences

Everything downstream trusts the register unconditionally, which makes `register.py` the one
component whose correctness the system depends on. It contains no LLM, and its tests are
adversarial: `close` must refuse a failing test, a missing test, a test that errors on
collection, and a test modified after authoring.
