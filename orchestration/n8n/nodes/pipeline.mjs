// The decision logic of the publication pipeline's Code nodes, extracted so it can be
// tested. These functions decide what reaches a public, DOI-bearing deposit and when a
// deposit is refused; until now they were JavaScript living only in a remote n8n instance,
// which nothing in this repository exercised.
//
// THE SYNC RULE. n8n has no filesystem access to this repo, so a Code node cannot import
// this file — the node bodies are copies. This file is the source of truth: edit here, run
// the tests, then push the body into the node. `build-node-bodies.mjs` emits each body from
// these functions so the copy is generated rather than retyped.
//
// Residual risk, stated rather than hidden: someone editing a node in the n8n UI diverges
// from this file, and without an n8n API key nothing here can read the instance back to
// notice. Re-export the workflow after any UI edit.

/**
 * The value of a top-level `key:` in a YAML subset. Quotes stripped, trailing comment
 * dropped.
 *
 * The comment handling is not cosmetic: without it, a key written
 * `topic: thing   # required, no default` returned the comment as part of the value, which
 * is how an explanatory note ends up inside a published DOI record. A `#` inside a quoted
 * value is kept, because there it is content rather than a comment.
 */
export function scalar(yaml, key) {
  const re = new RegExp('^' + key + ':\\s*(.*)$');
  for (const ln of yaml.split('\n')) {
    const m = ln.match(re);
    if (!m) continue;
    let v = m[1].trim();
    const quoted = v.match(/^"([^"]*)"/);
    if (quoted) return quoted[1];
    v = v.replace(/\s+#.*$/, '').trim();
    return v.replace(/^"|"$/g, '');
  }
  return null;
}

/** A `key: |` block scalar, dedented by two spaces and trimmed. */
export function blockScalar(yaml, key) {
  const lines = yaml.split('\n');
  const i = lines.findIndex((l) => new RegExp('^' + key + ':\\s*\\|').test(l));
  if (i === -1) return null;
  const body = [];
  for (let j = i + 1; j < lines.length; j++) {
    if (lines[j].trim() === '') { body.push(''); continue; }
    if (!/^\s/.test(lines[j])) break;
    body.push(lines[j].replace(/^\s\s/, ''));
  }
  return body.join('\n').trim();
}

/** A flow sequence, `key: [a, b, c]`. */
export function flowSeq(yaml, key) {
  const v = scalar(yaml, key);
  if (!v || v[0] !== '[') return null;
  return v.slice(1, -1).split(',').map((s) => s.trim().replace(/^"|"$/g, '')).filter(Boolean);
}

/** A list of flow maps under `key:` — `  - { a: "x", b: "y" }`. */
export function flowMaps(yaml, key) {
  const out = [];
  let inBlock = false;
  for (const ln of yaml.split('\n')) {
    if (/^[A-Za-z_][A-Za-z0-9_]*:/.test(ln)) { inBlock = new RegExp('^' + key + ':').test(ln); continue; }
    if (!inBlock) continue;
    const m = ln.match(/^\s*-\s*\{(.+)\}\s*$/);
    if (!m) continue;
    const o = {};
    for (const pair of m[1].split(',')) {
      const kv = pair.split(':');
      if (kv.length < 2) continue;
      o[kv[0].trim()] = kv.slice(1).join(':').trim().replace(/^"|"$/g, '');
    }
    out.push(o);
  }
  return out.length ? out : null;
}

/** `authors:` — a list of maps introduced by `- name:` with indented siblings. */
export function authors(yaml) {
  const out = [];
  let inBlock = false;
  let cur = null;
  for (const ln of yaml.split('\n')) {
    if (/^[A-Za-z_][A-Za-z0-9_]*:/.test(ln)) {
      if (cur) { out.push(cur); cur = null; }
      inBlock = /^authors:/.test(ln);
      continue;
    }
    if (!inBlock) continue;
    const start = ln.match(/^\s*-\s*name:\s*"?([^"\n]+?)"?\s*$/);
    if (start) { if (cur) out.push(cur); cur = { name: start[1] }; continue; }
    const kv = ln.match(/^\s+([a-z_]+):\s*"?([^"\n]*?)"?\s*(?:#.*)?$/);
    if (kv && cur) cur[kv[1]] = kv[2];
  }
  if (cur) out.push(cur);
  return out.length ? out : null;
}

/** The `- path:` entries under the top-level `artifacts:` key. */
export function artifactPaths(yaml) {
  const paths = [];
  let inArtifacts = false;
  for (const ln of yaml.split('\n')) {
    if (/^[A-Za-z_][A-Za-z0-9_]*:/.test(ln)) { inArtifacts = /^artifacts:/.test(ln); continue; }
    if (!inArtifacts) continue;
    const m = ln.match(/^\s*-\s*path:\s*"?([^"\n]+?)"?\s*$/);
    if (m) paths.push(m[1]);
  }
  return paths;
}

/**
 * The deposit's file list. Fails CLOSED on anything it cannot resolve: a deposit silently
 * missing a declared artifact is worse than no deposit. Only `type: blob` tree entries are
 * taken, which is what makes gitignored material structurally unreachable rather than
 * merely absent — a `.pyc` under figures/ carrying a username reached the payload that way
 * once, and regenerated after deletion.
 */
export function resolvePayloadFiles({ yaml, tree, vars }) {
  if (!yaml || !yaml.trim()) throw new Error('publish.yml came back empty');
  const paths = artifactPaths(yaml);
  if (!paths.length) throw new Error('publish.yml declared no artifacts: nothing to deposit');
  if (!tree || !tree.length) throw new Error('the git tree at ref ' + vars.ref + ' came back empty');

  const blobs = tree.filter((e) => e.type === 'blob');
  const base = String(vars.projectPath).replace(/\/+$/, '') + '/';
  const files = [];
  for (const p of paths) {
    const full = base + p;
    if (p.endsWith('/')) {
      const hits = blobs.filter((e) => e.path.indexOf(full) === 0);
      if (!hits.length) throw new Error('declared artifact directory is empty or absent at ref: ' + full);
      for (const h of hits) files.push(h.path);
    } else {
      if (!blobs.some((e) => e.path === full)) {
        throw new Error('declared artifact is not a tracked file at ref: ' + full);
      }
      files.push(full);
    }
  }

  const RAW = 'https://raw.githubusercontent.com/' + vars.repo + '/' + vars.ref + '/';
  const out = files.map((f) => ({
    filename: f.slice(base.length), url: RAW + f, kind: 'artifact', repoPath: f,
  }));
  // Spec D6: a frozen source snapshot beside the PDF, so a reader of the DOI can reach the
  // exact tree the evidence came from. A git archive is tracked content by construction.
  out.push({
    filename: vars.repo.split('/')[1] + '-' + vars.ref + '-source.tar.gz',
    url: 'https://codeload.github.com/' + vars.repo + '/tar.gz/' + vars.ref,
    kind: 'snapshot',
  });
  return out;
}

/**
 * The metadata a repository indexes, read from the manifest rather than hardcoded. A record
 * nobody can find is a record that did not publish, so a MISSING field is an error naming
 * the field — never a silent omission leaving the deposit uncategorised.
 */
export function buildZenodoMetadata({ yaml, vars }) {
  const lines = yaml.split('\n');
  const need = {
    title: scalar(yaml, 'title'),
    description: blockScalar(yaml, 'description'),
    language: scalar(yaml, 'language'),
    keywords: flowSeq(yaml, 'keywords'),
    subjects: flowMaps(yaml, 'subjects'),
    related: flowMaps(yaml, 'related_identifiers'),
    creators: authors(yaml),
  };
  const missing = Object.keys(need).filter((k) => !need[k]);
  if (missing.length) {
    throw new Error('publish.yml is missing discovery metadata the repository indexes: ' + missing.join(', '));
  }

  const i = lines.findIndex((l) => /^\s+zenodo:/.test(l));
  const got = { upload_type: null, publication_type: null, zenodo_license: null };
  if (i !== -1) {
    for (let j = i + 1; j < lines.length && /^\s{4,}/.test(lines[j]); j++) {
      const m = lines[j].match(/^\s+([a-z_]+):\s*"?([^"\n]*?)"?\s*(?:#.*)?$/);
      if (m && Object.prototype.hasOwnProperty.call(got, m[1])) got[m[1]] = m[2];
    }
  }
  if (!got.upload_type || !got.publication_type) {
    throw new Error('publish.yml venues.zenodo is missing upload_type or publication_type');
  }

  return {
    title: need.title,
    description: need.description,
    upload_type: got.upload_type,
    publication_type: got.publication_type,
    license: got.zenodo_license || scalar(yaml, 'license') || 'mit',
    version: vars.version,
    language: need.language,
    keywords: need.keywords,
    subjects: need.subjects.map((s) => ({ term: s.term, identifier: s.identifier, scheme: s.scheme })),
    related_identifiers: need.related.map((r) => ({
      relation: r.relation, identifier: r.identifier, resource_type: r.resource_type, scheme: r.scheme,
    })),
    creators: need.creators.map((a) => {
      const c = { name: a.name };
      if (a.affiliation) c.affiliation = a.affiliation;
      if (a.orcid) c.orcid = a.orcid;
      return c;
    }),
  };
}

/**
 * Two refusals, both before anything is created. `mode` used to be accepted and then
 * IGNORED, so a second run minted a SECOND unrelated DOI instead of a new version. And
 * Zenodo cannot withdraw a published DOI, so the create call is the last cheap moment to
 * notice that the record already exists.
 */
export function assertNotAlreadyDeposited({ yaml, depositions, vars }) {
  if (vars.mode !== 'publish') {
    throw new Error(
      "mode '" + vars.mode + "' is NOT IMPLEMENTED by the deposit path - only 'publish' creates "
      + "a record. 'update' requires Zenodo's newversion action plus a committed state file "
      + "recording the concept DOI, and neither is built; 'prepare' requires a branch that skips "
      + 'the deposit. Failing by name, because the alternative is silently minting a new record '
      + 'and calling it an update.');
  }
  const tm = yaml.match(/^title:\s*"?(.+?)"?\s*$/m);
  if (!tm) throw new Error('publish.yml carries no title, so an existing record cannot be ruled out');
  const title = tm[1].trim();

  // Only PUBLISHED records block. A leftover draft is not a duplicate.
  const clashes = (depositions || [])
    .filter((d) => d && d.submitted === true)
    .filter((d) => {
      const t = String((d.title || (d.metadata && d.metadata.title) || '')).trim();
      const v = (d.metadata && d.metadata.version) || null;
      return t === title && String(v) === String(vars.version);
    });

  if (clashes.length) {
    const c = clashes[0];
    throw new Error(
      'ALREADY DEPOSITED: "' + title + '" version ' + vars.version + ' is already a published '
      + 'record (deposition ' + c.id + ', DOI ' + (c.doi || 'pending') + '). Refusing to mint a '
      + 'second DOI for the same paper and version. Bump `version` in the payload for a new '
      + 'release, or implement mode=update for a true new version of this record.');
  }
  return { duplicate_check: 'passed', title, version: vars.version, published_records_seen: (depositions || []).length };
}

/**
 * A locked bucket accepts the request shape and stores nothing, so without this the run
 * reports PUBLISHED over an empty record. Ported from the Python submitter this replaces,
 * which was caught doing exactly that.
 */
export function assertOpenDraft(deposition) {
  const d = deposition;
  if (!d || !d.id) {
    throw new Error('Zenodo did not return a deposition id: ' + JSON.stringify(d).slice(0, 300));
  }
  if (d.submitted === true) {
    throw new Error('deposition ' + d.id + ' is already SUBMITTED - refusing to upload into a published record');
  }
  const bucket = d.links && d.links.bucket;
  if (!bucket) {
    throw new Error('deposition ' + d.id + ' has no links.bucket - the file bucket is locked or '
      + 'absent, so an upload would report success and store nothing');
  }
  return { depositionId: d.id, bucket, selfLink: d.links.self, publishLink: d.links.publish };
}
