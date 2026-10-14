/* Chalupník – nový web (varianta 1a „Nejdřív region"). Vanilla JS, bez build kroku.
   Stránka si nic nepamatuje: žádné localStorage, žádné parametry v URL. */
(() => {
'use strict';

const NB = ' ';
const PAGE = 24;                       // kolik karet se ukáže naráz
const FRESH_DAYS = 14, STALE_DAYS = 30;
const PORTALS = ['e-chalupy.cz', 'chata.cz', 'cs-chalupy.cz'];
const SRC = { 'e-chalupy.cz': 'e', 'chata.cz': 'chata', 'cs-chalupy.cz': 'cs' };
const PORTAL_COLOR = { e: 'var(--portal-e)', chata: 'var(--portal-chata)', cs: 'var(--portal-cs)' };
const ACC = { sumava: 'Šumavu', 'jizni-morava': 'Jižní Moravu', vysocina: 'Vysočinu' };
const GROUPS = [
  ['Vnitřní vybavení', ['sauna', 'společenská místnost', 'myčka nádobí', 'lednička', 'klimatizace', 'televize', 'wifi']],
  ['Venku a okolí', ['bazén', 'vířivka', 'krb', 'na samotě', 'u lesa', 'u vody', 'pískoviště', 'ohniště', 'gril']],
  ['Další', ['se psem', 'pro děti', 'parkování', 'lyžárna/kolárna', 'oplocení']],
];
const AMENITY_LABEL = { 'myčka nádobí': 'myčka', 'lyžárna/kolárna': 'lyžárna / kolárna' };      // zkrácený popisek čipu (v datech je celý název)
const amLabel = a => AMENITY_LABEL[a] || a;

const $app = document.getElementById('app');
const mq = window.matchMedia('(min-width: 900px)');
const S = {
  index: null, mapa: null,
  view: { t: 'intro' },              // intro | region(id) | kraj(id = název)
  tab: 'oblasti',
  load: 'nacita', err: '',
  items: [], cov: {}, meta: null,    // data právě otevřené oblasti
  f: freshFilters(), shown: PAGE,
  sheet: false, dlg: null, opener: null,
};
const cache = new Map();             // soubor -> pole nabídek

function freshFilters() {
  return { osobyOd: null, osobyDo: null, lozniceOd: null, lozniceDo: null, maxCena: null, jenCele: false, skrytApart: false, vybaveni: [] };
}

/* ---------- pomocné funkce ---------- */
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = n => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, NB);
const plural = (n, one, few, many) => n === 1 ? one : (n >= 2 && n <= 4 ? few : many);
const nabAcc = n => `${fmt(n)}${NB}${plural(n, 'nabídku', 'nabídky', 'nabídek')}`;
const nab = n => `${fmt(n)}${NB}${plural(n, 'nabídka', 'nabídky', 'nabídek')}`;
const day0 = d => new Date(d.getFullYear(), d.getMonth(), d.getDate());
function daysSince(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d)) return null;
  return Math.max(0, Math.round((day0(new Date()) - day0(d)) / 864e5));
}
const stav = d => d == null ? 'none' : d <= FRESH_DAYS ? 'fresh' : d <= STALE_DAYS ? 'aging' : 'stale';
const ago = d => d === 0 ? 'dnes' : d === 1 ? `před${NB}1${NB}dnem` : `před${NB}${d}${NB}dny`;
const LABEL = { fresh: 'čerstvé', aging: 'doporučujeme aktualizovat', stale: 'zastaralé, aktualizujte', none: 'zatím nestaženo' };
const ICON = { fresh: '✓', aging: '↻', stale: '!', none: '–' };
function freshPill(d, jenStari) {
  const st = stav(d);
  let text = jenStari && st !== 'none' ? '' : LABEL[st];
  if (st !== 'none') text = text ? `${text} · ${ago(d)}` : ago(d);
  return `<span class="fresh ${st}${jenStari ? ' jen' : ''}"><span class="ic" aria-hidden="true">${ICON[st]}</span><span>${esc(text)}</span></span>`;
}
const shortDate = iso => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || ''); return m ? `${+m[3]}.${NB}${+m[2]}.` : ''; };
function termText(t) {
  const a = t && /^(\d{4})-(\d{2})-(\d{2})/.exec(t.from || ''), b = t && /^(\d{4})-(\d{2})-(\d{2})/.exec(t.to || '');
  if (!a || !b) return '';
  const days = Math.round((Date.UTC(+b[1], +b[2] - 1, +b[3]) - Date.UTC(+a[1], +a[2] - 1, +a[3])) / 864e5);
  const left = +a[2] === +b[2] ? `${+a[3]}.` : `${+a[3]}.${NB}${+a[2]}.`;
  return `${days === 7 ? 'týden' : 'pobyt'} ${left}–${+b[3]}.${NB}${+b[2]}.`;
}

/* ---------- data ---------- */
const getJSON = async url => {
  const r = await fetch(url, { cache: 'no-cache' });
  if (!r.ok) throw new Error(`${url} neodpověděl (${r.status})`);
  return r.json();
};
const regionInfo = id => S.index.regions.find(r => r.region === id);
const oblast = id => S.mapa.oblasti.find(o => o.id === id);
const withData = () => S.index.regions.filter(r => r.listing_count > 0);

function prep(l) {
  const loc = l.location || '', i = loc.lastIndexOf(', ');
  const obec = i > 0 ? loc.slice(0, i) : loc, reg = i > 0 ? loc.slice(i + 2) : '';
  l._place = [obec, l.okres ? `okres ${l.okres}` : '', reg].filter(Boolean).join(' · ');
  l._src = SRC[l.source] || 'e';
  l._ent = l.entire_property === true ? 'ano' : l.entire_property === false ? 'ne' : 'neznámo';
  l._avail = l.seen_in_last_run !== false;
  return l;
}
async function loadFile(file) {
  if (!cache.has(file)) {
    const d = await getJSON(`data/${file}`);
    cache.set(file, (d.listings || []).map(prep));
  }
  return cache.get(file);
}
function coverage(items) {                       // jak často který portál uvádí které vybavení
  const tot = {}, has = {};
  items.forEach(l => {
    tot[l.source] = (tot[l.source] || 0) + 1;
    (l.amenities || []).forEach(a => { const k = `${l.source}|${a}`; has[k] = (has[k] || 0) + 1; });
  });
  return { tot, has };
}
function oldestDays(info) {
  const su = info.sources_updated || {};
  const days = PORTALS.map(p => daysSince(su[p])).filter(d => d != null);
  if (days.length) return Math.max(...days);
  return daysSince(info.last_updated);
}
function agesFor(info) {
  const su = info.sources_updated || {};
  return PORTALS.map(p => ({ name: p, d: daysSince(su[p]) }));
}

// Anonymní statistika (GoatCounter, bez cookies): počítá se, které oblasti a kraje se otevírají.
function track(path, title) {
  try { if (window.goatcounter && window.goatcounter.count) window.goatcounter.count({ path, title, event: true }); } catch (e) { /* statistika nikdy nesmí rozbít web */ }
}
async function open(view) {
  if (view.t === 'region') track('oblast/' + view.id, 'Oblast: ' + (oblast(view.id)?.name || view.id));
  else if (view.t === 'kraj') track('kraj/' + view.id, 'Kraj: ' + view.id);
  S.view = view; S.f = freshFilters(); S.shown = PAGE; S.sheet = false; S.dlg = null;
  S.load = 'nacita'; S.err = ''; S.items = []; S.meta = null;
  render(); window.scrollTo(0, 0);
  try {
    let infos, items;
    if (view.t === 'region') {
      const info = regionInfo(view.id);
      if (!info || !info.listing_count) { S.load = 'bezdat'; S.meta = { title: oblast(view.id)?.name || view.id, infos: [], region: view.id }; return render(); }
      infos = [info]; items = await loadFile(info.file);
    } else {
      infos = withData().filter(r => (r.kraje || {})[view.id] > 0);
      const lists = await Promise.all(infos.map(r => loadFile(r.file)));
      const seen = new Map();
      lists.flat().forEach(l => { if (l.kraj === view.id && !seen.has(l.id)) seen.set(l.id, l); });
      items = [...seen.values()];
    }
    S.items = items; S.cov = coverage(items);
    const days = infos.map(oldestDays).filter(d => d != null);
    S.meta = {
      title: view.t === 'region' ? infos[0].region_label : krajTitle(view.id),
      infos, region: infos.length === 1 ? infos[0].region : null,
      oldest: days.length ? Math.max(...days) : null,
      ages: view.t === 'region' ? agesFor(infos[0]) : mergeAges(infos),
    };
    S.load = 'ok';
  } catch (e) {
    S.load = 'chyba'; S.err = String(e.message || e);
  }
  render();
}
function mergeAges(infos) {
  return PORTALS.map(p => {
    const ds = infos.map(i => daysSince((i.sources_updated || {})[p])).filter(d => d != null);
    return { name: p, d: ds.length ? Math.max(...ds) : null };
  });
}

/* ---------- filtrování: splňuje / nesplňuje / neznámo ---------- */
function judge(l) {
  const f = S.f, unk = [];
  const rng = (v, lo, hi, what) => {
    if (lo == null && hi == null) return true;
    if (v == null) { unk.push(what); return true; }
    return !((lo != null && v < lo) || (hi != null && v > hi));
  };
  if (!rng(l.capacity, f.osobyOd, f.osobyDo, 'počet osob')) return null;
  if (!rng(l.bedrooms, f.lozniceOd, f.lozniceDo, 'počet ložnic')) return null;
  if (f.maxCena != null) {
    if (l.price_per_night_from == null) unk.push('cenu');
    else if (l.price_per_night_from > f.maxCena) return null;
  }
  if (f.skrytApart && l.likely_apartment === true) return null;
  if (f.jenCele) {
    if (l._ent === 'ne') return null;
    if (l._ent === 'neznámo') unk.push('zda jde o celý objekt');
  }
  for (const a of f.vybaveni) {
    if ((l.amenities || []).includes(a)) continue;
    const tot = S.cov.tot[l.source] || 0, has = S.cov.has[`${l.source}|${a}`] || 0;
    if (tot >= 10 && has / tot < 0.02) unk.push(`vybavení „${amLabel(a)}"`);   // portál tento údaj prakticky neuvádí
    else return null;
  }
  return unk;
}
function compute() {
  const all = [];
  S.items.forEach(l => {
    const j = judge(l);
    if (j === null) return;
    l._unk = j;                       // údaje, které portál neuvádí a podle kterých filtrujeme (jen poznámka na kartě)
    all.push(l);
  });
  const weak = l => (l.likely_apartment === true ? 1 : 0) + (l._ent === 'ne' ? 1 : 0);   // pravděpodobné apartmány až za celé objekty
  all.sort((a, b) => (b._avail - a._avail) || (weak(a) - weak(b)) || ((a.price_per_night_from ?? 1e12) - (b.price_per_night_from ?? 1e12)) || (a.id < b.id ? -1 : 1));
  return { all, shown: all.length, total: S.items.length };
}
function chipList() {
  const f = S.f, c = [];
  const range = (lo, hi, one, many, key) => {
    if (lo == null && hi == null) return;
    const w = n => plural(n, one, many, many);
    const t = lo != null && hi != null ? (lo === hi ? `${lo} ${w(lo)}` : `${lo}–${hi} ${many}`) : lo != null ? `od ${lo} ${lo === 1 ? one.replace(/a$/, 'y').replace(/e$/, 'e') : many}` : `do ${hi} ${many}`;
    c.push({ key, text: t });
  };
  range(f.osobyOd, f.osobyDo, 'osoba', 'osob', 'osoby');
  range(f.lozniceOd, f.lozniceDo, 'ložnice', 'ložnic', 'lozince');
  if (f.maxCena != null) c.push({ key: 'cena', text: `do ${fmt(f.maxCena)}${NB}Kč/noc` });
  if (f.jenCele) c.push({ key: 'cele', text: 'jen celé objekty' });
  if (f.skrytApart) c.push({ key: 'apart', text: 'bez apartmánů' });
  f.vybaveni.forEach(a => c.push({ key: 'am:' + a, text: amLabel(a) }));
  return c;
}
function dropFilter(key) {
  const f = S.f;
  if (key === 'osoby') f.osobyOd = f.osobyDo = null;
  else if (key === 'lozince') f.lozniceOd = f.lozniceDo = null;
  else if (key === 'cena') f.maxCena = null;
  else if (key === 'cele') f.jenCele = false;
  else if (key === 'apart') f.skrytApart = false;
  else if (key.startsWith('am:')) f.vybaveni = f.vybaveni.filter(a => a !== key.slice(3));
}

/* ---------- mapa (inline SVG) ---------- */
let mapUid = 0;
function mapSVG(mode, compact) {
  const d = S.mapa, uid = 'p' + (++mapUid);
  const regs = withData();
  const countO = {}; regs.forEach(r => { countO[r.region] = r.listing_count; });
  const countK = {}; regs.forEach(r => Object.entries(r.kraje || {}).forEach(([k, n]) => { countK[k] = (countK[k] || 0) + n; }));
  const halo = `paint-order:stroke;stroke:var(--panel);stroke-width:${compact ? 5 : 4};stroke-linejoin:round`;
  const labelPos = { 'Středočeský': [262, 186], 'Olomoucký': [438, 198], 'Moravskoslezský': [545, 176] };
  let o = `<defs><pattern id="${uid}" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="7" height="7" style="fill:var(--mapa-srafa-podklad)"/><line x1="0" y1="0" x2="0" y2="7" stroke-width="2" style="stroke:var(--mapa-srafa-cara)"/></pattern></defs>`;
  d.kraje.forEach(k => {
    const has = countK[k.short] != null;
    const fill = mode === 'oblasti' ? 'var(--mapa-zeme)' : has ? 'var(--mapa-kraj-data)' : `url(#${uid})`;
    const pick = mode === 'kraje' && has ? ` data-pick="k:${esc(k.short)}"` : '';
    o += `<path d="${k.d}"${pick} stroke-width="1" stroke-linejoin="round" style="fill:${fill};stroke:var(--mapa-hranice)"/>`;
  });
  if (mode === 'kraje') {
    d.kraje.forEach(k => {
      const [x, y] = labelPos[k.short] || [k.lx, k.ly];
      const c = countK[k.short];
      const pick = c != null ? ` data-pick="k:${esc(k.short)}"` : '';
      if (compact) {
        if (c == null) return;
        o += `<text x="${x}" y="${y + 7}" text-anchor="middle"${pick} style="font:700 21px Public Sans,sans-serif;fill:var(--text);${halo}">${fmt(c)}</text>`;
        return;
      }
      if (k.short === 'Praha') return;
      o += `<text x="${x}" y="${y - 2}" text-anchor="middle"${pick} style="font:600 12.5px Public Sans,sans-serif;fill:var(--text);${halo}">${esc(k.short)}</text>`;
      o += `<text x="${x}" y="${y + 13}" text-anchor="middle"${pick} style="font:${c != null ? 700 : 500} 11.5px Public Sans,sans-serif;fill:${c != null ? 'var(--cerstve-text)' : 'var(--text-2)'};${halo}">${c != null ? nab(c) : 'nestaženo'}</text>`;
    });
  } else {
    const anchor = { 'jizerske-hory': 'l', 'cesky-raj': 'l', sumava: 'l', beskydy: 'l', 'krusne-hory': 'r' };
    if (compact) Object.assign(anchor, { 'krusne-hory': 't', 'orlicke-hory': 'l', 'jizerske-hory': 't', 'ceske-svycarsko': 'l', 'stredni-cechy': 'r' });
    else Object.assign(anchor, { 'cesky-raj': 'r', vysocina: 'l', 'jizerske-hory': 'r', 'ceske-svycarsko': 'l', 'stredni-cechy': 'r' });   // desktop: štítky se nesmí potkat (Krušné hory × Český ráj, Vysočina × Beskydy)
    const fs = compact ? 17 : 13.5;
    d.oblasti.forEach(ob => {
      const c = countO[ob.id], has = c != null;
      const pick = ` data-pick="o:${ob.id}"`;
      o += `<circle cx="${ob.x}" cy="${ob.y}" r="${compact ? 20 : 15}"${pick} style="fill:transparent"/>`;
      o += `<circle cx="${ob.x}" cy="${ob.y}" r="${has ? (compact ? 12 : 9) : (compact ? 8 : 6)}"${pick} stroke-width="${has ? 2.5 : 2}" style="fill:${has ? 'var(--zelena)' : 'var(--panel)'};stroke:${has ? 'var(--panel)' : 'var(--placeholder)'}"/>`;
      const a = anchor[ob.id] || 'r', off = compact ? 18 : 14;
      const x = a === 'l' ? ob.x - off : a === 'r' ? ob.x + off : ob.x;
      const y = a === 't' ? ob.y - off + 2 : ob.y + fs * 0.35;
      const label = has && !compact ? `${ob.name} · ${fmt(c)}` : ob.name;
      o += `<text x="${x}" y="${y}" text-anchor="${a === 'l' ? 'end' : a === 'r' ? 'start' : 'middle'}"${pick} style="font:${has ? 700 : 500} ${fs}px Public Sans,sans-serif;fill:${has ? 'var(--text)' : 'var(--text-2)'};${halo}">${esc(label)}</text>`;
    });
  }
  return `<svg viewBox="0 0 ${d.w} ${d.h}" role="img" aria-label="${mode === 'kraje' ? 'Mapa krajů České republiky' : 'Mapa oblíbených oblastí'}">${o}</svg>`;
}
const legendHTML = `<div class="legend"><span><i class="dot"></i>nabídky staženy</span><span><i class="dot empty"></i>zatím nestaženo</span></div>`;
const legendKraje = `<div class="legend"><span><i class="dot"></i>kraj s nabídkami</span><span><i class="dot empty"></i>zatím nestaženo (šrafováno)</span></div>`;

/* ---------- úvod ---------- */
const header = back => `<header class="hdr"><button class="logo" data-act="home" aria-label="Chalupník – úvod"><i></i><b>Chalupník</b></button>
  <span class="hdr-sub">Chaty, chalupy a roubenky k pronájmu na jednom místě</span>
  ${back ? `<button class="back" data-act="home"><span aria-hidden="true">‹</span> <span class="t-m">Oblasti</span><span class="t-d">Všechny oblasti</span></button>` : ''}</header>`;

function oblastItem(info, ob) {
  if (info && info.listing_count) {
    return `<button class="ritem" data-act="open-region" data-id="${esc(ob.id)}"><span class="t"><span class="n">${esc(ob.name)}</span><span class="s">${nab(info.listing_count)}</span>${freshPill(oldestDays(info))}</span><span class="arrow" aria-hidden="true">›</span></button>`;
  }
  return `<button class="ritem none" data-act="open-region" data-id="${esc(ob.id)}"><span class="t"><span class="n">${esc(ob.name)}</span></span>${freshPill(null)}</button>`;
}
function krajeList() {
  const regs = withData(), rows = [];
  const count = {}, from = {};
  regs.forEach(r => Object.entries(r.kraje || {}).forEach(([k, n]) => { count[k] = (count[k] || 0) + n; (from[k] = from[k] || []).push(r.region_label); }));
  S.mapa.kraje.filter(k => count[k.short]).sort((a, b) => count[b.short] - count[a.short]).forEach(k => {
    rows.push(`<button class="ritem" data-act="open-kraj" data-id="${esc(k.short)}"><span class="t"><span class="n">${esc(k.short)}</span><span class="s">z oblasti ${esc(from[k.short].join(', '))}</span></span><span class="cnt num">${fmt(count[k.short])}</span><span class="arrow" aria-hidden="true">›</span></button>`);
  });
  const rest = S.mapa.kraje.length - rows.length;
  if (rest > 0) rows.push(`<div class="ritem none" role="note"><span class="t"><span class="n">Ostatní kraje (${rest})</span><span class="s">zatím nestaženo</span></span></div>`);
  return rows.join('');
}
function introHTML() {
  const regs = withData();
  const desk = mq.matches;
  const byId = Object.fromEntries(S.index.regions.map(r => [r.region, r]));
  const have = S.mapa.oblasti.filter(o => byId[o.id]?.listing_count), none = S.mapa.oblasti.filter(o => !byId[o.id]?.listing_count);
  let body;
  if (desk) {
    body = `<div class="maps2">
      <section class="mapcard" aria-labelledby="m1"><h2 id="m1">Oblíbené oblasti</h2><div class="mapbox">${mapSVG('oblasti', false)}</div>${legendHTML}</section>
      <section class="mapcard" aria-labelledby="m2"><h2 id="m2">Podle krajů</h2><div class="mapbox">${mapSVG('kraje', false)}</div>${legendKraje}</section></div>
      <h2 class="sect">Všechny oblasti</h2>
      <div class="rgrid">${[...have, ...none].map(o => oblastItem(byId[o.id], o)).join('')}</div>`;
  } else {
    const kr = S.tab === 'kraje';
    body = `<div class="seg" role="group" aria-label="Způsob výběru"><button data-act="tab" data-id="oblasti" aria-pressed="${!kr}">Oblíbené oblasti</button><button data-act="tab" data-id="kraje" aria-pressed="${kr}">Podle krajů</button></div>
      <div class="mapcard"><div class="mapbox">${mapSVG(kr ? 'kraje' : 'oblasti', true)}</div>${kr ? legendKraje : legendHTML}</div>
      ${kr ? `<p class="note">Kraj ukazuje jen nabídky ze stažených oblastí.</p><div class="rlist">${krajeList()}</div>`
           : `${have.length ? `<h2 class="sect">S nabídkami</h2><div class="rlist">${have.map(o => oblastItem(byId[o.id], o)).join('')}</div>` : ''}
              ${none.length ? `<h2 class="sect">Zatím nestaženo</h2><div class="rlist">${none.map(o => oblastItem(byId[o.id], o)).join('')}</div>` : ''}`}`;
  }
  if (desk && regs.length === 0) body += '<p class="note">Zatím nejsou stažené žádné nabídky.</p>';
  return `${header(false)}<main class="intro wrap"><h1>Kam pojedete?</h1><p class="lead">Vyberte oblast. Ukážeme nabídky z e-chalupy.cz, chata.cz a cs-chalupy.cz najednou.</p>${body}</main>`;
}

/* ---------- karta nabídky ---------- */
function priceHTML(l) {
  const from = l.price_per_night_from, to = l.price_per_night_to;
  if (from == null) return `<div class="price"><div class="v none">cena neuvedena</div></div>`;
  let v;
  if (l.price_estimated) v = `cca ${fmt(from)}${NB}Kč/noc (odhad)`;
  else if (to != null && to !== from) v = `od ${fmt(from)} do ${fmt(to)}${NB}Kč/noc`;
  else if (to == null) v = `od ${fmt(from)}${NB}Kč/noc`;
  else v = `${fmt(from)}${NB}Kč/noc`;
  const meta = [l.price_as_of ? `k${NB}${shortDate(l.price_as_of)}` : '', termText(l.price_term), l.price_estimated ? 'přepočteno z ceny za osobu' : ''].filter(Boolean).join(' · ');
  return `<div class="price"><div class="v">${v}</div>${meta ? `<div class="m">${esc(meta)}</div>` : ''}${l.price_note ? `<div class="pn">${esc(l.price_note)}</div>` : ''}</div>`;
}
function unkText(r) {
  const zda = r.includes('zda jde o celý objekt'), parts = r.filter(x => x !== 'zda jde o celý objekt');
  if (!parts.length) return 'Portál neuvádí, zda jde o celý objekt.';
  return `Portál neuvádí ${parts.join(', ')}${zda ? ' ani to, zda jde o celý objekt' : ''}.`;
}
function cardHTML(l) {
  const cap = l.capacity != null ? `<span>${l.capacity} ${plural(l.capacity, 'osoba', 'osoby', 'osob')}</span>` : `<em>kapacita neuvedena</em>`;
  const bed = l.bedrooms != null ? `<span>${l.bedrooms} ${plural(l.bedrooms, 'ložnice', 'ložnice', 'ložnic')}</span>` : `<em>ložnice neuvedeny</em>`;
  const am = l.amenities || [], tags = am.slice(0, 6).map(a => `<span class="tag">${esc(amLabel(a))}</span>`).join('');
  const more = am.length > 6 ? `<span class="plus">+ ${am.length - 6} další</span>` : '';
  const url = /^https?:\/\//.test(l.url || '') ? l.url : '#';
  const img = /^https?:\/\//.test(l.image_url || '') ? `<img class="pimg" src="${esc(l.image_url)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer">` : '';
  return `<article class="card${l._avail ? '' : ' unavail'}">
    <div class="photo"><div class="ph"><span>fotka objektu</span></div>${img}<span class="src ${l._src}">${esc(l.source)}</span>${l._avail ? '' : '<div class="gone"><i aria-hidden="true">?</i>možná už není k dispozici</div>'}</div>
    <div class="cbody"><h3>${esc(l.title)}</h3><div class="place">${esc(l._place)}</div><div class="cap">${cap}${bed}</div>
    ${priceHTML(l)}${l._unk && l._unk.length ? `<div class="unk">${esc(unkText(l._unk))} Ověřte na portálu.</div>` : ''}${l.likely_apartment ? '<div class="warn"><span aria-hidden="true">⚠</span><span>možná jen apartmán, ne celá chalupa</span></div>' : ''}
    ${am.length ? `<div class="tags">${tags}${more}</div>` : ''}
    <a class="btn block" href="${esc(url)}" target="_blank" rel="noopener noreferrer">Zobrazit na portálu <span aria-hidden="true">↗</span></a></div></article>`;
}

/* ---------- výsledky ---------- */
function resultsHTML() {
  const c = compute(), chips = chipList(), m = S.meta;
  const where = S.view.t === 'region' ? `v ${esc(locative(m.title))}` : esc(krajWhere(S.view.id));
  const bar = `<div class="bar"><div class="sum"><b class="num" role="status">Zobrazeno ${fmt(c.shown)} z ${fmt(c.total)}</b><span>nabídek ${where}</span></div>
    <button class="fbtn" data-act="filters" aria-haspopup="dialog">Filtry ${chips.length ? `<span class="badge">${chips.length}</span>` : ''}</button></div>`;
  const cnt = {}; c.all.forEach(l => { cnt[l.source] = (cnt[l.source] || 0) + 1; });
  const pills = `<div class="pills">${PORTALS.map(p => `<span class="pill"><i style="background:${PORTAL_COLOR[SRC[p]]}"></i>${p} <b class="num">${fmt(cnt[p] || 0)}</b></span>`).join('')}</div>`;
  const chipsH = chips.length ? `<div class="chips">${chips.map(x => `<button class="chip" data-act="drop" data-id="${esc(x.key)}">${esc(x.text)} <span aria-hidden="true">×</span><span class="sr-only">zrušit filtr</span></button>`).join('')}</div>` : '';
  if (!c.shown) {
    return `${bar}${pills}<div class="state empty-box"><h2>Těmto filtrům neodpovídá žádná nabídka</h2><p>Zkuste některý filtr zrušit:</p>
      <div class="chips" style="padding:0">${chips.map(x => `<button class="chip" data-act="drop" data-id="${esc(x.key)}">${esc(x.text)} <span aria-hidden="true">×</span></button>`).join('')}</div>
      <div class="acts"><button class="btn solid" data-act="clear">Zrušit všechny filtry</button></div></div>`;
  }
  let html = `<div class="cards">${c.all.slice(0, S.shown).map(cardHTML).join('')}</div>`;
  const rest = c.shown - S.shown;
  if (rest > 0) html += `<div class="more"><button class="btn big" data-act="more">Zobrazit dalších ${Math.min(PAGE, rest)} <span class="nowrap">(zbývá ${fmt(rest)})</span></button></div>`;
  return bar + pills + chipsH + html;
}
function krajTitle(k) { return k === 'Praha' ? 'Hlavní město Praha' : k === 'Vysočina' ? 'Kraj Vysočina' : `${k} kraj`; }
function krajWhere(k) { return k === 'Praha' ? 'v Praze' : k === 'Vysočina' ? 'na Vysočině' : `v ${k.replace(/ý$/, 'ém')} kraji`; }
function locative(name) {
  const m = { 'Krkonoše': 'Krkonoších', 'Šumava': 'Šumavě', 'Jeseníky': 'Jeseníkách', 'Beskydy': 'Beskydech', 'Jižní Morava': 'Jižní Moravě', 'Český ráj': 'Českém ráji', 'Jizerské hory': 'Jizerských horách', 'Jižní Čechy': 'Jižních Čechách', 'Krušné hory': 'Krušných horách', 'Vysočina': 'Vysočině', 'Orlické hory': 'Orlických horách' };
  return m[name] || name;
}
function updateBtn(region) {
  if (!region) return '';
  return `<button class="btn big" data-act="update" data-id="${esc(region)}"><span aria-hidden="true">↻</span><span class="two"><span>Aktualizovat region</span><small>trvá několik minut</small></span></button>`;
}
function regionHTML() {
  const m = S.meta;
  if (S.load === 'nacita') {
    return `${header(true)}<main class="wrap"><div class="state"><h2 role="status">Načítám nabídky…</h2><div class="loadbar"><i></i></div></div><div class="skels" style="padding:0 16px 40px"><div class="skel"></div><div class="skel"></div></div></main>`;
  }
  if (S.load === 'chyba') {
    return `${header(true)}<main class="wrap"><div class="state"><div class="ic" aria-hidden="true">!</div><h2>Nabídky se nepodařilo načíst</h2>
      <p>Zkontrolujte připojení k internetu a zkuste to znovu. Pokud se chyba opakuje, pomůže oblast aktualizovat.</p>
      <div class="acts"><button class="btn solid" data-act="retry">Zkusit znovu</button><button class="btn" data-act="home">Zpět na oblasti</button></div><code>${esc(S.err)}</code></div></main>`;
  }
  if (S.load === 'bezdat') {
    return `${header(true)}<main class="wrap"><div class="state"><h1 style="font:600 32px/1.1 var(--serif)">${esc(m.title)}</h1>${freshPill(null)}
      <p>Pro tuto oblast zatím nemáme žádné nabídky. Můžete je stáhnout ze všech tří portálů.</p>
      <button class="btn solid big" data-act="update" data-id="${esc(m.region)}"><span aria-hidden="true">↓</span><span class="two"><span>Stáhnout nabídky</span><small style="color:inherit;opacity:.8">trvá několik minut</small></span></button>
      <button class="back" data-act="home">Zatím vybrat jinou oblast</button></div></main>`;
  }
  const ages = `<div class="ages">${m.ages.map(a => `<div><span>${a.name}</span>${freshPill(a.d, true)}<b class="ago">${a.d == null ? 'nestaženo' : ago(a.d)}</b></div>`).join('')}</div>`;
  return `${header(true)}<main class="wrap"><section class="res-head"><div class="tt"><h1>${esc(m.title)}</h1><div class="line">${freshPill(m.oldest)}${ages}</div></div>${updateBtn(m.region)}</section>
    <div class="layout"><aside class="side" aria-label="Filtry"><div id="fp-side">${mq.matches ? panelHTML(compute().shown) : ''}</div></aside><div class="main" id="results">${resultsHTML()}</div></div></main>`;
}

/* ---------- panel filtrů ---------- */
function stepper(key, label, val, min, max) {
  return `<label><small>${label}</small><div class="step"><button type="button" data-act="step" data-k="${key}" data-d="-1" data-fk="${key}-"${val == null ? ' disabled' : ''} aria-label="${label}: méně">−</button>
    <output class="num${val == null ? ' empty' : ''}" aria-live="polite">${val == null ? 'bez limitu' : val}</output>
    <button type="button" data-act="step" data-k="${key}" data-d="1" data-fk="${key}+"${val === max ? ' disabled' : ''} aria-label="${label}: více">+</button></div></label>`;
}
function switchRow(key, title, hint, on) {
  return `<button type="button" class="sw" role="switch" aria-checked="${on}" data-act="toggle" data-k="${key}" data-fk="sw-${key}"><span class="tx"><b>${title}</b><small>${hint}</small></span><span class="trk"><i aria-hidden="true">✓</i></span></button>`;
}
function panelHTML(count, bare) {
  const f = S.f, n = chipList().length;
  const head = `<div class="fp-h"><h2>Filtry</h2><small data-bind="active">${n ? `${n} ${plural(n, 'aktivní', 'aktivní', 'aktivních')}` : ''}</small><button class="clear" data-act="clear" data-fk="clear"${n ? '' : ' hidden'}>Zrušit vše</button></div>`;
  const groups = GROUPS.map(([t, list]) => `<div class="fg"><h3>${t}</h3><div class="cw">${list.filter(a => S.cov.tot && (hasAny(a) || f.vybaveni.includes(a))).map(a => `<button type="button" class="cb" data-act="am" data-id="${esc(a)}" data-fk="am-${esc(a)}" aria-pressed="${f.vybaveni.includes(a)}">${esc(amLabel(a))}</button>`).join('')}</div></div>`).join('');
  return `<div class="fp">${bare ? '' : head}
    <div class="fg"><div class="lab">Počet osob <span>1–70</span></div><div class="pair">${stepper('osobyOd', 'od', f.osobyOd, 1, 70)}${stepper('osobyDo', 'do', f.osobyDo, 1, 70)}</div></div>
    <div class="fg"><div class="lab">Počet ložnic <span>1–15</span></div><div class="pair">${stepper('lozniceOd', 'od', f.lozniceOd, 1, 15)}${stepper('lozniceDo', 'do', f.lozniceDo, 1, 15)}</div><p class="hint">Nabídky bez uvedeného počtu ložnic zůstanou ve výsledcích, s poznámkou na kartě.</p></div>
    <div class="fg"><label class="lab" for="maxc">Maximální cena za noc</label><div class="money"><input id="maxc" inputmode="numeric" autocomplete="off" placeholder="bez omezení" value="${f.maxCena != null ? fmt(f.maxCena) : ''}"><span>Kč</span></div><p class="hint">Nabídky bez uvedené ceny zůstanou ve výsledcích, s poznámkou na kartě.</p></div>
    <div class="fg">${switchRow('jenCele', 'Jen celé objekty', 'Skryje nabídky, kde portál uvádí jen část objektu.', f.jenCele)}${switchRow('skrytApart', 'Skrýt pravděpodobné apartmány', 'Podle popisu to vypadá na apartmán v domě.', f.skrytApart)}</div>
    ${groups}</div>`;
}
const hasAny = a => S.items.some(l => (l.amenities || []).includes(a)) || ['parkování'].includes(a);

function refreshPanels() {
  const fk = document.activeElement?.dataset?.fk, count = compute().shown;
  const side = document.getElementById('fp-side'), sheet = document.getElementById('fp-sheet');
  if (side && mq.matches) side.innerHTML = panelHTML(count);
  if (sheet) sheet.innerHTML = panelHTML(count, true);
  const root = sheet || side;
  if (fk && root) { const el = root.querySelector(`[data-fk="${CSS.escape(fk)}"]`); if (el && !el.disabled) el.focus(); }
  syncMeta(count);
}
function syncMeta(count) {
  const n = chipList().length;
  document.querySelectorAll('[data-bind="count"]').forEach(e => { e.textContent = `Zobrazit ${nabAcc(count)}`; });
  document.querySelectorAll('[data-bind="active"]').forEach(e => { e.textContent = n ? `${n} ${plural(n, 'aktivní', 'aktivní', 'aktivních')}` : ''; });
  document.querySelectorAll('.fp-h .clear').forEach(e => { e.hidden = !n; });
}
function updateResults() {
  const el = document.getElementById('results');
  if (el) el.innerHTML = resultsHTML();
  syncMeta(compute().shown);
}
function sheetHTML() {
  const count = compute().shown, n = chipList().length;
  return `<div class="scrim" data-act="scrim"><div class="sheet" role="dialog" aria-modal="true" aria-labelledby="sh-t"><div class="grab"></div>
    <div class="sh"><h2 id="sh-t">Filtry</h2><small data-bind="active">${n ? `${n} ${plural(n, 'aktivní', 'aktivní', 'aktivních')}` : ''}</small><button class="xbtn" data-act="close" aria-label="Zavřít filtry">×</button></div>
    <div class="sb" id="fp-sheet">${panelHTML(count, true)}</div>
    <div class="sf"><button class="btn" data-act="clear">Zrušit vše</button><button class="btn solid" data-act="close" data-bind="count">Zobrazit ${nabAcc(count)}</button></div></div></div>`;
}
function dialogHTML() {
  const id = S.dlg.region, ob = oblast(id), name = ACC[id] || ob?.name || id;
  return `<div class="scrim" data-act="scrim"><div class="dlg" role="dialog" aria-modal="true" aria-labelledby="dl-t"><div class="ic" aria-hidden="true">↻</div>
    <h2 id="dl-t">Aktualizovat ${esc(name)}?</h2><p>Stáhneme aktuální nabídky ze všech tří portálů.</p>
    <div class="tm"><span aria-hidden="true">⏱</span><span>Trvá to několik minut. Stránku nechte otevřenou, nabídky se pak samy obnoví.</span></div>
    ${S.dlg.msg ? `<div class="msg" role="status">${esc(S.dlg.msg)}</div>` : ''}
    <div class="acts"><button class="btn solid big" data-act="run-update" data-id="${esc(id)}">Spustit aktualizaci</button><button class="btn big" data-act="close">Teď ne</button></div></div></div>`;
}

/* ---------- vykreslení a události ---------- */
function render() {
  if (!S.index) return;
  const html = S.view.t === 'intro' ? introHTML() : regionHTML();
  const keepScroll = window.scrollY;
  $app.innerHTML = html + (S.sheet ? sheetHTML() : '') + (S.dlg ? dialogHTML() : '');
  document.body.classList.toggle('locked', !!(S.sheet || S.dlg));
  if (S.view.t === 'intro') window.scrollTo(0, keepScroll);
  const dlg = $app.querySelector('.scrim [role="dialog"]');
  if (dlg) (dlg.querySelector('.btn.solid, .xbtn') || dlg).focus();
}
function closeOverlay() {
  const op = S.opener; S.sheet = false; S.dlg = null; S.opener = null;
  render();
  if (op) { const el = document.querySelector(`[data-act="${op}"]`); if (el) el.focus(); }
}
function setStep(k, dir) {
  const f = S.f, lim = k.startsWith('osoby') ? [1, 70] : [1, 15], base = k.startsWith('osoby') ? 'osoby' : 'lozince';
  const lo = k.startsWith('osoby') ? 'osobyOd' : 'lozniceOd', hi = k.startsWith('osoby') ? 'osobyDo' : 'lozniceDo';
  let v = f[k];
  if (v == null) v = dir > 0 ? (k === lo ? lim[0] : (f[lo] ?? lim[0])) : null;
  else { v += dir; if (v < lim[0]) v = null; if (v != null && v > lim[1]) v = lim[1]; }
  f[k] = v;
  if (f[lo] != null && f[hi] != null && f[lo] > f[hi]) { if (k === lo) f[hi] = f[lo]; else f[lo] = f[hi]; }
  void base;
}
// Anonymní analytika (Umami): jen název akce a oblast, žádné osobní údaje.
function track(name, data) {
  try { if (window.umami && typeof window.umami.track === 'function') window.umami.track(name, data); } catch (_) { /* analytika nesmí rozbít web */ }
}
document.addEventListener('click', e => {
  const link = e.target.closest('a.btn[href^="http"]');
  if (link) { try { track('detail-nabidky', { portal: new URL(link.href).hostname }); } catch (_) {} }
  const ev = e.target.closest('[data-act="open-region"],[data-act="open-kraj"],[data-act="run-update"]');
  if (ev) track(ev.dataset.act, { id: ev.dataset.id || '' });
  const t = e.target.closest('[data-act],[data-pick]');
  if (!t) return;
  if (t.dataset.pick) {
    const [kind, id] = [t.dataset.pick.slice(0, 1), t.dataset.pick.slice(2)];
    return open(kind === 'o' ? { t: 'region', id } : { t: 'kraj', id });
  }
  const a = t.dataset.act, id = t.dataset.id;
  if (a === 'scrim') { if (e.target === t) closeOverlay(); return; }
  switch (a) {
    case 'home': S.view = { t: 'intro' }; S.sheet = false; S.dlg = null; render(); window.scrollTo(0, 0); break;
    case 'tab': S.tab = id; render(); break;
    case 'open-region': open({ t: 'region', id }); break;
    case 'open-kraj': open({ t: 'kraj', id }); break;
    case 'retry': open(S.view); break;
    case 'more': S.shown += PAGE; updateResults(); break;
    case 'filters': S.sheet = true; S.opener = 'filters'; render(); break;
    case 'close': closeOverlay(); break;
    case 'update': track('aktualizace/' + id, 'Dialog aktualizace: ' + id); S.dlg = { region: id }; S.opener = 'update'; render(); break;
    case 'run-update': {
      const hook = window.Chalupnik && window.Chalupnik.onUpdate;
      if (typeof hook === 'function') { try { hook(id); } catch (err) { console.error(err); } closeOverlay(); }
      else { S.dlg.msg = 'Spouštění aktualizace přímo z webu se teprve připravuje. Zatím ji spouští majitel aplikace.'; render(); }
      break;
    }
    case 'drop': dropFilter(id); S.shown = PAGE; updateResults(); refreshPanels(); break;
    case 'clear': S.f = freshFilters(); S.shown = PAGE; updateResults(); refreshPanels(); break;
    case 'step': setStep(t.dataset.k, +t.dataset.d); S.shown = PAGE; updateResults(); refreshPanels(); break;
    case 'toggle': S.f[t.dataset.k] = !S.f[t.dataset.k]; S.shown = PAGE; updateResults(); refreshPanels(); break;
    case 'am': {
      const v = S.f.vybaveni, i = v.indexOf(id);
      if (i >= 0) v.splice(i, 1); else v.push(id);
      S.shown = PAGE; updateResults(); refreshPanels(); break;
    }
  }
});
document.addEventListener('input', e => {
  if (e.target.id !== 'maxc') return;
  const digits = e.target.value.replace(/\D/g, '').slice(0, 7);
  S.f.maxCena = digits ? +digits : null;
  S.shown = PAGE; updateResults();
});
document.addEventListener('change', e => { if (e.target.id === 'maxc') e.target.value = S.f.maxCena != null ? fmt(S.f.maxCena) : ''; });   // jen přeformátuje; panel se nepřekresluje, aby se neztratilo klepnutí
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && (S.sheet || S.dlg)) { closeOverlay(); return; }
  if (e.key === 'Tab') {
    const dlg = document.querySelector('.scrim [role="dialog"]');
    if (!dlg) return;
    const f = [...dlg.querySelectorAll('button:not([disabled]):not([hidden]), input, a[href]')].filter(x => x.offsetParent !== null);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    else if (!dlg.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
  }
});
document.addEventListener('error', e => { if (e.target.classList?.contains('pimg')) e.target.remove(); }, true);   // fotka se nenačetla -> zůstane pruhovaná plocha
mq.addEventListener('change', () => { S.sheet = false; render(); });

/* ---------- start ---------- */
(async function init() {
  try {
    const [index, mapa] = await Promise.all([getJSON('data/index.json'), getJSON('data/mapa-cr.json')]);
    S.index = index; S.mapa = mapa; S.load = 'ok';
    render();
  } catch (e) {
    $app.innerHTML = `${'<header class="hdr"><span class="logo"><i></i><b>Chalupník</b></span></header>'}<main class="wrap"><div class="state"><div class="ic" aria-hidden="true">!</div><h2>Nabídky se nepodařilo načíst</h2>
      <p>Zkontrolujte připojení k internetu a zkuste to znovu. Pokud se chyba opakuje, pomůže oblast aktualizovat.</p>
      <div class="acts"><button class="btn solid" onclick="location.reload()">Zkusit znovu</button></div><code>${esc(e.message || e)}</code></div></main>`;
  }
})();
})();
