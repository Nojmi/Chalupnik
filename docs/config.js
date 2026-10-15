/* Nastavení webu (načítá se před app.js).
   worker = adresa Cloudflare Workeru bez lomítka na konci, např. 'https://chalupnik-worker.<účet>.workers.dev'.
   Prázdné = tlačítko „Aktualizovat“ zatím nic nespouští (postup nasazení: worker/README.md).
   Po změně tohoto souboru zvyš ?v= u config.js v index.html, jinak ho prohlížeče drží z cache. */
window.CHALUPNIK = { worker: '' };
