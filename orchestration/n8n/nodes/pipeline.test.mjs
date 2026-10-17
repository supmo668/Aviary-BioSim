// Tests for the publication pipeline's decision logic.
//
// The happy path is the easy half, and a sandbox deposit covers it. What a sandbox run can
// NEVER exercise is every refusal: a duplicate record, a wrong mode, a locked bucket, a
// declared artifact that is not tracked, a manifest missing a field the repository indexes.
// Those are the paths that decide whether a wrong deposit is prevented or merely hoped
// against, so most of what follows tests a refusal.
//
// Run: node --test orchestration/n8n/nodes/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import {
  resolvePayloadFiles, buildZenodoMetadata, assertNotAlreadyDeposited, assertOpenDraft,
  artifactPaths, scalar, blockScalar, flowSeq, flowMaps, authors,
} from './pipeline.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
// The REAL manifest, not a reduced copy: a parser tested only against a fixture shaped for
// it proves nothing about the file it will actually meet.
const YAML = readFileSync(join(HERE, '../../../paper/publish.yml'), 'utf8');
const VARS = {
  repo: 'supmo668/Aviary-BioSim', ref: 'whitepaper', projectPath: 'paper',
  topic: 'v2r-biosim-whitepaper', version: '0.1.0-draft', mode: 'publish', sandbox: true,
};
const tree = (...paths) => paths.map((p) => ({ path: p, type: 'blob' }));

// --- the manifest parser, against the real file ----------------------------------------

test('the artifact paths come from the manifest, in order', () => {
  assert.deepEqual(artifactPaths(YAML), ['main.pdf', 'evidence/', 'claims.yaml', 'figures/']);
});

test('a top-level scalar is read with quotes stripped, and a missing key is null', () => {
  // The primitive the whole parser rests on. A silently-null scalar is how a deposit ends up
  // with no title, so "missing" must be distinguishable from "empty string".
  assert.equal(scalar(YAML, 'topic'), 'v2r-biosim-whitepaper');
  assert.equal(scalar(YAML, 'license'), 'MIT');
  assert.ok(!scalar(YAML, 'title').includes('"'), 'quotes must be stripped');
  assert.equal(scalar(YAML, 'no_such_key_here'), null);
  // a key that is a PREFIX of another must not match the longer one
  assert.equal(scalar('version_control: x\nversion: "9"\n', 'version'), '9');
  // A trailing YAML comment is a comment, not part of the value. Without this the real
  // manifest returned 'v2r-biosim-whitepaper            # required, no default: names the
  // asset folder' — which is how an explanatory note ends up inside a published DOI record.
  assert.equal(scalar('k: value   # explanatory note\n', 'k'), 'value');
  // but a # inside a quoted value is content, not a comment
  assert.equal(scalar('k: "a # b"\n', 'k'), 'a # b');
});


test('a block scalar is dedented and trimmed, not returned raw', () => {
  const d = blockScalar(YAML, 'description');
  assert.ok(d.length > 100, 'description should be substantial');
  assert.ok(!d.startsWith(' '), 'leading indentation must be stripped');
  assert.ok(!/\n\s\s\S/.test(d), 'no line should keep the two-space block indent');
});

test('a flow sequence parses and quotes are stripped', () => {
  const k = flowSeq(YAML, 'keywords');
  assert.ok(k.length >= 4);
  assert.ok(k.every((s) => !s.includes('"')), 'quotes must be stripped');
});

test('subjects parse as flow maps with the three keys a repository indexes', () => {
  const s = flowMaps(YAML, 'subjects');
  assert.ok(s.length >= 1);
  for (const o of s) assert.deepEqual(Object.keys(o).sort(), ['identifier', 'scheme', 'term']);
});

test('an identifier containing a colon survives the flow-map split', () => {
  // The naive split(':') would truncate a URL at "https". This is the bug that would have
  // shipped a deposit whose domain category pointed nowhere.
  const s = flowMaps(YAML, 'subjects');
  assert.ok(s.every((o) => o.identifier.startsWith('http')), 'identifier must keep its scheme');
});

test('the author parses with ORCID and affiliation, ignoring a trailing comment', () => {
  const a = authors(YAML);
  assert.equal(a.length, 1);
  assert.match(a[0].orcid, /^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$/);
  assert.ok(a[0].affiliation && !a[0].affiliation.includes('#'), 'a trailing YAML comment must not leak in');
});

// --- the payload file list --------------------------------------------------------------

test('a directory artifact expands to its tracked blobs, and the snapshot is appended', () => {
  const t = tree('paper/main.pdf', 'paper/claims.yaml', 'paper/evidence/a.json',
    'paper/evidence/b.csv', 'paper/figures/f.pdf');
  const out = resolvePayloadFiles({ yaml: YAML, tree: t, vars: VARS });
  assert.deepEqual(out.filter((f) => f.kind === 'artifact').map((f) => f.filename),
    ['main.pdf', 'evidence/a.json', 'evidence/b.csv', 'claims.yaml', 'figures/f.pdf']);
  const snap = out.filter((f) => f.kind === 'snapshot');
  assert.equal(snap.length, 1, 'exactly one D6 source snapshot');
  assert.match(snap[0].url, /^https:\/\/codeload\.github\.com\//);
});

test('only tracked blobs are taken, so gitignored material is unreachable', () => {
  // This is the structural reason the username-bearing .pyc cannot return: it is not a blob
  // in the tree at the ref, so there is no path by which it enters the deposit.
  const t = [
    ...tree('paper/main.pdf', 'paper/claims.yaml', 'paper/evidence/a.json', 'paper/figures/f.pdf'),
    { path: 'paper/figures/__pycache__', type: 'tree' },
  ];
  const out = resolvePayloadFiles({ yaml: YAML, tree: t, vars: VARS });
  assert.ok(!out.some((f) => f.filename.includes('__pycache__')));
});

test('a declared artifact that is not tracked is REFUSED, naming the path', () => {
  const t = tree('paper/claims.yaml', 'paper/evidence/a.json', 'paper/figures/f.pdf'); // no main.pdf
  assert.throws(() => resolvePayloadFiles({ yaml: YAML, tree: t, vars: VARS }),
    /not a tracked file at ref: paper\/main\.pdf/);
});

test('a declared directory with no tracked files is REFUSED, naming it', () => {
  const t = tree('paper/main.pdf', 'paper/claims.yaml', 'paper/figures/f.pdf'); // no evidence/
  assert.throws(() => resolvePayloadFiles({ yaml: YAML, tree: t, vars: VARS }),
    /directory is empty or absent at ref: paper\/evidence\//);
});

test('an empty tree is REFUSED rather than producing a snapshot-only deposit', () => {
  assert.throws(() => resolvePayloadFiles({ yaml: YAML, tree: [], vars: VARS }), /tree at ref .* came back empty/);
});

test('a manifest declaring no artifacts is REFUSED', () => {
  assert.throws(() => resolvePayloadFiles({ yaml: 'title: "x"\nvenues:\n', tree: tree('paper/x'), vars: VARS }),
    /declared no artifacts/);
});

// --- the metadata ----------------------------------------------------------------------

test('the metadata carries every field the repository indexes', () => {
  const m = buildZenodoMetadata({ yaml: YAML, vars: VARS });
  assert.equal(m.upload_type, 'publication');
  assert.equal(m.publication_type, 'preprint');
  assert.equal(m.version, VARS.version, 'version comes from the RUN, not the manifest');
  assert.equal(m.language, 'eng');
  assert.ok(m.keywords.length >= 4);
  assert.ok(m.subjects.length >= 1, 'a domain category, or the record lands in no facet');
  assert.equal(m.creators[0].orcid, authors(YAML)[0].orcid);
  assert.ok(m.creators[0].affiliation);
  const rel = m.related_identifiers.find((r) => r.relation === 'isSupplementTo');
  assert.ok(rel && rel.identifier.startsWith('https://github.com/'), 'must point at the code');
});

test('a manifest missing an indexed field is REFUSED, naming the field', () => {
  const stripped = YAML.split('\n').filter((l) => !/^language:/.test(l)).join('\n');
  assert.throws(() => buildZenodoMetadata({ yaml: stripped, vars: VARS }), /missing discovery metadata.*language/s);
});

test('a manifest missing the zenodo upload type is REFUSED', () => {
  const stripped = YAML.split('\n').filter((l) => !/^\s+upload_type:/.test(l)).join('\n');
  assert.throws(() => buildZenodoMetadata({ yaml: stripped, vars: VARS }), /missing upload_type or publication_type/);
});

// --- the refusals that prevent a wrong deposit ------------------------------------------

test('a mode other than publish is REFUSED by name, not silently treated as publish', () => {
  for (const mode of ['update', 'prepare', '']) {
    assert.throws(() => assertNotAlreadyDeposited({ yaml: YAML, depositions: [], vars: { ...VARS, mode } }),
      /NOT IMPLEMENTED/, `mode=${mode} must refuse`);
  }
});

test('an already-published topic+version is REFUSED, naming the DOI', () => {
  const title = YAML.match(/^title:\s*"?(.+?)"?\s*$/m)[1];
  const existing = [{ id: 42, submitted: true, doi: '10.5072/zenodo.42', title, metadata: { version: VARS.version } }];
  assert.throws(() => assertNotAlreadyDeposited({ yaml: YAML, depositions: existing, vars: VARS }),
    /ALREADY DEPOSITED.*10\.5072\/zenodo\.42/s);
});

test('a leftover DRAFT of the same version does not block a deposit', () => {
  const title = YAML.match(/^title:\s*"?(.+?)"?\s*$/m)[1];
  const drafts = [{ id: 43, submitted: false, title, metadata: { version: VARS.version } }];
  const r = assertNotAlreadyDeposited({ yaml: YAML, depositions: drafts, vars: VARS });
  assert.equal(r.duplicate_check, 'passed');
});

test('a different version of the same paper is allowed through', () => {
  const title = YAML.match(/^title:\s*"?(.+?)"?\s*$/m)[1];
  const other = [{ id: 44, submitted: true, title, metadata: { version: '0.0.9' } }];
  assert.equal(assertNotAlreadyDeposited({ yaml: YAML, depositions: other, vars: VARS }).duplicate_check, 'passed');
});

test('a locked bucket is REFUSED — it accepts the request and stores nothing', () => {
  assert.throws(() => assertOpenDraft({ id: 7, submitted: false, links: {} }), /no links\.bucket/);
});

test('an already-submitted deposition is REFUSED before a byte is uploaded', () => {
  assert.throws(() => assertOpenDraft({ id: 8, submitted: true, links: { bucket: 'b' } }), /already SUBMITTED/);
});

test('a response with no deposition id is REFUSED rather than dereferenced', () => {
  assert.throws(() => assertOpenDraft({}), /did not return a deposition id/);
  assert.throws(() => assertOpenDraft(null), /did not return a deposition id/);
});

test('an open draft yields the links the rest of the chain needs', () => {
  const r = assertOpenDraft({ id: 9, submitted: false, links: { bucket: 'B', self: 'S', publish: 'P' } });
  assert.deepEqual(r, { depositionId: 9, bucket: 'B', selfLink: 'S', publishLink: 'P' });
});

// --- the sync rule, enforced -------------------------------------------------------------

test('every exported decision function is covered by a named refusal test', () => {
  // A cheap tripwire, not a coverage tool: it fails when someone adds a decision function
  // and no test for it. The gap it guards against is the one this whole file exists to
  // close, so it should not be possible to widen the logic silently.
  const src = readFileSync(join(HERE, 'pipeline.mjs'), 'utf8');
  const exported = [...src.matchAll(/^export function (\w+)/gm)].map((m) => m[1]);
  const tests = readFileSync(join(HERE, 'pipeline.test.mjs'), 'utf8');
  const untested = exported.filter((fn) => !tests.includes(fn + '('));
  assert.deepEqual(untested, [], 'these exported functions have no test: ' + untested.join(', '));
});

test('the node bodies in n8n are copies, and that is recorded where it can be acted on', () => {
  // n8n has no filesystem access to this repo, so a Code node cannot import pipeline.mjs.
  // The bodies are therefore copies and CAN drift. Nothing offline can detect drift in a
  // remote instance, so the honest guard is that the risk is written down next to the
  // thing that carries it, rather than a check that pretends to verify it.
  const readme = readFileSync(join(HERE, '../README.md'), 'utf8');
  assert.match(readme, /SYNC|copies|source of truth/i,
    'orchestration/n8n/README.md must state that the node bodies are copies of this logic');
});
