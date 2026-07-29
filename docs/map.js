// Propojení klikací mapy ČR s textovým polem lokality (#f-location).
// Pravidlo: textové pole je "zdroj pravdy". Klik na mapu vyplní text
// a zvýrazní oblast. Ruční přepsání textu, které přestane odpovídat
// naposledy vybrané oblasti, zvýraznění na mapě zruší.
(function () {
  const regions = document.querySelectorAll(".map-region");
  const locationInput = document.getElementById("f-location");
  const selectedHint = document.getElementById("map-selected-hint");
  const resetBtn = document.getElementById("btn-reset");

  if (!regions.length || !locationInput) return;

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
