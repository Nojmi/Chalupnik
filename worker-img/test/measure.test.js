import { test } from 'node:test';
import assert from 'node:assert/strict';
import { pickSample, summarize } from '../scripts/measure.mjs';

function rng(seed) {                         // deterministický generátor
  return () => { seed |= 0; seed = (seed + 0x6D2B79F5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
const make = (host, n) => Array.from({ length: n }, (_, i) => `https://${host}/f/${i}.jpg`);

test('vzorek je rovnoměrný mezi portály, bez duplicit a bez překročení n', () => {
  const urls = [...make('e-chalupy.cz', 500), ...make('www.cs-chalupy.cz', 100), ...make('www.chata.cz', 80), ...make('www.chata.cz', 10)];
  const s = pickSample(urls, 100, rng(1));
  assert.equal(s.length, 100);
  assert.equal(new Set(s).size, 100);
  const by = {};
  for (const u of s) by[new URL(u).hostname] = (by[new URL(u).hostname] || 0) + 1;
  assert.deepEqual(by, { 'e-chalupy.cz': 34, 'www.chata.cz': 33, 'www.cs-chalupy.cz': 33 });
});

test('portál s málo fotkami dá, kolik má; prázdný vstup dá prázdný vzorek', () => {
  const s = pickSample([...make('a.cz', 3), ...make('b.cz', 50)], 20, rng(2));
  assert.equal(s.filter(u => u.includes('a.cz')).length, 3);
  assert.deepEqual(pickSample([], 10), []);
});

test('souhrn po hostech: úspěšnost, chyby, velikosti a HIT', () => {
  const row = (host, status, extra = {}) => ({ url: `https://${host}/x.jpg`, status, type: status === 200 ? 'image/jpeg' : '', bytes: 100 * 1024, ms: 100, cache: '', error: '', ...extra });
  const sum = summarize([
    row('e-chalupy.cz', 200, { bytes: 200 * 1024, cache: 'HIT' }), row('e-chalupy.cz', 200, { ms: 300 }), row('e-chalupy.cz', 404), row('e-chalupy.cz', 502, { error: 'type' }),
    row('www.chata.cz', 200),
  ]);
  const e = sum.find(s => s.host === 'e-chalupy.cz');
  assert.equal(e.n, 4); assert.equal(e.ok, 2); assert.equal(e.okPct, 50);
  assert.deepEqual(e.errors, { 404: 1, type: 1 });
  assert.equal(e.avgKB, 150); assert.equal(e.maxKB, 200); assert.equal(e.hits, 1);
  assert.equal(sum.find(s => s.host === 'www.chata.cz').okPct, 100);
});
