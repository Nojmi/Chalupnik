// Propojení klikací mapy ČR s textovým polem lokality (#f-location).
// Pravidlo: textové pole je "zdroj pravdy". Klik na mapu vyplní text
// a zvýrazní oblast. Ruční přepsání textu, které přestane odpovídat
// naposledy vybrané oblasti, zvýraznění na mapě zruší.
(function () {
  const regions = document.querySelectorAll(".map-region");
  const locationInput = document.getElementById("f-location");
  const selectedHint = document.getElementById("map-selected-hint");
  const resetBtn = document.getElementById("btn-reset");
  const runBtn = document.getElementById("btn-run-workflow");
  const copiedHint = document.getElementById("run-btn-copied-hint");

  if (!regions.length || !locationInput) return;

  // Tlačítko "Spustit nové hledání" je neaktivní, dokud není vybraná
  // lokalita (z mapy nebo ručně napsaná). Jakmile je, tlačítko se
  // aktivuje a jeho text ukáže přesně, pro jakou lokalitu se hledání
  // spustí - dokud nemáme backend (viz diskuze o Cloudflare Workeru
  // pro přístup bez GitHubu), pořád jen odkazuje na GitHub Actions, ale
  // aspoň je jasné, co se vyplní, a při kliku se to zkopíruje do schránky.
  function syncRunButton() {
    if (!runBtn) return;
    const val = locationInput.value.trim();
    if (val) {
      runBtn.classList.remove("is-disabled");
      runBtn.removeAttribute("aria-disabled");
      runBtn.removeAttribute("title");
      runBtn.textContent = `Spustit hledání: ${val} ↗`;
    } else {
      runBtn.classList.add("is-disabled");
      runBtn.setAttribute("aria-disabled", "true");
      runBtn.setAttribute("title", "Nejprve vyberte oblast na mapě nebo ji napište do pole Lokalita");
      runBtn.textContent = "Spustit nové hledání ↗";
    }
  }

  if (runBtn) {
    runBtn.addEventListener("click", (e) => {
      const val = locationInput.value.trim();
      if (!val) {
        // pointer-events:none blokuje myš, ale ne klávesovou aktivaci
        // (Enter na fokusovaném odkazu) - bez tohohle by klávesnicoví
        // uživatelé mohli gating obejít a otevřít GitHub Actions
        // bez vybrané lokality.
        e.preventDefault();
        return;
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(val).then(() => {
          if (!copiedHint) return;
          copiedHint.textContent = `„${val}“ zkopírováno – vložte na GitHubu do pole Location`;
          copiedHint.classList.add("visible");
          setTimeout(() => copiedHint.classList.remove("visible"), 4000);
        }).catch(() => {});
      }
    });
  }

  // Nastaví aktivní stav podle textu; vrací true, pokud nějaká oblast sedí.
  function syncActiveWithText() {
    const val = locationInput.value.trim().toLowerCase();
    let matched = false;
    regions.forEach((r) => {
      const isMatch = val.length > 0 && r.dataset.region.toLowerCase() === val;
      r.classList.toggle("active", isMatch);
      r.setAttribute("aria-pressed", isMatch ? "true" : "false");
      if (isMatch) matched = true;
    });
    return matched;
  }

  function updateHint() {
    const active = document.querySelector(".map-region.active");
    if (active) {
      selectedHint.textContent = "Vybráno: " + active.dataset.region;
    } else if (locationInput.value.trim()) {
      selectedHint.textContent = "Vlastní lokalita: " + locationInput.value.trim();
    } else {
      selectedHint.textContent = "Zatím nic nevybráno.";
    }
    syncRunButton();
  }

  function selectRegion(el) {
    locationInput.value = el.dataset.region;
    syncActiveWithText();
    updateHint();
    locationInput.focus({ preventScroll: true });
  }

  regions.forEach((r) => {
    r.addEventListener("click", () => selectRegion(r));
    r.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        selectRegion(r);
      }
    });
  });

  // Ruční psaní do pole — mapa se snaží sedět, jinak se zvýraznění zruší.
  locationInput.addEventListener("input", () => {
    syncActiveWithText();
    updateHint();
  });

  if (resetBtn) {
    // app.js má na stejném tlačítku vlastní click listener (resetFilters),
    // který mimo jiné vyprázdní #f-location.value - ale je registrovaný
    // AŽ PO tomhle (map.js se načítá první, viz index.html). Kdybychom
    // tady čapli hint hned synchronně, přečetli bychom ještě starou
    // hodnotu pole. setTimeout(…, 0) odloží re-sync na další tick, až
    // po tom, co doběhnou všechny synchronní listenery na tomhle kliku.
    resetBtn.addEventListener("click", () => {
      setTimeout(() => {
        syncActiveWithText();
        updateHint();
      }, 0);
    });
  }

  updateHint();
})();
