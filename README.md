# Chalupník

Hledač chat a chalup k pronájmu z vybraných českých portálů. Výsledky se zobrazují na statickém frontendu (GitHub Pages).

---

## Jak to funguje

```
Spuštění workflow
      ↓
GitHub Actions spustí scraper (Python)
      ↓
Výsledky se uloží do results/latest.json a commitnou do repa
      ↓
Frontend (docs/index.html) načte JSON a zobrazí karty
```

1. **Spustit hledání** — přejdi na [Actions → Scrape listings](https://github.com/Nojmi/Chalupnik/actions/workflows/scrape.yml), klikni *Run workflow* a vyplň kritéria (lokalita, kapacita, cena, vybavení, termín).
2. **GitHub Actions** spustí `scraper/main.py`, který projde všechny registrované portály, vyfiltruje výsledky a zapíše `results/latest.json` zpátky do repozitáře.
3. **GitHub Pages** servíruje `/docs` — stránka při načtení stáhne aktuální `latest.json` a zobrazí karty nabídek. Filtry v levém panelu pracují na klientovi nad stáhnutými daty (nevyžadují nové spuštění scraperu).

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
results/
  latest.json                  Výsledky posledního běhu
docs/                          GitHub Pages (statický frontend)
  index.html
  style.css
  app.js
```
