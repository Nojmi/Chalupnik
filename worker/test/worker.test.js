import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import worker, { resetState } from '../src/index.js';

const ORIGIN = 'https://nojmi.github.io';
const MAP_URL = 'https://nojmi.github.io/Chalupnik/data/mapa-cr.json';
const ENV = {
  GH_TOKEN: 'test-token', GH_REPO: 'Nojmi/Chalupnik', GH_WORKFLOW: 'scrape.yml', GH_REF: 'main',
  ALLOWED_ORIGIN: ORIGIN, MAP_URL, REGION_COOLDOWN_MIN: '60', DAILY_LIMIT: '20',
};
const REGIONS = ['Šumava', 'Krkonoše', 'Český ráj', 'Jižní Morava'];
const MIN = 60 * 1000;

const realFetch = globalThis.fetch;
beforeEach(() => resetState());
afterEach(() => { globalThis.fetch = realFetch; });

// Běh workflow tak, jak ho vrací GitHub API (jen pole, která Worker čte).
let seq = 1000;
function run(region, minutesAgo, { status = 'completed', conclusion = 'success', title } = {}) {
  const t = new Date(Date.now() - minutesAgo * MIN).toISOString();
  return {
    id: ++seq, display_title: title ?? `Scrape ${region}`, status, conclusion: status === 'completed' ? conclusion : null,
    created_at: t, run_started_at: t, updated_at: t, html_url: `https://github.com/Nojmi/Chalupnik/actions/runs/${seq}`,
  };
}

// Mock fetch: Pages (mapa-cr.json) + GitHub API (seznam běhů, dispatch). Zaznamenává volání.
function mockNetwork({ runs = [], dispatch = 204, runsStatus = 200, mapStatus = 200 } = {}) {
  const calls = { map: 0, list: [], dispatch: [] };
  globalThis.fetch = async (url, init = {}) => {
    const u = new URL(String(url));
    if (String(url) === MAP_URL) {
      calls.map++;
      return new Response(JSON.stringify({ oblasti: REGIONS.map(name => ({ name })) }), { status: mapStatus });
    }
    assert.equal(u.origin, 'https://api.github.com', `nečekané volání ${url}`);
    assert.equal(init.headers.Authorization, 'Bearer test-token');
    assert.ok(init.headers['User-Agent']);
    if (u.pathname.endsWith('/dispatches')) {
      calls.dispatch.push({ path: u.pathname, body: JSON.parse(init.body), method: init.method });
      return new Response(dispatch === 204 ? null : '{"message":"x"}', { status: dispatch });
    }
    assert.equal(u.pathname, '/repos/Nojmi/Chalupnik/actions/workflows/scrape.yml/runs');
    calls.list.push(u.searchParams);
    if (runsStatus !== 200) return new Response('{}', { status: runsStatus });
    const created = u.searchParams.get('created');
    const min = created ? Date.parse(created.replace(/^>=/, '')) : -Infinity;
    return new Response(JSON.stringify({ workflow_runs: runs.filter(r => Date.parse(r.created_at) >= min) }), { status: 200 });
  };
  return calls;
}

function call(method, path, { origin = ORIGIN, body, env = ENV } = {}) {
  const headers = {};
  if (origin) headers.Origin = origin;
  const init = { method, headers };
  if (body !== undefined) { init.body = typeof body === 'string' ? body : JSON.stringify(body); headers['Content-Type'] = 'application/json'; }
  return worker.fetch(new Request(`https://chalupnik.example.workers.dev${path}`, init), env);
}
const post = (region, opts) => call('POST', '/run', { body: { region }, ...opts });
const readJson = async res => res.json();

/* ---------- Origin a CORS ---------- */
test('POST /run s cizím Originem je 403 a nevolá GitHub', async () => {
  const net = mockNetwork();
  const res = await post('Šumava', { origin: 'https://evil.example' });
  assert.equal(res.status, 403);
  assert.equal((await readJson(res)).error, 'bad_origin');
  assert.equal(res.headers.get('Access-Control-Allow-Origin'), null);
  assert.equal(net.list.length + net.dispatch.length + net.map, 0);
});

test('POST /run bez Originu je 403', async () => {
  mockNetwork();
  assert.equal((await post('Šumava', { origin: null })).status, 403);
});

test('Origin se musí shodovat přesně (ne jen prefix)', async () => {
  mockNetwork();
  assert.equal((await post('Šumava', { origin: 'https://nojmi.github.io.evil.example' })).status, 403);
  assert.equal((await post('Šumava', { origin: 'http://nojmi.github.io' })).status, 403);
});

test('preflight: náš Origin dostane CORS hlavičky, cizí ne', async () => {
  const ok = await call('OPTIONS', '/run');
  assert.equal(ok.status, 204);
  assert.equal(ok.headers.get('Access-Control-Allow-Origin'), ORIGIN);
  assert.match(ok.headers.get('Access-Control-Allow-Methods'), /POST/);
  const bad = await call('OPTIONS', '/run', { origin: 'https://evil.example' });
  assert.equal(bad.status, 403);
  assert.equal(bad.headers.get('Access-Control-Allow-Origin'), null);
});

test('CORS hlavička je jen pro náš origin (i u /status)', async () => {
  mockNetwork();
  assert.equal((await call('GET', '/status')).headers.get('Access-Control-Allow-Origin'), ORIGIN);
  resetState();
  assert.equal((await call('GET', '/status', { origin: 'https://evil.example' })).headers.get('Access-Control-Allow-Origin'), null);
});

/* ---------- validace oblasti ---------- */
test('neznámá oblast je 400 a nic se nespustí', async () => {
  const net = mockNetwork();
  const res = await post('Mordor');
  assert.equal(res.status, 400);
  assert.equal((await readJson(res)).error, 'unknown_region');
  assert.equal(net.dispatch.length, 0);
  assert.equal(net.list.length, 0);
});

test('víc oblastí najednou, prázdný název i špatné typy jsou 400', async () => {
  const net = mockNetwork();
  for (const region of ['Šumava; Krkonoše', 'Šumava;', '', '   ', 'KRAJE', 42, null, ['Šumava']]) {
    const res = await post(region);
    assert.equal(res.status, 400, `region ${JSON.stringify(region)}`);
  }
  assert.equal((await call('POST', '/run', { body: '{nejde to' })).status, 400);
  assert.equal((await call('POST', '/run', { body: '{}' })).status, 400);
  assert.equal((await call('POST', '/run', { body: 'null' })).status, 400);
  assert.equal(net.dispatch.length, 0);
});

test('příliš velké tělo je 413', async () => {
  mockNetwork();
  const res = await call('POST', '/run', { body: JSON.stringify({ region: 'Šumava', x: 'a'.repeat(5000) }) });
  assert.equal(res.status, 413);
});

test('seznam oblastí se načítá z Pages jednou za hodinu', async () => {
  const net = mockNetwork();
  await post('Šumava');
  await post('Šumava');
  await post('Krkonoše');
  assert.equal(net.map, 1);
});

test('nedostupný mapa-cr.json je 502 a nic se nespustí', async () => {
  const net = mockNetwork({ mapStatus: 404 });
  const res = await post('Šumava');
  assert.equal(res.status, 502);
  assert.equal((await readJson(res)).error, 'map_unavailable');
  assert.equal(net.dispatch.length, 0);
});

test('název oblasti se porovnává po normalizaci Unicode (NFC)', async () => {
  const net = mockNetwork();
  const res = await post('Šumava'.normalize('NFD'));
  assert.equal(res.status, 202);
  assert.equal(net.dispatch[0].body.inputs.location, 'Šumava');
});

/* ---------- úspěšné spuštění ---------- */
test('úspěšné spuštění: dispatch na správnou adresu se správným tělem', async () => {
  const net = mockNetwork();
  const res = await post('Šumava');
  assert.equal(res.status, 202);
  const body = await readJson(res);
  assert.equal(body.ok, true);
  assert.equal(body.region, 'Šumava');
  assert.ok(Math.abs(Date.parse(body.dispatched_at) - Date.now()) < 5000);
  assert.deepEqual(net.dispatch, [{
    path: '/repos/Nojmi/Chalupnik/actions/workflows/scrape.yml/dispatches', method: 'POST',
    body: { ref: 'main', inputs: { location: 'Šumava' } },
  }]);
  assert.equal(res.headers.get('Access-Control-Allow-Origin'), ORIGIN);
  assert.equal(net.list[0].get('event'), 'workflow_dispatch');
  assert.match(net.list[0].get('created'), /^>=\d{4}-/);
});

test('jiná oblast spuštěná před 30 min cooldown nespouští', async () => {
  const net = mockNetwork({ runs: [run('Krkonoše', 30)] });
  assert.equal((await post('Šumava')).status, 202);
  assert.equal(net.dispatch.length, 1);
});

/* ---------- zámek: běží / čeká ---------- */
test('409, když nějaký běh běží', async () => {
  const net = mockNetwork({ runs: [run('Krkonoše', 5, { status: 'in_progress' })] });
  const res = await post('Šumava');
  assert.equal(res.status, 409);
  const body = await readJson(res);
  assert.equal(body.error, 'already_running');
  assert.equal(body.active.region, 'Krkonoše');
  assert.equal(body.active.state, 'running');
  assert.equal(net.dispatch.length, 0);
});

test('409, když běh čeká ve frontě (queued / pending / waiting)', async () => {
  for (const status of ['queued', 'pending', 'waiting', 'requested']) {
    resetState();
    const net = mockNetwork({ runs: [run('Šumava', 2, { status })] });
    const res = await post('Krkonoše');
    assert.equal(res.status, 409, status);
    assert.equal((await readJson(res)).active.state, 'queued');
    assert.equal(net.dispatch.length, 0);
  }
});

test('409 má přednost před cooldownem téže oblasti', async () => {
  mockNetwork({ runs: [run('Šumava', 3, { status: 'in_progress' })] });
  const res = await post('Šumava');
  assert.equal(res.status, 409);
  assert.equal((await readJson(res)).active.region, 'Šumava');
});

test('dokončené běhy zámek nedrží', async () => {
  mockNetwork({ runs: [run('Krkonoše', 90, { conclusion: 'failure' }), run('Český ráj', 120, { conclusion: 'cancelled' })] });
  assert.equal((await post('Šumava')).status, 202);
});

test('pojistka: druhý požadavek hned po spuštění, než GitHub běh vrátí, je 409', async () => {
  const net = mockNetwork({ runs: [] });          // GitHub nový běh zatím nevidí
  assert.equal((await post('Šumava')).status, 202);
  const res = await post('Krkonoše');
  assert.equal(res.status, 409);
  assert.equal((await readJson(res)).active.region, 'Šumava');
  assert.equal(net.dispatch.length, 1);
});

test('pojistka se uvolní, jakmile GitHub běh vrátí jako dokončený', async () => {
  mockNetwork({ runs: [] });
  assert.equal((await post('Šumava')).status, 202);
  mockNetwork({ runs: [run('Šumava', 0, { conclusion: 'success' })] });
  assert.equal((await post('Krkonoše')).status, 202);
});

/* ---------- cooldown oblasti ---------- */
test('429 s retry_after_s, když byla stejná oblast spuštěna před 20 min', async () => {
  const net = mockNetwork({ runs: [run('Šumava', 20)] });
  const res = await post('Šumava');
  assert.equal(res.status, 429);
  const body = await readJson(res);
  assert.equal(body.error, 'region_cooldown');
  assert.ok(body.retry_after_s >= 39 * 60 && body.retry_after_s <= 40 * 60 + 1, `retry_after_s=${body.retry_after_s}`);
  assert.equal(res.headers.get('Retry-After'), String(body.retry_after_s));
  assert.ok(Math.abs(Date.parse(body.retry_at) - (Date.now() + body.retry_after_s * 1000)) < 2000);
  assert.equal(net.dispatch.length, 0);
});

test('cooldown se počítá od vytvoření běhu a po 60 min končí', async () => {
  mockNetwork({ runs: [run('Šumava', 59)] });
  assert.equal((await post('Šumava')).status, 429);
  resetState();
  mockNetwork({ runs: [run('Šumava', 61)] });
  assert.equal((await post('Šumava')).status, 202);
});

test('cooldown platí i pro neúspěšný a zrušený běh', async () => {
  mockNetwork({ runs: [run('Šumava', 10, { conclusion: 'failure' })] });
  assert.equal((await post('Šumava')).status, 429);
});

test('cooldown jde nastavit proměnnou REGION_COOLDOWN_MIN', async () => {
  mockNetwork({ runs: [run('Šumava', 20)] });
  assert.equal((await post('Šumava', { env: { ...ENV, REGION_COOLDOWN_MIN: '10' } })).status, 202);
});

/* ---------- denní strop ---------- */
test('429 daily_limit při 20 spuštěních za 24 h (běhy starší než cooldown)', async () => {
  const runs = Array.from({ length: 20 }, (_, i) => run(REGIONS[i % 4], 120 + i * 30));   // 2 h … 11,5 h zpět
  const net = mockNetwork({ runs });
  const res = await post('Šumava');
  assert.equal(res.status, 429);
  const body = await readJson(res);
  assert.equal(body.error, 'daily_limit');
  const oldestMin = 120 + 19 * 30;                                   // nejstarší běh vyprší za 24 h − 11,5 h
  const expected = (24 * 60 - oldestMin) * 60;
  assert.ok(Math.abs(body.retry_after_s - expected) <= 2, `retry_after_s=${body.retry_after_s}, čekáno ${expected}`);
  assert.equal(net.dispatch.length, 0);
});

test('19 spuštění za 24 h ještě projde', async () => {
  const runs = Array.from({ length: 19 }, (_, i) => run(REGIONS[i % 4], 120 + i * 30));
  mockNetwork({ runs });
  assert.equal((await post('Šumava')).status, 202);
});

test('do stropu se počítají i běhy jiných oblastí, ale ne starší než 24 h', async () => {
  const fresh = Array.from({ length: 19 }, (_, i) => run('Krkonoše', 120 + i * 20));
  const old = [run('Krkonoše', 25 * 60), run('Krkonoše', 30 * 60)];
  mockNetwork({ runs: [...fresh, ...old] });
  assert.equal((await post('Šumava')).status, 202);
});

test('strop jde nastavit proměnnou DAILY_LIMIT', async () => {
  const runs = [run('Krkonoše', 120), run('Český ráj', 180)];
  mockNetwork({ runs });
  const res = await post('Šumava', { env: { ...ENV, DAILY_LIMIT: '2' } });
  assert.equal(res.status, 429);
  assert.equal((await readJson(res)).error, 'daily_limit');
});

/* ---------- chyby GitHubu a nastavení ---------- */
test('selhání seznamu běhů je 502 a nic se nespustí', async () => {
  const net = mockNetwork({ runsStatus: 401 });
  const res = await post('Šumava');
  assert.equal(res.status, 502);
  const body = await readJson(res);
  assert.equal(body.error, 'github_error');
  assert.equal(body.github_status, 401);
  assert.equal(net.dispatch.length, 0);
});

test('selhání dispatche je 502 a nezablokuje další pokus', async () => {
  mockNetwork({ dispatch: 422 });
  const res = await post('Šumava');
  assert.equal(res.status, 502);
  mockNetwork();
  assert.equal((await post('Šumava')).status, 202);
});

test('chybějící GH_TOKEN je 500 bez úniku detailů', async () => {
  mockNetwork();
  const res = await post('Šumava', { env: { ...ENV, GH_TOKEN: '' } });
  assert.equal(res.status, 500);
  assert.ok(!JSON.stringify(await readJson(res)).includes('test-token'));
});

test('neznámá adresa je 404, špatná metoda 405', async () => {
  mockNetwork();
  assert.equal((await call('GET', '/')).status, 404);
  assert.equal((await call('POST', '/status')).status, 405);
  const res = await call('GET', '/run');
  assert.equal(res.status, 405);
  assert.equal(res.headers.get('Allow'), 'POST');
});

/* ---------- GET /status ---------- */
test('status: běží', async () => {
  mockNetwork({ runs: [run('Šumava', 4, { status: 'in_progress' }), run('Krkonoše', 300)] });
  const body = await readJson(await call('GET', '/status'));
  assert.equal(body.state, 'running');
  assert.equal(body.run.region, 'Šumava');
  assert.equal(body.active.region, 'Šumava');
});

test('status: fronta (pending)', async () => {
  mockNetwork({ runs: [run('Šumava', 1, { status: 'pending' })] });
  assert.equal((await readJson(await call('GET', '/status'))).state, 'queued');
});

test('status: hotovo, selhalo, zrušeno', async () => {
  const cases = [['success', 'success'], ['failure', 'failed'], ['timed_out', 'failed'], ['cancelled', 'cancelled']];
  for (const [conclusion, state] of cases) {
    resetState();
    mockNetwork({ runs: [run('Šumava', 10, { conclusion })] });
    const body = await readJson(await call('GET', '/status'));
    assert.equal(body.state, state, conclusion);
    assert.equal(body.active, null);
    assert.ok(body.run.finished_at);
  }
});

test('status: žádný běh', async () => {
  mockNetwork({ runs: [] });
  const body = await readJson(await call('GET', '/status'));
  assert.equal(body.state, 'none');
  assert.equal(body.run, null);
});

test('status: filtr podle oblasti', async () => {
  mockNetwork({ runs: [run('Krkonoše', 1, { status: 'in_progress' }), run('Šumava', 200)] });
  const body = await readJson(await call('GET', '/status?region=' + encodeURIComponent('Šumava')));
  assert.equal(body.state, 'success');
  assert.equal(body.run.region, 'Šumava');
  assert.equal(body.active.region, 'Krkonoše');
});

test('status: se since ignoruje starší běh téže oblasti a vrátí pending', async () => {
  mockNetwork({ runs: [run('Šumava', 120)] });
  const since = new Date().toISOString();
  const body = await readJson(await call('GET', `/status?region=${encodeURIComponent('Šumava')}&since=${encodeURIComponent(since)}`));
  assert.equal(body.state, 'pending');
  assert.equal(body.run, null);
});

test('status: se since najde nově vytvořený běh', async () => {
  const since = new Date(Date.now() - 2 * MIN).toISOString();
  mockNetwork({ runs: [run('Šumava', 1, { status: 'in_progress' }), run('Šumava', 120)] });
  const body = await readJson(await call('GET', `/status?region=${encodeURIComponent('Šumava')}&since=${encodeURIComponent(since)}`));
  assert.equal(body.state, 'running');
});

test('status: špatné since je 400', async () => {
  mockNetwork();
  assert.equal((await call('GET', '/status?since=nesmysl')).status, 400);
});

test('status: seznam běhů se cachuje 20 s, spuštění cache zneplatní', async () => {
  const net = mockNetwork({ runs: [run('Šumava', 200)] });
  await call('GET', '/status');
  await call('GET', '/status?region=' + encodeURIComponent('Šumava'));
  assert.equal(net.list.length, 1);
  assert.equal((await post('Krkonoše')).status, 202);        // POST čte čerstvá data (+1) a zneplatní cache
  const before = net.list.length;
  await call('GET', '/status');
  assert.equal(net.list.length, before + 1);
});

test('status: chyba GitHubu je 502', async () => {
  mockNetwork({ runsStatus: 500 });
  assert.equal((await call('GET', '/status')).status, 502);
});

test('odpovědi nejsou cachovatelné prohlížečem a nenesou token', async () => {
  mockNetwork({ runs: [run('Šumava', 200)] });
  const res = await call('GET', '/status');
  assert.equal(res.headers.get('Cache-Control'), 'no-store');
  assert.ok(!(await res.text()).includes('test-token'));
});
