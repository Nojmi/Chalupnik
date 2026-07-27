"use strict";

const DATA_URL =
  "https://raw.githubusercontent.com/Nojmi/Chalupnik/main/results/latest.json";

const grid      = document.getElementById("results-grid");
const metaEl    = document.getElementById("results-meta");
const emptyEl   = document.getElementById("empty-state");

let allListings = [];

// ── Fetch ──────────────────────────────────────────────────────
async function loadData() {
  try {
    const resp = await fetch(DATA_URL);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    allListings = data.listings || [];

    const ts = data.generated_at
      ? new Date(data.generated_at).toLocaleString("cs-CZ")
      : "–";
    metaEl.textContent =
      `Poslední běh: ${ts}  |  Nalezeno celkem: ${data.total_found ?? allListings.length}`;

    renderCards(allListings);
  } catch (err) {
    metaEl.textContent = "Nepodařilo se načíst výsledky.";
    console.error(err);
  }
}

// ── Ridge SVG (randomised mountain silhouette) ─────────────────
function buildRidgeSVG() {
  const W = 400, H = 48;
  const points = [];
  const steps  = 14;

  // Start at bottom-left
  points.push([0, H]);

  // Generate a ridge profile with random peaks
  for (let i = 0; i <= steps; i++) {
    const x = (i / steps) * W;
    // Higher variance in the middle, flatter near edges
    const mid = 1 - Math.abs((i / steps) - 0.5) * 1.6;
    const base = H * 0.55;
    const range = H * 0.42 * Math.max(0, mid);
    const y = base - Math.random() * range;
    points.push([x, y]);
  }

  // End at bottom-right
  points.push([W, H]);

  const d = points
    .map((p, i) => (i === 0 ? `M${p[0]},${p[1]}` : `L${p[0]},${p[1]}`))
    .join(" ") + " Z";

  return `<svg class="card-ridge" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">
    <path d="${d}" fill="#1E362B" />
    <path d="${d}" fill="none" stroke="rgba(189,134,54,.35)" stroke-width="1.2" />
  </svg>`;
}

// ── Render ─────────────────────────────────────────────────────
function formatPrice(price, unit) {
  if (price == null) return "";
  const formatted = price.toLocaleString("cs-CZ");
  const suffix = unit ? ` Kč / ${unit}` : " Kč";
  return `${formatted}${suffix}`;
}

function renderCards(listings) {
  grid.innerHTML = "";

  if (!listings.length) {
    emptyEl.classList.remove("hidden");
    return;
  }
  emptyEl.classList.add("hidden");

  listings.forEach((l) => {
    const amenityTags = (l.amenities || [])
      .map((a) => `<span class="amenity-tag">${escHtml(a)}</span>`)
      .join("");

    const stats = [
      l.capacity  != null ? `<span class="stat">👥 ${l.capacity}</span>` : "",
      l.bedrooms  != null ? `<span class="stat">🛏 ${l.bedrooms}</span>` : "",
    ].filter(Boolean).join("");

    const priceStr = formatPrice(l.price, l.price_unit);

    const card = document.createElement("article");
    card.className = "listing-card";
    card.innerHTML = `
      ${buildRidgeSVG()}
      <div class="card-body">
        <span class="card-source">${escHtml(l.source)}</span>
        <h2 class="card-title">${escHtml(l.title)}</h2>
        <p class="card-location">${escHtml(l.location)}</p>
        ${stats ? `<div class="card-stats">${stats}</div>` : ""}
        ${amenityTags ? `<div class="card-amenities">${amenityTags}</div>` : ""}
      </div>
      <div class="card-footer">
        <div>
          ${priceStr
            ? `<span class="card-price">${priceStr.split(" Kč")[0]} Kč</span>
               <span class="card-price-unit">${l.price_unit ? `/ ${l.price_unit}` : ""}</span>`
            : ""}
        </div>
        <a class="card-link" href="${escAttr(l.url)}" target="_blank" rel="noopener noreferrer">
          Zobrazit →
        </a>
      </div>`;
    grid.appendChild(card);
  });

  metaEl.textContent = metaEl.textContent.replace(/Zobrazeno: \d+/, "")
    + `  |  Zobrazeno: ${listings.length}`;
}

// ── Client-side filtering ──────────────────────────────────────
function getFilters() {
  const location     = document.getElementById("f-location").value.trim().toLowerCase();
  const capacity     = parseInt(document.getElementById("f-capacity").value)     || null;
  const capacityMax  = parseInt(document.getElementById("f-capacity-max").value) || null;
  const bedrooms     = parseInt(document.getElementById("f-bedrooms").value)     || null;
  const bedroomsMax  = parseInt(document.getElementById("f-bedrooms-max").value) || null;
  const maxPrice     = parseFloat(document.getElementById("f-maxprice").value)   || null;
  const entireProperty = document.getElementById("f-entire-property").checked;
  const amenities    = [...document.querySelectorAll(".amenity-group .amenity-check input:checked")]
    .map((cb) => cb.value.toLowerCase());
  return { location, capacity, capacityMax, bedrooms, bedroomsMax, maxPrice, entireProperty, amenities };
}

function applyFilters() {
  const f = getFilters();
  const filtered = allListings.filter((l) => {
    if (f.location && l.location != null) {
      if (!l.location.toLowerCase().includes(f.location)) return false;
    }
    if (f.capacity != null && l.capacity != null) {
      if (l.capacity < f.capacity) return false;
    }
    if (f.capacityMax != null && l.capacity != null) {
      if (l.capacity > f.capacityMax) return false;
    }
    if (f.bedrooms != null && l.bedrooms != null) {
      if (l.bedrooms < f.bedrooms) return false;
    }
    if (f.bedroomsMax != null && l.bedrooms != null) {
      if (l.bedrooms > f.bedroomsMax) return false;
    }
    if (f.maxPrice != null && l.price != null) {
      if (l.price > f.maxPrice) return false;
    }
    if (f.entireProperty && l.entire_property != null) {
      if (!l.entire_property) return false;
    }
    if (f.amenities.length) {
      const has = (l.amenities || []).map((a) => a.toLowerCase());
      if (!f.amenities.every((a) => has.includes(a))) return false;
    }
    return true;
  });

  renderCards(filtered);
  metaEl.textContent = metaEl.textContent.replace(/\s*\|?\s*Zobrazeno: \d+/, "")
    + `  |  Zobrazeno: ${filtered.length}`;
}

function resetFilters() {
  document.getElementById("f-location").value      = "";
  document.getElementById("f-capacity").value      = "";
  document.getElementById("f-capacity-max").value  = "";
  document.getElementById("f-bedrooms").value      = "";
  document.getElementById("f-bedrooms-max").value  = "";
  document.getElementById("f-maxprice").value      = "";
  document.getElementById("f-entire-property").checked = false;
  document.querySelectorAll(".amenity-group .amenity-check input").forEach((cb) => (cb.checked = false));
  renderCards(allListings);
}

// ── Helpers ────────────────────────────────────────────────────
function escHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
function escAttr(str) { return escHtml(str); }

// ── Bootstrap ──────────────────────────────────────────────────
document.getElementById("btn-apply").addEventListener("click", applyFilters);
document.getElementById("btn-reset").addEventListener("click", resetFilters);

loadData();
