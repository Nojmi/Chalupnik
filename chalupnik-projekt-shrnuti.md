# Chalupník — shrnutí projektu (stav k 29. 7. 2026)

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

Prioritní zdroje: e-chalupy.cz (hotovo), chata.cz (hotovo), cs-chalupy.cz
(hotovo, viz sekce 6), hauzi.com, chatyachalupy-chatar.cz, alkatravel.cz,
zars.cz.
Booking.com/Airbnb/Facebook skupiny jsou záměrně vyřazené (anti-bot ochrana,
smluvní zákazy, žádné API).

## 2. Architektura (zdůvodnění + jak zapadá dohromady)

| Komponenta | Řešení | Proč |
|---|---|---|
| Spouštění scraperu | GitHub Actions, `workflow_dispatch` (ruční) | Jediný způsob, jak GitHub Pages "spustit backend" — Pages sám kód nespouští |
| Scraping | Python (`requests`+`BeautifulSoup`, nebo přímé JSON API pokud existuje) | Viz sekce 4 — u e-chalupy.cz se ukázalo JSON API lepší než HTML parsing |
| Filtrování | Dvouvrstvé: server-side (při scrapingu) + client-side (`docs/app.js` nad staženými daty) | Viz sekce 7 — rozhodli jsme se přesunout co nejvíc filtrů na client-side |
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
- **Firemní síť blokuje git protokol (klonování, push) i přímé přihlašování
  na cs-chalupy.cz** (viz recon sekce 6) — v práci proto probíhá jen
  prohlížení/recon přes prohlížeč (kde síť funguje normálně), žádné
  programování ani git operace. Zkoušené obchozí cesty (Claude Desktop
  appka Code tab, github.dev, Codespaces) narazily na stejnou síťovou
  blokaci na úrovni gitu — funkční jen `Download ZIP` přes prohlížeč jako
  read-only obchvat pro nouzové prohlížení kódu v práci.

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
- **Doplňkový nález**: portál má i interní JSON endpoint používaný pro
  infinite-scroll donačítání (`/vyhledavani/properties?destinations=...&limit=60&offset=60`)
  — funguje stejně jako hlavní `api-pub.e-chalupy.cz/properties` endpoint,
  jen jinou cestou; stránkuje přes `offset` navyšovaný o `limit`.

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

### GitHub Actions — 403 Forbidden (stav k 27.–28. 7. 2026: BLOKOVÁNO,
### řešeno lokálním spuštěním; stav k 29. 7. 2026: PŘESNĚJI
### DIAGNOSTIKOVÁNO A OBEJITO, viz aktualizace níže)
- Portál e-chalupy.cz **blokuje požadavky z GitHub Actions runnerů**
  (403 Forbidden) — i po vylepšení HTTP hlaviček na realistický Chrome
  User-Agent + Accept/Accept-Language/Accept-Encoding. Lokálně (domácí IP)
  identický požadavek funguje bez problémů.
- **Diagnóza (tehdejší)**: pravděpodobně IP-based blokace (GitHub Actions
  běží na známých Azure/Microsoft cloudových IP adresách, které anti-bot
  systémy často blokují plošně, bez ohledu na hlavičky).
- **Řešení tehdy zvolené**: spouštět e-chalupy.cz **lokálně** (na domácím
  PC Nojmiho), ne přes GitHub Actions. Postup zdokumentován v README.
- Zvažovaná, ale nikdy neimplementovaná alternativa: rezidenční proxy
  služba (aby GitHub Actions vypadal jako domácí IP), $1-5/měsíc. Ukázalo
  se zbytečné, viz aktualizace níže — proxy nakonec nebyla potřeba.
- Bonus objev cestou: `Accept-Encoding: br` (Brotli) v hlavičkách vyžaduje
  mít nainstalovaný balíček `brotli` (přidán do `requirements.txt`), jinak
  `requests` tiše vrátí porušený/nedekódovaný obsah (status 200, ale 0
  nalezených karet — TICHÁ chyba, žádná exception).

**AKTUALIZACE 29. 7. 2026 — přesnější diagnóza, 403 obejito pro
nejčastější lokality:**

Při vyšetřování jednoho konkrétního Actions běhu (run `30466427760`),
kde e-chalupy.cz vrátilo podezřele málo nabídek (434 místo očekávaných
~1000+ pro Šumavu) navzdory 0 chybám v logu, jsme nejdřív mylně
podezírali poškozené kódování `CRIT_LOCATION` (diakritika v env
proměnné). **Tahle domněnka se ukázala jako mylná** — ověřeno na
úrovni syrových bajtů v commitnutém `results/latest.json` i v
Actions logu (`CRIT_LOCATION: Šumava` se zobrazovalo správně) — šlo
jen o artefakt nespolehlivého zobrazování non-ASCII znaků v lokálním
bash terminálu při diagnostice, ne o skutečnou chybu v datech.

**Skutečná příčina**: 403 blokace pořád reálně existuje, ale je
**užší, než jsme si mysleli** — týká se jen `e-chalupy.cz/<slug>` HTML
stránky, kterou `_resolve_area_id()` používá k překladu textu lokality
na interní `area_XXXXX` kód (viz sekce výše). **Hlavní datové API
(`api-pub.e-chalupy.cz/properties`) 403 nedostává a z Actions funguje
bez problémů** — proto v tom podezřelém běhu žádná výjimka nespadla:
`search()` má už z dřívějška vestavěný tichý fallback (žádný area kód
→ hledej celostátně bez `destinations` filtru), takže se to neprojevilo
jako chyba, jen jako neúměrně málo výsledků po client-side location
filtru (nabídky ze všech krajů ČR, ne jen ze Šumavy). Přidali jsme
diagnostický log (`scraper/profiles/e_chalupy.py`, `_resolve_area_id`)
na stderr pro tenhle konkrétní selhávající krok, což tohle přesně
potvrdilo (`[e-chalupy.cz] area lookup pro 'sumava' selhal (HTTP 403)`).

**Řešení: `STATIC_AREA_IDS`** — v `e_chalupy.py` přidána
předresolvovaná tabulka slug → area_id pro 11 "oblíbených destinací"
z hlavní navigace portálu (Šumava, Jeseníky, Beskydy, Krkonoše, Jižní
Morava, Český ráj, Jizerské hory, Jižní Čechy, Krušné hory, Vysočina,
Orlické hory) — resolvováno ručně z domácí sítě, kde blokace neplatí.
`_resolve_area_id()` tuhle tabulku zkontroluje PŘED živým HTML
dotazem, takže pro těchto 11 regionů se blokovaný endpoint vůbec
nevolá — funguje to jak lokálně (rychlejší, o 1 request méně), tak na
Actions (obchází 403 úplně). Pro lokality mimo seznam zůstává živé
resolvování jako fallback (na Actions dál degraduje na celostátní
hledání + diagnostický log, lokálně funguje normálně).

**Ověřeno end-to-end na živém Actions běhu** (`30471567220`, po
nasazení opravy): žádný 403 v logu, `Wrote 1047 listings` — **přesná
shoda s lokálním referenčním během** (909 e-chalupy.cz + 22 chata.cz +
116 cs-chalupy.cz). **Závěr: e-chalupy.cz teď může běžet plně
automatizovaně přes GitHub Actions `workflow_dispatch` bez lokálního
zásahu — ale JEN pro těch 11 pokrytých regionů.** Lokalita mimo tenhle
seznam se na Actions pořád tiše degraduje na celostátní fallback (nižší
relevance, ne chyba/pád) — při zadávání nové/neobvyklé lokality přes
workflow_dispatch je lepší běh zkontrolovat (stderr log v Actions) nebo
tabulku rozšířit o další resolvovaný region.

**Historický kontext zůstává platný**: 403 blokace v době prvního
zjištění (červenec 2026) byla reálná a plošná (blokovala tehdy
testované requesty vůbec, ne jen tenhle jeden HTML endpoint) — možné
vysvětlení rozdílu je, že šlo o dočasnou/IP-rozsahovou blokaci, která
se od července nějak zúžila/změnila, nebo že tehdejší testy cílily
právě na tenhle konkrétní HTML endpoint a hlavní API se tehdy netestovalo
zvlášť. Nelze s jistotou říct, jestli se blokace časem zmírnila, nebo
jsme ji jen teď lépe izolovali na správnou příčinu — do budoucna sledovat,
jestli se 403 neobjeví i na `api-pub.e-chalupy.cz` (zatím ne).

**Ověřeno i na druhém regionu (Krkonoše, 29. 7. 2026)**: čerstvý
`workflow_dispatch` běh (`30472565045`) s `CRIT_LOCATION=Krkonoše` proběhl
bez 403, `Wrote 1293 listings` ze všech tří portálů, žádný lokální zásah.
Potvrzuje to, že oprava funguje spolehlivě napříč regiony z tabulky
`STATIC_AREA_IDS`, ne jen na Šumavě, kde se testovala poprvé.

### Jak spustit e-chalupy.cz (a celý scraper) — lokálně i na Actions
Pro 11 pokrytých regionů (viz `STATIC_AREA_IDS` výše) stačí spustit
workflow `Run scraper` (`workflow_dispatch`) přímo na GitHub, žádný
lokální zásah není potřeba. Lokální spuštění (všech tří profilů
najednou) zůstává užitečné pro netypické lokality nebo rychlejší
iteraci při vývoji:
```powershell
cd C:\Users\N-noj\Chalupnik
$env:REQUESTS_CA_BUNDLE="C:\Users\N-noj\AppData\Local\Temp\combined_ca.pem"  # nebo aktuální cesta
$env:CRIT_LOCATION="Šumava"
python -m scraper.main
git add results/latest.json
git commit -m "chore: naostro běh e-chalupy.cz + chata.cz + cs-chalupy.cz - <lokalita>"
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
"chybějící pole neblokuje", sekce 7).

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
  pro 3-4 osoby`...), cenou a dostupností (`X volný`/`X volné`). Zdroj pro
  `likely_apartment` heuristiku (viz e-chalupy, sekce 4 a IMPLEMENTACE
  níže). Cena bez termínu chybí (viz výše).

  **IMPLEMENTACE — KRITICKÁ PAST: počet/obsah `sec-price` bloků NENÍ
  stabilní strukturální vlastnost objektu, mění se podle FromDate/ToDate
  v dotazu.** S vyplněným termínem portál bloky přeskládá podle
  dostupnosti/restrikcí PRO TO KONKRÉTNÍ OBDOBÍ, ne podle skutečné
  struktury objektu:
  - Objekt se 4 samostatně rezervovatelnými jednotkami (např. "Chata
    Jawa": Apartmán/Chata/Celý objekt) se s výchozím týdenním termínem,
    kdy je obsazený, zabalí do JEDNOHO řádku `"Termín je obsazen."` —
    vypadá jako single-unit objekt, i když není.
  - Naopak skutečně jednotkový objekt (jeden `sec-price` blok bez
    termínu, např. "Chalupa Cista 76" — "Chalupa pro 11 osob") se může
    s termínem přesahujícím hranici dvou různých restrikčních období
    (jiné "min. nocí" v první a druhé části pobytu) rozštěpit na 2
    `"restricted"` bloky — vypadá jako vícejednotkový, i když je to jen
    artefakt zvoleného data.
  - **Důsledek: `likely_apartment`/jakýkoli signál založený na počtu
    nebo obsahu `sec-price` bloků SE MUSÍ počítat z dotazu BEZ
    `FromDate`/`ToDate`** (samostatný, "strukturální" fetch stejných
    parametrů location/AccType bez termínu — viz
    `_fetch_structural_rooms`/`_apply_likely_apartment` v
    `chata_cz.py`), NIKDY z hlavního date-scoped fetche použitého pro
    cenu/dostupnost. Při jakékoli budoucí úpravě (refaktoring,
    optimalizace requestů) tenhle rozdíl NEMAZAT — bez něj se signál
    náhodně mění podle toho, jaký termín se zrovna poslal.
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

## 6. cs-chalupy.cz — profil (HOTOVO, `scraper/profiles/cs_chalupy.py`
napsán a otestován lokálně na Šumavě — 129 karet, 116 nabídek po
lokálním typovém filtru, 115/116 s dopočtenou cenou)

Recon proběhl výhradně přes screenshoty a HTML dumpy z prohlížeče v práci
(žádné psaní kódu) — stejný vzorec jako u chata.cz v sekci 5. Portál
nebyl v původním seznamu čtyř zbývajících (hauzi.com,
chatyachalupy-chatar.cz, alkatravel.cz, zars.cz), byl objeven a
prozkoumán dodatečně.

### Základní charakteristika
- **Server-rendered HTML, žádné JSON API pro výpis** — potvrzeno
  opakovaně přes Network tab (jen analytická volání `collect`/
  `conversion`/`gtag`, žádný Fetch/XHR se skutečnými daty nabídek).
- Model **"kontakt na majitele bez provize"** (jiný než e-chalupy.cz/
  chata.cz, kde se rezervuje/dotazuje přes portál) — **žádná cena na
  kartě výpisu**, jen odkaz "Ceník ZDE" a tlačítko "Zobrazit kontakty".
- Existuje pomocný AJAX endpoint `/filtrace/?hash=<region>/<typ>&id=<N>`
  (vidět v Network tabu), pravděpodobně jen pro live-update počtů
  v sidebaru vedle checkboxů, ne pro data karet — **neprozkoumáno do
  detailu, nízká priorita, TODO doma pokud bude čas**.
- **Region jako povinný vstup**: 13 regionů ČR + 4 SK + Zahraničí
  (mnohem hrubší dělení než chata.cz ~80 regionů nebo e-chalupy.cz
  desítky lokalit) — mapování název→ID/slug v HTML formuláři
  (`oblast[]` select, hodnoty 3-49 + 57176 pro Zahraničí).
- **Celkový katalog bez filtru**: 2167 objektů napříč celou ČR+SK
  (výchozí vstupní stránka bez filtru) — řádově tisíce, ne desetitisíce
  jako e-chalupy.cz. Pravděpodobně **žádný Elasticsearch-style strop**
  jako u e-chalupy.cz, ale region zůstává povinný vstup kvůli
  konzistenci s ostatními profily a praktičnosti (nikdo nechce
  procházet stovky stránek scraperem pro celý katalog najednou).

### URL struktura — pretty URL + query parametry, KRITICKÁ PAST u typu objektu
Portál kombinuje dva mechanismy:
```
/<region-slug>[,<region2-slug>,...]              # region(y), pretty URL
/<region-slug>/<typ-slug>[,<typ2-slug>,...]      # typ objektu, pretty URL
?p=<N>&of=<celkový_počet>                        # stránkování, query
```

**KLÍČOVÁ PAST: typ objektu přes pretty URL slug `chaty-a-chalupy`
NEFUNGUJE spolehlivě, tiše spadá zpátky na "bez filtru".** Ověřeno
opakovaně na regionu Šumava a západní Čechy:

| URL (typ) | Nalezeno |
|---|---|
| `/sumava-a-zapadni-cechy` (bez typu) | 129 |
| `/sumava-a-zapadni-cechy/chaty-a-chalupy` | 129 (stejné!) |
| `/sumava-a-zapadni-cechy/chaty-a-chalupy,sruby-a-roubenky` | 129 |
| `/sumava-a-zapadni-cechy/chaty-a-chalupy,sruby-a-roubenky,glamping,vinne-sklepy,rekreacni-domy` | 129 |
| `/sumava-a-zapadni-cechy/glamping,vinne-sklepy,rekreacni-domy` (BEZ chaty-a-chalupy/sruby-a-roubenky) | 77 (správně menší) |
| `/sumava-a-zapadni-cechy/glamping` samostatně | 9 (správně) |

**Závěr: slug `chaty-a-chalupy` (a pravděpodobně i `sruby-a-roubenky`)
se serverem nerozpoznává a tiše spadne na "bez filtru typu" = celý
region.** Ostatní typové slugy (`glamping`, `vinne-sklepy`,
`rekreacni-domy`) fungují správně.

**Stejný test s `typ[]=` query parametrem (číselné ID z formuláře)
TAKÉ NEFUNGUJE** přes prostý GET request — vyzkoušeno
`?typ[]=38&typ[]=39&typ[]=41&typ[]=42&typ[]=40` (chata/chalupa/srub/
roubenka/rekreační dům) na `/sumava-a-zapadni-cechy` — číslo se
nezměnilo (pořád 129) a sidebar checkboxy zůstaly neaškrtnuté. Filtr
typu se pravděpodobně aplikuje jen přes JS/AJAX (možná `/filtrace/`
endpoint) nebo POST formulář, ne přes GET query parametry ani pretty
URL segmenty pro `chaty-a-chalupy`.

**ROZHODNUTÍ (schváleno Nojmim): NEŘEŠIT server-side filtr typu vůbec.**
Stáhnout **celý region bez typového filtru** a filtrovat typ **lokálně**
podle textu v `<title>` tagu detail stránky (portál tam kanonicky
zapisuje typ, např. `"...glamping č. 3C-117..."`,
`"...chalupa č. 3C-353..."`) nebo breadcrumb (`<p id="path">...
&gt; <strong>chalupa č. 3C-353</strong></p>`) — spolehlivější než
marketingový název nabídky, protože je to portálem kanonizovaná
kategorie. Konzistentní s principem `likely_apartment` heuristiky
u e-chalupy.cz/chata.cz — nedůvěřovat portálovým server-side filtrům
bez ověření na konkrétních protipříkladech.

**TODO doma**: zkusit v DevTools skutečně KLIKNOUT na checkbox "Chaty
a chalupy" (ne ruční editace URL) a sledovat Network tab — zjistit,
jestli jde AJAX na `/filtrace/`, POST formulář, nebo něco jiného. Zatím
neověřeno, jestli existuje vůbec nějaký funkční způsob server-side
filtrace typu.

Kompletní seznam typů (ze sidebaru, rozbalené "+zobrazit méně",
odpovídá `typ[]=` hodnotám z formuláře):
```
Chaty a chalupy (38 chata, 39 chalupa), Sruby a roubenky (41 srub, 42 roubenka),
Glamping (431), Vinné sklepy (43), Rekreační domy (40),
Apartmány (45), Penziony (44), Farmy (50), Kempy (48), Resorty (49), Ubytovny (47)
```
`typ-a=1` (`name="typ-a"`, ne `typ[]`) = checkbox "sami v objektu" —
samostatný filtr, viz níže.

### Stránkování — vyřešeno
```
?p=<N>&of=<celkový_počet>
```
- `p=` řídí skutečné stránkování (1, 2, 3...)
- `of=` je **celkový počet nalezených objektů pro daný dotaz** (přesně
  odpovídá textu "Nalezené objekty (N)" v HTML) — zůstává STEJNÉ napříč
  všemi stránkami stejného dotazu (ne offset podle stránky, jak se dalo
  původně předpokládat)
- Patička stránky má klasickou číslovanou navigaci (`1 2 3`), poslední
  číslo = poslední stránka, žádná šipka "další" za ní
- **Přesný PageSize neověřen** (odhad ~12-13 karet/stránka podle počtu
  karet na screenshotech, ale nepotvrzeno počítáním) — TODO doma
- **Chování na velkém počtu stránek (desítky+) neotestováno** — TODO
  doma, ověřit na celostátním dotazu bez regionu (2167 objektů,
  odhadem 170+ stránek)
- Doporučený scraper algoritmus: první request bez `p=`/`of=` (nebo
  `p=1`), z HTML vytáhnout "Nalezené objekty (N)" → `total`, iterovat
  `p=2,3,...` s `of=<total>` do konce (nebo dokud stránka nevrátí
  prázdný/kratší seznam karet)

### "Sami v objektu" filtr — NEDOKONČENĚ OVĚŘENO
- `Chaty a chalupy Šumava a západní Čechy` (bez "sami v objektu"): 129
- `Chaty a chalupy Šumava a západní Čechy sami v objektu`: **72**
- Chybí mezistupeň (jen typ "Chaty a chalupy" BEZ "sami v objektu", ale
  BEZ toho matoucího 129 = celý region efektu) na potvrzení přesného
  rozdílu — **TODO doma**, odškrtnout "Sami v objektu" a nechat jen
  "Chaty a chalupy" checkbox, porovnat číslo.
- Poznámka: v kapacitním filtru (`Sami v objektu`, `1-4 osoby`, `5-8
  osob`...) je i **jiná položka "Sami v objektu"**, možná duplicitní/
  alias k `typ-a=1` — ověřit, jestli je to tentýž koncept nebo dva
  různé.

### Struktura karty výpisu (`div.objekt-list`)
```html
<div class="objekt-list ic3"><div class="in">
  <div class="o-foto">...</div>
  <div class="o-content">
    <div class="o-info">
      <p class="rating"><strong><i class="fa fa-star"></i> 9.9</strong>
         <a href="...#hodnoceni">8 hodnocení</a></p>   <!-- volitelné -->
      <p class="silvestr">Silvestr je obsazený</p>      <!-- volitelný badge -->
      <p class="kod">3C-098</p>
      <p class="luzka">max. 14 osob</p>
    </div>
    <div class="ad">
      <h2><a href="...">Název</a></h2>
      <addr>Obec <a href="...#mapa">mapa</a></addr>
      <a class="showKontakt" href="...">Zobrazit kontakty</a>
      <ul>
        <li class="png png-bed">4x</li>          <!-- počet ložnic -->
        <li class="png png-koupelna">4x</li>
        <li class="png png-wc">4x</li>
        <li class="png png-wifi"><strong>Internet ANO</strong></li>
        <li class="png png-dog-no"><strong>Domácí zvíře NE</strong></li>
        <li>Ceník<br/><a href="...#cenik">ZDE</a></li>
      </ul>
    </div>
    <p class="promo">„citace z popisku“</p>
  </div>
</div></div>
```

**Klíčový vzor**: `_disabled`/`-no` sufix konvence = "Ne" (stejný
princip jako `_disabled.png` u chata.cz sekce 5) — `png-dog` = ANO,
`png-dog-no` = NE.

**Chybějící pole = žádná data, NE "NE"** — ověřeno na více kartách:
`png-wifi` `<li>` může úplně chybět (ne jen mít "-no" variantu) —
model musí rozlišovat tři stavy (ANO/NE/chybí), princip "chybějící
pole neblokuje" (sekce 7) platí i tady.

**Region matching past — DVOJITÝ VÝPIS na jedné stránce**: HTML
u regionálních stránek obsahuje **dvě oddělené sekce s vlastním
"Počet nalezených objektů"** — první přesná (odpovídá zadanému
textu), druhá širší regionální (víc karet, částečně překrývající se
s první). Stejný princip jako "location matching" u e-chalupy.cz
(nabídky ze sousedních regionů) — **parsovat jen PRVNÍ/přesnou sekci,
jinak vzniknou duplicity.**

### Struktura detailu nabídky

**Ceník (sekce `#cenik`)** — celý HTML dokument obsahuje VŠECHNY taby
(Ceník/Obsazenost/Popis/Fotogalerie/Mapa/Hodnocení/Okolí/Výlety)
najednou, přepínání je jen CSS/JS zobrazení — **žádné AJAX dotahování
obsahu**, `requests.get()` bez JS renderování by měl vrátit kompletní
ceník i bez zadaného termínu:
```
Základní CENÍK - ceny za ubytování
| Sezóna (název + rozsah dat)     | Cena  | Typ ceny        | Poznámka |
| Vánoce                          | 8500  | Objekt / noc    | Min. nocí: 5 |
| Sezóna LÉTO (červenec-srpen)    | 5000  | Objekt / noc    | Min. nocí: 5 |
| Celoročně                        | 4700  | Objekt / noc    | Min. nocí: 4 |
```
- **Cena NEZÁVISÍ na zadaném termínu** (na rozdíl od chata.cz!) — je
  to fixní sezónní sazba, vždycky přítomná na stránce. **Nepotřebuješ
  posílat `od=`/`do=` do requestu, abys dostal cenu.**
- Počet sezónních řádků je proměnlivý (ověřeno 1 řádek i 9 řádků
  u různých nabídek) — kód musí zvládnout obojí
- **Typ ceny NENÍ konzistentně "Objekt / noc"/"Objekt / víkend" — OPRAVA
  živým fetchem při psaní `cs_chalupy.py`.** Reálně pozorováno napříč
  nabídkami: "Osoba / noc", "Objekt / noc", "Objekt / týden", "Objekt /
  pobyt", "Apartmán / noc", "Přistýlka / noc", "Dítě / noc" — stejná
  komplikace "za osobu" jako u e-chalupy.cz, jen se to nedalo poznat
  z jednoho vzorku v reconu. Profil proto ukládá skutečný text typu
  z portálu do `price_unit`, nepředpokládá pevný formát.
- **KRITICKÁ OPRAVA — "Celoročně" NENÍ spolehlivě hlavní cena.** Původní
  doporučení (použít řádek "Celoročně" jako hlavní `Listing.price`) se
  ukázalo nebezpečné na konkrétním protipříkladu (nabídka 3C-017,
  "Chalupa Šumava - Teplá Vltava - Borová Lada"): jediný řádek se
  sezónou "Celoročně" měl typ "Přistýlka / noc" za 300 Kč (příplatek za
  přistýlku, ne cena pobytu) — naivní výběr by vrátil zavádějící cenu
  300 Kč místo reálné ~1800 Kč/noc za apartmán v sezónních řádcích.
  **Řešení v `cs_chalupy.py` (`_extract_price`)**: řádky s typem
  obsahujícím "přistýlka" nebo "dítě" (vedlejší/doplňkové sazby) se
  z výběru hlavní ceny vyloučí úplně; teprve mezi zbylými kandidáty se
  hledá "Celoročně" → "Mimosezóna" → první platný kandidátní řádek.
  Celý ceník (všechny řádky beze ztráty) jde do `raw_extra["cenik"]`,
  vybraný řádek je jen `Listing.price`/`price_unit`. Poučení: i recon
  z jednoho reprezentativního vzorku může minout okrajový, ale reálný
  případ — ověřovat na víc protipříkladech, stejný princip jako
  `entire_property`/`filters=84` past u e-chalupy.cz (sekce 4) a
  `distributePersons` past u chata.cz (sekce 5).
- Doplňkový ceník (kauce, energie, poplatek za psa, parkovné) →
  `raw_extra`
- Sobota bývá pevný příjezdový/odjezdový den v sezóně (podobný princip
  jako `pobyty jen SO-SO` u chata.cz), textově v poznámce ceníku, ne
  strukturovaně — do `raw_extra`.

**Vybavení (sekce `#popis`) — KLÍČOVÝ POZITIVNÍ NÁLEZ, výrazně lepší
situace než u e-chalupy.cz/chata.cz:**
```
Vybavení objektu - vnitřní: společenská místnost, kachlová kamna,
  internet - wifi, vybavená kuchyně, ..., sauna, TV, ...
Vybavení objektu - venkovní: zahradní nábytek, terasa, ...,
  koupací sud / vířivka, ..., oplocený objekt
```
**Kompletní čárkami oddělený text přímo na detailu, ověřeno na 2
různých typech objektů (chalupa i glamping) s bohatým i chudším
vybavením — konzistentní formát.** Hodnoty přímo odpovídají `<select>`
options z formuláře (`is_vnitrni[]`, `vybaveni_objektu_venkovni[]`,
`is_wellness[]`) → canonicalizace na frontend stringy by měla být
přímočará.

**Tohle znamená JEDNODUŠŠÍ enrichment architekturu, než u ostatních
dvou portálů**: e-chalupy.cz i chata.cz vyžadují samostatné server-side
enrichment requesty (`filters=<id>` resp. `Equipment*=true`) pro
vybavení bez textového pokrytí. **cs-chalupy.cz zatím nevyžaduje
žádný takový enrichment** — jeden fetch detailu = kompletní textové
vybavení. **TODO doma**: ověřit na širším vzorku (víc než 2 nabídky,
ideálně napříč regiony), jestli formát je konzistentně bohatý, nebo
jestli u některých (starších/méně vyplněných) nabídek je řídší.

**JSON-LD strukturovaná data** (`<script type="application/ld+json">`,
`@type: LodgingBusiness`) na KAŽDÉ detail stránce:
```json
{
  "name": "...", "description": "...", "image": "...", "url": "...",
  "address": {"streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry"},
  "geo": {"latitude", "longitude"},
  "telephone": "...",
  "priceRange": "2200 Kč osoba / noc",
  "aggregateRating": {"ratingValue", "reviewCount", "bestRating", "worstRating"}
}
```
Strojově čitelný, `json.loads()` na obsahu — spolehlivější zdroj pro
adresu/GPS/telefon/hodnocení než parsování HTML tabulek/divů.
**DŮLEŽITÁ VÝHRADA: `priceRange` v JSON-LD NEODPOVÍDÁ ceníkové tabulce**
(ověřeno na příkladu: JSON-LD `"2200 Kč osoba / noc"` vs. ceníková
tabulka `4400 Kč Objekt / noc` při kapacitě 2 osoby — JSON-LD si to
přepočítal automaticky na osobu/noc). **NEPOUŽÍVAT JSON-LD `priceRange`
jako zdroj pravdy pro `Listing.price`** — vždy parsovat ceníkovou
tabulku přímo, JSON-LD používat jen pro adresu/GPS/telefon/hodnocení.

**Rozložení ložnic** jako čitelný text (`"2 ložnice: 1x 4, 1x 3+1"`),
kapacity WC/koupelen odděleně, **domácí zvíře má tři stavy** (ANO/NE/
"Pouze po dohodě" — jemnější než binární ikona na kartě), vzdálenosti
(parkování/zastávka/obchod/les/koupání) v metrech, "Členění objektu"
s ikonkami postelí u každé ložnice — vše vhodné do `raw_extra`.

### Rozporná čísla u kombinace typů — vysvětleno past s `chaty-a-chalupy`
Testováno `glamping,vinne-sklepy,rekreacni-domy` (bez chaty-a-chalupy/
sruby-a-roubenky) → 77, samostatně `glamping` → 9. Matematicky
konzistentní (podmnožina). To potvrzuje, že **problém je specificky
u slugu `chaty-a-chalupy`/`sruby-a-roubenky`**, ne obecně u kombinování
víc typů v URL — viz sekce "KLÍČOVÁ PAST" výše.

### Rozhodnutí o strategii stahování (schváleno Nojmim)
Vzhledem k nespolehlivosti server-side typového filtru: **stáhnout
celý region bez filtru typu** a filtrovat lokálně podle:
1. Textu v `<title>` tagu nebo breadcrumb (`<strong>chalupa č. ...`) —
   spolehlivý zdroj typu, portálem kanonizovaný
2. Vyřadit nabídky s jasnými signály nechtěných typů (apartmán,
   penzion, glamping, vinný sklep, farma, kemp, resort, ubytovna) —
   **pozor na false positives** jako "Apartmánová chalupa" (obsahuje
   obě slova) — tohle je case podobný `likely_apartment` heuristice
   u e-chalupy.cz, ne důvod k úplnému vyřazení, spíš k varovnému štítku

### TODO ověřit doma (recon zatím z prohlížeče, žádný kód nenapsán)
1. **Nejdůležitější**: zkusit `?typ[]=` s explicitně JINÝM než
   `chaty-a-chalupy`/`sruby-a-roubenky` typem (např. jen
   `typ[]=431` glamping) a ověřit, jestli aspoň číselné ID `typ[]=`
   funguje pro typy, které fungují i jako pretty URL slug — pomůže to
   rozlišit, jestli je problém v konkrétním slugu, nebo v mechanismu
   `typ[]=` obecně
2. Zkusit v DevTools skutečně kliknout na checkbox "Chaty a chalupy"
   (ne ruční editace URL), sledovat Network tab — AJAX na `/filtrace/`?
   POST formulář? Něco jiného?
3. Dokončit "sami v objektu" test — mezistupeň bez matoucího 129
4. Přesný `PageSize`, chování na velkém počtu stránek (celostátní dotaz)
5. Textové pokrytí vybavení na širším vzorku nabídek (víc než 2)
6. GitHub Actions blokace — netestováno vůbec (na rozdíl od e-chalupy.cz
   a chata.cz, kde už proběhl test)
7. Poloha filtr (`poloha_objektu` — na samotě, u lesa, u jezera...) —
   vědomě odloženo, nízká priorita
8. Ikony na kartě vs. `Domácí zvíře: Pouze po dohodě` — jak se
   "po dohodě" stav zobrazuje na kartě výpisu (jen `png-dog`/
   `png-dog-no`, nebo existuje třetí varianta?) — vědomě odloženo

## 7. Obecné technické konvence napříč projektem

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
zvlášť relevantní pro cenu, viz sekce 5; u cs-chalupy.cz pro
domácí-zvíře třístavový příznak, viz sekce 6.)

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
- **Štítky se statistikou podle zdroje** (přidáno 29. 7. 2026): pod
  hlavním řádkem statistiky (Poslední aktualizace/Lokalita/Nalezeno
  celkem/Zobrazeno) se zobrazují malé pilulky — jedna na každý zdrojový
  portál (`e-chalupy.cz`, `chata.cz`, `cs-chalupy.cz`) s počtem nabídek
  **z aktuálně filtrované sady** (ne z celkového nefiltrovaného datasetu
  — ten zobrazuje progress bar úplně nahoře, ten se touhle změnou
  nedotkl). Počty se přepočítávají live při každé změně filtru, stejně
  jako "Zobrazeno: N". Vizuálně stejný styl jako amenity tagy na
  kartách, používá existující design tokeny z `docs/style.css`.
- **Klikací mapa ČR pro výběr lokality** (`docs/map.js`, přidáno
  29. 7. 2026): `<section class="map-section">` vložená mezi `</header>`
  a `.layout` (celá šířka stránky — postranní panel s filtry je jen
  280px, na čitelnou mapu příliš úzký). SVG s 11 klikatelnými
  `<g class="map-region" data-region="...">` (ilustrativní "shluky
  kopečků" nad mapou, ne skutečné hranice regionů). Pokrývá přesně
  těch **11 regionů sdílených napříč všemi třemi portály** — shodný
  seznam s `STATIC_AREA_IDS` v `scraper/profiles/e_chalupy.py` (sekce
  4): Šumava, Jeseníky, Beskydy, Krkonoše, Jižní Morava, Český ráj,
  Jizerské hory, Jižní Čechy, Krušné hory, Vysočina, Orlické hory.
  - **Aktualizace 29. 7. 2026 (týž den, druhá verze)**: podkladová
    silueta ČR (`<path class="cr-outline">`, jeden zjednodušený
    "mrak" tvar) nahrazena geograficky přesnými hranicemi 14 krajů
    (`<g class="kraj-boundaries">`, 14× `<path class="kraj"
    data-kraj="...">` — 13 krajů + Praha). Souřadnice pocházejí ze
    skutečných hraničních dat (Natural Earth přes
    `@highcharts/map-collection`, použity jen samotné geometrické
    souřadnice hranic, žádný text/branding/kód navíc). Souřadnice 11
    klikacích oblastí (kroužky + popisek) byly přepočítané, aby seděly
    na reálná místa vůči novým hranicím (např. Šumava do jihozápadního
    rohu Jihočeského/Plzeňského kraje, Krkonoše na severní hranici
    Královéhradeckého kraje) — ověřeno i programově (bounding box
    každého kraje vs. střed každé klikací oblasti), sedí na
    odpovídající kraj podle skutečné geografie. `docs/style.css`:
    `.cr-outline` → `.kraj-boundaries .kraj` (14 tenčích 1px hranic
    vedle sebe by s původní 2px tloušťkou působilo přetíženě). **`docs/
    map.js` se touhle změnou vůbec nedotkl** — pracuje čistě přes
    `data-region`/`#f-location`, na tvaru podkladu pod tím mu nezáleží.
  - **Aktualizace 29. 7. 2026 (třetí verze téhož dne)**: klikací
    oblasti přestaly být trojice koleček (`<circle class="hill">`) a
    staly se jedním organickým nepravidelným tvarem na region
    (`<path class="region-patch">`) — protáhlé podél hřebene u
    pásmových oblastí (Krušné hory, Krkonoše, Beskydy), kulatější u
    plošších oblastí (Vysočina, Jižní Čechy, Jižní Morava). **Pokus
    získat oficiální hranice CHKO/NP od AOPK ČR ztroskotal** - jejich
    GIS server blokuje automatizovaný přístup - tvary jsou proto
    ilustrační odhad reálného průběhu pohoří/oblasti, ne právně přesné
    hranice chráněných území. `docs/style.css`: `.hill` →
    `.map-region .region-patch` (poloprůhledné mechové vybarvení,
    `fill-opacity: .55`, hover/aktivní stav → jantarová), popisek
    (`.map-region-label`) dostal `paint-order: stroke` + obrys v barvě
    papíru, aby zůstal čitelný i přes vybarvenou plochu. **`docs/
    map.js` opět beze změny** - stejně jako u kraj-hranic v předchozí
    aktualizaci mu na tvaru klikací plochy nezáleží.
    - **Ověření bez prohlížeče (žádný nebyl po ruce ani tentokrát) —
      geometrická kontrola místo vizuální**: naivní kontrola "leží
      střed plochy uvnitř bounding boxu kraje" ukázala, že 3 z 11
      nových organických tvarů (Krušné hory, Krkonoše, Orlické hory -
      všechny tři severní pohraniční pásma) mají těžiště mimo
      jakýkoli kraj. Přesnější kontrola (rozvinutí skutečných
      kubických Bézierových křivek na mnohoúhelník + vzorkování
      plochy, ne jen jeden bod) potvrdila, že jde o reálný problém, ne
      artefakt měření: tyhle 3 tvary měly jen 3,7–29 % plochy uvnitř
      libovolného kraje (zbytek trčel do prázdného prostoru nad
      hranicí ČR), zatímco zbylých 8 mělo rozumných 57–100 %.
      Opraveno posunem (translace, tvar zachován) na cíl 55–90 % (jako
      u ostatních regionů, ne 100 % - mírný přesah přes hranici je u
      pohraničních pásem záměrný/reálný): Krušné hory 69,3 %, Krkonoše
      70,8 %. Popisky (`<text>`) posunuty o stejné dx/dy, ať zůstanou
      u vybarvené plochy. **Orlické hory - jedna nuance**: automatický
      posun cílený čistě na "55-90 % v libovolném kraji" našel
      matematicky vyhovující, ale geograficky ŠPATNÉ řešení (posun tak
      daleko, že plocha sklouzla pryč z Královéhradeckého kraje do
      Olomouckého, přes celou Moravu) - zahozeno. Použit místo toho
      posun cílený konkrétně na Královéhradecký kraj (70 % pokrytí
      TOHOTO kraje specificky), který ale díky reálné poloze Orlických
      hor na hranici Královéhradeckého/Pardubického kraje vychází na
      100 % pokrytí "libovolným krajem" (rozděleno 297:125 mezi
      oběma) - ponecháno, protože je to geograficky správně (Orlické
      hory leží na hranici těchto dvou krajů), i když to formálně
      nesedí do cílového pásma 55-90 %. Zkontrolováno i, že se žádné
      dva ze všech 11 tvarů po posunu vzájemně nepřekrývají.
  - **Aktualizace 30. 7. 2026 (čtvrtá verze)**: ilustrační odhady tvarů
    (třetí verze výše) nahrazeny tvary odvozenými přímo z reálné
    geometrie státní hranice ČR — stejná zdrojová data jako hranice
    krajů (druhá verze). Metoda (Python, `shapely`): u 7 pohraničních
    oblastí (Krušné hory, Jizerské hory, Krkonoše, Orlické hory,
    Jeseníky, Beskydy, Šumava) se vezme příslušný úsek skutečné hranice
    ČR, "nafoukne" do pásu (`buffer`) a ořízne přesným průnikem
    (`intersection`) s obrysem republiky — výsledný tvar tak kopíruje
    reálný klikatý průběh hranice a vizuální přesah za hranici ČR není
    fyzicky možný (je to matematický průnik, ne odhad). U 4
    vnitrozemských oblastí (Vysočina, Jižní Čechy, Jižní Morava, Český
    ráj) zůstávají organické kompaktní plochy jako ve třetí verzi;
    Jižní Morava byla výrazně zvětšena (~4× plocha), aby odpovídala
    velikosti, kterou reálně zabírá v Jihomoravském kraji. **`docs/
    style.css` ani `docs/map.js` se touhle změnou vůbec nedotkly** —
    třídy (`.region-patch`, `.map-region-label`, hover/aktivní stavy)
    i JS logika (čistě přes `data-region`) zůstávají stejné, mění se
    jen souřadnice (`d`) 11 `<path class="region-patch">`. Ověřeno
    programově (Node skript): žádný z 11 `d` atributů není prázdný ani
    neobsahuje NaN, všechny souřadnice leží uvnitř `viewBox="0 0 700
    400"`, všechny cesty jsou uzavřené (`Z`).
  - **Aktualizace 30. 7. 2026 (pátá verze) — oprava 2 problémů nahlášených
    uživatelem se screenshoty**: (1) Šumava a Beskydy byly po nafouknutí
    pásu (čtvrtá verze) nereálně objemné — na ostrých zákrutech hranice
    nafouknutí čáry přirozeně vytvoří kulatý "balonek". U Šumavy opraveno
    vyhlazením linie hranice před nafouknutím (odstranění drobných
    zákrutů). U Beskyd šlo o špičku východního výběžku u trojmezí
    ČR-PL-SK, kterou nešlo vyhladit bez ztráty tvaru — místo toho je z
    pásu úplně vynechaná, takže Beskydy jsou teď **dvě oddělené
    subcesty v jednom `d`** (`M... Z M... Z`) s mezerou přesně v místě
    té špičky. (2) Jižní Čechy zvětšeny (byly vizuálně malé vůči
    ostatním oblastem). Vedlejší efekt rozdělení Beskyd: v mezeře mezi
    oběma kusy SVG nezaregistruje klik (jen na vybarvené ploše) — přidán
    `<path class="region-hit">` jako první potomek `<g data-region=
    "Beskydy">`, kopírující původní nezmenšený (celistvý) tvar,
    `fill: transparent; pointer-events: auto` (`docs/style.css`), takže
    klik funguje i v té vizuálně prázdné mezeře. **`docs/map.js` se
    touhle změnou vůbec nedotkl** — klik listener visí na `.map-region`
    (rodič), na počet/tvar potomků mu nezáleží. Ověřeno bez prohlížeče
    (žádný po ruce ani tentokrát): geometricky (Node skript — 11×
    `region-patch` + 1× `region-hit`, žádné prázdné/NaN `d`, všechny
    souřadnice ve `viewBox`, všechny podcesty uzavřené `Z`, Beskydy
    `region-patch` má potvrzeno přesně 2 subcesty) a funkčně (jsdom +
    reálný `map.js` běžící nad vygenerovaným DOM, simulace kliků): klik
    na `region-hit` (mezera) i na `region-patch` (viditelné kusy Beskyd)
    obojí správně vyplní pole a zvýrazní region, přepnutí na jiný region
    ho korektně odaktivuje, reset maže vše.
  - **Princip: `#f-location` textové pole zůstává jediný zdroj
    pravdy.** Mapa ho jen ovládá obousměrně, nezavádí žádný nový stav
    mimo něj. Klik na region vyplní přesný název do pole a zvýrazní ho
    (jantarová). Psaní do pole přepočítává, jestli text přesně
    (case-insensitive) odpovídá některé z 11 oblastí — pokud ne,
    zvýraznění zmizí. Filtrování samo (substring match nad
    `l.location`, `app.js`) zůstává **beze změny** — mapa jen
    předvyplňuje totéž textové pole, které se tam dalo psát i předtím.
  - `<script src="map.js">` musí být PŘED `<script src="app.js">` v
    `index.html` — ne kvůli závislosti při načtení (oba skripty běží
    nezabalené na konci `<body>`, DOM už existuje), ale kvůli pořadí
    registrace `click` listenerů na `#btn-reset` (viz bug níže).
  - **Bug objevený a opravený při code review (žádný prohlížeč po
    ruce, ověřeno jen trasováním kódu)**: `map.js` i `app.js` mají na
    stejném `#btn-reset` tlačítku každý svůj vlastní `click` listener.
    `map.js` se registruje první (načítá se dřív), takže by při kliku
    přečetl `#f-location` hodnotu JEŠTĚ PŘED tím, než ji `app.js`
    (`resetFilters()`) stihne vyprázdnit — nápovědný text pod mapou by
    zůstal zaseknutý na "Vlastní lokalita: <stará hodnota>" místo
    "Zatím nic nevybráno.". Oprava: `map.js`ův reset handler přehodí
    přes `setTimeout(…, 0)`, aby se přepočet spustil AŽ po doběhnutí
    všech synchronních listenerů na tom kliknutí (tedy i po
    `resetFilters()`).
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
5. **Nedůvěra v server-side portálové filtry bez ověření**: opakující se
   vzorec napříč všemi třemi hotovými/rozpracovanými profily —
   e-chalupy.cz `filters=84` nedělá, co název slibuje (sekce 4);
   cs-chalupy.cz `chaty-a-chalupy` pretty-URL slug se tiše ignoruje
   (sekce 6). **Obecné poučení: každý server-side filtr, i takový, co
   "zní" jako přesně to, co chceš, vždy ověřit na konkrétním
   protipříkladu/čísly před a po, ne předpokládat, že funguje podle
   názvu.**

## 8. Co zbývá udělat

- [x] Dokončit chata.cz: doladit "TODO ověřit doma" ze sekce 5, pak
      napsat `scraper/profiles/chata_cz.py` a otestovat end-to-end.
      (Hotovo, otestováno lokálně na Šumavě a Krkonoších.)
- [x] chata.cz — implementovat `likely_apartment` heuristiku (analogicky
      k e-chalupy). Hotovo: tři signály přes OR (title obsahuje
      "apartmán", >1 `sec-price` blok, název pokoje obsahuje "apartmán"
      — třetí signál upraven oproti původnímu návrhu "osoba v
      price_unit", ten byl na datech 94% šum). Ověřeno na Šumava +
      Krkonoše: 7/79 (9 %). Viz sekce 5, IMPLEMENTACE u `sec-rooms`/
      `sec-price`.
- [x] cs-chalupy.cz — napsán `scraper/profiles/cs_chalupy.py`, otestován
      end-to-end na Šumavě (129→116 nabídek po typovém filtru) i na
      GitHub Actions. Viz sekce 6.
- [x] e-chalupy.cz na GitHub Actions bez 403 — vyřešeno přes
      `STATIC_AREA_IDS` tabulku (11 pokrytých regionů), ověřeno na dvou
      různých regionech (Šumava, Krkonoše). Proxy služba už není
      potřeba pro tyhle regiony. Viz sekce 4. Pro lokality mimo tabulku
      zůstává tichý fallback na celostátní hledání (nižší relevance,
      ne chyba) — rozšíření tabulky o další region zůstává na TODO,
      pokud se ukáže potřeba.
- [x] Frontend — štítky se statistikou nabídek podle zdroje ve
      filtrovaném výsledku (live přepočet). Viz sekce 7, Frontend
      struktura.
- [ ] hauzi.com, chatyachalupy-chatar.cz, alkatravel.cz, zars.cz
- [ ] Zvážit rozšíření `STATIC_AREA_IDS` o další regiony, pokud se běžně
      používají lokality mimo současných 11 pokrytých (Šumava, Jeseníky,
      Beskydy, Krkonoše, Jižní Morava, Český ráj, Jizerské hory, Jižní
      Čechy, Krušné hory, Vysočina, Orlické hory).
- [ ] Případně: tlačítko na frontendu pro přímé spuštění GitHub Actions
      bez nutnosti přecházet na GitHub (odloženo, nice-to-have)
- [ ] Zvážit vlastní ikonu/favicon (icons8-cabin-64) — Nojmi měl soubor
      ve Windows Downloads, cesta nebyla dosud ověřena/dokončena (STAV
      NEJASNÝ — možná už hotovo, možná ne, zkontrolovat).

## 9. Obecná doporučení pro práci na dalších portálech

Při přidávání nového portálu (viz i README "Přidání nového portálu"):
1. Získat od Nojmiho screenshot vyhledávacího formuláře, screenshot
   výpisu výsledků (ideálně s konkrétním vyhledáním), a HTML jedné karty
   z DevTools.
2. **Prověřit, jestli existuje JSON API** podobně jako u e-chalupy.cz
   (Network tab → Fetch/XHR filtr → scrollovat/stránkovat a sledovat,
   jestli se objeví strukturovaný datový endpoint) — je to spolehlivější
   než HTML scraping, pokud existuje. U chata.cz i cs-chalupy.cz se
   ukázalo, že i bez plnohodnotného JSON API pro výpis mohou existovat
   užitečné pomocné JSON AJAX endpointy (např. pro překlad lokalita→ID
   u chata.cz) — stojí za to je hledat i tam, kde hlavní výpis JSON API
   nemá.
3. **Ověřit textové pokrytí KAŽDÉHO vybavení na reálném vzorku dat** před
   tím, než se checkbox přidá do frontendu — nepředpokládat, že vybavení
   bude v textu, může to být jen server-side ID filtr (viz sekce 4).
   cs-chalupy.cz je zatím jedinou výjimkou s dobrým textovým pokrytím
   přímo na detailu (sekce 6) — i tak ověřit na širším vzorku, než se
   tomu plně důvěřuje.
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
10. **Nikdy nedůvěřovat server-side portálovému filtru jen podle názvu
    parametru/slugu** — vždy ověřit na konkrétním čísle před/po filtrem
    a na konkrétním protipříkladu. Dvě různá selhání stejného typu
    (e-chalupy.cz `filters=84`, cs-chalupy.cz `chaty-a-chalupy` slug)
    naznačují, že tohle je systematické riziko u každého nového portálu,
    ne ojedinělá náhoda.
11. Pokud portál nabízí JSON-LD strukturovaná data (`<script
    type="application/ld+json">`) na detailu nabídky, využít je pro
    snadno strojově čitelná pole (adresa, GPS, telefon, hodnocení) —
    ale vždy ověřit, jestli JSON-LD ceny (pokud existují) odpovídají
    skutečné ceníkové tabulce, než se jim důvěřuje (viz cs-chalupy.cz
    `priceRange` nesoulad, sekce 6).
