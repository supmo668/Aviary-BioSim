# The publication pipeline

The deposit pipeline runs in a remote n8n instance, and it exists **only** there. There is no
reviewable artifact and no version control over it: its Code nodes — including the ones that
decide which files reach a public, DOI-bearing deposit — cannot be diffed, reviewed or rolled
back. This file records what it does and how to get an export; it is not itself the export.

**The export is deliberately absent rather than guessed.** Producing it needs an n8n API key or
the editor UI, neither available when this was written: the REST API returns 401 without a key,
and the MCP token in the vault is scoped `aud=mcp-server-api`, not `/api/v1`. A hand-transcribed
copy was **not** written, because a subtly wrong export is worse than none — the next reader
would diff against it and believe it.

To produce it:

```
# UI:  open the workflow -> ... menu -> Download, save as publish-academic.json beside this file
# API: curl -H "X-N8N-API-KEY: $KEY" \
#        https://n8n.syntropyhealth.bio/api/v1/workflows/t2SmnfD3VwVV11wx \
#        | python3 -m json.tool > orchestration/n8n/publish-academic.json
```

Do that before the next edit to the workflow, so there is a baseline to diff against.

| | |
|---|---|
| workflow | `[bioFM] 03-PUBLISH: Academic Repositories` (`t2SmnfD3VwVV11wx`) |
| trigger | `POST /webhook/biofm-publish-academic`, or the manual trigger |
| payload | `{repo, ref, projectPath, topic, version, mode, sandbox}` — `topic` has **no default** |

## What it does

`resolve → fetch publish.yml → validate → preflight → create deposition → guard → tree →
list files → fetch → upload → metadata → publish → Drive → checklist → summarise → Slack`

A project is publishable **iff** it has a valid `<projectPath>/publish.yml`. Nothing else about
a project needs to be known, which is what makes the pipeline generic rather than per-paper.

## Properties worth preserving if you edit it

- **Everything is read from GitHub at a pinned `ref`**, and only `type: blob` tree entries are
  taken. Gitignored material is therefore *structurally unreachable*, not merely absent today —
  a `__pycache__` `.pyc` carrying the author's username and home path is how a PII leak reached
  the declared payload once, and it regenerated itself after being deleted.
- **The deposit publishes what is committed AND pushed.** An unpushed local change will not
  appear. This has bitten before: GitHub being stale meant the pipeline would have published old
  content.
- **Two guards ported from the Python submitter this replaces**, each from a defect that returned
  API *success* on a wrong publication: refuse a submitted deposition or a locked bucket (both
  accept the request shape and store nothing), and send metadata on **every** run, not only on
  create (the sibling republished with an old description and author name).
- **Discovery metadata is parameterized from the manifest**, so what a repository indexes is
  reviewed in a committed file rather than buried in a node.
- **`PREPARED` never counts as published.** arXiv and bioRxiv have no deposit API, so `PUBLISHED`
  is structurally unreachable for them; a run where only those ran published nothing.
- **Drive continues on error; the Zenodo chain does not.** Drive is a convenience copy, so losing
  it must not report the deposit as failed. A failed Zenodo call stops the run, because
  continuing would publish an incomplete record and call it a success.

## The decision logic is tested — and the node bodies are COPIES of it

`nodes/pipeline.mjs` holds the logic that decides what reaches a public, DOI-bearing deposit and
when a deposit is refused. `nodes/pipeline.test.mjs` exercises it — 25 tests, run by
`node --test` and wired into `paper/scripts/repo_tests.py` so one command covers the repo.

Most of those tests are **refusals**, because a sandbox deposit can only ever prove the happy
path. A duplicate record, a wrong `mode`, a locked bucket, a declared artifact that is not
tracked, a manifest missing a field the repository indexes — none of those are reachable from a
successful run, and all of them decide whether a wrong deposit is *prevented* or merely hoped
against. Five mutations were applied and all five were caught, including taking every tree entry
instead of only blobs (which would re-admit gitignored material) and splitting a flow map on the
first colon (which truncates the domain-category URL at `https`).

### THE SYNC RULE

n8n has no filesystem access to this repository, so a Code node **cannot import**
`pipeline.mjs`. The node bodies are therefore **copies**. `pipeline.mjs` is the **source of
truth**: edit there, run the tests, then push the body into the node.

**Residual risk, stated rather than hidden:** someone editing a node in the n8n UI diverges from
this file, and with no n8n API key nothing here can read the instance back to notice. Re-export
the workflow after any UI edit. A test asserts this rule is written down; no test can verify the
remote instance from here.

## Credential

`Zenodo Sandbox API` (Bearer Auth) must exist in the n8n instance; the four Zenodo nodes request
`httpBearerAuth`. **No secret value is stored in the workflow or in this export** — only the
credential's name. GitHub needs no credential: the source repository is public.
