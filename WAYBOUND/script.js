"use strict";

/* Deccan Trails — JavaScript fixes only. The existing HTML and CSS/UI stay unchanged. */

const ALLOWED = ["Andhra Pradesh", "Telangana"];
const NA = '<span class="na">Information not available</span>';

function readStorageArray(key) {
  try {
    const value = JSON.parse(localStorage.getItem(key) || "[]");
    return Array.isArray(value) ? value : [];
  } catch (error) {
    console.warn(`Ignoring invalid localStorage value for ${key}.`, error);
    return [];
  }
}

const S = {
  dest: [], food: [], gi: [], crafts: [], exp: [], media: [], sources: [],
  start: null, selected: null, trip: readStorageArray("trip"),
  map: null, markers: {}, startMarker: null, line: null,
  dmap: null, pickMap: null, pick: null, setPick: null, initPickMap: null,
  loaded: false
};

const $ = (selector) => document.querySelector(selector);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[c]));
const val = (v) => (v == null || String(v).trim() === "" ? NA : esc(v));
const isUrl = (u) => /^https?:\/\//i.test(String(u || "").trim());
const link = (u, t) => isUrl(u)
  ? `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(t || u)}</a>`
  : "";
const num = (v) => {
  if (v == null || String(v).trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

// ---------- CSV ----------
function parseCSV(text) {
  text = String(text || "").replace(/^\uFEFF/, "");
  if (!text.trim()) return [];

  const rows = [];
  let row = [], field = "", quoted = false;

  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; }
        else quoted = false;
      } else {
        field += c;
      }
    } else if (c === '"') {
      quoted = true;
    } else if (c === ",") {
      row.push(field); field = "";
    } else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field); rows.push(row); row = []; field = "";
    } else {
      field += c;
    }
  }

  if (field.length || row.length) { row.push(field); rows.push(row); }
  const nonEmptyRows = rows.filter((r) => r.some((x) => String(x).trim() !== ""));
  if (!nonEmptyRows.length) return [];

  const headers = nonEmptyRows.shift().map((h) => h.trim());
  return nonEmptyRows.map((values) => Object.fromEntries(
    headers.map((h, i) => [h, String(values[i] ?? "").trim()])
  ));
}

const LOAD_ERRORS = [];
async function load(name, required = true) {
  const path = `./data/${name}`;
  try {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(response.status === 404 ? "file not found (404)" : `HTTP ${response.status}`);
    }
    const text = await response.text();
    // Header-only or zero-byte optional CSVs are valid empty datasets.
    return parseCSV(text);
  } catch (error) {
    const reason = location.protocol === "file:"
      ? "fetch is blocked on file:// pages; open through a local web server"
      : error.message;
    LOAD_ERRORS.push(`${path}: ${reason}`);
    if (required) console.error("CSV load failed:", path, error);
    return [];
  }
}

// ---------- State and field helpers ----------
function normalizeState(value) {
  const s = String(value || "").trim().toLowerCase();
  if (s === "andhra pradesh" || s === "andhrapradesh") return "Andhra Pradesh";
  if (s === "telangana") return "Telangana";
  return String(value || "").trim();
}

// CSV fields may contain one state, or several separated by ; / , / &.
function statesOf(value) {
  return String(value || "")
    .split(/[;,/|&]+/)
    .map((x) => normalizeState(x))
    .filter(Boolean);
}

function inScope(value) {
  const states = statesOf(value);
  return states.length > 0 && states.every((state) => ALLOWED.includes(state));
}

function firstValue(row, keys) {
  for (const key of keys) {
    if (row && row[key] !== undefined && String(row[key]).trim() !== "") {
      return String(row[key]).trim();
    }
  }
  return "";
}

function normalizeDestination(row) {
  return {
    ...row,
    states: statesOf(row.state),
    lat: num(row.latitude ?? row.lat),
    lng: num(row.longitude ?? row.lng ?? row.lon)
  };
}

function hasXY(destination) {
  return destination && destination.lat != null && destination.lng != null &&
    Math.abs(destination.lat) <= 90 && Math.abs(destination.lng) <= 180;
}

// Route distance: from the user's starting location to a destination.
function distTo(destination) {
  return S.start && hasXY(destination) ? km(S.start, destination) : null;
}

// Browse/filter distance: from the selected destination to every other destination.
function distFromSelected(destination) {
  return S.selected && hasXY(S.selected) && hasXY(destination)
    ? km(S.selected, destination)
    : null;
}

function updateDistanceFilterAvailability() {
  const slider = $("#distFilter");
  if (slider) slider.disabled = !(S.selected && hasXY(S.selected));
}

function showError(message) {
  const box = $("#loadErrors");
  if (!box) return;
  box.hidden = false;
  box.innerHTML = `<b>Some data could not be loaded:</b><ul><li>${esc(message)}</li></ul>`;
}

// ---------- Geo ----------
function km(a, b) {
  const R = 6371, rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad;
  const dLng = (b.lng - a.lng) * rad;
  const h = Math.sin(dLat / 2) ** 2 +
    Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

async function geocode(query) {
  if (!query || query.trim().length < 3) return [];
  const url = `https://nominatim.openstreetmap.org/search?format=json&limit=6&countrycodes=in&q=${encodeURIComponent(query)}`;
  const response = await fetch(url, { headers: { "Accept-Language": "en" } });
  return response.ok ? response.json() : [];
}

// ---------- Autocomplete ----------
function autocomplete(input, list, fetcher, onPick) {
  let items = [], activeIndex = -1, timer = null, requestNumber = 0;

  const render = () => {
    list.innerHTML = items.map((item, index) => `
      <li class="${index === activeIndex ? "hi" : ""}" data-i="${index}">
        ${esc(item.label)}${item.sub ? `<small>${esc(item.sub)}</small>` : ""}
      </li>
    `).join("");
    list.hidden = !items.length;
  };

  const run = async () => {
    const query = input.value.trim();
    if (query.length < 3) { items = []; render(); return; }
    const thisRequest = ++requestNumber;
    try {
      const results = await fetcher(query);
      if (thisRequest !== requestNumber) return; // Ignore stale responses.
      items = Array.isArray(results) ? results : [];
      activeIndex = -1;
      render();
    } catch (error) {
      console.warn("Autocomplete request failed:", error);
      items = [];
      render();
    }
  };

  const pick = (index) => {
    const item = items[index];
    if (!item) return;
    input.value = item.label;
    list.hidden = true;
    onPick(item);
  };

  // Nominatim is queried no more often than roughly once per second while typing.
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(run, 1100);
  });

  input.addEventListener("focus", () => {
    if (input.value.trim().length >= 3) run();
  });

  input.addEventListener("keydown", (event) => {
    if (list.hidden) return;
    if (event.key === "ArrowDown") {
      activeIndex = Math.min(activeIndex + 1, items.length - 1);
      render(); event.preventDefault();
    } else if (event.key === "ArrowUp") {
      activeIndex = Math.max(activeIndex - 1, 0);
      render(); event.preventDefault();
    } else if (event.key === "Enter" && activeIndex >= 0) {
      event.preventDefault(); pick(activeIndex);
    } else if (event.key === "Escape") {
      list.hidden = true;
    }
  });

  list.addEventListener("mousedown", (event) => {
    const li = event.target.closest("li[data-i]");
    if (li) { event.preventDefault(); pick(Number(li.dataset.i)); }
  });

  input.addEventListener("blur", () => setTimeout(() => { list.hidden = true; }, 180));
}

const placeFetcher = async (query) => {
  const results = await geocode(query);
  return results.map((place) => ({
    label: String(place.display_name || "").split(",").slice(0, 2).join(","),
    sub: place.display_name || "",
    lat: Number(place.lat),
    lng: Number(place.lon)
  })).filter((place) => Number.isFinite(place.lat) && Number.isFinite(place.lng));
};

// ---------- Starting location ----------
function clearRouteLine() {
  if (S.line && S.map) S.map.removeLayer(S.line);
  S.line = null;
}

function updateRouteLine() {
  clearRouteLine();
  if (!S.map || !S.start || !S.selected || !hasXY(S.selected)) return;
  S.line = L.polyline(
    [[S.start.lat, S.start.lng], [S.selected.lat, S.selected.lng]],
    { color: "#c0603a", dashArray: "6 6", weight: 3 }
  ).addTo(S.map);
}

function setStart(place) {
  if (!Number.isFinite(Number(place.lat)) || !Number.isFinite(Number(place.lng))) {
    $("#startStatus").textContent = "That location did not return valid coordinates.";
    return;
  }

  S.start = { label: place.label || "Starting location", lat: Number(place.lat), lng: Number(place.lng) };
  $("#startStatus").textContent = `Starting from ${S.start.label} (${S.start.lat.toFixed(4)}, ${S.start.lng.toFixed(4)})`;
  // Starting location is used for the route estimate, not the max-distance filter.

  if (S.startMarker && S.map) S.startMarker.remove();
  if (S.map && window.L) {
    S.startMarker = L.circleMarker([S.start.lat, S.start.lng], {
      radius: 9, color: "#2f5d46", fillColor: "#3f7a5c", fillOpacity: 0.9
    }).addTo(S.map).bindPopup(`<b>Your start:</b> ${esc(S.start.label)}`);
  }

  renderAll();
  updateDistance();
  updateRouteLine();
  updateMapBounds();
}

function useGeo() {
  if (!navigator.geolocation) {
    $("#startStatus").textContent = "Geolocation is not supported by this browser.";
    return;
  }

  $("#startStatus").textContent = "Locating…";
  navigator.geolocation.getCurrentPosition(async (position) => {
    const lat = position.coords.latitude;
    const lng = position.coords.longitude;
    let label = "My location";
    try {
      const response = await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}`);
      if (response.ok) {
        const result = await response.json();
        if (result.display_name) label = result.display_name.split(",").slice(0, 2).join(",");
      }
    } catch (error) { console.warn("Reverse geocoding unavailable:", error); }
    $("#startInput").value = label;
    setStart({ label, lat, lng });
  }, (error) => {
    $("#startStatus").textContent = "Could not get location: " + error.message;
  }, { enableHighAccuracy: true, timeout: 10000 });
}

function updateDistance() {
  const destination = S.selected;
  const output = $("#distanceOut");
  if (!destination) { output.textContent = ""; return; }
  if (!hasXY(destination)) {
    output.textContent = `${destination.name}: coordinates not available, so distance cannot be calculated.`;
  } else if (!S.start) {
    output.textContent = `Set a starting location to see the distance to ${destination.name}.`;
  } else {
    const distance = distTo(destination);
    output.innerHTML = `<span class="dist">${distance.toFixed(1)} km</span> straight-line from ${esc(S.start.label)} to ${esc(destination.name)}`;
  }
}

// ---------- Filters ----------
function fillSelect(select, values, label) {
  const current = select.value;
  select.innerHTML = `<option value="">${esc(label)}</option>` + values.map((value) =>
    `<option value="${esc(value)}" ${value === current ? "selected" : ""}>${esc(value)}</option>`
  ).join("");
}

const catsOf = (destination) => String(destination.category || "")
  .split(/[;,/|]+/).map((x) => x.trim().toLowerCase()).filter(Boolean);

function refreshFilterOptions() {
  const state = $("#stateFilter").value;
  const pool = S.dest.filter((destination) => !state || destination.states.includes(state));
  fillSelect($("#districtFilter"), [...new Set(pool.map((d) => d.district).filter(Boolean))].sort(), "All districts");
  fillSelect($("#categoryFilter"), [...new Set(pool.flatMap(catsOf))].sort(), "All categories");
}

function filtered() {
  const query = $("#searchInput").value.toLowerCase().trim();
  const state = $("#stateFilter").value;
  const district = $("#districtFilter").value;
  const category = $("#categoryFilter").value;
  const maxDistance = Number($("#distFilter").value);
  const hasDistanceCentre = Boolean(S.selected && hasXY(S.selected));
  const useDistance = Boolean(hasDistanceCentre && maxDistance < 1000);

  const list = S.dest.filter((destination) => {
    const matchesState = !state || destination.states.includes(state);
    const matchesDistrict = !district || destination.district === district;
    const matchesCategory = !category || catsOf(destination).includes(category);
    const searchText = [destination.name, destination.description, destination.category, destination.district].join(" ").toLowerCase();
    const matchesSearch = !query || searchText.includes(query);
    const distance = distFromSelected(destination);
    // Keep records with no coordinates visible; their distance is unknown, not zero.
    const matchesDistance = !useDistance || distance == null || distance <= maxDistance;
    return matchesState && matchesDistrict && matchesCategory && matchesSearch && matchesDistance;
  });

  // When a destination is selected, show the nearest destinations to it first.
  // Otherwise retain the original convenience sort from the user's starting point.
  if (S.selected && hasXY(S.selected)) {
    list.sort((a, b) => (distFromSelected(a) ?? Infinity) - (distFromSelected(b) ?? Infinity));
  } else if (S.start) {
    list.sort((a, b) => (distTo(a) ?? Infinity) - (distTo(b) ?? Infinity));
  }
  return list;
}

// ---------- Cards and map ----------
function photoOf(destinationId) {
  return S.media.find((media) => media.destination_id === destinationId && isUrl(media.file_url));
}

function card(destination) {
  const photo = destination.photo ? { file_url: destination.photo } : photoOf(destination.destination_id);
  const distance = S.selected && hasXY(S.selected)
    ? distFromSelected(destination)
    : distTo(destination);
  const distanceLabel = S.selected && hasXY(S.selected) ? "from selected destination" : "from start";
  const inTrip = S.trip.includes(destination.destination_id);
  const picture = photo
    ? `<img class="thumb" src="${esc(photo.file_url)}" alt="${esc(destination.name)}" loading="lazy">`
    : `<div class="thumb ph-thumb"><span>${esc((destination.name || "?")[0])}</span><small>Photo not available</small></div>`;

  return `<article class="card dcard ${S.selected?.destination_id === destination.destination_id ? "sel" : ""}" data-id="${esc(destination.destination_id)}">
    ${picture}
    <div>
      <h3>${esc(destination.name)}</h3>
      <div class="meta">${val(destination.district)} · ${esc(destination.state)}</div>
      <div class="tags">${catsOf(destination).slice(0, 3).map((category) => `<span class="tag">${esc(category)}</span>`).join("")}${!hasXY(destination) ? '<span class="tag warn">No coordinates</span>' : ""}${destination.user ? '<span class="tag warn">User submitted · unverified</span>' : ""}</div>
      <p class="desc">${val(destination.description)}</p>
      <div class="meta">${distance != null ? `<span class="dist">${distance.toFixed(1)} km</span> ${distanceLabel}` : (S.selected || S.start) ? "Distance not available" : ""}</div>
      <div class="actions"><button class="btn sm primary" data-act="details">Details</button><button class="btn sm ${inTrip ? "added" : "ghost"}" data-act="trip">${inTrip ? "✓ In trip" : "+ Add to trip"}</button></div>
    </div></article>`;
}

function renderAll() {
  if (!S.loaded) return;
  const list = filtered();
  $("#cards").innerHTML = list.length
    ? list.map(card).join("")
    : '<p class="muted">No destinations match your filters.</p>';

  const withoutCoords = list.filter((destination) => !hasXY(destination)).length;
  $("#resultCount").textContent = `${list.length} destination${list.length === 1 ? "" : "s"}${withoutCoords ? ` · ${withoutCoords} without coordinates (not on map)` : ""}`;

  const visibleIds = new Set(list.map((destination) => destination.destination_id));
  if (S.map) {
    Object.entries(S.markers).forEach(([id, marker]) => {
      if (visibleIds.has(id)) marker.addTo(S.map);
      else marker.remove();
    });
  }
  $("#tripCount").textContent = S.trip.length;
}

function buildMarkers() {
  Object.values(S.markers).forEach((marker) => marker.remove());
  S.markers = {};
  if (!S.map || !window.L) return;

  S.dest.filter(hasXY).forEach((destination) => {
    const precisionNote = destination.coordinate_note
      ? `<br><small>${esc(destination.coordinate_note)}</small>`
      : "";
    const marker = L.marker([destination.lat, destination.lng])
      .bindPopup(`<b>${esc(destination.name)}</b><br>${esc(destination.district || "")}, ${esc(destination.state)}${precisionNote}<br><a href="#details/${encodeURIComponent(destination.destination_id)}">View details →</a>`)
      .on("click", () => selectDest(destination, false));
    S.markers[destination.destination_id] = marker;
  });
}

function fitAllDestinationMarkers() {
  if (!S.map || !window.L) return;
  const points = S.dest.filter(hasXY).map((destination) => [destination.lat, destination.lng]);
  if (points.length === 1) {
    S.map.setView(points[0], 9);
  } else if (points.length > 1) {
    // Frame every dataset destination on first load instead of using a fixed centre/zoom.
    S.map.fitBounds(L.latLngBounds(points).pad(0.08), { maxZoom: 8 });
  }
}

function updateMapBounds() {
  if (!S.map) return;
  if (S.start && S.selected && hasXY(S.selected)) {
    S.map.fitBounds([[S.start.lat, S.start.lng], [S.selected.lat, S.selected.lng]], { padding: [30, 30], maxZoom: 10 });
  }
}

function selectDest(destination, fly = true) {
  S.selected = destination;
  $("#destInput").value = destination.name;
  updateDistanceFilterAvailability();
  updateDistance();
  renderAll();
  updateRouteLine();

  if (S.map && hasXY(destination) && fly) {
    S.map.flyTo([destination.lat, destination.lng], 10);
    S.markers[destination.destination_id]?.openPopup();
  }
  updateMapBounds();
}

function toggleTrip(id) {
  const index = S.trip.indexOf(id);
  if (index >= 0) S.trip.splice(index, 1);
  else S.trip.push(id);
  localStorage.setItem("trip", JSON.stringify(S.trip));
  renderAll();
  renderBudget();
}

// ---------- Details ----------
function srcLinks(record) {
  return [
    link(record.source_url_primary, "Primary source"),
    link(record.source_url_secondary, "Secondary source")
  ].filter(Boolean).join(" · ") || NA;
}

function renderDetails(id) {
  const destination = S.dest.find((item) => item.destination_id === id);
  if (!destination) { $("#detail").innerHTML = "<p>Destination not found.</p>"; return; }

  const photos = S.media.filter((media) => media.destination_id === id);
  const image = destination.photo || photos.find((media) => isUrl(media.file_url))?.file_url;
  const crafts = S.crafts.filter((craft) => craft.destination_id === id);
  const gi = S.gi.filter((product) => product.destination_id === id || crafts.some((craft) => craft.gi_id === product.gi_id));
  const experiences = S.exp.filter((experience) => experience.destination_id === id || crafts.some((craft) => craft.craft_id === experience.craft_id));
  const giIds = new Set(gi.map((product) => product.gi_id));
  const foods = S.food.filter((food) => (food.gi_id && giIds.has(food.gi_id)) || (destination.district && food.district === destination.district));
  const sourceRows = S.sources.filter((source) => source.record_id === id && isUrl(source.source_url));
  const distance = distTo(destination);

  const section = (title, rows, renderRow) => `<div class="sec"><h3>${title}</h3>${rows.length ? `<div class="sub">${rows.map(renderRow).join("")}</div>` : `<p>${NA}</p>`}</div>`;

  $("#detail").innerHTML = `
    <div class="dhero">
      <div>${image ? `<img src="${esc(image)}" alt="${esc(destination.name)}">` : `<div class="ph"><div><b>Photo</b><br>${NA}</div></div>`}
        ${photos.map((media) => `<p class="meta">${esc(media.title || "Image")}${media.attribution_text ? " — " + esc(media.attribution_text) : ""} ${link(media.source_page_url, "Source page")}${media.licence ? " · Licence: " + esc(media.licence) : ""}</p>`).join("")}
      </div>
      <div><p class="eyebrow">${esc(destination.state)}</p><h2>${esc(destination.name)}</h2>
        <p>${val(destination.description)}</p>
        <dl class="facts">
          <dt>District</dt><dd>${val(destination.district)}</dd>
          <dt>Category</dt><dd>${val(destination.category)}</dd>
          <dt>Best season</dt><dd>${val(destination.best_season)} ${link(destination.best_season_source_url, "(source)")}</dd>
          <dt>Coordinates</dt><dd>${hasXY(destination) ? `${destination.lat}, ${destination.lng} ${link(destination.coordinate_source_url, "(source)")}` : NA}</dd>
          <dt>Distance</dt><dd>${distance != null ? distance.toFixed(1) + " km (straight-line)" : S.start ? NA : "Set a starting location"}</dd>
          <dt>Verification</dt><dd>${val(destination.verification_status)}</dd>
          <dt>Sources</dt><dd class="links">${destination.user ? (link(destination.source) || NA) : srcLinks(destination)}</dd>
        </dl>
        <div class="actions"><button class="btn primary" id="dTrip">${S.trip.includes(id) ? "✓ In trip" : "+ Add to trip"}</button></div>
      </div>
    </div>
    ${section("Local food", foods, (food) => `<div class="card"><h4>${esc(food.food_name)}</h4><p class="meta">${val(food.origin_place)}, ${val(food.district)}</p><p>${val(food.description)}</p><p><b>Ingredients:</b> ${val(food.ingredients)}</p><p><b>Significance:</b> ${val(food.cultural_significance)}</p><p class="links">${srcLinks(food)}</p></div>`)}
    ${section("GI crafts &amp; products", [...crafts.map((craft) => ({ craft })), ...gi.filter((product) => !crafts.some((craft) => craft.gi_id === product.gi_id)).map((product) => ({ product }))], (item) => item.craft
      ? `<div class="card"><h4>${esc(item.craft.craft_name)}</h4><p class="meta">GI: ${esc(S.gi.find((product) => product.gi_id === item.craft.gi_id)?.gi_name || item.craft.gi_id || "Information not available")}</p><p><b>Materials:</b> ${val(item.craft.materials)}</p><p><b>Process:</b> ${val(item.craft.techniques_process)}</p><p><b>Products:</b> ${val(item.craft.products)}</p><p><b>History:</b> ${val(item.craft.history_note)}</p><p class="links">${srcLinks(item.craft)}</p></div>`
      : `<div class="card"><h4>${esc(item.product.gi_name || item.product.base_name)}</h4><p class="meta">${val(item.product.goods_category)} · ${val(item.product.registration_period)}</p><p><b>Origin:</b> ${val(item.product.origin_place)}, ${val(item.product.origin_district)}</p><p class="links">${link(item.product.source_url, "GI registry")}${item.product.destination_link_source_url ? " · " + link(item.product.destination_link_source_url, "Link source") : ""}</p></div>`)}
    ${section("Cultural experiences", experiences, (experience) => `<div class="card"><h4>${esc(experience.name)}</h4><p class="meta">${val(experience.experience_type)}</p><p>${val(experience.description)}</p><p><b>Season:</b> ${val(experience.months_or_season)}</p><p><b>Availability:</b> ${val(experience.availability_note)}</p><p><b>Price:</b> ${val(experience.price)}</p><p class="links">${srcLinks(experience)}</p></div>`)}
    <div class="sec"><h3>Location</h3>${hasXY(destination) ? '<div id="detailMap" class="detail-map"></div>' : `<p>${NA} — no coordinates in the dataset, so no map is shown.</p>`}</div>
    <div class="sec"><h3>Image credits</h3>${photos.length ? `<ul class="links">${photos.map((media) => `<li>${esc(media.title || "Image")} — ${val(media.creator)} · Licence: ${val(media.licence)} ${link(media.licence_url, "(licence)")} · ${link(media.source_page_url, "source page")}</li>`).join("")}</ul>` : `<p>${NA}</p>`}</div>
    <div class="sec"><h3>All source links</h3>${sourceRows.length ? `<ul class="links">${sourceRows.map((source) => `<li>${esc(source.source_field)}: ${link(source.source_url)}</li>`).join("")}</ul>` : `<p>${NA}</p>`}</div>
  `;

  $("#dTrip").onclick = () => { toggleTrip(id); renderDetails(id); };

  if (hasXY(destination) && window.L) {
    setTimeout(() => {
      const mapElement = $("#detailMap");
      if (!mapElement) return;
      if (S.dmap) { S.dmap.remove(); S.dmap = null; }
      S.dmap = L.map("detailMap", { scrollWheelZoom: false }).setView([destination.lat, destination.lng], 11);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap contributors" }).addTo(S.dmap);
      L.marker([destination.lat, destination.lng]).addTo(S.dmap).bindPopup(esc(destination.name));
      if (S.start) {
        L.circleMarker([S.start.lat, S.start.lng], { radius: 8, color: "#2f5d46" }).addTo(S.dmap);
        const line = L.polyline([[S.start.lat, S.start.lng], [destination.lat, destination.lng]], { color: "#c0603a", dashArray: "6 6" }).addTo(S.dmap);
        S.dmap.fitBounds(line.getBounds(), { padding: [30, 30] });
      }
      S.dmap.invalidateSize();
    }, 80);
  }
}

// ---------- Add a place ----------
function userPlaces() { return readStorageArray("userPlaces"); }

function cleanText(value) {
  return value.replace(/\s+/g, " ")
    .replace(/\s+([,.!?;:])/g, "$1")
    .replace(/([,.!?;:])(?=[^\s\d])/g, "$1 ")
    .replace(/([!?.]){2,}/g, "$1")
    .trim()
    .replace(/(^|[.!?]\s+)([a-z])/g, (match, start, letter) => start + letter.toUpperCase())
    .replace(/\bi\b/g, "I")
    .replace(/([^.!?])$/, "$1.");
}

function renderMyPlaces() {
  const places = userPlaces();
  $("#myPlaces").innerHTML = places.length
    ? `<h3>Your submissions</h3>` + places.map((place) => `<div class="trip-item"><span><b>${esc(place.name)}</b> · ${esc(place.state)}</span><button class="btn sm ghost" data-del="${esc(place.destination_id)}">Remove</button></div>`).join("")
    : "";
}

function renderBudget() {
  const items = S.trip.map((id) => S.dest.find((destination) => destination.destination_id === id)).filter(Boolean);
  $("#tripList").innerHTML = `<h3>Selected destinations</h3>` + (items.length
    ? items.map((destination) => `<div class="trip-item"><span><b>${esc(destination.name)}</b><br><small class="muted">${esc(destination.district || "")}, ${esc(destination.state)} · ${distTo(destination) != null ? distTo(destination).toFixed(1) + " km from start" : "distance not available"}</small></span><button class="btn sm ghost" data-rm="${esc(destination.destination_id)}">Remove</button></div>`).join("")
    : '<p class="muted">No destinations yet. Use “+ Add to trip” on Explore.</p>');

  let routeDistance = 0;
  const withCoordinates = items.filter(hasXY);
  const missingCoordinates = items.length - withCoordinates.length;
  if (S.start && withCoordinates.length) {
    let previous = S.start;
    withCoordinates.forEach((destination) => { routeDistance += km(previous, destination); previous = destination; });
    routeDistance += km(previous, S.start);
  }

  const people = Math.max(1, Number($("#bTravellers").value) || 1);
  const nights = Math.max(0, Number($("#bNights").value) || 0);
  const peoplePerRoom = Math.max(1, Number($("#bRoom").value) || 1);
  const days = nights + 1;
  const rooms = Math.ceil(people / peoplePerRoom);
  const rate = (id) => {
    const input = $(id).value;
    return input === "" ? null : Math.max(0, Number(input));
  };

  const rows = [
    ["Travel", "Km", S.start && withCoordinates.length ? routeDistance : null, S.start ? `${routeDistance.toFixed(0)} km estimated loop` : "set a starting location"],
    ["Stay", "Stay", rooms * nights, `${rooms} room(s) × ${nights} night(s)`],
    ["Food", "Food", people * days, `${people} × ${days} day(s)`],
    ["Other", "Other", people, `${people} traveller(s)`]
  ].map(([name, key, quantity, note]) => {
    const low = rate(`#b${key}Min`);
    const high = rate(`#b${key}Max`);
    return {
      name, note,
      low: quantity != null && low != null ? quantity * low : null,
      high: quantity != null && (high ?? low) != null ? quantity * (high ?? low) : null
    };
  });

  const format = (amount) => "₹" + Math.round(amount).toLocaleString("en-IN");
  const lowTotal = rows.reduce((sum, row) => sum + (row.low || 0), 0);
  const highTotal = rows.reduce((sum, row) => sum + (row.high || 0), 0);

  $("#budgetOut").innerHTML = `
    <h3>Estimated budget</h3>
    <table>
      <tr><td></td><td>Minimum</td><td>Maximum</td></tr>
      ${rows.map((row) => `<tr><td>${row.name} <small>(${row.note})</small></td><td>${row.low == null ? "—" : format(row.low)}</td><td>${row.high == null ? "—" : format(row.high)}</td></tr>`).join("")}
      <tr class="sum"><td>Total</td><td>${format(lowTotal)}</td><td>${format(highTotal)}</td></tr>
      <tr><td>Per person</td><td>${format(lowTotal / people)}</td><td>${format(highTotal / people)}</td></tr>
    </table>
    ${missingCoordinates ? `<p><small>${missingCoordinates} destination(s) lack coordinates and are excluded from travel distance.</small></p>` : ""}
    <p class="disclaimer"><small>Disclaimer: your datasets contain no prices, timings or fees. This estimate uses only the rates you enter and straight-line distances, which are shorter than real road routes. Confirm all costs before travelling.</small></p>
  `;
}

// ---------- View routing ----------
function show(view, argument) {
  document.querySelectorAll(".view").forEach((element) => element.classList.toggle("active", element.id === "view-" + view));
  document.querySelectorAll("nav a").forEach((anchor) => anchor.classList.toggle("active", anchor.dataset.view === view));
  $("#nav").classList.remove("open");

  if (view === "details") renderDetails(argument);
  if (view === "budget") renderBudget();
  if (view === "add") {
    renderMyPlaces();
    setTimeout(() => S.initPickMap && S.initPickMap(), 80);
  }
  if (view === "explore" && S.map) setTimeout(() => S.map.invalidateSize(), 80);
  window.scrollTo(0, 0);
}

function route() {
  const [view, ...rest] = location.hash.slice(1).split("/");
  const allowedViews = ["details", "budget", "add"];
  const targetView = allowedViews.includes(view) ? view : "explore";
  const argument = rest.length ? decodeURIComponent(rest.join("/")) : undefined;
  show(targetView, argument);
}

// ---------- Initialize ----------
async function init() {
  // Initialize map when Leaflet is available; data and cards still work without it.
  if (window.L) {
    S.map = L.map("map", { scrollWheelZoom: false }).setView([16.8, 79.5], 6);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: "© OpenStreetMap contributors"
    }).addTo(S.map);
  } else {
    showError("The map library could not load. Check your internet connection; the destination list can still be used.");
  }

  const fileNames = [
    "destinations.csv", "food.csv", "gi_products.csv", "crafts.csv",
    "cultural_experiences.csv", "media_assets.csv", "sources_reference.csv"
  ];

  const loaded = await Promise.all(fileNames.map((file) => load(file, !["media_assets.csv", "sources_reference.csv"].includes(file))));
  const [destinations, food, gi, crafts, experiences, media, sources] = loaded;

  if (LOAD_ERRORS.length) {
    $("#loadErrors").innerHTML = "<b>Some data could not be loaded:</b><ul>" + LOAD_ERRORS.map((error) => `<li>${esc(error)}</li>`).join("") + "</ul>";
    $("#loadErrors").hidden = false;
  } else {
    $("#loadErrors").hidden = true;
  }

  const sourceDestinationCount = destinations.length;
  const inScopeDestinationCount = destinations.filter((destination) => inScope(destination.state)).length;

  S.dest = [...destinations, ...userPlaces()]
    .filter((destination) => inScope(destination.state))
    .map(normalizeDestination);

  const mappedDestinationCount = S.dest.filter(hasXY).length;
  console.info(
    `Deccan Trails data: ${sourceDestinationCount} CSV rows; ` +
    `${inScopeDestinationCount} Andhra Pradesh/Telangana records; ` +
    `${mappedDestinationCount} records with coordinate references.`
  );

  // This pilot dataset contains 45 destination records. Warn if an older, smaller
  // CSV was copied into data/ by mistake; do not silently claim the list is complete.
  if (sourceDestinationCount < 45) {
    showError(
      `Only ${sourceDestinationCount} destination rows were read from ./data/destinations.csv. ` +
      `The enriched Phase 1 file contains 45 rows. Replace this file with the destinations.csv ` +
      `from the Deccan_Trails_45_Dataset_Update package, then refresh the page.`
    );
  }

  S.food = food.filter((record) => inScope(record.state));
  S.crafts = crafts.filter((record) => inScope(record.state));
  S.exp = experiences.filter((record) => inScope(record.state));

  // Prefer states_in_phase1: it correctly includes GI goods shared with another state
  // when the uploaded phase-one scope identifies AP or Telangana as part of the product.
  S.gi = gi.filter((record) => inScope(
    record.states_in_phase1 || record.state_ut_normalised || record.state_raw
  ));

  S.media = media;
  S.sources = sources;
  S.loaded = true;

  // Remove stale trip IDs left over from deleted/renamed records.
  const validIds = new Set(S.dest.map((destination) => destination.destination_id));
  S.trip = S.trip.filter((id) => validIds.has(id));
  localStorage.setItem("trip", JSON.stringify(S.trip));

  const heroImage = S.media.find((mediaItem) =>
    isUrl(mediaItem.file_url) && S.dest.some((destination) => destination.destination_id === mediaItem.destination_id)
  );
  if (heroImage) {
    $("#hero").style.setProperty("--hero-img", `url("${heroImage.file_url}")`);
    $("#hero").classList.add("has-img");
    const heroDestination = S.dest.find((destination) => destination.destination_id === heroImage.destination_id);
    $("#heroCredit").innerHTML = `${esc(heroDestination.name)} · ${link(heroImage.source_page_url, "image source")}`;
  }

  if (!S.dest.length) {
    $("#cards").innerHTML = '<p class="muted">No Andhra Pradesh or Telangana destinations were found in destinations.csv. Check the state column.</p>';
  }

  fillSelect($("#stateFilter"), ALLOWED, "All states");
  refreshFilterOptions();
  buildMarkers();
  renderAll();
  fitAllDestinationMarkers();
  renderBudget();

  autocomplete($("#startInput"), $("#startSuggest"), placeFetcher, setStart);
  autocomplete($("#destInput"), $("#destSuggest"), async (query) => S.dest
    .filter((destination) => !query || (destination.name + " " + destination.district).toLowerCase().includes(query.toLowerCase()))
    .slice(0, 30)
    .map((destination) => ({ label: destination.name, sub: `${destination.district || "District not available"}, ${destination.state}`, d: destination })),
  (item) => selectDest(item.d));
  autocomplete($("#addLoc"), $("#addSuggest"), placeFetcher, (place) => S.setPick && S.setPick(place.lat, place.lng));

  $("#geoBtn").onclick = useGeo;

  ["#searchInput", "#districtFilter", "#categoryFilter"].forEach((selector) => {
    $(selector).addEventListener("input", renderAll);
  });

  $("#stateFilter").addEventListener("input", () => {
    refreshFilterOptions();
    renderAll();
  });

  $("#distFilter").addEventListener("input", (event) => {
    $("#distLabel").textContent = Number(event.target.value) >= 1000 ? "Any" : event.target.value + " km";
    renderAll();
  });

  // The maximum-distance filter is available only after choosing a destination.
  updateDistanceFilterAvailability();

  $("#resetBtn").onclick = () => {
    ["#searchInput", "#stateFilter", "#districtFilter", "#categoryFilter"].forEach((selector) => { $(selector).value = ""; });
    $("#distFilter").value = 1000;
    updateDistanceFilterAvailability();
    $("#distLabel").textContent = "Any";
    refreshFilterOptions();
    renderAll();
    fitAllDestinationMarkers();
  };

  $("#cards").addEventListener("click", (event) => {
    const article = event.target.closest(".dcard");
    if (!article) return;
    const destination = S.dest.find((item) => item.destination_id === article.dataset.id);
    if (!destination) return;
    const action = event.target.dataset.act;
    if (action === "details") location.hash = "details/" + encodeURIComponent(destination.destination_id);
    else if (action === "trip") toggleTrip(destination.destination_id);
    else selectDest(destination);
  });

  $("#tripList").addEventListener("click", (event) => {
    if (event.target.dataset.rm) toggleTrip(event.target.dataset.rm);
  });

  $("#budgetForm").addEventListener("input", renderBudget);
  $("#menuBtn").onclick = () => $("#nav").classList.toggle("open");

  document.querySelectorAll("[data-view]").forEach((anchor) => {
    anchor.addEventListener("click", (event) => {
      event.preventDefault();
      location.hash = anchor.dataset.view;
    });
  });

  // Add-place form
  const form = $("#addForm");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    const place = Object.fromEntries([...formData.entries()].map(([key, value]) => [key, String(value).trim()]));

    if (!ALLOWED.includes(place.state)) {
      alert("Please choose Andhra Pradesh or Telangana.");
      return;
    }
    if ((place.latitude === "") !== (place.longitude === "")) {
      alert("Enter both latitude and longitude, or leave both empty.");
      return;
    }
    if (place.latitude !== "" && (num(place.latitude) == null || num(place.longitude) == null || Math.abs(num(place.latitude)) > 90 || Math.abs(num(place.longitude)) > 180)) {
      alert("Please enter valid latitude and longitude values.");
      return;
    }

    place.destination_id = "USR-" + Date.now();
    place.user = true;
    place.verification_status = "User submitted · unverified";

    const savedPlaces = userPlaces();
    savedPlaces.push(place);
    localStorage.setItem("userPlaces", JSON.stringify(savedPlaces));

    S.dest.push(normalizeDestination(place));
    buildMarkers();
    refreshFilterOptions();
    renderAll();
    renderMyPlaces();

    form.reset();
    $("#photoPreview").hidden = true;
    $("#photoPreview").innerHTML = "";
    if (S.pick) { S.pick.remove(); S.pick = null; }
    $("#addMsg").hidden = false;
    $("#addMsg").textContent = `✓ Thank you! “${place.name}” was saved as a user-submitted, unverified suggestion.`;
  });

  S.pick = null;
  const setPick = (lat, lng) => {
    if (!Number.isFinite(Number(lat)) || !Number.isFinite(Number(lng))) return;
    form.elements.latitude.value = Number(lat).toFixed(5);
    form.elements.longitude.value = Number(lng).toFixed(5);
    if (!S.pickMap) return;
    if (S.pick) S.pick.setLatLng([lat, lng]);
    else S.pick = L.marker([lat, lng]).addTo(S.pickMap);
    S.pickMap.setView([lat, lng], Math.max(S.pickMap.getZoom(), 9));
  };
  S.setPick = setPick;

  S.initPickMap = () => {
    if (!window.L) return;
    if (S.pickMap) { S.pickMap.invalidateSize(); return; }
    S.pickMap = L.map("pickMap").setView([16.8, 79.5], 6);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: "© OpenStreetMap contributors"
    }).addTo(S.pickMap);
    S.pickMap.on("click", (event) => setPick(event.latlng.lat, event.latlng.lng));
  };

  ["latitude", "longitude"].forEach((name) => {
    form.elements[name].addEventListener("change", () => {
      const lat = num(form.elements.latitude.value);
      const lng = num(form.elements.longitude.value);
      if (lat != null && lng != null) setPick(lat, lng);
    });
  });

  form.elements.photo.addEventListener("input", () => {
    const url = form.elements.photo.value.trim();
    const preview = $("#photoPreview");
    preview.hidden = !isUrl(url);
    if (isUrl(url)) {
      preview.innerHTML = `<img src="${esc(url)}" alt="Photo preview" onerror="this.parentNode.innerHTML='<p class=muted>Could not load this image URL.</p>'">`;
    } else {
      preview.innerHTML = "";
    }
  });

  $("#cleanBtn").onclick = () => {
    const description = form.elements.description;
    if (!description.value.trim()) {
      $("#cleanMsg").textContent = "Write a description first.";
      return;
    }
    description.value = cleanText(description.value);
    $("#cleanMsg").textContent = "Cleaned. Review it before submitting.";
  };

  $("#myPlaces").addEventListener("click", (event) => {
    const id = event.target.dataset.del;
    if (!id) return;
    localStorage.setItem("userPlaces", JSON.stringify(userPlaces().filter((place) => place.destination_id !== id)));
    S.dest = S.dest.filter((destination) => destination.destination_id !== id);
    S.trip = S.trip.filter((tripId) => tripId !== id);
    localStorage.setItem("trip", JSON.stringify(S.trip));
    buildMarkers(); renderAll(); renderBudget(); renderMyPlaces();
  });

  window.addEventListener("hashchange", route);
  route();
}

init().catch((error) => {
  console.error(error);
  const cards = $("#cards");
  if (cards) cards.innerHTML = `<p class="muted">Could not start the site: ${esc(error.message)}</p>`;
});