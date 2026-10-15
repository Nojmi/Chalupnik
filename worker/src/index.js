/* Chalupník – Cloudflare Worker pro spouštění aktualizace dat z webu.
 *
 * POST /run     {region}   spustí workflow scrape.yml pro jednu oblast
 * GET  /status             stav posledního běhu (volitelně ?region=…&since=…)
 *
 * Žádné KV ani databáze: všechny zámky se počítají ze seznamu běhů workflow
 * v GitHub API. Jediný stav v paměti je krátká pojistka proti dvojímu kliknutí
 * (GitHub ukáže nově spuštěný běh se zpožděním několika sekund).
 *
 * Konfigurace (wrangler.toml [vars]): GH_REPO, GH_WORKFLOW, GH_REF, ALLOWED_ORIGIN,
 * MAP_URL, REGION_COOLDOWN_MIN, DAILY_LIMIT. Tajemství: GH_TOKEN.
 */

const API = 'https://api.github.com';
const MAP_TTL_MS = 60 * 60 * 1000;       // seznam oblastí se drží v paměti 1 h
const STATUS_TTL_MS = 20 * 1000;         // seznam běhů pro /status se drží 20 s
const DAY_MS = 24 * 60 * 60 * 1000;
const FRESH_GUARD_MS = 45 * 1000;        // po spuštění tak dlouho počítáme s během, i když ho GitHub ještě nevrací
const SINCE_TOLERANCE_MS = 10 * 1000;    // tolerance rozdílu hodin Workeru a GitHubu
const MAX_BODY = 2048;
const ACTIVE = new Set(['queued', 'in_progress', 'waiting', 'requested', 'pending']);
const QUEUED = new Set(['queued', 'waiting', 'requested', 'pending']);

/* ---------- stav v paměti (jen cache a pojistka, nikdy zdroj pravdy) ---------- */
const mem = { map: null, runs: null, lastDispatch: null };
export function resetState() { mem.map = null; mem.runs = null; mem.lastDispatch = null; }

/* ---------- pomocné funkce ---------- */
const num = (v, def) => { const n = Number(v); return Number.isFinite(n) && n > 0 ? n : def; };
const cfg = env => ({
  repo: env.GH_REPO, workflow: env.GH_WORKFLOW, ref: env.GH_REF || 'main',
  origin: env.ALLOWED_ORIGIN, mapUrl: env.MAP_URL,
  cooldownMs: num(env.REGION_COOLDOWN_MIN, 60) * 60 * 1000,
  dailyLimit: Math.floor(num(env.DAILY_LIMIT, 20)),
});
const norm = s => String(s ?? '').normalize('NFC').trim();
const ms = iso => { const t = Date.parse(iso); return Number.isFinite(t) ? t : NaN; };
const secs = n => Math.max(1, Math.ceil(n / 1000));

function corsHeaders(request, c) {
  const h = { 'Vary': 'Origin' };
  if (c.origin && request.headers.get('Origin') === c.origin) {
    h['Access-Control-Allow-Origin'] = c.origin;
    h['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS';
    h['Access-Control-Allow-Headers'] = 'Content-Type';
    h['Access-Control-Max-Age'] = '86400';
  }
  return h;
}
function json(request, c, status, body, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...corsHeaders(request, c), ...extra },
  });
}
const fail = (request, c, status, error, message, extra = {}, headers = {}) =>
  json(request, c, status, { ok: false, error, message, ...extra }, headers);

/* ---------- GitHub API ---------- */
async function gh(env, path, init = {}) {
  return fetch(`${API}${path}`, {
    ...init,
    headers: {
      'Authorization': `Bearer ${env.GH_TOKEN}`,
      'Accept': 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'chalupnik-worker',
      ...(init.headers || {}),
    },
  });
}

// Název oblasti z run-name „Scrape <oblast>“ (viz .github/workflows/scrape.yml).
function regionOf(run) {
  const t = norm(run.display_title || run.name);
  return t.startsWith('Scrape ') ? t.slice(7).trim() : null;
}
function stateOf(run) {
  if (run.status !== 'completed') return QUEUED.has(run.status) ? 'queued' : 'running';
  if (run.conclusion === 'success') return 'success';
  if (run.conclusion === 'cancelled') return 'cancelled';
  return 'failed';
}
const brief = run => run && ({
  run_id: run.id, region: regionOf(run), state: stateOf(run), created_at: run.created_at,
  started_at: run.run_started_at || null, finished_at: run.status === 'completed' ? run.updated_at : null,
  url: run.html_url || null,
});

// Seznam běhů workflow, nejnovější první. since = jen běhy vytvořené po tomto čase (ms).
async function listRuns(env, c, { since, fresh }) {
  if (!fresh && !since && mem.runs && Date.now() - mem.runs.at < STATUS_TTL_MS) return mem.runs.list;
  const q = new URLSearchParams({ event: 'workflow_dispatch', per_page: since ? '100' : '30' });
  if (since) q.set('created', `>=${new Date(since).toISOString()}`);
  const r = await gh(env, `/repos/${c.repo}/actions/workflows/${encodeURIComponent(c.workflow)}/runs?${q}`);
  if (!r.ok) { const e = new Error(`GitHub vrátil ${r.status}`); e.githubStatus = r.status; throw e; }
  const list = ((await r.json()).workflow_runs || []).slice().sort((a, b) => ms(b.created_at) - ms(a.created_at));
  if (!since) mem.runs = { at: Date.now(), list };
  return list;
}

/* ---------- seznam oblastí z mapa-cr.json na Pages ---------- */
async function knownRegions(c) {
  if (mem.map && Date.now() - mem.map.at < MAP_TTL_MS) return mem.map.names;
  try {
    const r = await fetch(c.mapUrl, { cf: { cacheTtl: 3600, cacheEverything: true } });
    if (!r.ok) throw new Error(`mapa-cr.json: ${r.status}`);
    const names = new Set(((await r.json()).oblasti || []).map(o => norm(o.name)).filter(Boolean));
    if (!names.size) throw new Error('mapa-cr.json neobsahuje oblasti');
    mem.map = { at: Date.now(), names };
    return names;
  } catch (e) {
    if (mem.map) return mem.map.names;     // lepší trochu zastaralý seznam než žádný
    throw e;
  }
}

/* ---------- POST /run ---------- */
async function handleRun(request, env, c) {
  if (request.headers.get('Origin') !== c.origin) {
    return fail(request, c, 403, 'bad_origin', 'Požadavek nepřišel z povolené stránky.');
  }
  const raw = await request.text();
  if (raw.length > MAX_BODY) return fail(request, c, 413, 'too_large', 'Požadavek je příliš velký.');
  let body;
  try { body = JSON.parse(raw); } catch { return fail(request, c, 400, 'bad_json', 'Tělo požadavku musí být JSON.'); }
  if (!body || typeof body.region !== 'string' || !norm(body.region)) return fail(request, c, 400, 'bad_region', 'Chybí název oblasti.');
  const region = norm(body.region);

  let names;
  try { names = await knownRegions(c); } catch (e) {
    console.error('mapa-cr.json se nepodařilo načíst:', e.message);
    return fail(request, c, 502, 'map_unavailable', 'Seznam oblastí se nepodařilo načíst. Zkuste to za chvíli.');
  }
  if (!names.has(region)) return fail(request, c, 400, 'unknown_region', 'Tuto oblast nelze aktualizovat.');

  const now = Date.now();
  let runs;
  try { runs = await listRuns(env, c, { since: now - DAY_MS, fresh: true }); } catch (e) {
    console.error('Seznam běhů selhal:', e.message);
    return fail(request, c, 502, 'github_error', 'Nepodařilo se zjistit stav aktualizací. Zkuste to za chvíli.', { github_status: e.githubStatus || null });
  }

  // 1) Běží nebo čeká nějaký běh? (včetně právě spuštěného, který GitHub ještě nevrací)
  const active = runs.find(r => ACTIVE.has(r.status));
  let busy = active ? brief(active) : null;
  const g = mem.lastDispatch;
  if (!busy && g && now - g.at < FRESH_GUARD_MS) {
    const listed = runs.some(r => ms(r.created_at) >= g.at - SINCE_TOLERANCE_MS && regionOf(r) === g.region);
    if (!listed) busy = { run_id: null, region: g.region, state: 'queued', created_at: new Date(g.at).toISOString(), started_at: null, finished_at: null, url: null };
  }
  if (busy) {
    return fail(request, c, 409, 'already_running', 'Právě běží jiná aktualizace nebo čeká ve frontě.', { active: busy });
  }

  // 2) Stejná oblast za posledních N minut?
  const last = runs.filter(r => regionOf(r) === region).map(r => ms(r.created_at)).filter(Number.isFinite).sort((a, b) => b - a)[0];
  if (last != null && now - last < c.cooldownMs) {
    const wait = secs(last + c.cooldownMs - now);
    return fail(request, c, 429, 'region_cooldown', 'Tato oblast se nedávno aktualizovala.', { retry_after_s: wait, retry_at: new Date(now + wait * 1000).toISOString() }, { 'Retry-After': String(wait) });
  }

  // 3) Celkový strop za 24 hodin
  const times = runs.map(r => ms(r.created_at)).filter(t => Number.isFinite(t) && now - t < DAY_MS).sort((a, b) => a - b);
  if (times.length >= c.dailyLimit) {
    const wait = secs(times[times.length - c.dailyLimit] + DAY_MS - now);
    return fail(request, c, 429, 'daily_limit', 'Za posledních 24 hodin už bylo spuštěno maximum aktualizací.', { retry_after_s: wait, retry_at: new Date(now + wait * 1000).toISOString() }, { 'Retry-After': String(wait) });
  }

  // 4) Spuštění workflow
  let r;
  try {
    r = await gh(env, `/repos/${c.repo}/actions/workflows/${encodeURIComponent(c.workflow)}/dispatches`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ref: c.ref, inputs: { location: region } }),
    });
  } catch (e) {
    console.error('Spuštění workflow selhalo:', e.message);
    return fail(request, c, 502, 'github_error', 'Aktualizaci se nepodařilo spustit. Zkuste to za chvíli.');
  }
  if (!r.ok) {
    console.error('Spuštění workflow: GitHub vrátil', r.status);
    return fail(request, c, 502, 'github_error', 'Aktualizaci se nepodařilo spustit. Zkuste to za chvíli.', { github_status: r.status });
  }
  mem.lastDispatch = { region, at: now };
  mem.runs = null;                          // další /status si vyžádá čerstvá data
  return json(request, c, 202, { ok: true, region, dispatched_at: new Date(now).toISOString(), message: 'Aktualizace byla spuštěna.' });
}

/* ---------- GET /status ---------- */
async function handleStatus(request, env, c, url) {
  const region = norm(url.searchParams.get('region')).slice(0, 80);
  const sinceRaw = url.searchParams.get('since');
  const since = sinceRaw ? ms(sinceRaw) : null;
  if (sinceRaw && !Number.isFinite(since)) return fail(request, c, 400, 'bad_since', 'Parametr since musí být datum ve formátu ISO 8601.');
  let runs;
  try { runs = await listRuns(env, c, { fresh: false }); } catch (e) {
    console.error('Seznam běhů selhal:', e.message);
    return fail(request, c, 502, 'github_error', 'Stav aktualizace se nepodařilo zjistit.', { github_status: e.githubStatus || null });
  }
  const active = runs.find(r => ACTIVE.has(r.status));
  let mine = runs;
  if (region) mine = mine.filter(r => regionOf(r) === region);
  if (since != null) mine = mine.filter(r => ms(r.created_at) >= since - SINCE_TOLERANCE_MS);
  const run = mine[0] || null;
  const state = run ? stateOf(run) : since != null ? 'pending' : 'none';
  return json(request, c, 200, { ok: true, state, run: brief(run), active: active ? brief(active) : null, now: new Date().toISOString() });
}

/* ---------- vstup ---------- */
export async function handle(request, env) {
  const c = cfg(env);
  const url = new URL(request.url);
  const path = url.pathname.replace(/\/+$/, '') || '/';

  if (request.method === 'OPTIONS') {
    if (!c.origin || request.headers.get('Origin') !== c.origin) return new Response(null, { status: 403 });
    return new Response(null, { status: 204, headers: corsHeaders(request, c) });
  }
  if (path !== '/run' && path !== '/status') return fail(request, c, 404, 'not_found', 'Neznámá adresa.');
  const method = path === '/run' ? 'POST' : 'GET';
  if (request.method !== method && !(method === 'GET' && request.method === 'HEAD')) {
    return fail(request, c, 405, 'method_not_allowed', 'Nepovolená metoda.', {}, { 'Allow': method });
  }
  if (!env.GH_TOKEN || !c.repo || !c.workflow || !c.origin || !c.mapUrl) {
    console.error('Worker není správně nastaven (chybí GH_TOKEN nebo některá proměnná).');
    return fail(request, c, 500, 'misconfigured', 'Služba není správně nastavena.');
  }
  return path === '/run' ? handleRun(request, env, c) : handleStatus(request, env, c, url);
}

export default { fetch: (request, env) => handle(request, env) };
