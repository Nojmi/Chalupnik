import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import worker, { resetState } from '../src/index.js';

const ENV = { ALLOWED_HOSTS: 'e-chalupy.cz,www.cs-chalupy.cz,www.chata.cz', CACHE_TTL_DAYS: '30', NEG_TTL_MIN: '10', MAX_MB: '6' };
const PHOTO = 'https://e-chalupy.cz/foto/abc-123.jpg';
const BYTES = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3, 4]);

const realFetch = globalThis.fetch;
beforeEach(() => resetState());
afterEach(() => { globalThis.fetch = realFetch; });

// Mock fetch na portály; zaznamenává volání.
function upstream(handler) {
  const calls = [];
  globalThis.fetch = async (url, init = {}) => { calls.push({ url: String(url), init }); return handler(String(url), init, calls.length); };
  return calls;
}
const jpeg = (extra = {}) => new Response(BYTES, { status: 200, headers: { 'Content-Type': 'image/jpeg', 'cf-cache-status': 'MISS', ...extra } });
const get = (u, { method = 'GET', env = ENV, path = '/img' } = {}) =>
  worker.fetch(new Request(`https://chalupnik-img.example.workers.dev${path}${u === null ? '' : `?u=${encodeURIComponent(u)}`}`, { method }), env);

/* ---------- vstup a whitelist ---------- */
test('chybějící parametr u je 400', async () => {
  const calls = upstream(() => jpeg());
  assert.equal((await get(null)).status, 400);
  assert.equal(calls.length, 0);
});

test('adresy mimo whitelist, s přihlášením, portem nebo cizím schématem jsou 400 a portál se nevolá', async () => {
  const calls = upstream(() => jpeg());
  for (const u of [
    'https://evil.example/a.jpg', 'https://www.chata.cz.evil.example/a.jpg', 'https://evilwww.chata.cz/a.jpg',
    'https://chata.cz/a.jpg',                                    // jen www.chata.cz je povolený host
    'https://user:pw@e-chalupy.cz/a.jpg', 'https://e-chalupy.cz:8080/a.jpg',
    'ftp://e-chalupy.cz/a.jpg', 'javascript:alert(1)', 'file:///etc/passwd', 'neni-url', 'http://127.0.0.1/a.jpg', 'http://localhost/a.jpg',
  ]) {
    const res = await get(u);
    assert.equal(res.status, 400, u);
    assert.equal((await res.json()).ok, false);
  }
  assert.equal(calls.length, 0);
});

test('příliš dlouhá adresa je 400', async () => {
  upstream(() => jpeg());
  assert.equal((await get(`https://e-chalupy.cz/${'a'.repeat(2100)}.jpg`)).status, 400);
});

test('špatná metoda je 405, jiná cesta 404', async () => {
  upstream(() => jpeg());
  const res = await get(PHOTO, { method: 'POST' });
  assert.equal(res.status, 405);
  assert.equal(res.headers.get('Allow'), 'GET, HEAD');
  assert.equal((await get(PHOTO, { path: '/neco' })).status, 404);
});

test('bez ALLOWED_HOSTS je 500', async () => {
  upstream(() => jpeg());
  assert.equal((await get(PHOTO, { env: {} })).status, 500);
});

/* ---------- úspěch ---------- */
test('fotka se stáhne jednou a vrátí se s cache hlavičkami na 30 dní', async () => {
  const calls = upstream(() => jpeg());
  const res = await get(PHOTO);
  assert.equal(res.status, 200);
  assert.deepEqual(new Uint8Array(await res.arrayBuffer()), BYTES);
  assert.equal(res.headers.get('Content-Type'), 'image/jpeg');
  assert.equal(res.headers.get('Cache-Control'), 'public, max-age=2592000, immutable');
  assert.equal(res.headers.get('X-Content-Type-Options'), 'nosniff');
  assert.equal(res.headers.get('X-Upstream-Cache'), 'MISS');
  assert.equal(calls.length, 1);
});

test('dotaz na portál: správná adresa, cache volby, bez Refereru, s User-Agentem', async () => {
  const calls = upstream(() => jpeg());
  await get(PHOTO);
  const { url, init } = calls[0];
  assert.equal(url, PHOTO);
  assert.equal(init.redirect, 'manual');
  assert.deepEqual(init.cf, { cacheEverything: true, cacheTtlByStatus: { '200-299': 2592000, '400-499': 600, '500-599': 0 } });
  assert.match(init.headers['User-Agent'], /^Chalupnik\//);
  assert.ok(!Object.keys(init.headers).some(k => k.toLowerCase() === 'referer'));
});

test('TTL jde měnit proměnnými', async () => {
  const calls = upstream(() => jpeg());
  const res = await get(PHOTO, { env: { ...ENV, CACHE_TTL_DAYS: '1', NEG_TTL_MIN: '5' } });
  assert.equal(res.headers.get('Cache-Control'), 'public, max-age=86400, immutable');
  assert.equal(calls[0].init.cf.cacheTtlByStatus['200-299'], 86400);
  assert.equal(calls[0].init.cf.cacheTtlByStatus['400-499'], 300);
});

test('http adresa se povýší na https', async () => {
  const calls = upstream(() => jpeg());
  assert.equal((await get('http://www.chata.cz/img_vypis_big/CZ0005-letni.jpg#x')).status, 200);
  assert.equal(calls[0].url, 'https://www.chata.cz/img_vypis_big/CZ0005-letni.jpg');
});

test('HEAD vrací hlavičky bez těla', async () => {
  upstream(() => jpeg());
  const res = await get(PHOTO, { method: 'HEAD' });
  assert.equal(res.status, 200);
  assert.equal(res.headers.get('Content-Length'), String(BYTES.length));
  assert.equal(await res.text(), '');
});

/* ---------- chyby ---------- */
test('404 a 410 z portálu: 404 s negativní cache 10 min', async () => {
  for (const status of [404, 410]) {
    resetState();
    upstream(() => new Response('nic', { status }));
    const res = await get(PHOTO);
    assert.equal(res.status, 404, String(status));
    assert.equal(res.headers.get('Cache-Control'), 'public, max-age=600');
  }
});

test('5xx, 403 a výpadek sítě: 502 s krátkou cache a důvodem', async () => {
  upstream(() => new Response('x', { status: 500 }));
  let res = await get(PHOTO);
  assert.equal(res.status, 502);
  assert.equal(res.headers.get('Cache-Control'), 'public, max-age=60');
  assert.equal(res.headers.get('X-Upstream-Error'), 'status 500');
  upstream(() => new Response('x', { status: 403 }));
  res = await get(PHOTO);
  assert.equal(res.status, 502);
  assert.equal(res.headers.get('X-Upstream-Error'), 'status 403');
  upstream(() => { throw new Error('boom'); });
  res = await get(PHOTO);
  assert.equal(res.status, 502);
  assert.equal(res.headers.get('X-Upstream-Error'), 'network');
});

test('odpověď, která není fotka (HTML, SVG), se nepřeposílá', async () => {
  for (const type of ['text/html; charset=utf-8', 'image/svg+xml', 'application/octet-stream', '']) {
    resetState();
    upstream(() => new Response('<html>', { status: 200, headers: type ? { 'Content-Type': type } : {} }));
    const res = await get(PHOTO);
    assert.equal(res.status, 502, type);
    assert.equal(res.headers.get('X-Upstream-Error'), 'type');
  }
});

test('příliš velká nebo prázdná fotka je 502', async () => {
  upstream(() => jpeg({ 'Content-Length': String(7 * 1024 * 1024) }));
  let res = await get(PHOTO);
  assert.equal(res.status, 502);
  assert.equal(res.headers.get('X-Upstream-Error'), 'size');
  resetState();
  upstream(() => new Response(new Uint8Array(0), { status: 200, headers: { 'Content-Type': 'image/jpeg' } }));
  res = await get(PHOTO);
  assert.equal(res.status, 502);
  resetState();
  upstream(() => jpeg());
  assert.equal((await get(PHOTO, { env: { ...ENV, MAX_MB: '0.000001' } })).status, 502);   // velikost se hlídá i podle skutečného těla
});

/* ---------- přesměrování ---------- */
const redirect = (to, status = 301) => new Response(null, { status, headers: { Location: to } });

test('přesměrování na povolený host se následuje (i relativní)', async () => {
  const calls = upstream((url, init, n) => n === 1 ? redirect('https://www.chata.cz/novy.jpg') : n === 2 ? redirect('/jeste-jinam.jpg') : jpeg());
  const res = await get(PHOTO);
  assert.equal(res.status, 200);
  assert.deepEqual(calls.map(c => c.url), [PHOTO, 'https://www.chata.cz/novy.jpg', 'https://www.chata.cz/jeste-jinam.jpg']);
});

test('přesměrování na cizí host nebo do smyčky je 502', async () => {
  const calls = upstream(() => redirect('https://evil.example/a.jpg'));
  let res = await get(PHOTO);
  assert.equal(res.status, 502);
  assert.equal(res.headers.get('X-Upstream-Error'), 'redirect');
  assert.equal(calls.length, 1);
  resetState();
  const loop = upstream(() => redirect(PHOTO));
  res = await get(PHOTO);
  assert.equal(res.status, 502);
  assert.ok(loop.length <= 4, `volání: ${loop.length}`);
});

/* ---------- souběh ---------- */
test('souběžné dotazy na stejnou fotku sdílejí jediný dotaz na portál', async () => {
  let release;
  const gate = new Promise(r => { release = r; });
  const calls = upstream(async () => { await gate; return jpeg(); });
  const [a, b, c] = [get(PHOTO), get(PHOTO), get(PHOTO)];
  await new Promise(r => setImmediate(r));
  release();
  const res = await Promise.all([a, b, c]);
  assert.deepEqual(res.map(r => r.status), [200, 200, 200]);
  assert.equal(calls.length, 1);
  for (const r of res) assert.deepEqual(new Uint8Array(await r.arrayBuffer()), BYTES);
  upstream(() => jpeg());
  assert.equal((await get(PHOTO)).status, 200);                  // po dokončení se nic nedrží v paměti
});

test('různé fotky se nesdílejí', async () => {
  const calls = upstream(() => jpeg());
  await Promise.all([get(PHOTO), get('https://e-chalupy.cz/foto/jina.jpg')]);
  assert.equal(calls.length, 2);
});
