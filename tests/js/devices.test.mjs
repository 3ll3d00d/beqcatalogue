// Sanity checks for the browser-side device maths, run by tests/test_devices_js.py:
//   node tests/js/devices.test.mjs <cases.json>
// - FNV-1a page shard buckets agree with Python (tests/fixtures/fnv1a.json)
// - page paths resolve relative to the site root
// - biquad.js's float32 "as loaded" responses reproduce the optimiser's validated max errors
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const context = vm.createContext({ TextEncoder, URL, Math, Number, String, Array, Object });
context.globalThis = context;
for (const file of ['docs/javascripts/biquad.js', 'docs/javascripts/devices-flag.js']) {
  vm.runInContext(readFileSync(join(root, file), 'utf8'), context, { filename: file });
}
const B = context.BeqBiquad;
const F = context.BeqDeviceFlag;

const fixture = JSON.parse(readFileSync(join(root, 'tests/fixtures/fnv1a.json'), 'utf8'));
for (const [value, bucket] of Object.entries(fixture)) assert.equal(F.bucketOf(value), bucket, value);

const site = new URL('https://beqcatalogue.readthedocs.io/en/latest/');
assert.equal(F.pagePath(new URL('https://beqcatalogue.readthedocs.io/en/latest/aron7awol/56743108/'), site), 'aron7awol/56743108/');
assert.equal(F.pagePath(new URL('https://beqcatalogue.readthedocs.io/en/latest/kaelaria/am%C3%A9lie_194'), site), 'kaelaria/amélie_194/');
assert.equal(F.pagePath(new URL('https://beqcatalogue.readthedocs.io/en/latest/a/b/index.html'), site), 'a/b/');
assert.equal(F.pagePath(new URL('https://example.com/other/'), site), null);

// the optimiser evaluates on dense grids with extremum refinement; a dense log grid gets close
const freqs = B.logSpace(2, 200, 20000);
const maxError = (sections, ideal, rate) => {
  const r = B.sectionsResponseDb(B.toFloat32(sections), freqs, rate);
  return Math.max(...r.map((v, i) => Math.abs(v - ideal[i])));
};
const cases = JSON.parse(readFileSync(process.argv[2], 'utf8'));
assert.ok(cases.length > 0);
for (const c of cases) {
  const ideal = B.sectionsResponseDb(B.sectionsFromParams(c.filters, c.rate), freqs, c.rate);
  const sent = B.sectionsFromPublished(c.filters, c.rate) || B.sectionsFromParams(c.filters, c.rate);
  const before = maxError(sent, ideal, c.rate);
  assert.ok(Math.abs(before - c.before_db) <= 0.01 + 0.002 * c.before_db, `${c.name} before ${before} vs ${c.before_db}`);
  if (c.after) {
    const after = maxError(c.after.map(B.sectionFromPublished), ideal, c.rate);
    assert.ok(Math.abs(after - c.after_db) <= 0.01, `${c.name} after ${after} vs ${c.after_db}`);
    assert.ok(after < before, `${c.name} optimised is not better`);
  }
  console.log(`${c.name}: before ${before.toFixed(4)} (${c.before_db.toFixed(4)}), after ${c.after ? maxError(c.after.map(B.sectionFromPublished), ideal, c.rate).toFixed(4) : '-'} (${c.after_db ?? '-'})`);
}
console.log('ok');
