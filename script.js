"use strict";

/*
  WAYBOUND — FRONTEND-ONLY VERSION
  - Loads tourism CSV files directly from ./data using fetch().
  - Allows searching ANY Indian town/city/place using Photon geocoding.
  - The selected searched location becomes the centre of the nearby-place filter.
  - Curated recommendations/details still come only from the uploaded AP/Telangana CSVs.
  - Trip selections and user-added suggestions are saved in this browser's localStorage.
  - No FastAPI, no backend server code, and no database are used.
*/

console.info("Waybound frontend-only script loaded: any-location-search");

// Clear saved values from the retired trip scheduling feature.
localStorage.removeItem("wayboundItinerary");
localStorage.removeItem("wayboundItineraryDays");

const ALLOWED_STATES = ["Andhra Pradesh", "Telangana"];
const FILES = {
  destinations: "./data/destinations.csv",
  food: "./data/food.csv",
  gi: "./data/gi_products.csv",
  crafts: "./data/crafts.csv",
  experiences: "./data/cultural_experiences.csv",
  media: "./data/media_assets.csv",
  sources: "./data/sources_reference.csv"
};

function readArray(key) {
  try {
    const value = JSON.parse(localStorage.getItem(key) || "[]");
    return Array.isArray(value) ? value : [];
  } catch (error) {
    console.warn(`Invalid saved value for ${key}; starting empty.`, error);
    localStorage.removeItem(key);
    return [];
  }
}

const S = {
  dest: [], food: [], gi: [], crafts: [], exp: [], media: [], sources: [],
  start: null,
  selected: null,       // Can be a CSV destination OR an external geocoded location.
  selectedIsExternal: false,
  trip: readArray("wayboundTrip"),
  activeInterests: localStorage.getItem("wayboundInterests") === null ? [] : readArray("wayboundInterests"),
  map: null,
  markers: {},
  markersLayer: null,
  startMarker: null,
  selectedMarker: null,
  routeLine: null,
  detailMap: null,
  pickMap: null,
  pickMarker: null,
  loaded: false
};

const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[char]));
const isUrl = (url) => /^https?:\/\//i.test(String(url || "").trim());
// Image sources may be HTTPS URLs OR local files placed in the ./images/ folder.
// Keep isUrl() for external source/credit links; use isImageSource() for <img> elements.
const isImageSource = (source) => {
  const value = String(source || "").trim();
  return /^https?:\/\//i.test(value) || /^(?:\.\/)?images\/[a-zA-Z0-9._/-]+\.(?:jpe?g|png|webp|gif)$/i.test(value);
};
const NA = '<span class="na">Information not available</span>';
const val = (value) => value == null || String(value).trim() === "" ? NA : esc(value);
const num = (value) => {
  if (value == null || String(value).trim() === "") return null;
  const result = Number(value);
  return Number.isFinite(result) ? result : null;
};
const link = (url, label) => isUrl(url)
  ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label || url)}</a>`
  : "";

// ------------------------------- CSV loading -------------------------------
// Supports quoted commas, double quotes, CRLF line endings and UTF-8 BOM.
function parseCSV(text) {
  text = String(text || "").replace(/^\uFEFF/, "");
  if (!text.trim()) return [];

  const rows = [];
  let row = [], field = "", quoted = false;

  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (quoted) {
      if (char === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; }
        else quoted = false;
      } else field += char;
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(field); field = "";
    } else if (char === "\n" || char === "\r") {
      if (char === "\r" && text[i + 1] === "\n") i++;
      row.push(field);
      if (row.some((cell) => String(cell).trim() !== "")) rows.push(row);
      row = []; field = "";
    } else field += char;
  }
  if (field.length || row.length) {
    row.push(field);
    if (row.some((cell) => String(cell).trim() !== "")) rows.push(row);
  }
  if (!rows.length) return [];

  const headers = rows.shift().map((header) => header.trim());
  return rows.map((cells) => Object.fromEntries(
    headers.map((header, index) => [header, String(cells[index] ?? "").trim()])
  ));
}

const loadErrors = [];
async function loadCSV(path, optional = false) {
  try {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) throw new Error(response.status === 404 ? "file not found (404)" : `HTTP ${response.status}`);
    return parseCSV(await response.text());
  } catch (error) {
    if (!optional) loadErrors.push(`${path}: ${location.protocol === "file:" ? "fetch is blocked on file:// pages; use VS Code Live Server" : error.message}`);
    console.error(`Could not load ${path}`, error);
    return [];
  }
}

// ------------------------------- Data helpers ------------------------------
function normalState(state) {
  const value = String(state || "").trim().toLowerCase();
  if (value === "andhra pradesh" || value === "andhrapradesh") return "Andhra Pradesh";
  if (value === "telangana") return "Telangana";
  return String(state || "").trim();
}
function stateParts(value) {
  return String(value || "").split(/[;,/|&]+/).map((part) => normalState(part)).filter(Boolean);
}
function inProjectScope(value) {
  const states = stateParts(value);
  return states.length > 0 && states.every((state) => ALLOWED_STATES.includes(state));
}
function firstValue(row, keys) {
  for (const key of keys) {
    if (row && row[key] != null && String(row[key]).trim() !== "") return String(row[key]).trim();
  }
  return "";
}
function normalizeDestination(row) {
  return {
    ...row,
    lat: num(row.latitude ?? row.lat),
    lng: num(row.longitude ?? row.lng ?? row.lon),
    states: stateParts(row.state)
  };
}
function hasCoordinates(place) {
  return !!place && place.lat != null && place.lng != null &&
    Math.abs(place.lat) <= 90 && Math.abs(place.lng) <= 180;
}
function destinationName(row) { return firstValue(row, ["name", "destination_name"]); }
function destinationId(row) { return firstValue(row, ["destination_id", "id"]); }
function getSavedUserPlaces() { return readArray("wayboundUserPlaces"); }
function getTripIds() { return S.trip; }

function showLoadErrors() {
  const panel = $("#loadErrors");
  if (!panel) return;
  if (!loadErrors.length) { panel.hidden = true; return; }
  panel.hidden = false;
  panel.innerHTML = `<b>Some data could not be loaded:</b><ul>${loadErrors.map((error) => `<li>${esc(error)}</li>`).join("")}</ul><p class="small">Place the CSV files inside a folder named <code>data</code>, beside index.html, and open the site using Live Server.</p>`;
}

// --------------------------------- Geography --------------------------------
function distanceKm(a, b) {
  const earthRadius = 6371.0088;
  const rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad;
  const dLng = (b.lng - a.lng) * rad;
  const h = Math.sin(dLat / 2) ** 2 +
    Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLng / 2) ** 2;
  return 2 * earthRadius * Math.asin(Math.sqrt(h));
}
function distanceFromStart(place) {
  return S.start && hasCoordinates(place) ? distanceKm(S.start, place) : null;
}
function distanceFromSelected(place) {
  return S.selected && hasCoordinates(S.selected) && hasCoordinates(place)
    ? distanceKm(S.selected, place)
    : null;
}

// ------------------------- Search ANY Indian location ----------------------
// Photon is used for public geocoding. This does not add the result to the
// curated CSV dataset; it only gives the user a map point to search around.
let lastPhotonRequest = 0;
async function searchIndianPlaces(query) {
  const cleanQuery = String(query || "").trim();
  if (cleanQuery.length < 2) return [];

  // Keep requests spaced apart to avoid flooding the public geocoder.
  const now = Date.now();
  const wait = Math.max(0, 650 - (now - lastPhotonRequest));
  if (wait) await new Promise((resolve) => setTimeout(resolve, wait));
  lastPhotonRequest = Date.now();

  const url = `https://photon.komoot.io/api/?q=${encodeURIComponent(cleanQuery + ", India")}&limit=8&lang=en`;
  const response = await fetch(url, { headers: { "Accept": "application/json" } });
  if (!response.ok) throw new Error("External location search is temporarily unavailable.");
  const json = await response.json();

  return (json.features || []).map((feature) => {
    const properties = feature.properties || {};
    const coords = feature.geometry?.coordinates || [];
    const lng = Number(coords[0]);
    const lat = Number(coords[1]);
    const country = String(properties.country || "").toLowerCase();
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
    if (country && country !== "india") return null;

    const label = properties.name || properties.city || properties.town || properties.village || properties.county || cleanQuery;
    const state = properties.state || "";
    const district = properties.district || properties.county || "";
    const description = [district, state, properties.country || "India"].filter(Boolean).join(", ");
    return {
      kind: "external",
      label,
      sub: `${description} · Search result (not a curated listing)`,
      name: label,
      state,
      district,
      lat,
      lng,
      osmId: properties.osm_id || ""
    };
  }).filter(Boolean);
}

function csvDestinationSuggestions(query) {
  const text = String(query || "").trim().toLowerCase();
  if (!text) return [];
  return S.dest.filter((destination) => {
    const searchable = [destination.name, destination.state, destination.district, destination.category].join(" ").toLowerCase();
    return searchable.includes(text);
  }).slice(0, 8).map((destination) => ({
    kind: "dataset",
    label: destination.name,
    sub: `${destination.district || "District not available"}, ${destination.state} · Curated Waybound dataset`,
    destination
  }));
}

async function destinationSearch(query) {
  const text = String(query || "").trim();
  if (text.length < 2) return [];
  const curated = csvDestinationSuggestions(text);
  let external = [];
  if (text.length >= 3) {
    try {
      external = await searchIndianPlaces(text);
    } catch (error) {
      console.warn("External destination search failed:", error);
    }
  }

  // Avoid duplicate external suggestions close to curated CSV places.
  external = external.filter((place) => !curated.some((item) => {
    const d = item.destination;
    return hasCoordinates(d) && distanceKm(place, d) < 3;
  }));
  return [...curated, ...external].slice(0, 14);
}

// ----------------------------- Autocomplete UI -----------------------------
function attachAutocomplete(input, list, fetcher, onChoose, minChars = 2) {
  let choices = [];
  let activeIndex = -1;
  let timer = null;
  let requestId = 0;

  function draw() {
    list.innerHTML = choices.map((choice, index) => `
      <li class="${index === activeIndex ? "hi" : ""}" data-index="${index}" role="option">
        ${esc(choice.label)}
        ${choice.sub ? `<small>${esc(choice.sub)}</small>` : ""}
      </li>
    `).join("");
    list.hidden = choices.length === 0;
  }

  async function runSearch() {
    const query = input.value.trim();
    const thisRequest = ++requestId;
    if (query.length < minChars) { choices = []; draw(); return; }
    try {
      choices = await fetcher(query);
      if (thisRequest !== requestId) return; // Ignore an older response.
      activeIndex = -1;
      draw();
    } catch (error) {
      console.warn("Autocomplete failed:", error);
      choices = [];
      draw();
    }
  }

  function choose(index) {
    const choice = choices[index];
    if (!choice) return;
    input.value = choice.label;
    list.hidden = true;
    onChoose(choice);
  }

  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(runSearch, 450);
  });
  input.addEventListener("focus", () => {
    if (input.value.trim().length >= minChars) runSearch();
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Escape") { list.hidden = true; return; }
    if (event.key === "ArrowDown" && choices.length) {
      activeIndex = Math.min(activeIndex + 1, choices.length - 1);
      draw(); event.preventDefault();
    } else if (event.key === "ArrowUp" && choices.length) {
      activeIndex = Math.max(activeIndex - 1, 0);
      draw(); event.preventDefault();
    } else if (event.key === "Enter" && choices.length) {
      event.preventDefault();
      choose(activeIndex >= 0 ? activeIndex : 0);
    }
  });
  list.addEventListener("mousedown", (event) => {
    const item = event.target.closest("li[data-index]");
    if (item) { event.preventDefault(); choose(Number(item.dataset.index)); }
  });
  input.addEventListener("blur", () => setTimeout(() => { list.hidden = true; }, 180));
}

// --------------------------------- Leaflet map ------------------------------
function initMap() {
  if (!window.L || S.map) return;
  S.map = L.map("map", { scrollWheelZoom: false }).setView([16.8, 79.5], 6);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "© OpenStreetMap contributors"
  }).addTo(S.map);
  S.markersLayer = L.layerGroup().addTo(S.map);
}

function buildMapMarkers() {
  if (!S.map || !S.markersLayer) return;
  S.markersLayer.clearLayers();
  S.markers = {};

  S.dest.filter(hasCoordinates).forEach((destination) => {
    const id = destination.destination_id;
    const marker = L.marker([destination.lat, destination.lng])
      .bindPopup(`<b>${esc(destination.name)}</b><br>${esc(destination.district || "")}, ${esc(destination.state)}<br><small>Curated Waybound destination</small><br><a href="#details/${encodeURIComponent(id)}">View details →</a>`)
      .on("click", () => selectCsvDestination(destination, false));
    S.markers[id] = marker;
    marker.addTo(S.markersLayer);
  });

  if (S.start) {
    S.startMarker = L.circleMarker([S.start.lat, S.start.lng], {
      radius: 8, color: "#2f5d46", fillColor: "#3f7a5c", fillOpacity: 0.95
    }).bindPopup(`<b>Starting location</b><br>${esc(S.start.label)}`).addTo(S.map);
  }
  updateSelectedMarker();
  fitAllMarkers();
}

function updateSelectedMarker() {
  if (!S.map) return;
  if (S.selectedMarker) { S.selectedMarker.remove(); S.selectedMarker = null; }
  if (S.selected && hasCoordinates(S.selected)) {
    const label = S.selectedIsExternal ? "Searched map location" : "Selected curated destination";
    S.selectedMarker = L.marker([S.selected.lat, S.selected.lng])
      .bindPopup(`<b>${esc(S.selected.name)}</b><br><small>${label}</small>`)
      .addTo(S.map);
  }
}

function updateRouteLine() {
  if (S.routeLine && S.map) { S.routeLine.remove(); S.routeLine = null; }
  if (!S.map || !S.start || !S.selected || !hasCoordinates(S.selected)) return;
  S.routeLine = L.polyline(
    [[S.start.lat, S.start.lng], [S.selected.lat, S.selected.lng]],
    { color: "#c0603a", dashArray: "6 6", weight: 3 }
  ).addTo(S.map);
}

function fitAllMarkers() {
  if (!S.map) return;
  const points = S.dest.filter(hasCoordinates).map((d) => [d.lat, d.lng]);
  if (S.selected && hasCoordinates(S.selected)) points.push([S.selected.lat, S.selected.lng]);
  if (S.start) points.push([S.start.lat, S.start.lng]);
  if (!points.length) return;
  if (points.length === 1) S.map.setView(points[0], 9);
  else S.map.fitBounds(L.latLngBounds(points).pad(0.08), { maxZoom: 8 });
}

function setStart(place) {
  S.start = { label: place.label, lat: Number(place.lat), lng: Number(place.lng) };
  if (!Number.isFinite(S.start.lat) || !Number.isFinite(S.start.lng)) return;
  $("#startStatus").textContent = `Starting from ${S.start.label}`;
  if (S.startMarker && S.map) S.startMarker.remove();
  if (S.map) {
    S.startMarker = L.circleMarker([S.start.lat, S.start.lng], {
      radius: 8, color: "#2f5d46", fillColor: "#3f7a5c", fillOpacity: 0.95
    }).bindPopup(`<b>Starting location</b><br>${esc(S.start.label)}`).addTo(S.map);
  }
  updateDistanceText();
  updateRouteLine();
  renderAll();
  renderBudget();
  if (S.selected && hasCoordinates(S.selected) && S.map) {
    S.map.fitBounds([[S.start.lat, S.start.lng], [S.selected.lat, S.selected.lng]], { padding: [30, 30], maxZoom: 10 });
  }
}

function useCurrentLocation() {
  if (!navigator.geolocation) {
    $("#startStatus").textContent = "Location access is not supported by this browser.";
    return;
  }
  $("#startStatus").textContent = "Finding your location…";
  navigator.geolocation.getCurrentPosition(async (position) => {
    const lat = position.coords.latitude;
    const lng = position.coords.longitude;
    let label = "My current location";
    try {
      const response = await fetch(`https://photon.komoot.io/reverse?lat=${lat}&lon=${lng}&lang=en`);
      if (response.ok) {
        const json = await response.json();
        const p = json.features?.[0]?.properties;
        if (p) label = [p.name, p.city, p.state].filter(Boolean).join(", ") || label;
      }
    } catch (error) { console.warn("Could not reverse-geocode location", error); }
    $("#startInput").value = label;
    setStart({ label, lat, lng });
  }, (error) => {
    $("#startStatus").textContent = `Could not get location: ${error.message}`;
  }, { enableHighAccuracy: true, timeout: 12000 });
}

function updateDistanceText() {
  const output = $("#distanceOut");
  if (!S.selected) {
    output.textContent = "Search any town, city or destination — not only places in our CSV.";
    return;
  }
  if (!hasCoordinates(S.selected)) {
    output.textContent = "Coordinates are unavailable for this selection.";
    return;
  }
  if (!S.start) {
    output.textContent = `Selected search centre: ${S.selected.name}. Set a starting location to calculate your route distance.`;
    return;
  }
  output.innerHTML = `<span class="dist">${distanceKm(S.start, S.selected).toFixed(1)} km</span> straight-line from ${esc(S.start.label)} to ${esc(S.selected.name)}`;
}

// -------------------------- Destination filtering --------------------------
function categoriesOf(destination) {
  return String(destination.category || "").split(/[;,/|]+/).map((item) => item.trim().toLowerCase()).filter(Boolean);
}
function fillSelect(select, values, label) {
  const previous = select.value;
  select.innerHTML = `<option value="">${esc(label)}</option>` + values.map((value) =>
    `<option value="${esc(value)}" ${value === previous ? "selected" : ""}>${esc(value)}</option>`
  ).join("");
}
function refreshFilterOptions() {
  const state = $("#stateFilter").value;
  const pool = S.dest.filter((d) => !state || d.states.includes(state));
  fillSelect($("#districtFilter"), [...new Set(pool.map((d) => d.district).filter(Boolean))].sort(), "All districts");
  fillSelect($("#categoryFilter"), [...new Set(pool.flatMap(categoriesOf))].sort(), "All categories");
}
const INTEREST_KEYWORDS = {
  "Nature": ["nature", "eco-tourism", "eco tourism", "hill", "valley", "beach", "coast", "waterfall", "lake", "forest", "wildlife", "cave", "river", "birdwatching", "viewpoint", "reservoir"],
  "Heritage": ["heritage", "temple", "fort", "architecture", "history", "ancient", "unesco", "spiritual", "monument", "kakatiya", "buddhist", "cultural heritage"],
  "Local Food": ["food", "culinary", "cuisine", "sweet", "laddu", "pootharekulu", "bamboo chicken", "coffee", "food experience", "food heritage"],
  "Traditional Crafts": ["craft", "handloom", "textile", "toy", "toys", "metal craft", "brass", "ikat", "weaving", "lace", "kalankari", "kalamkari", "carving", "filigree", "dokra", "veena", "khadi", "saree", "sari"],
  "Adventure": ["adventure", "trek", "trekking", "hiking", "boating", "camping", "waterfall", "cave", "beach", "cycling", "outdoor"],
  "Village Experiences": ["village", "rural tourism", "craft village", "workshop", "artisan", "weaver", "weaving", "demonstration", "community", "local experience", "tribal culture"]
};

function relatedRowsForDestination(destination) {
  const id = destination.destination_id;
  const district = String(destination.district || "").toLowerCase();
  const crafts = S.crafts.filter((row) => row.destination_id === id);
  const experiences = S.exp.filter((row) => row.destination_id === id || (crafts.some((craft) => craft.craft_id === row.craft_id)));
  const foods = S.food.filter((row) => (district && String(row.district || "").toLowerCase() === district) ||
    (row.origin_place && String(row.origin_place).toLowerCase().includes(String(destination.name || "").toLowerCase())));
  return { crafts, experiences, foods };
}

function destinationMatchesInterest(destination, interest) {
  const related = relatedRowsForDestination(destination);
  const combined = [
    destination.name, destination.category, destination.description, destination.district,
    ...related.crafts.flatMap((row) => [row.craft_name, row.materials, row.techniques_process, row.products, row.history_note, row.artisan_community]),
    ...related.experiences.flatMap((row) => [row.name, row.experience_type, row.description]),
    ...related.foods.flatMap((row) => [row.food_name, row.description, row.origin_place])
  ].filter(Boolean).join(" ").toLowerCase();

  if (interest === "Local Food" && related.foods.length) return true;
  if (interest === "Traditional Crafts" && related.crafts.length) return true;
  const keywords = INTEREST_KEYWORDS[interest] || [];
  return keywords.some((keyword) => combined.includes(keyword));
}

function renderInterestControls() {
  document.querySelectorAll("[data-interest]").forEach((button) => {
    const active = S.activeInterests.includes(button.dataset.interest);
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
}

function setActiveInterest(interest) {
  const index = S.activeInterests.indexOf(interest);
  if (index >= 0) S.activeInterests.splice(index, 1);
  else S.activeInterests.push(interest);
  localStorage.setItem("wayboundInterests", JSON.stringify(S.activeInterests));
  renderInterestControls();
  renderAll();
}

function updateNearbyPanel(results = filteredDestinations()) {
  const title = $("#nearbyTitle");
  const text = $("#nearbyText");
  const count = $("#nearbyCount");
  const radius = Number($("#distFilter").value);
  const hasCentre = S.selected && hasCoordinates(S.selected);

  document.querySelectorAll("[data-radius]").forEach((button) => {
    button.disabled = !hasCentre;
    button.classList.toggle("active", Number(button.dataset.radius) === radius);
    button.setAttribute("aria-pressed", String(Number(button.dataset.radius) === radius));
  });

  if (!hasCentre) {
    title.textContent = "Discover places around your destination";
    text.textContent = "Search for any city, town or place above. Waybound will find curated destinations near it.";
    count.textContent = "Choose a destination";
    return;
  }

  const numericDistances = results.map((place) => distanceFromSelected(place)).filter((distance) => distance != null);
  const within = radius >= 1000 ? results.length : numericDistances.filter((distance) => distance <= radius).length;
  title.textContent = `Explore around ${S.selected.name}`;
  text.textContent = radius >= 1000
    ? "Showing curated destinations sorted by straight-line distance from your selected map location."
    : `Showing curated destinations within ${radius} km of ${S.selected.name}. Distances are straight-line estimates, not road distances.`;
  count.textContent = `${within} nearby place${within === 1 ? "" : "s"}`;
}

function filteredDestinations() {
  const query = $("#searchInput").value.trim().toLowerCase();
  const state = $("#stateFilter").value;
  const district = $("#districtFilter").value;
  const category = $("#categoryFilter").value;
  const radius = Number($("#distFilter").value);
  const applyRadius = !!(S.selected && hasCoordinates(S.selected) && radius < 1000);

  const results = S.dest.filter((destination) => {
    const stateMatch = !state || destination.states.includes(state);
    const districtMatch = !district || destination.district === district;
    const categoryMatch = !category || categoriesOf(destination).includes(category);
    const text = [destination.name, destination.description, destination.category, destination.district, destination.state].join(" ").toLowerCase();
    const searchMatch = !query || text.includes(query);
    const interestMatch = !S.activeInterests.length || S.activeInterests.some((interest) => destinationMatchesInterest(destination, interest));
    const distance = S.selected ? distanceFromSelected(destination) : null;
    // Keep places with missing coordinates in the list, but don't invent a distance.
    const radiusMatch = !applyRadius || distance == null || distance <= radius;
    return stateMatch && districtMatch && categoryMatch && searchMatch && interestMatch && radiusMatch;
  });

  if (S.selected && hasCoordinates(S.selected)) {
    results.sort((a, b) => (distanceFromSelected(a) ?? Infinity) - (distanceFromSelected(b) ?? Infinity));
  }
  return results;
}

function destinationPhoto(destination) {
  if (isImageSource(destination.photo)) return { file_url: destination.photo };
  return S.media.find((media) => media.destination_id === destination.destination_id && isImageSource(media.file_url)) || null;
}
function destinationCard(destination) {
  const media = destinationPhoto(destination);
  const distance = S.selected ? distanceFromSelected(destination) : null;
  const image = media
    ? `<img class="thumb" src="${esc(media.file_url)}" alt="${esc(destination.name)}" loading="lazy">${destination.destination_id === "DST-TG-0021" ? '<small class="image-context-note">Regional handloom image · Mothkur, not Puttapaka</small>' : ''}`
    : `<div class="thumb ph-thumb"><span>${esc((destination.name || "?").charAt(0))}</span><small>Photo not available</small></div>`;
  const inTrip = S.trip.includes(destination.destination_id);
  const distanceText = distance != null
    ? `<span class="dist">${distance.toFixed(1)} km</span> from selected location`
    : S.selected ? "Distance not available (coordinates missing)" : "Select a destination to see nearby places";

  return `<article class="card dcard ${S.selected?.destination_id === destination.destination_id ? "sel" : ""}" data-id="${esc(destination.destination_id)}">
    ${image}
    <div>
      <h3>${esc(destination.name)}</h3>
      <div class="meta">${esc(destination.district || "District unavailable")} · ${esc(destination.state || "State unavailable")}</div>
      <div class="tags">${categoriesOf(destination).slice(0, 3).map((category) => `<span class="tag">${esc(category)}</span>`).join("")}${!hasCoordinates(destination) ? '<span class="tag warn">No coordinates</span>' : ""}</div>
      <p class="desc">${val(destination.description)}</p>
      <div class="meta">${distanceText}</div>
      <div class="actions">
        <button class="btn sm primary" data-act="details">Details</button>
        <button class="btn sm ${inTrip ? "added" : "ghost"}" data-act="trip">${inTrip ? "✓ In trip" : "+ Add to trip"}</button>
      </div>
    </div>
  </article>`;
}

function renderAll() {
  if (!S.loaded) return;
  const results = filteredDestinations();
  $("#cards").innerHTML = results.length
    ? results.map(destinationCard).join("")
    : '<p class="muted">No curated destinations match this search radius or filters. Try increasing the distance.</p>';

  const noCoordinates = results.filter((destination) => !hasCoordinates(destination)).length;
  const centreName = S.selected ? ` · Nearby ${esc(S.selected.name)}` : "";
  const interestLabel = S.activeInterests.length ? ` · Interests: ${S.activeInterests.map(esc).join(", ")}` : "";
  $("#resultCount").innerHTML = `${results.length} curated destination${results.length === 1 ? "" : "s"}${centreName}${interestLabel}${noCoordinates ? ` · ${noCoordinates} without coordinates` : ""}`;
  updateNearbyPanel(results);
  const interestStatus = $("#interestStatus");
  if (interestStatus) interestStatus.textContent = S.activeInterests.length
    ? `${results.length} destinations currently match at least one selected interest. Multiple interests work as OR filters.`
    : "No interest filter selected. Showing destinations matching your other filters.";

  const visibleIds = new Set(results.map((destination) => destination.destination_id));
  Object.entries(S.markers).forEach(([id, marker]) => {
    if (visibleIds.has(id)) marker.addTo(S.markersLayer);
    else marker.remove();
  });
  $("#tripCount").textContent = S.trip.length;
}

// ---------------------------- Select destinations --------------------------
function selectCsvDestination(destination, fly = true) {
  S.selected = destination;
  S.selectedIsExternal = false;
  $("#destInput").value = destination.name;
  $("#distFilter").disabled = !hasCoordinates(destination);
  updateSelectedMarker();
  updateRouteLine();
  updateDistanceText();
  renderAll();
  if (S.map && hasCoordinates(destination) && fly) {
    S.map.flyTo([destination.lat, destination.lng], 9);
    S.markers[destination.destination_id]?.openPopup();
  }
  if (S.map && S.start && hasCoordinates(destination)) {
    S.map.fitBounds([[S.start.lat, S.start.lng], [destination.lat, destination.lng]], { padding: [30, 30], maxZoom: 10 });
  }
}

function selectExternalDestination(place) {
  S.selected = {
    destination_id: `SEARCH-${Number(place.lat).toFixed(5)}-${Number(place.lng).toFixed(5)}`,
    name: place.name || place.label,
    state: place.state || "India",
    district: place.district || "",
    category: "External map search",
    description: "This is a location selected from an external map search. It is not a verified tourism record in Waybound's curated dataset.",
    lat: Number(place.lat),
    lng: Number(place.lng),
    latitude: Number(place.lat),
    longitude: Number(place.lng),
    mapSearch: true
  };
  S.selectedIsExternal = true;
  $("#distFilter").disabled = false;
  $("#distFilter").value = 1000;
  $("#distLabel").textContent = "Any";
  updateSelectedMarker();
  updateRouteLine();
  updateDistanceText();
  renderAll();
  if (S.map && hasCoordinates(S.selected)) {
    S.map.flyTo([S.selected.lat, S.selected.lng], 9);
    if (S.start) S.map.fitBounds([[S.start.lat, S.start.lng], [S.selected.lat, S.selected.lng]], { padding: [30, 30], maxZoom: 10 });
  }
}

function chooseDestinationSuggestion(item) {
  if (item.kind === "dataset") selectCsvDestination(item.destination);
  else selectExternalDestination(item);
}

function selectDestinationCard(id) {
  const destination = S.dest.find((item) => item.destination_id === id);
  if (destination) selectCsvDestination(destination);
}

// -------------------------------- Destination details -----------------------
function sourceLinks(row) {
  return [link(row.source_url_primary, "Primary source"), link(row.source_url_secondary, "Secondary source")].filter(Boolean).join(" · ") || NA;
}
function detailBlock(title, rows, renderer) {
  return `<div class="sec"><h3>${title}</h3>${rows.length ? `<div class="sub">${rows.map(renderer).join("")}</div>` : `<p>${NA}</p>`}</div>`;
}
function renderExternalDetails() {
  const d = S.selected;
  $("#detail").innerHTML = `
    <div class="dhero">
      <div><div class="ph"><div><b>Map search location</b><br>${esc(d.name)}</div></div></div>
      <div><p class="eyebrow">EXTERNAL MAP SEARCH</p><h2>${esc(d.name)}</h2>
        <p>This location was found through an external geocoding service. It is not part of Waybound's verified tourism dataset, so verified tourism descriptions, prices, timings and facilities are not claimed here.</p>
        <dl class="facts"><dt>State/region</dt><dd>${val(d.state)}</dd><dt>District</dt><dd>${val(d.district)}</dd><dt>Coordinates</dt><dd>${d.lat.toFixed(6)}, ${d.lng.toFixed(6)}</dd>
        <dt>From starting point</dt><dd>${S.start ? distanceKm(S.start, d).toFixed(1) + " km straight-line" : "Set a starting location"}</dd>
        <dt>Record type</dt><dd>External map result · Not curated</dd></dl>
        <div class="actions"><button class="btn primary" id="externalBack">Find nearby curated places</button></div>
      </div>
    </div>
    <div class="sec"><h3>Nearby Waybound destinations</h3><p class="muted">The results on Explore are selected from your Andhra Pradesh and Telangana tourism CSV files. Adjust the distance slider to discover places around this location.</p></div>
  `;
  $("#externalBack").onclick = () => { location.hash = "explore"; };
}

function renderDetails(id) {
  if (S.selectedIsExternal && S.selected && S.selected.destination_id === id) {
    renderExternalDetails();
    return;
  }
  const d = S.dest.find((destination) => destination.destination_id === id);
  if (!d) {
    $("#detail").innerHTML = `<div class="card"><p>Destination not found in the curated dataset.</p></div>`;
    return;
  }

  const photos = S.media.filter((media) => media.destination_id === id && isImageSource(media.file_url));
  const photo = destinationPhoto(d);
  const crafts = S.crafts.filter((craft) => craft.destination_id === id);
  const linkedCraftIds = new Set(crafts.map((craft) => craft.craft_id));
  const giIds = new Set(crafts.map((craft) => craft.gi_id).filter(Boolean));
  const gi = S.gi.filter((product) => product.destination_id === id || giIds.has(product.gi_id));
  gi.forEach((product) => { if (product.gi_id) giIds.add(product.gi_id); });
  const food = S.food.filter((item) => (item.gi_id && giIds.has(item.gi_id)) || (d.district && item.district === d.district));
  const experiences = S.exp.filter((item) => item.destination_id === id || linkedCraftIds.has(item.craft_id));
  const sources = S.sources.filter((source) => source.record_id === id && isUrl(source.source_url));
  const distance = distanceFromStart(d);

  $("#detail").innerHTML = `
    <div class="dhero">
      <div>${photo ? `<img src="${esc(photo.file_url)}" alt="${esc(d.name)}">` : `<div class="ph"><div><b>Photo</b><br>${NA}</div></div>`}
        ${photos.map((media) => `<p class="meta">${esc(media.title || "Image")}${media.attribution_text ? " — " + esc(media.attribution_text) : ""} ${link(media.source_page_url, "Source page")} ${media.licence ? "· Licence: " + esc(media.licence) : ""}</p>`).join("")}
      </div>
      <div><p class="eyebrow">${esc(d.state)}</p><h2>${esc(d.name)}</h2><p>${val(d.description)}</p>
        <dl class="facts">
          <dt>District</dt><dd>${val(d.district)}</dd>
          <dt>Category</dt><dd>${val(d.category)}</dd>
          <dt>Best season</dt><dd>${val(d.best_season)} ${link(d.best_season_source_url, "(source)")}</dd>
          <dt>Coordinates</dt><dd>${hasCoordinates(d) ? `${d.lat}, ${d.lng} ${link(d.coordinate_source_url, "(source)")}` : NA}</dd>
          <dt>Distance from start</dt><dd>${distance != null ? distance.toFixed(1) + " km (straight-line)" : S.start ? NA : "Set a starting location"}</dd>
          <dt>Verification</dt><dd>${val(d.verification_status)}</dd>
          <dt>Sources</dt><dd class="links">${sourceLinks(d)}</dd>
        </dl>
        <div class="actions"><button class="btn primary" id="dTrip">${S.trip.includes(id) ? "✓ In trip" : "+ Add to trip"}</button></div>
      </div>
    </div>
    ${detailBlock("Local food", food, (f) => `<div class="card"><h4>${esc(f.food_name)}</h4><p class="meta">${val(f.origin_place)}, ${val(f.district)}</p><p>${val(f.description)}</p><p><b>Ingredients:</b> ${val(f.ingredients)}</p><p><b>Significance:</b> ${val(f.cultural_significance)}</p><p class="links">${sourceLinks(f)}</p></div>`)}
    ${detailBlock("GI crafts &amp; products", [...crafts.map((craft) => ({ craft })), ...gi.filter((product) => !crafts.some((craft) => craft.gi_id === product.gi_id)).map((product) => ({ product }))], (item) => item.craft
      ? `<div class="card"><h4>${esc(item.craft.craft_name)}</h4><p><b>Materials:</b> ${val(item.craft.materials)}</p><p><b>Process:</b> ${val(item.craft.techniques_process)}</p><p><b>Products:</b> ${val(item.craft.products)}</p><p><b>History:</b> ${val(item.craft.history_note)}</p><p class="links">${sourceLinks(item.craft)}</p></div>`
      : `<div class="card"><h4>${esc(item.product.gi_name || item.product.base_name)}</h4><p class="meta">${val(item.product.goods_category)} · ${val(item.product.registration_period)}</p><p><b>Origin:</b> ${val(item.product.origin_place)}, ${val(item.product.origin_district)}</p><p class="links">${link(item.product.source_url, "GI registry")}</p></div>`)}
    ${detailBlock("Cultural experiences", experiences, (e) => `<div class="card"><h4>${esc(e.name)}</h4><p class="meta">${val(e.experience_type)}</p><p>${val(e.description)}</p><p><b>Season:</b> ${val(e.months_or_season)}</p><p><b>Availability:</b> ${val(e.availability_note || e.availability_status)}</p><p><b>Price:</b> ${val(e.price)}</p><p class="links">${sourceLinks(e)}</p></div>`)}
    <div class="sec"><h3>Location</h3>${hasCoordinates(d) ? '<div id="detailMap" class="detail-map"></div>' : `<p>${NA} — no coordinates are available.</p>`}</div>
    <div class="sec"><h3>Image credits</h3>${photos.length ? `<ul class="links">${photos.map((media) => `<li>${esc(media.title || "Image")} — ${val(media.creator)} · ${val(media.licence)} ${link(media.licence_url, "licence")} · ${link(media.source_page_url, "source page")}</li>`).join("")}</ul>` : `<p>${NA}</p>`}</div>
    <div class="sec"><h3>Source references</h3>${sources.length ? `<ul class="links">${sources.map((source) => `<li>${esc(source.source_field || "Source")}: ${link(source.source_url)}</li>`).join("")}</ul>` : `<p>${NA}</p>`}</div>
  `;

  $("#dTrip").onclick = () => { toggleTrip(id); renderDetails(id); };
  if (hasCoordinates(d) && window.L) {
    setTimeout(() => {
      if (S.detailMap) S.detailMap.remove();
      const el = $("#detailMap");
      if (!el) return;
      S.detailMap = L.map("detailMap", { scrollWheelZoom: false }).setView([d.lat, d.lng], 11);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap contributors" }).addTo(S.detailMap);
      L.marker([d.lat, d.lng]).addTo(S.detailMap).bindPopup(esc(d.name));
      S.detailMap.invalidateSize();
    }, 100);
  }
}

// -------------------------------- Trip storage ------------------------------
function toggleTrip(id) {
  const index = S.trip.indexOf(id);
  if (index >= 0) S.trip.splice(index, 1);
  else S.trip.push(id);
  localStorage.setItem("wayboundTrip", JSON.stringify(S.trip));
  renderAll();
  renderBudget();
}

function renderBudget() {
  const items = S.trip.map((id) => S.dest.find((d) => d.destination_id === id)).filter(Boolean);
  $("#tripList").innerHTML = `<h3>Selected destinations</h3>` + (items.length
    ? items.map((d) => `<div class="trip-item"><span><b>${esc(d.name)}</b><br><small class="muted">${esc(d.district || "")}, ${esc(d.state)} · ${distanceFromStart(d) != null ? distanceFromStart(d).toFixed(1) + " km from start" : "distance not available"}</small></span><button class="btn sm ghost" data-rm="${esc(d.destination_id)}">Remove</button></div>`).join("")
    : '<p class="muted">No destinations yet. Use “+ Add to trip” on Explore.</p>');

  let route = 0;
  const coordinatePlaces = items.filter(hasCoordinates);
  const missing = items.length - coordinatePlaces.length;
  if (S.start && coordinatePlaces.length) {
    let previous = S.start;
    coordinatePlaces.forEach((destination) => { route += distanceKm(previous, destination); previous = destination; });
    route += distanceKm(previous, S.start);
  }

  const travellers = Math.max(1, Number($("#bTravellers").value) || 1);
  const nights = Math.max(0, Number($("#bNights").value) || 0);
  const roomSize = Math.max(1, Number($("#bRoom").value) || 1);
  const days = nights + 1;
  const rooms = Math.ceil(travellers / roomSize);
  const rate = (selector) => $(selector).value === "" ? null : Math.max(0, Number($(selector).value));

  const rows = [
    ["Travel", "Km", S.start && coordinatePlaces.length ? route : null, "estimated straight-line route loop"],
    ["Stay", "Stay", rooms * nights, `${rooms} room(s) × ${nights} night(s)`],
    ["Food", "Food", travellers * days, `${travellers} × ${days} day(s)`],
    ["Other", "Other", travellers, `${travellers} traveller(s)`]
  ].map(([name, key, quantity, note]) => {
    const minRate = rate(`#b${key}Min`);
    const maxRate = rate(`#b${key}Max`);
    return {
      name, note,
      min: quantity != null && minRate != null ? quantity * minRate : null,
      max: quantity != null && (maxRate ?? minRate) != null ? quantity * (maxRate ?? minRate) : null
    };
  });

  const money = (amount) => "₹" + Math.round(amount).toLocaleString("en-IN");
  const minTotal = rows.reduce((sum, row) => sum + (row.min || 0), 0);
  const maxTotal = rows.reduce((sum, row) => sum + (row.max || 0), 0);
  $("#budgetOut").innerHTML = `<h3>Estimated budget</h3><table>
    <tr><td></td><td>Minimum</td><td>Maximum</td></tr>
    ${rows.map((row) => `<tr><td>${row.name} <small>(${row.note})</small></td><td>${row.min == null ? "—" : money(row.min)}</td><td>${row.max == null ? "—" : money(row.max)}</td></tr>`).join("")}
    <tr class="sum"><td>Total</td><td>${money(minTotal)}</td><td>${money(maxTotal)}</td></tr>
    <tr><td>Per person</td><td>${money(minTotal / travellers)}</td><td>${money(maxTotal / travellers)}</td></tr>
  </table>${missing ? `<p><small>${missing} place(s) without coordinates are excluded from travel distance.</small></p>` : ""}
  <p class="disclaimer"><small>Prices are entered by you; they are not included in the CSV data. The distance estimate is straight-line, not road distance.</small></p>`;
}

// ------------------------------ Artisan stories ----------------------------
function craftDestination(craft) {
  if (craft.destination_id) return S.dest.find((destination) => destination.destination_id === craft.destination_id) || null;
  const haystack = `${craft.craft_name || ""} ${craft.district || ""}`.toLowerCase();
  if (haystack.includes("warangal")) return S.dest.find((destination) => destination.destination_id === "DST-TG-0018") || null;
  return null;
}

function renderArtisanStories() {
  const host = $("#artisanStoryCards");
  if (!host) return;
  const query = String($("#artisanSearch")?.value || "").trim().toLowerCase();
  const state = $("#artisanStateFilter")?.value || "";

  const stories = S.crafts.filter((craft) => {
    const destination = craftDestination(craft);
    const craftState = craft.state || destination?.state || "";
    const searchable = [craft.craft_name, craft.artisan_community, craft.materials, craft.techniques_process, craft.products, craft.history_note, destination?.name, destination?.district].join(" ").toLowerCase();
    return (!state || craftState === state) && (!query || searchable.includes(query));
  });

  if (!stories.length) {
    host.innerHTML = '<p class="muted">No craft stories match your search. Try another keyword or state.</p>';
    return;
  }

  host.innerHTML = stories.map((craft) => {
    const destination = craftDestination(craft);
    const media = destination ? destinationPhoto(destination) : null;
    const image = media
      ? `<img class="story-image" src="${esc(media.file_url)}" alt="${esc(craft.craft_name)}" loading="lazy">`
      : `<div class="story-placeholder" aria-hidden="true">${esc((craft.craft_name || "C").charAt(0))}</div>`;
    const community = craft.artisan_community || "Local artisan community; individual group details are not listed in this dataset.";
    const process = craft.techniques_process || craft.history_note || "Further process details are not available in the current dataset.";
    const source = sourceLinks(craft);
    const relatedExperiences = S.exp.filter((experience) =>
      experience.craft_id === craft.craft_id || (destination && experience.destination_id === destination.destination_id)
    );
    const experienceHtml = relatedExperiences.length
      ? `<p><b>Related local experience:</b> ${relatedExperiences.map((experience) => esc(experience.name)).join("; ")}</p>`
      : "";
    const destinationButton = destination
      ? `<a class="btn sm primary" href="#details/${encodeURIComponent(destination.destination_id)}">Explore ${esc(destination.name)}</a>`
      : "";

    return `<article class="card story-card">
      ${image}
      <div class="story-body">
        <div class="story-kicker">${esc(craft.state || destination?.state || "Regional craft")}</div>
        <h3>${esc(craft.craft_name || "Traditional craft")}</h3>
        <p class="story-meta">${esc(destination?.district || craft.district || "Regional craft cluster")}${destination ? ` · ${esc(destination.name)}` : ""}</p>
        <p><b>Maker community:</b> ${val(community)}</p>
        <p><b>Materials and process:</b> ${val(process)}</p>
        ${craft.products ? `<p><b>Products:</b> ${val(craft.products)}</p>` : ""}
        ${craft.history_note ? `<p><b>Heritage:</b> ${val(craft.history_note)}</p>` : ""}
        ${experienceHtml}
        <p class="links">${source}</p>
        <div class="story-actions">${destinationButton}</div>
      </div>
    </article>`;
  }).join("");
}

// -------------------------------- Add a place -------------------------------
function cleanDescription(value) {
  return String(value || "").replace(/\s+/g, " ").replace(/\s+([,.!?;:])/g, "$1")
    .replace(/([,.!?;:])(?=[^\s\d])/g, "$1 ").trim()
    .replace(/(^|[.!?]\s+)([a-z])/g, (match, before, letter) => before + letter.toUpperCase())
    .replace(/\bi\b/g, "I").replace(/([^.!?])$/, "$1.");
}
function renderMyPlaces() {
  const places = getSavedUserPlaces();
  $("#myPlaces").innerHTML = places.length
    ? `<h3>Your saved suggestions (this device only)</h3>` + places.map((place) => `<div class="trip-item"><span><b>${esc(place.name)}</b> · ${esc(place.state)} <small class="muted">· User submitted · unverified</small></span><button class="btn sm ghost" data-del="${esc(place.destination_id)}">Remove</button></div>`).join("")
    : "";
}

function addUserPlace(event) {
  event.preventDefault();
  const form = $("#addForm");
  const fd = new FormData(form);
  const place = Object.fromEntries([...fd.entries()].map(([key, value]) => [key, String(value).trim()]));
  if (!ALLOWED_STATES.includes(place.state)) { alert("Choose Andhra Pradesh or Telangana for a curated community suggestion."); return; }
  if ((place.latitude === "") !== (place.longitude === "")) { alert("Enter both latitude and longitude, or leave both blank."); return; }
  const lat = place.latitude === "" ? null : Number(place.latitude);
  const lng = place.longitude === "" ? null : Number(place.longitude);
  if (lat != null && (!Number.isFinite(lat) || !Number.isFinite(lng) || Math.abs(lat) > 90 || Math.abs(lng) > 180)) {
    alert("Please enter valid coordinates."); return;
  }
  place.destination_id = `LOCAL-${Date.now()}`;
  place.latitude = lat == null ? "" : String(lat);
  place.longitude = lng == null ? "" : String(lng);
  place.user = true;
  place.verification_status = "User submitted · unverified";

  const saved = getSavedUserPlaces();
  saved.push(place);
  localStorage.setItem("wayboundUserPlaces", JSON.stringify(saved));
  S.dest.push(normalizeDestination(place));
  refreshFilterOptions();
  buildMapMarkers();
  renderAll();
  form.reset();
  $("#photoPreview").hidden = true;
  $("#photoPreview").innerHTML = "";
  $("#addMsg").hidden = false;
  $("#addMsg").textContent = `✓ ${place.name} was saved in this browser as an unverified suggestion.`;
  renderMyPlaces();
}

// -------------------------------- Navigation --------------------------------
function showView(view, argument) {
  document.querySelectorAll(".view").forEach((element) => element.classList.toggle("active", element.id === `view-${view}`));
  document.querySelectorAll("nav a").forEach((anchor) => anchor.classList.toggle("active", anchor.dataset.view === view));
  $("#nav").classList.remove("open");
  if (view === "details") renderDetails(argument);
  if (view === "budget") renderBudget();
  if (view === "add") {
    renderMyPlaces();
    setTimeout(() => S.initPickMap && S.initPickMap(), 100);
  }
  if (view === "explore" && S.map) setTimeout(() => S.map.invalidateSize(), 100);
  window.scrollTo(0, 0);
}
function handleHashRoute() {
  const [view, ...rest] = location.hash.slice(1).split("/");
  const allowed = ["details", "budget", "add"];
  const selectedView = allowed.includes(view) ? view : "explore";
  const argument = rest.length ? decodeURIComponent(rest.join("/")) : undefined;
  showView(selectedView, argument);
}

// -------------------------------- Initialize --------------------------------
async function init() {
  if (window.L) initMap();
  else console.warn("Leaflet did not load. Destination cards and search can still work without the map.");

  const [destinations, food, gi, crafts, experiences, media, sources] = await Promise.all([
    loadCSV(FILES.destinations),
    loadCSV(FILES.food),
    loadCSV(FILES.gi),
    loadCSV(FILES.crafts),
    loadCSV(FILES.experiences),
    loadCSV(FILES.media, true),
    loadCSV(FILES.sources, true)
  ]);

  S.dest = [...destinations, ...getSavedUserPlaces()]
    .filter((row) => inProjectScope(row.state))
    .map(normalizeDestination);
  S.food = food.filter((row) => inProjectScope(row.state));
  S.crafts = crafts.filter((row) => inProjectScope(row.state));
  S.exp = experiences.filter((row) => inProjectScope(row.state));
  S.gi = gi.filter((row) => inProjectScope(row.states_in_phase1 || row.state_ut_normalised || row.state_raw));
  S.media = media;
  S.sources = sources;
  S.loaded = true;

  const validIds = new Set(S.dest.map((destination) => destination.destination_id));
  S.trip = S.trip.filter((id) => validIds.has(id));
  localStorage.setItem("wayboundTrip", JSON.stringify(S.trip));

  const recordCounts = `Loaded ${S.dest.length} curated AP/Telangana destinations from CSV.`;
  console.info(recordCounts);
  if (!S.dest.length && !loadErrors.length) {
    loadErrors.push("No Andhra Pradesh or Telangana destination records were found. Check the state column in destinations.csv.");
  }
  showLoadErrors();
  $("#mapNote").textContent = `${recordCounts} External locations can also be searched and used as the nearby-search centre.`;

  // Keep the hero photo only if a checked media URL exists for a loaded record.
  const heroMedia = S.media.find((item) => isImageSource(item.file_url) && S.dest.some((d) => d.destination_id === item.destination_id));
  if (heroMedia) {
    $("#hero").style.setProperty("--hero-img", `url("${heroMedia.file_url}")`);
    $("#hero").classList.add("has-img");
    const destination = S.dest.find((d) => d.destination_id === heroMedia.destination_id);
    $("#heroCredit").innerHTML = `${esc(destination.name)} · ${link(heroMedia.source_page_url, "image source")}`;
  }

  fillSelect($("#stateFilter"), ALLOWED_STATES, "All states");
  refreshFilterOptions();
  buildMapMarkers();
  renderInterestControls();
  renderAll();
  renderArtisanStories();
  renderBudget();

  // Start location can be any place returned by Photon.
  attachAutocomplete($("#startInput"), $("#startSuggest"), searchIndianPlaces, (place) => setStart(place), 2);

  // Destination search combines CSV destinations + external map search results.
  attachAutocomplete($("#destInput"), $("#destSuggest"), destinationSearch, chooseDestinationSuggestion, 2);

  // Add-place location search also accepts any location; save the coordinates in the form.
  attachAutocomplete($("#addLoc"), $("#addSuggest"), searchIndianPlaces, (place) => setPick(place.lat, place.lng), 2);

  // Personalised-interest chips; multiple selected interests use OR matching.
  document.querySelectorAll("[data-interest]").forEach((button) => {
    button.addEventListener("click", () => setActiveInterest(button.dataset.interest));
  });
  $("#clearInterestsBtn").addEventListener("click", () => {
    S.activeInterests = [];
    localStorage.setItem("wayboundInterests", JSON.stringify(S.activeInterests));
    renderInterestControls();
    renderAll();
  });

  // Quick distance presets reuse the same selected-destination radius slider.
  document.querySelectorAll("[data-radius]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.disabled) return;
      $("#distFilter").value = button.dataset.radius;
      $("#distLabel").textContent = Number(button.dataset.radius) >= 1000 ? "Any" : `${button.dataset.radius} km`;
      renderAll();
    });
  });

  // Artisan story search and state filter.
  $("#artisanSearch").addEventListener("input", renderArtisanStories);
  $("#artisanStateFilter").addEventListener("change", renderArtisanStories);
  $("#artisanStoryCards").addEventListener("click", (event) => {
    const anchor = event.target.closest('a[href^="#details/"]');
    if (anchor) {
      const id = decodeURIComponent(anchor.getAttribute("href").split("/").slice(1).join("/"));
      const destination = S.dest.find((item) => item.destination_id === id);
      if (destination) selectCsvDestination(destination, false);
    }
  });

  $("#artisanNav").addEventListener("click", (event) => {
    event.preventDefault();
    if (location.hash !== "#explore") location.hash = "explore";
    setTimeout(() => $("#artisanStories").scrollIntoView({ behavior: "smooth", block: "start" }), 120);
    $("#nav").classList.remove("open");
  });

  $("#geoBtn").addEventListener("click", useCurrentLocation);

  // If the user starts typing a new destination, clear the previous selection centre.
  $("#destInput").addEventListener("input", () => {
    S.selected = null;
    S.selectedIsExternal = false;
    $("#distFilter").disabled = true;
    $("#distFilter").value = 1000;
    $("#distLabel").textContent = "Any";
    if (S.selectedMarker) { S.selectedMarker.remove(); S.selectedMarker = null; }
    if (S.routeLine) { S.routeLine.remove(); S.routeLine = null; }
    updateDistanceText();
    renderAll();
  });

  $("#searchInput").addEventListener("input", renderAll);
  $("#stateFilter").addEventListener("change", () => { refreshFilterOptions(); renderAll(); });
  $("#districtFilter").addEventListener("change", renderAll);
  $("#categoryFilter").addEventListener("change", renderAll);

  $("#distFilter").addEventListener("input", (event) => {
    $("#distLabel").textContent = Number(event.target.value) >= 1000 ? "Any" : `${event.target.value} km`;
    renderAll();
  });

  $("#resetBtn").addEventListener("click", () => {
    $("#searchInput").value = "";
    $("#stateFilter").value = "";
    refreshFilterOptions();
    $("#districtFilter").value = "";
    $("#categoryFilter").value = "";
    $("#distFilter").value = 1000;
    $("#distFilter").disabled = !(S.selected && hasCoordinates(S.selected));
    $("#distLabel").textContent = "Any";
    renderAll();
    if (S.map) fitAllMarkers();
  });

  // Click card body to select it; buttons perform their own action.
  $("#cards").addEventListener("click", (event) => {
    const card = event.target.closest(".dcard");
    if (!card) return;
    const destination = S.dest.find((item) => item.destination_id === card.dataset.id);
    if (!destination) return;
    const action = event.target.dataset.act;
    if (action === "details") location.hash = `details/${encodeURIComponent(destination.destination_id)}`;
    else if (action === "trip") toggleTrip(destination.destination_id);
    else selectCsvDestination(destination);
  });

  $("#tripList").addEventListener("click", (event) => {
    if (event.target.dataset.rm) toggleTrip(event.target.dataset.rm);
  });
  $("#budgetForm").addEventListener("input", renderBudget);
  $("#menuBtn").addEventListener("click", () => $("#nav").classList.toggle("open"));

  document.querySelectorAll("[data-view]").forEach((anchor) => anchor.addEventListener("click", (event) => {
    event.preventDefault();
    location.hash = anchor.dataset.view;
  }));

  // Add-place submissions are local to this browser only (no backend/server).
  $("#addForm").addEventListener("submit", addUserPlace);
  $("#cleanBtn").addEventListener("click", () => {
    const description = $("#addForm").elements.description;
    if (!description.value.trim()) { $("#cleanMsg").textContent = "Write a description first."; return; }
    description.value = cleanDescription(description.value);
    $("#cleanMsg").textContent = "Text tidied. Please review it; no new facts were added.";
  });

  // User-selected map pin for the Add a Place screen.
  S.initPickMap = () => {
    if (!window.L) return;
    if (S.pickMap) { S.pickMap.invalidateSize(); return; }
    S.pickMap = L.map("pickMap").setView([16.8, 79.5], 6);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: "© OpenStreetMap contributors"
    }).addTo(S.pickMap);
    S.pickMap.on("click", (event) => setPick(event.latlng.lat, event.latlng.lng));
  };

  function setPick(lat, lng) {
    const latitude = Number(lat), longitude = Number(lng);
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return;
    $("#addForm").elements.latitude.value = latitude.toFixed(6);
    $("#addForm").elements.longitude.value = longitude.toFixed(6);
    if (!S.pickMap) return;
    if (S.pickMarker) S.pickMarker.setLatLng([latitude, longitude]);
    else S.pickMarker = L.marker([latitude, longitude]).addTo(S.pickMap);
    S.pickMap.setView([latitude, longitude], Math.max(S.pickMap.getZoom(), 9));
  }

  ["latitude", "longitude"].forEach((name) => $("#addForm").elements[name].addEventListener("change", () => {
    const lat = num($("#addForm").elements.latitude.value);
    const lng = num($("#addForm").elements.longitude.value);
    if (lat != null && lng != null) setPick(lat, lng);
  }));

  $("#addForm").elements.photo.addEventListener("input", () => {
    const url = $("#addForm").elements.photo.value.trim();
    const box = $("#photoPreview");
    box.hidden = !isUrl(url);
    if (isUrl(url)) box.innerHTML = `<img src="${esc(url)}" alt="Photo preview" onerror="this.parentElement.hidden=true">`;
    else box.innerHTML = "";
  });

  $("#myPlaces").addEventListener("click", (event) => {
    const id = event.target.dataset.del;
    if (!id) return;
    const updated = getSavedUserPlaces().filter((place) => place.destination_id !== id);
    localStorage.setItem("wayboundUserPlaces", JSON.stringify(updated));
    S.dest = S.dest.filter((destination) => destination.destination_id !== id);
    S.trip = S.trip.filter((tripId) => tripId !== id);
    localStorage.setItem("wayboundTrip", JSON.stringify(S.trip));
    refreshFilterOptions(); buildMapMarkers(); renderAll(); renderBudget(); renderMyPlaces();
  });

  window.addEventListener("hashchange", handleHashRoute);
  handleHashRoute();
}

// Start only after HTML elements exist.
document.addEventListener("DOMContentLoaded", () => {
  init().catch((error) => {
    console.error("Waybound initialization failed:", error);
    const panel = $("#loadErrors");
    if (panel) {
      panel.hidden = false;
      panel.innerHTML = `<b>Could not start Waybound:</b><ul><li>${esc(error.message)}</li></ul>`;
    }
  });
});
