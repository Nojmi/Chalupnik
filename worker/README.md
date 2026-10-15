# Chalupník – Cloudflare Worker (tlačítko „Aktualizovat region“)

Malý Worker (ES modul, bez frameworku), který stránka na GitHub Pages volá, když chce spustit aktualizaci dat.
Sám nic nestahuje: jen ověří, že je spuštění v pořádku, a spustí workflow `scrape.yml` přes GitHub API.

```
web (nojmi.github.io) ──POST /run {region}──▶ Worker ──▶ GitHub API: dispatch scrape.yml (location = oblast)
        ▲                                        │
        └──────── GET /status (každých 20 s) ◀───┘  stav čte ze seznamu běhů workflow
```

GitHub token je jen ve Workeru (jako secret), nikdy ve webu.

## Endpointy

| Endpoint | Co dělá |
|---|---|
| `POST /run` `{"region":"Šumava"}` | Spustí aktualizaci jedné oblasti. Název musí být v `docs/data/mapa-cr.json` (Worker ho čte z Pages, 1 h v paměti). Vyžaduje `Origin: https://nojmi.github.io`. |
| `GET /status` | Stav běhů workflow (v paměti 20 s). Volitelně `?region=Šumava&since=<ISO čas>`: web si tak hlídá právě svůj běh. |

Odpovědi `POST /run`:

| Kód | `error` | Kdy |
|---|---|---|
| 202 | – | spuštěno; vrací `dispatched_at` |
| 400 | `unknown_region`, `bad_region`, `bad_json` | oblast není v `mapa-cr.json` (více oblastí najednou, prázdné pole nebo „KRAJE“ se také odmítne) |
| 403 | `bad_origin` | chybí nebo nesedí `Origin` |
| 409 | `already_running` | nějaký běh workflow běží nebo čeká ve frontě (v `active` je který) |
| 429 | `region_cooldown` | stejná oblast byla spuštěna za posledních 60 min (`retry_after_s`, `retry_at`, hlavička `Retry-After`) |
| 429 | `daily_limit` | za posledních 24 h bylo spuštěno 20 běhů (`retry_after_s`) |
| 502 | `github_error`, `map_unavailable` | GitHub nebo Pages neodpověděly |

`GET /status` vrací `state`: `pending` (spuštěno, GitHub běh ještě nevrací), `queued`, `running`, `success`, `failed`, `cancelled`, `none`.

Zámky se počítají jen ze seznamu běhů v GitHub API (žádné KV, žádná databáze). Název oblasti se pozná z `run-name` ve `scrape.yml` (`Scrape <oblast>`), proto ho z workflow nemazejte.

## Nasazení (jednorázově)

Potřebujete účet na Cloudflare (stačí zdarma) a Node.js 20+.

1. **Účet a přihlášení**
   ```bash
   cd worker
   npm install
   npx wrangler login        # otevře prohlížeč, přihlásíte se k Cloudflare
   ```

2. **GitHub token** (GitHub → Settings → Developer settings → Personal access tokens → *Fine-grained tokens* → *Generate new token*):
   - *Resource owner*: `Nojmi`
   - *Repository access*: **Only select repositories** → jen `Chalupnik`
   - *Repository permissions*: **Actions: Read and write** (zápis spouští workflow, čtení vrací seznam běhů). Nic jiného nezapínejte (Metadata: Read-only se přidá samo).
   - *Expiration*: třeba 1 rok. Po vypršení Worker začne vracet `github_error` (viz níže), stačí vyrobit nový token a zopakovat krok 4.

3. **Nasazení Workeru**
   ```bash
   npx wrangler deploy
   ```
   Na konci vypíše adresu, např. `https://chalupnik-worker.<vaše-poddoména>.workers.dev`.

4. **Token jako secret** (hodnotu vložíte do výzvy, nikam se nezapisuje):
   ```bash
   npx wrangler secret put GH_TOKEN
   ```

5. **Adresa do webu**: v `docs/config.js` nastavte `worker: 'https://chalupnik-worker.<vaše-poddoména>.workers.dev'` (bez lomítka na konci), v `docs/index.html` zvyšte `?v=` u `config.js` a změnu commitněte a pushněte. Pages se nasadí asi za minutu.

6. **Zkouška** (nic nespustí):
   ```bash
   curl -s https://chalupnik-worker.<vaše-poddoména>.workers.dev/status
   curl -si -X POST https://chalupnik-worker.<vaše-poddoména>.workers.dev/run \
     -H 'Origin: https://example.com' -d '{"region":"Šumava"}' | head -1     # očekávejte 403
   ```
   Pak na webu otevřete oblast a klepněte na „Aktualizovat region“.

## Nastavení (`wrangler.toml`, sekce `[vars]`)

| Proměnná | Výchozí | Význam |
|---|---|---|
| `GH_REPO` | `Nojmi/Chalupnik` | repozitář s workflow |
| `GH_WORKFLOW` | `scrape.yml` | soubor workflow |
| `GH_REF` | `main` | větev, na které se workflow spouští |
| `ALLOWED_ORIGIN` | `https://nojmi.github.io` | jediný povolený `Origin` (i pro CORS) |
| `MAP_URL` | `https://nojmi.github.io/Chalupnik/data/mapa-cr.json` | odkud se čte seznam oblastí |
| `REGION_COOLDOWN_MIN` | `60` | po kolika minutách smí jít stejná oblast znovu |
| `DAILY_LIMIT` | `20` | nejvýše tolik běhů za 24 h |
| `GH_TOKEN` | – | **secret**, ne v souboru (`wrangler secret put`) |

Po změně hodnoty stačí `npx wrangler deploy`.

## Vývoj a testy

```bash
npm test                  # node:test s mockovaným fetch, nic nevolá ven
npx wrangler dev          # lokálně; token patří do worker/.dev.vars (GH_TOKEN=…), soubor je v .gitignore
```

## Na co si dát pozor

- **Origin není heslo.** Prohlížeč cizí stránce `Origin` nepodvrhne, ale `curl` ano. Skutečnou ochranu dělají omezení: povolený seznam oblastí, jedna oblast najednou, cooldown a denní strop. Nejhorší, co někdo cizí zvládne, je spustit 20 běhů za den.
- **Do stropu se počítají všechny ruční běhy** workflow `scrape.yml` za 24 h, tedy i ty, které spustíte sami v GitHubu. Běhy z doby před přidáním `run-name` nemají v názvu oblast, takže se nezapočítají do cooldownu, jen do stropu.
- **Dvojí kliknutí.** GitHub nově spuštěný běh ukáže až po pár sekundách. Worker si proto na 45 s pamatuje poslední spuštění (v paměti jedné instance) a do té doby vrací 409. Při nasazení na více místech Cloudflare to není stoprocentní, ale souběh by jen zařadil druhý běh do fronty (`concurrency` ve workflow nic nepřepisuje).
- **Plná aktualizace všech oblastí** (prázdné `location`, asi hodina) Worker nikdy nespouští, jen ruční spuštění v GitHubu. Taková běžící aktualizace ale blokuje web (409).
- **Chyby `github_error`** se `github_status` 401/403/404 znamenají obvykle vypršelý nebo špatně nastavený token (chybí *Actions: Read and write* nebo repozitář).
- Cloudflare Workers zdarma dovolují 100 000 požadavků denně, což tento provoz ani zdaleka nevyčerpá.
