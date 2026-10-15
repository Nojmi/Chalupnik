#!/usr/bin/env node
/* Změří na vzorku fotek z docs/data, kolik jich portály vrací bez chyby a jak jsou velké.
 *
 *   node scripts/measure.mjs                       # přímo proti portálům (vzorek 200 fotek, nenáročně: 3 souběžně, pauza 300 ms)
 *   node scripts/measure.mjs --worker https://chalupnik-img.<poddoména>.workers.dev
 *                                                  # přes Worker, dvakrát: podruhé by měla přijít cache (HIT)
 *
 * Volby: --n 200  --delay 300  --concurrency 3  --data ../docs/data
 * Vzorek je rovnoměrně rozdělený mezi portály (ne podle počtu nabídek), aby bylo vidět každý zvlášť.
 * Spouštějte u sebe: z prostředí, kde pracuje Claude, se na portály nedostane.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const UA = 'Chalupnik/1.0 (+https://nojmi.github.io/Chalupnik/)';
const SKIP = new Set(['index.json', 'mapa-cr.json', 'duplicity.json']);

export function loadUrls(dir) {
  const out = [];
  for (const f of fs.readdirSync(dir)) {
    if (!f.endsWith('.json') || SKIP.has(f)) continue;
    for (const l of JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8')).listings || []) {
      if (/^https?:\/\//.test(l.image_url || '')) out.push(l.image_url);
    }
  }
  return out;
}

// Rovnoměrně mezi hosty, náhodně uvnitř hostu, bez duplicit.
export function pickSample(urls, n, rng = Math.random) {
  const by = new Map();
  for (const u of new Set(urls)) {
    const h = new URL(u).hostname;
    if (!by.has(h)) by.set(h, []);
    by.get(h).push(u);
  }
  const hosts = [...by.keys()].sort();
  if (!hosts.length) return [];
  const base = Math.floor(n / hosts.length), rem = n % hosts.length, out = [];
  hosts.forEach((h, i) => {
    const arr = by.get(h);
    for (let j = arr.length - 1; j > 0; j--) { const k = Math.floor(rng() * (j + 1)); [arr[j], arr[k]] = [arr[k], arr[j]]; }
    out.push(...arr.slice(0, base + (i < rem ? 1 : 0)));
  });
  return out;
}

const pct = (sorted, p) => sorted.length ? sorted[Math.min(sorted.length - 1, Math.floor(p * sorted.length))] : 0;
export function summarize(rows) {
  const by = new Map();
  for (const r of rows) { const h = new URL(r.url).hostname; if (!by.has(h)) by.set(h, []); by.get(h).push(r); }
  return [...by.entries()].sort().map(([host, rs]) => {
    const ok = rs.filter(r => r.status === 200 && /^image\//.test(r.type));
    const ms = rs.map(r => r.ms).sort((a, b) => a - b), kb = ok.map(r => r.bytes / 1024);
    const errors = {};
    for (const r of rs) if (!ok.includes(r)) { const k = r.error || String(r.status); errors[k] = (errors[k] || 0) + 1; }
    return {
      host, n: rs.length, ok: ok.length, okPct: rs.length ? Math.round(100 * ok.length / rs.length) : 0, errors,
      avgKB: kb.length ? Math.round(kb.reduce((a, b) => a + b, 0) / kb.length) : 0,
      maxKB: kb.length ? Math.round(Math.max(...kb)) : 0,
      p50: pct(ms, 0.5), p95: pct(ms, 0.95), hits: rs.filter(r => r.cache === 'HIT').length,
    };
  });
}

async function probe(url, worker) {
  const target = worker ? `${worker}/img?u=${encodeURIComponent(url)}` : url;
  const t0 = performance.now();
  try {
    const r = await fetch(target, { headers: { 'User-Agent': UA }, redirect: 'follow' });
    const buf = await r.arrayBuffer();
    return {
      url, status: r.status, type: (r.headers.get('content-type') || '').split(';')[0], bytes: buf.byteLength,
      ms: Math.round(performance.now() - t0), cache: r.headers.get('x-upstream-cache') || r.headers.get('cf-cache-status') || '',
      error: r.headers.get('x-upstream-error') || '',
    };
  } catch (e) {
    return { url, status: 0, type: '', bytes: 0, ms: Math.round(performance.now() - t0), cache: '', error: String(e.message || e) };
  }
}
async function run(urls, worker, concurrency, delay) {
  const rows = new Array(urls.length); let next = 0, done = 0;
  const lane = async () => {
    while (next < urls.length) {
      const i = next++;
      rows[i] = await probe(urls[i], worker);
      if (++done % 25 === 0) process.stderr.write(`  ${done}/${urls.length}\n`);
      await new Promise(r => setTimeout(r, delay));
    }
  };
  await Promise.all(Array.from({ length: concurrency }, lane));
  return rows;
}

function table(sum, withCache) {
  const head = ['Host', 'Vzorek', 'V pořádku', 'Chyby', 'Ø KB', 'Max KB', 'p50 ms', 'p95 ms', ...(withCache ? ['HIT'] : [])];
  const lines = [`| ${head.join(' | ')} |`, `|${head.map(() => '---').join('|')}|`];
  for (const s of sum) {
    const errs = Object.entries(s.errors).map(([k, v]) => `${k}×${v}`).join(', ') || '–';
    lines.push(`| ${[s.host, s.n, `${s.ok} (${s.okPct} %)`, errs, s.avgKB, s.maxKB, s.p50, s.p95, ...(withCache ? [s.hits] : [])].join(' | ')} |`);
  }
  return lines.join('\n');
}

async function main() {
  const a = process.argv.slice(2), opt = (k, d) => { const i = a.indexOf(`--${k}`); return i >= 0 ? a[i + 1] : d; };
  const n = Number(opt('n', 200)), delay = Number(opt('delay', 300)), conc = Number(opt('concurrency', 3));
  const worker = (opt('worker', '') || '').replace(/\/+$/, '');
  const dir = path.resolve(opt('data', path.join(HERE, '..', '..', 'docs', 'data')));
  const urls = pickSample(loadUrls(dir), n);
  if (!urls.length) { console.error(`V ${dir} nejsou žádné fotky.`); process.exit(1); }
  console.log(`Vzorek: ${urls.length} fotek, ${new Set(urls.map(u => new URL(u).hostname)).size} portály, ${worker ? `přes Worker ${worker}` : 'přímo z portálů'}\n`);
  const first = await run(urls, worker, conc, delay);
  console.log(worker ? '### První průchod (cache zatím prázdná)\n' : '### Výsledek\n');
  console.log(table(summarize(first), !!worker));
  if (worker) {
    const again = await run(urls.filter((_, i) => first[i].status === 200), worker, conc, delay);
    console.log('\n### Druhý průchod (fotky by měly přijít z cache)\n');
    console.log(table(summarize(again), true));
    const hit = again.filter(r => r.cache === 'HIT').length;
    console.log(`\nZ cache přišlo ${hit} z ${again.length} fotek (${again.length ? Math.round(100 * hit / again.length) : 0} %).`);
    if (again.length && hit / again.length < 0.5) console.log('Málo HIT: cache pravděpodobně na workers.dev nedrží. Viz README, část „Když cache nedrží“.');
  }
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
