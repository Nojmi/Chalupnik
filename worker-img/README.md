# Chalupník – Cloudflare Worker s cache fotek (`worker-img/`)

Samostatný Worker (oddělený od `worker/`, který spouští aktualizace). Web přes něj načítá fotky nabídek, aby se
každá fotka z portálu stáhla jen jednou a ne při každé návštěvě každého návštěvníka.

```
prohlížeč ──GET /img?u=<adresa fotky>──▶ Worker ──(jen při chybějící cache)──▶ e-chalupy.cz / www.cs-chalupy.cz / www.chata.cz
      ▲                                    │
      └── fotka, Cache-Control 30 dní ◀────┘
```

## Co dělá

- `GET /img?u=<adresa>` vrátí fotku. Adresa musí být **https (nebo http, povýší se) na jeden ze tří povolených hostů**: `e-chalupy.cz`, `www.cs-chalupy.cz`, `www.chata.cz`. Cokoli jiného je 400, takže Worker nejde zneužít jako obecná proxy.
- **Cache:** úspěšná fotka 30 dní (v Cloudflare i v prohlížeči), chyby 404/410 a ostatní 4xx 10 minut, 5xx se necachuje (prohlížeč si je pamatuje 60 s).
- **Šetrnost k portálům:** dotaz bez Refereru, s poctivým `User-Agent`, souběžné dotazy na stejnou fotku sdílejí jeden dotaz, přesměrování se sleduje jen na povolené hosty, přeposílají se jen fotky (JPEG, PNG, WebP, GIF, AVIF) do 6 MB.
- Žádná tajemství, žádný token.

## Důležité: jak je cache postavená a proč

Podle dokumentace Cloudflare mají **funkční `cache` operace (Cache API) jen Workery na vlastní doméně**, ne na `*.workers.dev`. Doménu nemáme, proto Worker cachuje **samotný dotaz na portál** (`fetch` s volbami `cf.cacheEverything` a `cf.cacheTtlByStatus`) a k tomu nastavuje 30denní cache v prohlížeči.

Co to znamená v praxi:
- Cache Cloudflare je **po datových centrech**: stejná fotka se může z portálu stáhnout jednou v každém centru, odkud ji někdo načte (pro návštěvníky z Česka jich bude jen pár).
- Cloudflare může málo používané položky z cache vyhodit dřív než za 30 dní. „Jeden dotaz na fotku“ je tedy cíl, ne záruka.
- Že cache na `workers.dev` opravdu drží, **není z dokumentace jisté**. Ověří to měřicí skript (viz níže): druhý průchod má vrátit převážně `HIT`.

### Když cache nedrží
Pokud druhý průchod ukáže málo `HIT`, zůstává aspoň 30denní cache v prohlížeči (každý návštěvník stáhne fotku nejvýš jednou za 30 dní) a Worker pořád chrání portály před výpadky a dotazy mimo whitelist. Plnohodnotnou cache by pak dala vlastní doména (Cache API) nebo úložiště (Workers KV / R2). To by byla samostatná úvaha.

## Nasazení

Účet Cloudflare už máš. V adresáři `worker-img/`:

```bash
npm install
npx wrangler login      # pokud ještě nejsi přihlášený
npx wrangler deploy     # vypíše adresu https://chalupnik-img.<poddoména>.workers.dev
```

Pak v `docs/config.js` nastav `img: 'https://chalupnik-img.<poddoména>.workers.dev'` (bez lomítka na konci), zvyš `?v=` u `config.js` v `docs/index.html` a změnu commitni a pushni. Prázdné `img` = fotky se berou přímo z portálů jako dosud, takže návrat je jedním řádkem.

**Při přidání nového portálu** doplň jeho host do `ALLOWED_HOSTS` v `wrangler.toml` a znovu nasaď. Do té doby jeho fotky z webu zmizí (zůstane šedá plocha).

## Změření před nasazením a po něm

Skript vybere vzorek fotek z `docs/data` (rovnoměrně mezi portály), stáhne je nenáročně (3 souběžně, pauza 300 ms) a vypíše tabulku: kolik je v pořádku, jaké chyby, velikosti a rychlost. Spouštěj ho u sebe (z prostředí, kde pracuje Claude, se na portály nedostane):

```bash
# 1) přímo proti portálům: kolik fotek vrací chybu (ideálně před nasazením)
node scripts/measure.mjs --n 200

# 2) přes nasazený Worker: první průchod plní cache, druhý má vracet HIT
node scripts/measure.mjs --n 200 --worker https://chalupnik-img.<poddoména>.workers.dev
```

Krok 2 stahuje z portálů znovu (jednou, přes Worker), nespouštěj ho tedy zbytečně často.

## Nastavení (`wrangler.toml`, `[vars]`)

| Proměnná | Výchozí | Význam |
|---|---|---|
| `ALLOWED_HOSTS` | `e-chalupy.cz,www.cs-chalupy.cz,www.chata.cz` | hosty, ze kterých se smí fotky brát (přesná shoda) |
| `CACHE_TTL_DAYS` | `30` | jak dlouho drží úspěšná fotka |
| `NEG_TTL_MIN` | `10` | jak dlouho drží chyba 4xx |
| `MAX_MB` | `6` | největší povolená fotka |
| `UPSTREAM_UA` | `Chalupnik/1.0 (+https://nojmi.github.io/Chalupnik/)` | User-Agent dotazů na portály; měnit jen kdyby ho portál odmítal |

## Vývoj a testy

```bash
npm test          # node:test s mockovaným fetch, nic nevolá ven
npx wrangler dev  # lokálně
```

## Limity

- Cloudflare Workers zdarma: 100 000 požadavků denně. Každá zobrazená fotka je jeden požadavek (i když je z cache), jedna stránka jich načte nejvýš 24 (lazy loading).
- Odpovědi nejsou omezeny na náš web (`<img>` nepřenáší `Origin`). Zneužití je omezené whitelistem hostů a limitem Cloudflare.
