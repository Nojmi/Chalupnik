/* Nastavení webu (načítá se před app.js). Po změně tohoto souboru zvyš ?v= u config.js v index.html, jinak ho prohlížeče drží z cache.
   worker = adresa Workeru na spouštění aktualizací (worker/), např. 'https://chalupnik-worker.<poddoména>.workers.dev'.
            Prázdné = tlačítko „Aktualizovat“ zatím nic nespouští.
   img    = adresa Workeru s cache fotek (worker-img/), např. 'https://chalupnik-img.<poddoména>.workers.dev'.
            Prázdné = fotky se berou přímo z portálů.
   Adresy bez lomítka na konci. */
window.CHALUPNIK = { worker: '', img: '' };
