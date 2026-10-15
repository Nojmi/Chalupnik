/* Chalupník – Cloudflare Worker s cache fotek.
 *
 * GET /img?u=<adresa fotky>   vrátí fotku z jednoho ze tří povolených portálů
 *
 * Cíl: portály zatěžovat co nejméně. Fotka se z portálu stáhne jednou, dál ji drží
 * cache Cloudflare (30 dní) a prohlížeč návštěvníka (30 dní). Chybové odpovědi se
 * drží v cache 10 minut, aby se na rozbité fotky portál nedotazoval pořád dokola.
 *
 * Cache API (caches.default) se záměrně nepoužívá: podle dokumentace Cloudflare funguje
 * jen na vlastní doméně, ne na *.workers.dev. Místo toho se cachuje samotný fetch
 * (volby cf.cacheEverything + cf.cacheTtlByStatus), což nevyžaduje doménu.
 *
 * Konfigurace (wrangler.toml [vars]): ALLOWED_HOSTS, CACHE_TTL_DAYS, NEG_TTL_MIN, MAX_MB,
 * volitelně UPSTREAM_UA. Žádná tajemství.
 */

const DAY = 24 * 60 * 60;
const MAX_REDIRECTS = 3;
const IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/avif']);   // SVG záměrně ne
const TRANSIENT_TTL = 60;                 // jak dlouho si prohlížeč pamatuje chvilkovou chybu (5xx, výpadek)
const inflight = new Map();               // souběžné dotazy na stejnou fotku sdílejí jeden dotaz na portál
export function resetState() { inflight.clear(); }

const num = (v, def) => { const n = Number(v); return Number.isFinite(n) && n > 0 ? n : def; };
const cfg = env => ({
  hosts: new Set(String(env.ALLOWED_HOSTS || '').split(',').map(s => s.trim().toLowerCase()).filter(Boolean)),
  ttl: Math.round(num(env.CACHE_TTL_DAYS, 30) * DAY),
  negTtl: Math.round(num(env.NEG_TTL_MIN, 10) * 60),
  maxBytes: Math.round(num(env.MAX_MB, 6) * 1024 * 1024),
  ua: env.UPSTREAM_UA || 'Chalupnik/1.0 (+https://nojmi.github.io/Chalupnik/)',
});

// Z adresy udělá povolený cíl (vždy https, bez přihlašovacích údajů a portu) nebo null.
export function parseTarget(raw, hosts) {
  let u;
  try { u = new URL(String(raw)); } catch { return null; }
  if (u.protocol !== 'https:' && u.protocol !== 'http:') return null;
  if (u.username || u.password) return null;
  if (u.port && u.port !== '80' && u.port !== '443') return null;
  u.protocol = 'https:'; u.port = ''; u.hash = '';
  return hosts.has(u.hostname.toLowerCase()) ? u : null;
}

const headersFor = (extra = {}) => ({
  'X-Content-Type-Options': 'nosniff',
  'Content-Security-Policy': "default-src 'none'",
  'Cross-Origin-Resource-Policy': 'cross-origin',
  ...extra,
});
function jsonError(status, error, message) {
  return new Response(JSON.stringify({ ok: false, error, message }), {
    status, headers: headersFor({ 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' }),
  });
}

// Jeden dotaz na portál (se sledováním přesměrování, jen na povolené hosty).
async function fromUpstream(target, c) {
  let url = target;
  for (let hop = 0; hop <= MAX_REDIRECTS; hop++) {
    let res;
    try {
      res = await fetch(url.href, {
        method: 'GET', redirect: 'manual',
        headers: { 'User-Agent': c.ua, 'Accept': 'image/avif,image/webp,image/*;q=0.8' },   // záměrně bez Refereru
        cf: { cacheEverything: true, cacheTtlByStatus: { '200-299': c.ttl, '400-499': c.negTtl, '500-599': 0 } },
      });
    } catch (e) {
      return { kind: 'bad', reason: 'network' };
    }
    if (res.status >= 300 && res.status < 400) {
      const next = parseTarget(new URL(res.headers.get('Location') || '', url).href, c.hosts);
      if (!next) return { kind: 'bad', reason: 'redirect' };
      url = next; continue;
    }
    if (res.status === 404 || res.status === 410) return { kind: 'gone' };
    if (res.status !== 200) return { kind: 'bad', reason: `status ${res.status}` };
    const type = (res.headers.get('Content-Type') || '').split(';')[0].trim().toLowerCase();
    if (!IMAGE_TYPES.has(type)) return { kind: 'bad', reason: 'type' };
    const declared = Number(res.headers.get('Content-Length'));
    if (Number.isFinite(declared) && declared > c.maxBytes) return { kind: 'bad', reason: 'size' };
    const buf = await res.arrayBuffer();
    if (buf.byteLength > c.maxBytes || buf.byteLength === 0) return { kind: 'bad', reason: 'size' };
    return { kind: 'ok', type, buf, cache: res.headers.get('cf-cache-status') || 'none' };
  }
  return { kind: 'bad', reason: 'redirect' };
}

function shared(target, c) {
  const key = target.href;
  let p = inflight.get(key);
  if (!p) { p = fromUpstream(target, c).finally(() => inflight.delete(key)); inflight.set(key, p); }
  return p;
}

function respond(r, c, head) {
  if (r.kind === 'ok') {
    return new Response(head ? null : r.buf, {
      status: 200,
      headers: headersFor({ 'Content-Type': r.type, 'Content-Length': String(r.buf.byteLength), 'Cache-Control': `public, max-age=${c.ttl}, immutable`, 'X-Upstream-Cache': r.cache }),
    });
  }
  const gone = r.kind === 'gone';
  return new Response(null, {
    status: gone ? 404 : 502,
    headers: headersFor({ 'Cache-Control': `public, max-age=${gone ? c.negTtl : TRANSIENT_TTL}`, 'X-Upstream-Error': gone ? 'gone' : r.reason }),
  });
}

export async function handle(request, env) {
  const c = cfg(env);
  const url = new URL(request.url);
  if (url.pathname.replace(/\/+$/, '') !== '/img') return jsonError(404, 'not_found', 'Neznámá adresa.');
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    const res = jsonError(405, 'method_not_allowed', 'Nepovolená metoda.'); res.headers.set('Allow', 'GET, HEAD'); return res;
  }
  if (!c.hosts.size) { console.error('ALLOWED_HOSTS není nastaveno.'); return jsonError(500, 'misconfigured', 'Služba není správně nastavena.'); }
  const raw = url.searchParams.get('u');
  if (!raw || raw.length > 2000) return jsonError(400, 'bad_url', 'Chybí adresa fotky (parametr u).');
  const target = parseTarget(raw, c.hosts);
  if (!target) return jsonError(400, 'host_not_allowed', 'Tuto adresu nelze načíst.');
  return respond(await shared(target, c), c, request.method === 'HEAD');
}

export default { fetch: (request, env) => handle(request, env) };
