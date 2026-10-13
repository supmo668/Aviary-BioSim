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

## Known gap

**The Code nodes have no automated tests.** They are JavaScript living in a remote instance, and
nothing in this repository exercises them. Their logic was validated once, by hand, against live
GitHub data at `ref whitepaper` — 20 tracked files plus the source snapshot resolved, and every
required metadata field parsed. That is a manual check, not a regression test, and it will not
catch the next edit. Re-export this file after any change so the diff is at least visible.

## Credential

`Zenodo Sandbox API` (Bearer Auth) must exist in the n8n instance; the four Zenodo nodes request
`httpBearerAuth`. **No secret value is stored in the workflow or in this export** — only the
credential's name. GitHub needs no credential: the source repository is public.
