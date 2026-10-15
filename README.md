# Chalupník

Hledač chat a chalup k pronájmu z vybraných českých portálů. Výsledky se zobrazují na statickém frontendu (GitHub Pages).

---

## Jak to funguje

```
Spuštění workflow (ručně, pro jednu oblast)
      ↓
GitHub Actions spustí scraper (Python)
      ↓
Nabídky se sloučí do databáze oblasti: docs/data/<oblast>.json (+ docs/data/index.json)
      ↓
Web (docs/index.html) načte index a data oblasti a zobrazí karty s filtry
```

0. **Automaticky** se stahují všechny oblasti 1. a 15. v měsíci (`schedule` ve `scrape.yml`).
1. **Spustit stahování ručně** — [Actions → Scrape listings](https://github.com/Nojmi/Chalupnik/actions/workflows/scrape.yml), *Run workflow*, do pole „Lokalita" napsat oblast (např. Krkonoše, Šumava) a ostatní pole nechat prázdná.
2. **Scraper** projde portály a sloučí výsledek do databáze oblasti. Nabídky se nepřepisují od nuly (stabilní `id`, `first_seen`/`last_seen`, ochrana proti výpadku portálu). Každá nabídka dostane `kraj` podle GPS.
3. **GitHub Pages** servíruje `/docs`. Web nic neukládá, filtruje v prohlížeči a stáří dat počítá z `last_updated` (≤ 14 dní čerstvé, 15–30 doporučit aktualizaci, > 30 zastaralé).
3a. **Režim:** výchozí je tmavý, světlý „lesní papír" se přepíná tlačítkem v hlavičce (atribut `data-theme="light"` na `<html>`, proměnné v `docs/style.css`). Volba se neukládá.
4. Tlačítko „Aktualizovat region“ spouští workflow přes Cloudflare Worker ([`worker/`](worker/README.md), adresa v `docs/config.js`). Dokud je `worker` v `docs/config.js` prázdný, tlačítko nic nespouští (zůstává hook `window.Chalupnik.onUpdate(regionId)`).

---

## Jak přidat nový portál

1. Pořiď **screenshoty** (nebo uložené HTML soubory):
   - vyhledávací/filtrační formulář (jméno polí, akce formu)
   - výpis výsledků (struktura karet/řádků, stránkování)
   - zdrojový HTML obou stránek (DevTools → Elements nebo *View Source*)

2. Zkopíruj šablonu:
   ```
   cp scraper/profiles/_template.py scraper/profiles/<nazev_portalu>.py
   ```

3. Vyplň `BASE_URL` a implementuj funkci `search(criteria)`:
   - namapuj kritéria na parametry dotazu portálu
   - parsuj HTML pomocí BeautifulSoup
   - ošetři stránkování (sleduj odkaz „další stránka", rozumný limit ~10 stran)

4. Registruj profil v `scraper/profiles/__init__.py`:
   ```python
   from scraper.profiles import nazev_portalu
   ALL_PROFILES = [nazev_portalu.search]
   ```

5. Otestuj lokálně (viz níže).

---

## Co není a proč

| Portál / zdroj | Důvod vynechání |
|---|---|
| **Booking.com, Airbnb** | Agresivní anti-bot ochrana (Cloudflare, CAPTCHA); navíc jejich ToS scraping explicitně zakazuje |
| **Facebook skupiny** | Žádné veřejné API; přihlášení nutné; riziko blokace účtu; obsah nestandardizovaný |

---

## Lokální spuštění

```bash
# Instalace závislostí
pip install -r scraper/requirements.txt

# Spuštění s kritérii přes env proměnné
CRIT_LOCATION="Šumava" \
CRIT_MIN_CAPACITY=6 \
CRIT_MAX_PRICE=4000 \
CRIT_AMENITIES="krb,parkování" \
python scraper/main.py

# Výsledek
cat results/latest.json
```

Frontend lze otevřít přímo jako soubor (`docs/index.html`), ale kvůli CORS bude načítat data z GitHubu — pro lokální vývoj doporuč jednoduchý HTTP server:

```bash
cd docs
python -m http.server 8080
# otevři http://localhost:8080
```

---

## Struktura projektu

```
.github/workflows/scrape.yml   GitHub Actions workflow (workflow_dispatch)
scraper/
  main.py                      Vstupní bod scraperu
  models.py                    Dataclass Listing
  filters.py                   Filtrování výsledků
  requirements.txt
  profiles/
    __init__.py                Registr aktivních profilů (ALL_PROFILES)
    _template.py               Šablona pro nový portál
docs/                          GitHub Pages (statický frontend)
  index.html, style.css, app.js  Web (vanilla JS, bez build kroku)
  data/                        Databáze oblastí (index.json, <oblast>.json, mapa-cr.json)
```
