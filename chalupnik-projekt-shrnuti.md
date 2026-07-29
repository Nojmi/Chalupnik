# Chalupník — shrnutí projektu (stav k 28. 7. 2026, večer)

Repozitář: `github.com/Nojmi/Chalupnik` (majitel: Nojmi/Tomáš Neumann)
Živá stránka: `https://nojmi.github.io/Chalupnik/`

Tento dokument slouží jako kontext pro pokračování práce v novém chatu nebo
jako referenční materiál pro Claude Code. Cílem je nedělat stejné objevy
znovu a nenarazit podruhé na stejné pasti.

---

## 1. Cíl projektu

Webová aplikace, která na vyžádání (ne automaticky na pozadí) prochází
vybrané české portály s chatami/chalupami k pronájmu, filtruje nabídky
a zobrazuje přehlednou sumarizaci. Náhrada za ruční procházení Facebook
skupin a jednotlivých portálů.

Prioritní zdroje: e-chalupy.cz (hotovo), chata.cz (rozpracováno, viz
sekce 5), hauzi.com, chatyachalupy-chatar.cz, alkatravel.cz, zars.cz.
Booking.com/Airbnb/Facebook skupiny jsou záměrně vyřazené (anti-bot ochrana,
smluvní zákazy, žádné API).

## 2. Architektura (zdůvodnění + jak zapadá dohromady)

| Komponenta | Řešení | Proč |
|---|---|---|
| Spouštění scraperu | GitHub Actions, `workflow_dispatch` (ruční) | Jediný způsob, jak GitHub Pages "spustit backend" — Pages sám kód nespouští |
| Scraping | Python (`requests`+`BeautifulSoup`, nebo přímé JSON API pokud existuje) | Viz sekce 4 — u e-chalupy.cz se ukázalo JSON API lepší než HTML parsing |
| Filtrování | Dvouvrstvé: server-side (při scrapingu) + client-side (`docs/app.js` nad staženými daty) | Viz sekce 6 — rozhodli jsme se přesunout co nejvíc filtrů na client-side |
| Uložení výsledku | `results/latest.json` v repu, commitovaný Actionem (nebo ručně při lokálním běhu) | Jednoduché, zdarma, žádná databáze |
| Frontend | Statické HTML/CSS/JS na GitHub Pages, servírováno ze složky `/docs` | Zdarma, žádný build krok |
| Vzhled | Vlastní CSS (ne Bootstrap/Tailwind) — lesní zelená `#1E362B`/`#2E5142`, papírová `#F1EEE3`, jantarová `#BD8636` akcent, mechová `#74845A` pro štítky. Fonty: Fraunces (nadpisy), Inter (text), IBM Plex Mono (čísla/ceny) | Odlišný, "cabin" vzhled, ne generický AI vzhled |

### Klíčové rozhodnutí: frontend nemůže sám spustit scraping
GitHub Pages je čistě statický hosting. Tlačítko "Spustit nové hledání" na
stránce **odkazuje na GitHub Actions** (`/actions/workflows/scrape.yml`),
neumí to spustit samo přes JS bez access tokenu. Řešení "tlačítko přímo na
stránce, co spustí workflow" bylo navrženo (fine-grained PAT zadávaný
uživatelem do prohlížeče, nebo serverless proxy), ale **zatím neimplementováno**
— odloženo na později, pokud o to Nojmi bude stát.

## 3. Vývojové prostředí — jak Nojmi pracuje

- **Claude Code** spouští v **samostatném terminálu ve VS Code** (ne
  desktopová appka, ne VS Code rozšíření) — `cd Chalupnik && claude`.
- Repo naklonováno na `C:\Users\N-noj\Chalupnik`.
- Windows, PowerShell.
- **Avast antivirus dělá TLS interception** (přepisuje HTTPS certifikáty) —
  způsobuje SSL chyby jak v `git push`, tak v Python `requests` voláních.
  **Řešení, co funguje a je zavedené:**
  - Pro git: `git -c http.sslVerify=false push` (nebo přes VS Code Source
    Control GUI, které tímhle problémem netrpí — používá jiný git klient/GCM).
  - Pro Python requests: exportovat Avastův root cert a spojit ho s
    oficiálními CA certifikáty do jednoho kombinovaného `.pem` souboru,
    pak nastavit `REQUESTS_CA_BUNDLE=<cesta k combined_ca.pem>` před
    spuštěním `python -m scraper.main`. Claude Code tenhle postup zná
    a má povolený (schváleno "don't ask again").
- GitHub push authentication: řešeno přes VS Code GitHub rozšíření (Allow
  přihlášení), funguje spolehlivě.
- Struktura příkazů: Claude Code se často ptá na potvrzení bash příkazů —
  u opakujících se kategorií (git add/commit, mkdir v `.github/`, atd.)
  vybíráme "Yes, and don't ask again for..." aby se to neopakovalo.
- **Nojmi sbírá podklady (screenshoty, HTML, DevTools Network tab) v práci
  na mobilu/jiném PC a nemůže odtud programovat** — sesbírané poznatky se
  průběžně zapisují sem, aby je Claude Code doma mohl rovnou použít, aniž
  by se objevy musely dělat znovu.

## 4. e-chalupy.cz — kompletní stav profilu (HOTOVO, důkladně vyladěno)

### Základní mechanismus
- Portál má **dva způsoby přístupu k datům**:
  1. Server-rendered stránky podle regionu: `e-chalupy.cz/<slug-lokality>`
     (např. `/krusne-hory`, `/sumava`) — HTML s kartami, dřívější přístup.
  2. **JSON API** na jiné doméně: `https://api-pub.e-chalupy.cz/properties`
     — **tohle je současný, preferovaný přístup**. Mnohem spolehlivější,
     strukturovaná data, žádné HTML parsování.
- API parametry: `destinations=area_XXXXX` (kód regionu), `persons`,
  `bedrooms`, `limit`, `offset`, `filters=<id>` (server-side filtr podle ID
  vybavení — viz níže).
- Area kód (`area_XXXXX`) se získává z HTML stránky `/<slug>` přes regex
  na `window.dataSearchBoxSelectedData` (žádné veřejné API pro překlad
  název→kód neexistuje).

### DŮLEŽITÝ LIMIT: strop 10 000 výsledků
- API má tvrdý Elasticsearch/OpenSearch strop `max_result_window: 10000`.
  Při dotazu bez `destinations` (celostátně) se `total` zasekne na
  `{"value": 10000, "relation": "gte"}` a stránkování přes offset se
  zastaví přesně na offsetu 10000 — **žádný workaround není možný** přes
  veřejný endpoint (žádný cursor/search_after parametr není vystaven).
- Celkový počet nabídek "Chaty a chalupy" pro ČR: ~10 894. Se "Sruby a
  roubenky": ~11 981. **Obojí je nad stropem 10 000** — celostátní
  scraping bez ohledu na kombinaci kategorií nikdy nedá kompletní data.
- **Rozhodnutí: lokalita (region) zůstává POVINNÝM vstupem.** Jeden region
  = řádově stovky až ~2200 nabídek (Jižní Čechy byly největší pozorovaný
  region), hluboko pod stropem → kompletní data.
- **Přesun filtrů na client-side**: `min_capacity`/`min_bedrooms`/
  `max_price` se **NEPOSÍLAJÍ** do API dotazu vůbec. Stahuje se kompletní
  dataset pro region, filtrování dělá `filters.py`/`docs/app.js`. Umožňuje
  to uživateli měnit filtry na stránce bez nutnosti nového scrape běhu.

### Location matching — vyřešeno
- API u `destinations=area_XXXXX` vrací i nabídky ze sousedních/
  překrývajících se regionů (ne jen striktně ten požadovaný region).
- Řešení: každá nabídka má `area2.slug` (region podle portálu) — profil
  porovnává přesně `area2.slug == <požadovaný slug>` a nesedící nabídky
  vyřazuje. To způsobuje viditelný "úbytek" (např. Šumava: 1200 nalezeno →
  913 po location filtru) — **tohle je ZÁMĚRNÉ a SPRÁVNÉ chování**, ne bug.
- `Listing.location` se ukládá jako `"{area.title}, {area2.title}"`
  (např. "Přebuz, Krušné hory") — čitelné pro člověka i pro filtrování.
- Frontend zobrazuje hezký název lokality (ne technický slug) v info
  řádce — bere se z `raw_extra` první nabídky v seznamu, s fallbackem na
  syrový slug pokud nejsou žádné nabídky.

### Vybavení (amenities) — dvojí zdroj dat
- **Textové tagy** (`tags`/`tagsFeatured` pole v API): fungují 100% pro
  vířivka, sauna, na samotě, krb (obě varianty sloučené), ~93% pro u lesa.
- **ID-only vybavení** (v `tags` textu se VŮBEC neobjevují, i když nabídka
  dané vybavení má): bazén, se psem, společenská místnost, myčka nádobí,
  lednička, klimatizace, televize, wifi, pískoviště, ohniště, gril.
  - Tohle bylo zjištěno POSTUPNĚ — nejdřív "se psem" a "společenská
    místnost" byly objeveny jako úplně mrtvé (0 shod), pak při rozšiřování
    o dalších 8 položek se ukázalo, že VŠECH 8 nových je taky ID-only.
  - **Nauč se z tohoto**: při přidávání jakéhokoli nového vybavení do
    filtru VŽDY nejdřív ověřit textové pokrytí na reálném vzorku dat,
    ne předpokládat, že bude fungovat jako textový tag.
  - Řešení: server-side `filters=<id>` dotaz vrací množinu ID nabídek,
    která mají dané vybavení. Profil stáhne tuhle množinu zvlášť
    (stránkovaně) pro každé ID-only vybavení a sjednotí ji s textovými
    tagy při stavbě `Listing.amenities`.
  - Mapování textového názvu → portálového ID viz `AMENITY_FILTER_IDS`
    (nebo podobně pojmenovaná konstanta) v `scraper/profiles/e_chalupy.py`.
  - **Výkon**: použití `ENRICH_LIMIT=1000` (místo `PAGE_SIZE=200` u
    hlavního dotazu) na obohacovacích requestech srazilo čas z odhadovaných
    ~76-80s na ~33-41s pro největší region (Jižní Čechy, 16 vybavení
    celkem). Menší regiony jsou rychlejší.
  - "Parkování" nemá na portálu odpovídající filtr ID — zůstává čistě
    textové (a nefunguje moc dobře, ale nedá se to zlepšit).

### Filtr "entire_property" (Jen celé objekty) — CAVEAT
- Existuje jak jako odvozené pole z `units.header` textu (heuristika:
  hledá fráze "pronajímá se celý" vs. "samostatná část"), tak jako
  server-side `filters=84` na portálu ("Pouze celé objekty").
- **Tyhle dva NESEDÍ na sebe** (569 vs. 1169 na jednom testu) — server-side
  `filters=84` na webu **neznamená to, co název napovídá** (ověřeno na
  konkrétním protipříkladu: nabídka "Šumavský mlýn" s `units.header`
  explicitně říkajícím "může být přítomen majitel" byla přesto webem
  zahrnuta do "Pouze celé objekty").
- **Rozhodnutí: NEPOUŽÍVAT `filters=84`.** Zůstat u `units`-based
  heuristiky, je sémanticky spolehlivější navzdory tomu, že je to jen
  textová heuristika. Nauč se z tohoto: server-side filtr, i když existuje
  a "zní" jako to, co chceš, může mít jinou sémantiku, než název napovídá
  — vždy ověřit na konkrétních protipříkladech, ne jen na součtech čísel.

### "Likely apartment" detekce (nabídka vypadá jako chata/chalupa, ale je
to spíš apartmán/jednotka v resortu)
- Zjištěno: ~50% nabídek v kategorii "Chaty a chalupy" na Šumavě splňuje
  aspoň jeden ze tří signálů: (1) "apartmán" v názvu, (2) `units`/
  `tagsFeatured` naznačuje víc typů jednotek, (3) `priceLabel` obsahuje
  "za apartmán"/"za osobu" místo "za objekt". Dokonce i portálové pole
  `item.type.title` samo o sobě je nespolehlivé (bývá "Apartmán" i uvnitř
  filtru "Chaty a chalupy").
- Rozklad signálů ukázal, že žádný jeden signál nedominuje (units samo:
  408, price samo: 376, title samo: 245 — hodně se překrývají), takže
  všechny tři signály se ponechaly (OR podmínka).
- Implementace: `Listing.likely_apartment: bool`, vizuální štítek na
  kartě "⚠️ Možná jen apartmán, ne celá chalupa" (vždy viditelný), PLUS
  samostatný volitelný checkbox filtru "Skrýt pravděpodobné apartmány"
  (odděleně od `.amenity-group`, aby ho neomylem nesebral selektor pro
  vybavení — stejná past jako u entire-property checkboxu).

### GitHub Actions — 403 Forbidden (BLOKOVÁNO, řeší se lokálním spuštěním)
- Portál e-chalupy.cz **blokuje požadavky z GitHub Actions runnerů**
  (403 Forbidden) — i po vylepšení HTTP hlaviček na realistický Chrome
  User-Agent + Accept/Accept-Language/Accept-Encoding. Lokálně (domácí IP)
  identický požadavek funguje bez problémů.
- **Diagnóza**: pravděpodobně IP-based blokace (GitHub Actions běží na
  známých Azure/Microsoft cloudových IP adresách, které anti-bot systémy
  často blokují plošně, bez ohledu na hlavičky).
- **Řešení zatím zvolené**: spouštět e-chalupy.cz **lokálně** (na domácím
  PC Nojmiho), ne přes GitHub Actions. Postup zdokumentován v README.
- **Zvažovaná, ale zatím NEIMPLEMENTOVANÁ alternativa**: rezidenční proxy
  služba (aby GitHub Actions vypadal jako domácí IP). Cena odhadem
  $1-5/měsíc při nízkém objemu (pay-as-you-go, např. DataImpulse od
  $1/GB) + možný minimální vklad $5-25. Nojmi chtěl nejdřív zkusit další
  portály, jestli mají stejný problém, než investuje do proxy.
- Bonus objev cestou: `Accept-Encoding: br` (Brotli) v hlavičkách vyžaduje
  mít nainstalovaný balíček `brotli` (přidán do `requirements.txt`), jinak
  `requests` tiše vrátí porušený/nedekódovaný obsah (status 200, ale 0
  nalezených karet — TICHÁ chyba, žádná exception).

### Jak spustit e-chalupy.cz lokálně (shrnutí, detaily v README)
```powershell
cd C:\Users\N-noj\Chalupnik
$env:REQUESTS_CA_BUNDLE="C:\Users\N-noj\AppData\Local\Temp\combined_ca.pem"  # nebo aktuální cesta
$env:CRIT_LOCATION="sumava"
python -m scraper.main
git add results/latest.json
git commit -m "chore: naostro běh e-chalupy.cz - <lokalita>"
git -c http.sslVerify=false push
```
(Claude Code zná celý postup včetně vygenerování combined_ca.pem, stačí mu
zadat úkol přirozeným jazykem.)

## 5. chata.cz — profil (HOTOVO, `scraper/profiles/chata_cz.py` napsán a
otestován lokálně na Šumavě a Krkonoších)

Reconnaissance začal jen prohlížením webu a Network tabu (žádné psaní kódu)
— Nojmi sbíral podklady z práce, kde nemůže programovat. Poznámky níže jsou
z tyhle fáze; implementační detaily/odchylky zjištěné až při psaní
`scraper/profiles/chata_cz.py` jsou označené **IMPLEMENTACE:**.

### Žádné centrální JSON API jako u e-chalupy — je to hybrid
Hlavní výpis nabídek (`/ubytovani/<region>/` i `/vyhledavani/?...`) je
server-rendered HTML, ne JSON. ALE portál má **dva pomocné JSON AJAX
endpointy** pro překlad názvu lokality na interní ID (viz níže) — takže
scraper bude pravděpodobně kombinovat: JSON volání pro vyřešení lokality
+ HTML parsing pro samotný výpis nabídek (podobně jako fáze 1 u
e-chalupy, než se přešlo na čisté API).

### Vyhledávací endpoint a jeho parametry
Hlavní stránka výpisu: `chata.cz/vyhledavani/?...` s parametry (potvrzeno
z živých URL, ne odhad):

```
Where=<text lokality>
fWhere=
Autocomplete.LocationId=<číslo, může být prázdné>
Autocomplete.LocationFull=
Autocomplete.LocationType=<číslo, může být prázdné — 6=region, 4=obec, 3=okres>
Distance=0                      # "vzdálenost od místa" (0 = přesně)
FromDate=DD.MM.YYYY
ToDate=DD.MM.YYYY
Adults=<počet>
GuestsType=TwoAdults            # zjevně fixní/derivovaná hodnota, ne uživatelský vstup
RoomAmountType=More             # "počet osob" typ dotazu
PageSize=10                     # potvrzený název parametru pro počet výsledků na stránku
SortingType=Regio
CatalogModel.CatalogUrl=
ExtendedSearch=
Fencing=                        # facet "oplocení"
BedroomsCount=0                 # facet "počet ložnic"
Bathing=                        # facet "koupání" (vzdálenost)
Skiing=                         # facet "lyžování" (vzdálenost)
page=N                          # STRÁNKOVÁNÍ — viz níže
```

**Dvě různé cesty, jak zadat lokalitu:**
1. **Přesná** (doporučeno používat v scraperu): získat `LocationId` +
   `LocationType` přes autocomplete endpointy (viz níže) a poslat je jako
   parametry `Autocomplete.LocationId`/`Autocomplete.LocationType`. Přímá
   analogie k `area_XXXXX` u e-chalupy — jednoznačné, spolehlivé.
2. **Fulltextová zkratka**: poslat jen `Where=<text>` s prázdným
   `Autocomplete.LocationId`/`LocationType` — portál si sám dohledá
   odpovídající objekty fulltextově. Funguje (ověřeno na "brno" → 3
   výsledky), ale je nejednoznačná/nekontrolovaná ve srovnání s (1).
   **Rozhodnutí: primárně používat variantu (1).**

**Cena se zobrazí jen s vyplněným `FromDate`/`ToDate`+`Adults`** — bez
termínu je na kartě jen tlačítko "ZJISTIT CENU", žádná číselná hodnota.
Scraper proto musí vždy poslat nějaký defaultní termín, jinak zůstane
`Listing.price` prázdné pole u všech nabídek (v souladu s principem
"chybějící pole neblokuje", sekce 6).

**IMPLEMENTACE: defaultní termín je celý týden od nejbližší soboty, NE
jen víkend.** Zkoušeli jsme nejdřív jednonoční víkendový dotaz (SO-NE) —
na Šumavě (33 nabídek) to vrátilo **0 reálných cen**, protože velká část
objektů má v sezóně restrikci `min. nocí: 2-7` a/nebo `pobyty jen SO-SO`,
kterou jedna noc nesplní (karta pak ukáže "UPRAVIT TERMÍN", ne cenu).
Týdenní dotaz (SO→SO, `DEFAULT_STAY_NIGHTS=7` v `chata_cz.py`) dal 4 reálné
ceny z 31 (zbytek "Termín je obsazen" — to je reálná dostupnost, ne bug).
Cena na kartě je navíc **celková za pobyt, ne za noc** — `price_unit` se
proto ukládá jako `"pobyt N nocí"`.

### Překlad název lokality → LocationId (dva JSON AJAX endpointy)
1. **`GET chata.cz/AutocompleteRegions/`** (bez query parametrů) — vrátí
   **JSON pole VŠECH regionů** najednou (LocationType 6), needitované
   podle textu:
   ```json
   [
     {"LocationFull": "region <strong>Bílé Karpaty</strong>", "LocationName": null,
      "LocationId": 4, "LocationType": 6, "LocationZip": null, "CityWithDistrict": null},
     {"LocationFull": "region <strong>Brdy</strong>", "LocationId": 4, "LocationType": 6, ...},
     ...
   ]
   ```
   Ideální zavolat **jednou** na začátku běhu a mít celý seznam region→ID
   v paměti/cache (analogie k tomu, jak e-chalupy nemělo žádné takové API
   a muselo se to řešit regexem z HTML — tady je to čistší).
   **POZOR**: `LocationFull` obsahuje HTML tagy (`<strong>...</strong>`)
   kolem názvu, nutno stripnout při parsování.
   **POZOR 2**: v ukázce jsou dva různé regiony s `LocationId: 4` (Bílé
   Karpaty i Brdy) — `LocationId` zjevně NENÍ globálně unikátní napříč
   `LocationType` hodnotami, je unikátní jen v kombinaci
   `(LocationId, LocationType)`. **Nutno vždy posílat oba parametry
   společně, nikdy jen LocationId samotné.**

2. **`GET chata.cz/Autocomplete/<text-lokality>`** (text je součástí
   CESTY URL, ne query parametr!) — vrátí JSON pole lokalit odpovídajících
   zadanému textu, napříč typy (`LocationType: 3` = okres, `4` = obec/
   část obce, patrně i `6` = region pro texty, které region matchují):
   ```json
   [
     {"LocationFull": "obec <strong>Brno</strong>, kraj Jihomoravský, okres Brno-město",
      "LocationId": 4705, "LocationType": 4, ...},
     {"LocationFull": "okres <strong>Brno-město</strong>", "LocationId": 4, "LocationType": 3, ...},
     ...
   ]
   ```
   Toto je jQuery UI Autocomplete widget (potvrzeno z Initiator chainu:
   `_searchTimeout`/`_delay`/`search`/`_search` — standardní jQuery UI
   metody) s krátkým debounce. **Pro scraper irelevantní** — stačí
   poslat celý název najednou (`Autocomplete/Šumava`), ne simulovat
   psaní znak po znaku jako prohlížeč.
   Request headers: `Accept: application/json, text/javascript, */*`,
   `X-Requested-With: XMLHttpRequest` — žádný speciální auth token,
   běžné cookies stačí (možná ani ty ne, nutno ověřit bez cookies).

3. Existuje i **`GET chata.cz/AutocompleteCount/?where=<text>&...`** —
   **NENÍ zdroj LocationId**, vrací jen holé číslo (`Content-Type:
   application/json`, tělo např. `3`) — počet objektů odpovídajících
   textu. Pro scraper nepotřebné, ale dobré vědět, že existuje, ať se
   s ním nezaměňuje `Autocomplete/<text>`.

### Stránkování — VYŘEŠENO A POTVRZENO (zdrojový HTML kód výpisu)
`&page=N` je normální URL query parametr, žádné složité AJAX volání
není potřeba. Na konci výpisu je klasický `<a href="...&page=2">další »</a>`
a `<a href="...&page=3">poslední »</a>` — funguje i jako obyčejný GET
request bez JS/AJAX. Doprovodné hidden inputy:
```html
<input type='hidden' name='apage' id='apage' value=1 />
<input type='hidden' name='startat' id='startat' value=1 />
<input type='hidden' name='itemsperpage' id='itemsperpage' value=10 />
<input type='hidden' name='totalitems' id='totalitems' value=27 />
```
`itemsperpage` = `PageSize`, `totalitems` = celkový počet nabídek pro
daný dotaz (nezávisle na stránce). **Scraper: iterovat `page=1,2,3...`,
dokud `(page-1) * itemsperpage < totalitems`.** Žádné dohadování konce
stránkování není potřeba, `totalitems` je k dispozici hned na první
stránce výpisu.
Text dole na stránce: `zobrazeny objekty 1-N z M`. Když se vejde vše na
jednu stránku, tlačítko je "TO JE VŠE" místo "NAČÍST DALŠÍ" (JS-only
odlišení, pro scraper irelevantní — server i tak podporuje `&page=N`).

### Přesné query parametry pro server-side filtrování (z HTML formuláře)
Zdrojový kód vyhledávacího formuláře odhalil skutečné `name=` atributy
posílané na server — scraper je může použít místo stahování všeho a
filtrování až v Pythonu:
```
AccType=2|3|6|7|8|11|18|25|27        # Chaty a chalupy (pipe-oddělený seznam kódů typu objektu)
AccType=1|4|5|10|12|18|24            # Apartmány
AccType=9|13|17|19|20|21|22|23|24    # Penziony a hotely
LastMinute=true
EquipmentPets=true                   # domácí zvíře
EquipmentInternet=true
EquipmentBicyclesStorage=true        # úschova kol/lyží
EquipmentSwimmingPoolOutdoor=true
EquipmentWhirpool=true               # vířivka
EquipmentSauna=true
EquipmentFireplaceIndoor=true
EquipmentFireplaceOutdoor=true       # zahradní krb/grill
EquipmentFridge=true
EquipmentTv=true
EquipmentRestaurant=true
EquipmentWheelChairAccessible=true
EquipmentChildernActivities=true     # POZOR: překlep v názvu portálu ("Childern"), nutno použít přesně takto
EquipmentObjectWithoutOwner=true     # objekt bez majitele
EquipmentSolitude=true               # samota/polosamota
EquipmentBathingBarrel=true          # koupací sud
EquipmentOutdoorSeating=true
EquipmentFishing=true                # rybaření v místě
Fencing=3                            # částečně oplocen
Fencing=4                            # zcela oplocen
BedroomsCount=2/3/4/5/6/7/8/9         # "N a více" ložnic
Bathing=1/3/5/10/20/30                # vzdálenost ke koupání v km
Skiing=1/3/5/10/20/30                 # vzdálenost k lyžování v km
```
**Poznámka k `balkon/terasa`**: objevilo se ve výsledcích jednoho dotazu
v sidebaru, ale nebylo vidět ve zdrojovém formuláři vybavení — možná
patří pod jiný název parametru, nebo je vázané na konkrétní kategorii.
Nutno ověřit, pokud bude potřeba filtrovat právě podle něj.

**IMPLEMENTACE: `AccType=2|3|6|7|8|11|18|25|27` ("Chaty a chalupy") se
posílá NAPEVNO v `chata_cz.py`, není odvozené od `criteria`.** Portál
kromě chat/chalup nabízí i apartmány/penziony/hotely/ATC, což je mimo
scope projektu (viz sekce 1 — projekt cílí jen na chaty/chalupy) — bez
tohohle filtru by se do výsledků míchaly i jiné typy ubytování. Stejný
princip jako u e-chalupy, kde tohle omezení dělá už samotný portál (celý
web je jen chaty/chalupy, žádný extra filtr nebyl potřeba).

### `distributePersons`/`hasPrice` — spolehlivý signál typu ceny (lepší než heuristika)
Na detailu nabídky jsou hidden inputy:
```html
<input type="hidden" id="distributePersons" value="false" />
<input type="hidden" value="true" id="hasPrice"/>
```
`distributePersons=false` + `hasPrice=true` = objekt má jednu propočítanou
cenu automaticky (i bez zadaného termínu se dopočítá k nejbližšímu volnému
datu). `distributePersons=true` (pozorováno nepřímo u objektů s více
pronajímatelnými pokoji/apartmány) = nutno vybrat konkrétní pokoj(e), než
se cena spočítá — karta pak místo ceny ukazuje "Pro výpočet ceny či
rezervaci je potřeba vybrat konkrétní pokoj(e)."
**Doporučení**: použít `distributePersons` jako primární, spolehlivý
signál pro `Listing.entire_property`/typ ceny, místo textové heuristiky
(analogie k `units`-based heuristice u e-chalupy, ale tady je to čistá
booleovská hodnota přímo v HTML).

**IMPLEMENTACE: `distributePersons`/`hasPrice` existují VÝHRADNĚ na
detailu nabídky, ne na kartě výpisu** — ověřeno prohledáním celé stránky
výpisu (33 karet, Šumava): nula výskytů. Karta samotná tenhle signál
nemá vůbec. `chata_cz.py` proto pro `entire_property` dotahuje detail
stránku KAŽDÉ jednotlivé nabídky zvlášť (přes `detail_objekt_url_*`
hidden input, viz níže) — o(N) requestů navíc oproti hlavnímu dotazu.
Přijatelné vzhledem k malým objemům na chata.cz (desítky nabídek na
region, ne stovky/tisíce jako u e-chalupy), ale je to jiný nákladový
profil než enrichment vybavení (ten je o(počet druhů vybavení), ne
o(počet nabídek)).

### Odznaky (badges) — kompletní přehled CSS tříd
- `indicator-green` — AKCE (zvýhodněná cena při menším obsazení, nebo
  mimosezónní sleva při obsazení celé chaty — text v `title` atributu
  se liší case by case, vždy ho číst, ne jen třídu)
- `indicator-darkgreen` — NEW ("Novinka")
- `indicator-blue` — TIP ("Doporučujeme")
- `indicator-red-lm` — Last minute, text obsahuje i procento slevy
  (např. `LM - 10%`, `LM - 25%`)

### Past: interní GTM kategorie NENÍ spolehlivý typ objektu
V `dataLayer.push` pro Google Analytics má každá nabídka `category`
(`CH-CH` nebo `H-P`) a `brand` (např. `chata`, `chalupa`, `apartmany`).
**Nekorespondují spolehlivě s názvem ani typem objektu** — např. "Chata
Zadov" (chata s bazénem) měla `category: 'H-P'`, ne `'CH-CH'`. Nepoužívat
tohle jako zdroj pravdy o typu objektu, držet se `AccType` filtru/kódu
nebo skutečného obsahu nabídky.

### Recenze a hodnocení — vědomě NEPARSOVAT do detailu
Projekt recenze ani podrobné hodnocení nepotřebuje. Stačí zůstat u
základního čísla a slovního hodnocení z karty (`sec-hodnoceni` blok,
sekce výše — `modry_box`/`no_text` varianty), bez further parsování
jednotlivých recenzí, jmen recenzentů, kladů/záporů apod.

### URL nejednotnost detailu nabídky — VYŘEŠENO přes hidden input
Detail nabídky má nejednotný URL prefix — někdy `/chalupa/<region>/<obec>/...`,
jindy `/ubytovani/<region>/<obec>/...` ve stejném výpisu regionu. **Past:
nestavět URL ručně podle vzoru.** Řešení: každá karta (`div.product`) má
skrytý input s hotovou, kompletní detail URL včetně termínu:
```html
<input type="hidden" id="detail_objekt_url_24481"
       value="https://www.chata.cz/chalupa/sumava/srni/horska-chata-samoobsluzny-hotel-vydra-CZ8695/?FromDate=30.07.2026&ToDate=02.08.2026&Kids=&Adults=4&KidsCount=0&GuestsType=TwoAdults&RoomAmountType=More">
```
Stačí přečíst hodnotu tohoto inputu, žádné hádání prefixu.

### Struktura jedné karty (`div.product`) — pole a selektory
- **Kód objektu a název**: `<a class="ppv" id="odkaz_CZ8695">Název</a>
  <span>(CZ8695)</span>` — kód lze číst i z `id` atributu (`odkaz_` +
  kód), dva nezávislé zdroje pro validaci. Prefix `CZ`/`SK` rozlišuje
  ČR/Slovensko (projekt chce oboje).
- **Lokalita**: `<p><img ...placeholder-filled-point.png"><span>
  <a href="/ubytovani/<region>/<obec>/...">Obec</a>, <a href="...">Region</a>
  </span></p>` — obec i region jako samostatné odkazy.
- **Vybavení — ikony**: potvrzené univerzální pravidlo napříč VŠÍM
  vybavením: soubor s `_disabled` sufixem v názvu = "Ne"/"zakázáno",
  bez sufixu = "Ano"/"povoleno". Např. `zvire.png` (pes povolen) vs.
  `zvire_disabled.png` (pes zakázán). Platí pro: zvíře, internet, bazén,
  vyžití pro děti, lyžárna/kolárna, parkování, povlečení, oplocení.
  - **Bonus**: kde je vedle ikony i ikonka "Upřesnění" (`mark.png`), její
    `data-tooltip` atribut obsahuje doplňující text v lidské řeči, např.
    `"parkování přímo před zámkem zdarma"`, `"Kolárna pod kamerovým
    systémem"`, `"zdarma"` (povlečení), `"zcela oplocen"`/`"bez
    oplocení"`. Ukládat do `raw_extra`, ať se neztratí.
- **Kapacita**: `<div class="sec-kapacita">Max. kapacita:<br>31</div>`.
- **Cena a jednotky (`sec-rooms`/`sec-price`)** — analogie k `units` u
  e-chalupy: jeden objekt může mít VÍC bloků `sec-price`, každý s vlastním
  `roomID`, názvem typu pokoje/apartmánu (`Rodinný byt`, `Zelený apartmán
  pro 3-4 osoby`...), cenou a dostupností (`X volný`/`X volné`). Možný
  zdroj pro budoucí `likely_apartment` heuristiku (viz e-chalupy, sekce 4).
  Cena bez termínu chybí (viz výše).
- **Hodnocení — DVĚ varianty stejného bloku** (`sec-hodnoceni`):
  - Bez recenzí: `<div class="no_text">Dosud nehodnoceno</div>`
  - S recenzemi: `<div class="modry_box"><span>9,5</span></div>` +
    `<span class="txt_hodnoceni">Fantastické</span>` + odkaz
    `dle N hodnocení`. Model/parser musí počítat s oběma tvary.
- **Odznaky**: `NEW`, `AKCE` (s tooltipem vysvětlujícím proč — např.
  "Při obsazení objektu menším počtem osob, než je celková kapacita,
  platí zvýhodněná cena.") — dobré pro `raw_extra`.

### Sidebar — facetový filtr per-region/per-dotaz s počty
Každý výpis (region i fulltextový dotaz) má sidebar s checkboxy a počtem
nabídek v závorce za každou položkou — užitečné pro rychlou kontrolu
pokrytí bez nutnosti stahovat vše:
- Typ objektu (Chaty a chalupy/Apartmány/Penziony a hotely/Rekreační
  střediska a ATC)
- Obsazenost (Online obsazenost/Jen volné objekty)
- Vybavení objektu (dlouhý seznam: pes, internet, úschova kol/lyží,
  venkovní bazén, vířivka, sauna, vnitřní krb, zahradní krb/grill,
  lednice, TV, klimatizace, restaurace v objektu, bezbariérový objekt,
  vyžití pro děti, objekt bez majitele, samota/polosamota, koupací sud,
  venkovní posezení, rybaření v místě, balkon/terasa)
- Oplocení (částečně/zcela)
- Počet ložnic (1 / 2 / 3 a více / 4 a více / 5 a více)
- Sport: Koupání a Lyžování (dle vzdálenosti v km)
- Obce v regionu se seznamem a počtem nabídek (užitečné pro
  `location_prefiltered` logiku, analogicky k e-chalupy sekci 4)

### Detail stránky nabídky — navíc oproti kartě
Textové Ano/Ne hodnoty (ne jen ikony) pro Internet/Zvíře/Parkování (i s
počtem míst)/Bazén/Vyžití pro děti/Lyžárnu-kolárnu/Povlečení (zdarma/za
poplatek)/Oplocení (částečně/zcela), GPS souřadnice, kraj/okres, popis
místností, poplatky (rekreační poplatek, kauce, parkovné), vzdálenosti
k restauraci/obchodu/lyžování/koupání, popis lokality a výletů v okolí —
hodně strukturovaných dat, vhodné do `raw_extra`.

### TODO ověřit doma — VÝSLEDKY (ověřeno 29. 7. 2026, viz i `chata_recon.py`
v scratchpadu, ad-hoc skript, nepatří do repa)

1. ~~Ověřit, jestli `Autocomplete/<text>` funguje i BEZ cookies/session~~ —
   **VYŘEŠENO, funguje.** Čistá `requests.Session()` bez jakýchkoli cookies
   dostala `200` a validní JSON (ověřeno na `Autocomplete/Sumava`, potvrdilo
   se i `LocationId=49`/`LocationType=6` pro region Šumava). Žádný auth
   token ani speciální session není potřeba.
2. ~~Zjistit přesný formát odpovědi při stránkování `&page=N`~~ —
   **VYŘEŠENO**, viz sekce výše. `&page=N` je normální GET parametr,
   `totalitems` dává celkový počet na první stránce.
3. ~~Ověřit textové pokrytí vířivka/sauna/krb na reálném vzorku dat~~ —
   **VYŘEŠENO: textové/ikonové pokrytí je prakticky NULOVÉ, stejná past
   jako u e-chalupy (sekce 4).** Karta výpisu (`sec-ikonky` blok) má ikony
   jen pro: zvíře, internet, vyžití pro děti, bazén, lyžárna/kolárna,
   parkování, povlečení, oplocení — **vířivka/sauna/krb (vnitřní ani
   venkovní) v `sec-ikonky` NEJSOU vůbec**. Jediné textové výskyty těchto
   slov na kartě pocházejí z `alt` atributů fotogalerie (popisky
   jednotlivých fotek jako "Finská sauna", "Obývací pokoj s krbem") —
   na Šumavě (33 nabídek, sidebar: vířivka 3, sauna 8, vnitřní krb 15,
   zahradní krb 26) to dalo jen 1/3 vířivka, 7/8 sauna, 9 objektů s "krb"
   v textu. **Nepoužitelné jako spolehlivý signál.**
   **Řešení (potvrzeno, přesná shoda s sidebarem): server-side query
   parametry** `EquipmentWhirpool=true`, `EquipmentSauna=true`,
   `EquipmentFireplaceIndoor=true`, `EquipmentFireplaceOutdoor=true`
   (názvy viz seznam parametrů výše v sekci 5) — dotaz s každým z nich
   vrátil `totalitems` přesně 3 / 8 / 15 / 26, tedy 100% shoda se
   sidebarem. **Profil `chata_cz.py` musí vířivku/saunu/krb obohacovat
   přes samostatné `Equipment*=true` dotazy, úplně stejně jako e-chalupy
   dělá s `filters=<id>` pro ID-only vybavení (sekce 4) — ne parsováním
   karty.** Totéž pravděpodobně platí i pro další vybavení bez ikony v
   `sec-ikonky` (např. restaurace, klimatizace, samota) — při psaní
   profilu ověřit každé zvlášť, nepředpokládat pokrytí.
4. ~~Zjistit, jestli existuje limit na počet výsledků na jeden dotaz~~ —
   **VYŘEŠENO: žádný pozorovaný strop, objem je řádově menší než u
   e-chalupy.** Napříč všemi 80 regiony (`LocationType=6`) součet
   `totalitems` je jen ~1158 nabídek celkem, největší jednotlivý region
   (Jeseníky) má 89 (další v pořadí: Krkonoše 78, Slovácko 74, Jižní
   Čechy 72, Beskydy a Valašsko 65). `PageSize=100` i `PageSize=1000` na
   Jeseníkách vrátily korektně přesně všech 89 karet v jednom requestu
   bez tichého ořezání, stránkování `page=N` sedí přesně (poslední
   stránka `page=9` při `PageSize=10` = objekty 81-89 z 89).
   **Region jako povinný vstup zůstává** — ne kvůli limitu (ten tu
   prakticky neexistuje), ale **kvůli konzistenci s e-chalupy profilem**
   (stejné UX, stejná struktura `search(criteria)` s lokalitou jako
   klíčovým parametrem) a protože fulltextová varianta bez
   `Autocomplete.LocationId` (viz výše) je nekontrolovaná.
5. ~~Otestovat, jestli GitHub Actions runner dostane 403~~ —
   **VYŘEŠENO: NEDOSTANE, chata.cz Actions neblokuje.** Ověřeno dočasným
   workflow (`test-chata-cz.yml`, smazán po ověření) spuštěným naostro na
   GitHub Actions runneru — 4 testované requesty (homepage, přímo
   `AutocompleteRegions`, `Autocomplete/Sumava`, `vyhledavani/` s reálnými
   parametry pro Šumavu) všechny vrátily `200`. **Na rozdíl od
   e-chalupy.cz (sekce 4, 403 Forbidden) chata.cz profil MŮŽE běžet přímo
   v GitHub Actions přes `workflow_dispatch`, lokální spouštění není
   potřeba.** Zatím netestováno: jestli 200 vydrží i při vyšší frekvenci/
   objemu requestů (celý region s obohacením vybavení = víc requestů za
   sebou) — ověřit při prvním ostrém běhu profilu.
6. **HTML jedné karty přes DevTools Copy outerHTML** (ne jen fetch/
   screenshot) — pro přesné CSS selektory k `sec-hodnoceni`/`sec-rooms`/
   `sec-ikonky` blokům, obzvlášť variantu s hodnocením (zatím vidět jen
   z jednoho konkrétního příkladu). *(Stále otevřené — dnešní recon
   ověřoval `sec-ikonky` skriptem/regexem, ne ručním DevTools výpisem.)*
7. Ověřit `LocationType` hodnoty systematicky (víme jistě: 6=region,
   4=obec/část obce, 3=okres — chybí případně kraj, pokud existuje
   samostatně). *(Stále otevřené.)*

**Vedlejší objev cestou**: `combined_ca.pem` (Avast SSL interception bundle,
viz sekce 3) byl zastaralý — Avast si mezitím otočil root certifikát a starý
bundle přestal fungovat i pro e-chalupy.cz. Přegenerován z aktuálních Avast
root certů (bylo jich v cert store 5, různé thumbprinty, všechny platné do
2040 — přidány všechny) + certifi. Pokud se `SSLCertVerificationError`
objeví znovu i po nastavení `REQUESTS_CA_BUNDLE`, nejdřív zkontrolovat, jestli
bundle sám není zastaralý (test na známém funkčním hostu jako e-chalupy.cz),
ne rovnou hledat chybu jinde.

## 6. Obecné technické konvence napříč projektem

### Datový model (`scraper/models.py`)
`Listing` dataclass: `source, title, location, url` (povinné),
`capacity, bedrooms, price, price_unit, amenities (list), image_url,
raw_extra (dict), entire_property (bool|None), likely_apartment (bool)`.
`raw_extra` slouží jako "odkladiště" pro portál-specifická data, co se
nehodí do hlavního modelu (např. `area2_title`, `tags` surová data,
u chata.cz např. `roomID`/tooltip texty vybavení).

### Filtrování — princip "chybějící pole neblokuje"
`filters.py` je navržený tak, že pokud nabídka nemá vyplněné nějaké pole
(kapacita, cena...), **projde filtrem** místo aby byla vyřazena. Důvod:
raději zobrazit nabídku s neúplnými daty, než ji ztratit kvůli chybějícímu
poli, které daný portál nemusí vždy poskytovat. (U chata.cz to bude
zvlášť relevantní pro cenu, viz sekce 5.)

### Profil portálu — kostra
Každý portál = vlastní soubor v `scraper/profiles/<nazev>.py` s funkcí
`search(criteria: dict) -> list[Listing]`. Registrace v
`scraper/profiles/__init__.py` (`ALL_PROFILES` seznam). Šablona/vzor v
`scraper/profiles/_template.py`. `scraper/main.py` volá všechny profily
v `try/except` (chyba jednoho portálu nesmí spadnout celý běh, chyby se
sbírají do listu a ukládají do výsledného JSON).

### Frontend struktura
- `docs/index.html` — formulář (lokalita, dual-range slidery pro kapacitu
  a ložnice, max cena, checkboxy "Jen celé objekty" a "Skrýt pravděpodobné
  apartmány" mimo `.amenity-group`, tři `<fieldset class="amenity-group">`
  sekce: Vnitřní vybavení / Venkovní vybavení / Další).
- `docs/app.js` — načítá `results/latest.json` přes
  `raw.githubusercontent.com/Nojmi/Chalupnik/main/results/latest.json`
  (ne relativní cestu — Pages servíruje jen `/docs`, `results/` je mimo,
  proto raw GitHub URL s permissivním CORS). Veškeré filtrování na
  klientovi (substring match pro vybavení, rozsahy pro kapacitu/ložnice/
  cenu, booly pro entire_property/likely_apartment).
- `docs/style.css` — vlastní design tokeny (CSS custom properties), viz
  barvy v sekci 2 výše. Signature vizuální prvek: náhodně generovaná SVG
  "hřebenová" linka (siluetа hor) nad každou kartou výsledku.
- Dual-range slidery (kapacita, ložnice): dva překrývající se
  `<input type="range">`, žádná externí JS knihovna, vlastní CSS styling
  přes `::-webkit-slider-thumb`/`::-moz-range-thumb`.

### GitHub Actions workflow (`.github/workflows/scrape.yml`)
`workflow_dispatch` s inputs: location, min_capacity, min_bedrooms,
max_price, amenities (čárkou oddělený seznam), date_from, date_to.
Spouští `python -m scraper.main` (DŮLEŽITÉ: `-m` modul syntax, ne
`python scraper/main.py` — bez toho padá `ModuleNotFoundError: No module
named 'scraper'`, protože skript-jako-soubor přidá do sys.path svou
vlastní složku, ne kořen repa). `permissions: contents: write` pro commit
zpátky do repa. Po scrapu commituje `results/latest.json` jen pokud se
změnil (`git diff --staged --quiet || git commit ...`).

### Řešené bugy (pro poučení, ať se neopakují)
1. **Import chyba v Actions**: `python scraper/main.py` → `python -m
   scraper.main` + chybějící `scraper/__init__.py` (musel existovat, i
   prázdný, aby Python poznal balíček).
2. **Location filtr nuloval všechny výsledky**: `filters.py` dělal
   substring match lokality proti konkrétní obci, i když profil už
   lokalitu vyřešil přes URL/API — dvojí filtrování se navzájem bilo.
   Oprava: `location_prefiltered` flag/podobný mechanismus, aby se
   nekontrolovalo znovu, co už bylo vyřešeno na úrovni profilu.
3. **CSS přetékání**: popisek "Min. ložnic" přetékal mimo panel do karet
   — opraveno přidáním `min-width: 0` na grid items + zkrácení textu na
   "Ložnice"/"Osob".
4. **Frontend checkbox omylem počítaný jako "vybavení"**: při přidávání
   nových checkboxů (entire-property, hide-apartments) je nutné je umístit
   MIMO `.amenity-group` div, jinak je JS selektor pro vybavení sebere
   omylem jako další položku vybavení k filtrování.

## 7. Co zbývá udělat

- [x] Dokončit chata.cz: doladit "TODO ověřit doma" ze sekce 5, pak
      napsat `scraper/profiles/chata_cz.py` a otestovat end-to-end.
      (Hotovo, otestováno lokálně na Šumavě a Krkonoších.)
- [ ] chata.cz — implementovat `likely_apartment` heuristiku (analogicky
      k e-chalupy), zatím vždy `False`; narazili jsme na apartmánové
      objekty schované v kategorii Chaty a chalupy, stejně jako u
      e-chalupy.
- [ ] hauzi.com, chatyachalupy-chatar.cz, alkatravel.cz, zars.cz
- [ ] Rozhodnutí o proxy službě pro e-chalupy.cz na GitHub Actions
      (odloženo, čeká na zjištění, jestli mají stejný 403 problém i
      další portály — chata.cz NEMÁ tenhle problém, viz sekce 5, takže
      proxy je potřeba jen pro e-chalupy.cz)
- [ ] Případně: tlačítko na frontendu pro přímé spuštění GitHub Actions
      bez nutnosti přecházet na GitHub (odloženo, nice-to-have)
- [ ] Zvážit vlastní ikonu/favicon (icons8-cabin-64) — Nojmi měl soubor
      ve Windows Downloads, cesta nebyla dosud ověřena/dokončena (STAV
      NEJASNÝ — možná už hotovo, možná ne, zkontrolovat).

## 8. Obecná doporučení pro práci na dalších portálech

Při přidávání nového portálu (viz i README "Přidání nového portálu"):
1. Získat od Nojmiho screenshot vyhledávacího formuláře, screenshot
   výpisu výsledků (ideálně s konkrétním vyhledáním), a HTML jedné karty
   z DevTools.
2. **Prověřit, jestli existuje JSON API** podobně jako u e-chalupy.cz
   (Network tab → Fetch/XHR filtr → scrollovat/stránkovat a sledovat,
   jestli se objeví strukturovaný datový endpoint) — je to spolehlivější
   než HTML scraping, pokud existuje. U chata.cz se ukázalo, že i bez
   plnohodnotného JSON API pro výpis mohou existovat užitečné pomocné
   JSON AJAX endpointy (např. pro překlad lokalita→ID) — stojí za to je
   hledat i tam, kde hlavní výpis JSON API nemá.
3. **Ověřit textové pokrytí KAŽDÉHO vybavení na reálném vzorku dat** před
   tím, než se checkbox přidá do frontendu — nepředpokládat, že vybavení
   bude v textu, může to být jen server-side ID filtr (viz sekce 4).
4. **Zkontrolovat, jestli portál má limit na počet výsledků na jeden
   dotaz** (podobně jako Elasticsearch strop 10 000 u e-chalupy.cz) — může
   to určit, jestli lokalita/region musí být povinný vstup.
5. Otestovat lokálně end-to-end (`python -m scraper.main`) před
   commitnutím, včetně edge casů (žádná lokalita, nesmyslná lokalita).
6. Zvážit, jestli je nutné SSL/Avast obcházení i pro nový portál (mělo by
   být, je to systémová věc na úrovni Windows/Pythonu, ne specifická pro
   e-chalupy.cz).
7. Testovat na víc než jedné lokalitě/scénáři, ne se spokojit s jedním
   šťastným případem.
8. Pokud portál blokuje GitHub Actions (403), zdokumentovat to stejně
   jako u e-chalupy.cz a zvážit lokální spouštění jako fallback.
9. Skryté inputy s hotovými URL/hodnotami (jako `detail_objekt_url_*` u
   chata.cz) jsou spolehlivější zdroj dat než stavění URL/hodnot ručně
   podle pozorovaného vzoru — pokud existují, vždy je přednostně použít.
