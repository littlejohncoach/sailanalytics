// viewer_leaflet.js
import { apiGet } from "./api_client.js";
import { state } from "./state.js";

let map = null;
let layersBySailor = new Map();     // sailor -> polyline
let markerBySailor = new Map();     // (kept for compatibility; we no longer draw start markers)
let timeMarksBySailor = new Map();
let rankMarkers = new Map(); // sailor -> rank label  // sailor -> array of time markers (dots + labels)

// Store current refresh track points so we can place bearing labels away from crowded tracks
let trackLatLngsBySailor = new Map(); // sailor -> [[lat, lon], ...]

/**
 * Geometry overlay (rum line + marks + bearing)
 */
let geometryLayer = null;
let geometryCache = {};

/**
 * Race metadata overlay (top-left Leaflet control)
 */
let raceMetadataControl = null;
let raceMetadataControlDiv = null;

// -------------------------------------------------
// Player controls (slider + play)
// TIME-BASED (seconds), not index-based.
// NO head markers (no moving dots).
// -------------------------------------------------
const player = (() => {
  let mapRef = null;
  let layersRef = null; // Map(sailor -> polyline)

  // full points per sailor (payload.points)
  let ptsBySailor = new Map(); // sailor -> [{lat,lon,t,...}, ...]

  // ui
  let ui = null;
  let minT = 0;
  let maxT = 0;
  let isPlaying = false;
  let timer = null;

  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  function fmtMMSS(seconds) {
    seconds = Math.max(0, Math.floor(Number(seconds) || 0));
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }

  // Robust time getter (in case payload key ever changes)
  function getT(p) {
    if (!p) return NaN;
    if (p.t !== undefined && p.t !== null) return Number(p.t);
    if (p.elapsed_race_time_s !== undefined && p.elapsed_race_time_s !== null) return Number(p.elapsed_race_time_s);
    if (p.time_s !== undefined && p.time_s !== null) return Number(p.time_s);
    return NaN;
  }

  function getUI() {
    if (ui) return ui;
    const wrap = document.getElementById("playerControls");
    if (!wrap) return null;

    ui = {
      wrap,
      slider: document.getElementById("timeSlider"),
      idxBox: document.getElementById("timeIndexBox"),
      lblStart: document.getElementById("lblStart"),
      lblFinish: document.getElementById("lblFinish"),
      lblNow: document.getElementById("lblNow"),
      btnPlay: document.getElementById("btnPlay"),
      btnStepBack: document.getElementById("btnStepBack"),
      btnStepFwd: document.getElementById("btnStepFwd"),
      btnFs: document.getElementById("btnFullscreen"), // can exist; we keep it harmless
    };

    for (const k of Object.keys(ui)) {
      if (!ui[k]) return null;
    }

    // Slider now represents ABSOLUTE SECONDS
    ui.slider.addEventListener("input", () => setTime(parseInt(ui.slider.value, 10) || 0));
    ui.idxBox.addEventListener("change", () => setTime(parseInt(ui.idxBox.value, 10) || 0));
    ui.btnPlay.addEventListener("click", () => togglePlay());
    ui.btnStepBack.addEventListener("click", () => setTime((parseInt(ui.slider.value, 10) || 0) - 10));
    ui.btnStepFwd.addEventListener("click", () => setTime((parseInt(ui.slider.value, 10) || 0) + 10));

    // If fullscreen button exists, keep it harmless
    ui.btnFs.addEventListener("click", async () => {
      try {
        if (!document.fullscreenElement) {
          await document.documentElement.requestFullscreen();
        } else {
          await document.exitFullscreen();
        }
        setTimeout(() => {
          try { if (mapRef) mapRef.invalidateSize(true); } catch (_) {}
        }, 150);
      } catch (e) {
        console.warn("Fullscreen failed:", e);
      }
    });

    return ui;
  }

  function stop() {
    isPlaying = false;
    if (ui) ui.btnPlay.textContent = "▶︎";
    if (timer) clearInterval(timer);
    timer = null;
  }

  function togglePlay() {
    if (!ui) return;
    isPlaying = !isPlaying;
    ui.btnPlay.textContent = isPlaying ? "⏸" : "▶︎";

    if (!isPlaying) {
      stop();
      return;
    }

    timer = setInterval(() => {
      const t = (parseInt(ui.slider.value, 10) || 0) + 1;
      if (t > maxT) {
        stop();
        return;
      }
      setTime(t);
    }, 200);
  }

  function setLabels() {
    if (!ui) return;

    if (!Number.isFinite(minT) || !Number.isFinite(maxT) || maxT <= minT) {
      ui.lblStart.textContent = "--:--";
      ui.lblFinish.textContent = "--:--";
      ui.lblNow.textContent = "T+--:--";
      return;
    }

    ui.lblStart.textContent = fmtMMSS(minT);
    ui.lblFinish.textContent = fmtMMSS(maxT);
    ui.lblNow.textContent = `T+${fmtMMSS(minT)}`;
  }

  // Binary search: last index where pts[idx].t <= tNow
  function lastIndexAtOrBeforeTime(pts, tNow) {
    let lo = 0;
    let hi = pts.length - 1;
    let ans = -1;

    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      const tm = getT(pts[mid]);
      if (!Number.isFinite(tm)) {
        hi = mid - 1;
        continue;
      }
      if (tm <= tNow) {
        ans = mid;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }
    return ans;
  }

  
function setTime(tNow) {
  if (!ui || !mapRef || !layersRef) return;

  tNow = clamp(tNow, minT, maxT);
  ui.slider.value = String(tNow);
  ui.idxBox.value = String(tNow);

  const rankData = [];

  for (const [sailor, pts] of ptsBySailor.entries()) {
    if (!Array.isArray(pts) || pts.length === 0) continue;

    const line = layersRef.get(sailor);
    if (!line) continue;

    const j = lastIndexAtOrBeforeTime(pts, tNow);

    if (j < 0) {
      line.setLatLngs([]);
      continue;
    }

    const latlngs = [];
    for (let k = 0; k <= j; k++) {
      const p = pts[k];
      const lat = Number(p.lat);
      const lon = Number(p.lon);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
      latlngs.push([lat, lon]);
    }

    line.setLatLngs(latlngs);

    const p = pts[j];
    if (p && p.dist !== undefined) {
      rankData.push({
        sailor,
        dist: Number(p.dist),
        lat: Number(p.lat),
        lon: Number(p.lon)
      });
    }
  }

  rankData.sort((a, b) => a.dist - b.dist);
  rankData.forEach((r, i) => r.rank = i + 1);

  for (const [, m] of rankMarkers) {
    try { mapRef.removeLayer(m); } catch {}
  }
  rankMarkers.clear();

  for (const r of rankData) {
    
// offset marker slightly back from track head
const pts = ptsBySailor.get(r.sailor);
let lat = r.lat;
let lon = r.lon;

if (pts && pts.length > 1) {
  const prev = pts[Math.max(0, pts.length - 2)];

  if (prev) {
    const p1 = mapRef.latLngToLayerPoint([r.lat, r.lon]);
    const p0 = mapRef.latLngToLayerPoint([prev.lat, prev.lon]);

    const dx = p1.x - p0.x;
    const dy = p1.y - p0.y;
    const mag = Math.hypot(dx, dy) || 1;

    const backPx = 10;

    const x = p1.x - (dx / mag) * backPx;
    const y = p1.y - (dy / mag) * backPx;

    const ll = mapRef.layerPointToLatLng([x, y]);
    lat = ll.lat;
    lon = ll.lng;
  }
}

const marker = L.marker([lat, lon], {

      interactive: false,
      icon: L.divIcon({
        className: "",
        html: `
          <div style="
            font-size:10px;
            font-weight:700;
            color:black;
            text-shadow:
              0 0 3px white,
              0 0 6px white,
              0 0 9px white;
            user-select:none;
            pointer-events:none;
          ">
            ${r.rank}
          </div>
        `,
        iconSize: [0,0],
        iconAnchor: [0,0],
      })
    });

    marker.addTo(mapRef);
    rankMarkers.set(r.sailor, marker);
  }

  ui.lblNow.textContent = `T+${fmtMMSS(tNow)}`;
}


  function init({ map, layersBySailor, tracksBySailorPoints }) {
    mapRef = map;
    layersRef = layersBySailor;

    const uiNow = getUI();
    if (!uiNow) return;

    stop();

    // Build ptsBySailor
    ptsBySailor.clear();
    for (const [sailor, pts] of Object.entries(tracksBySailorPoints || {})) {
      if (!Array.isArray(pts) || pts.length === 0) continue;
      ptsBySailor.set(sailor, pts);
    }

    // Compute minT/maxT from data (absolute seconds)
    minT = Infinity;
    maxT = -Infinity;

    for (const pts of ptsBySailor.values()) {
      if (!Array.isArray(pts) || pts.length === 0) continue;
      const t0 = getT(pts[0]);
      const tN = getT(pts[pts.length - 1]);
      if (Number.isFinite(t0)) minT = Math.min(minT, t0);
      if (Number.isFinite(tN)) maxT = Math.max(maxT, tN);
    }

    if (!Number.isFinite(minT) || !Number.isFinite(maxT) || maxT < minT) {
      minT = 0;
      maxT = 0;
    }

    uiNow.slider.min = String(minT);
    uiNow.slider.max = String(maxT);
    uiNow.slider.value = String(minT);
    uiNow.slider.step = "1";

    uiNow.idxBox.min = String(minT);
    uiNow.idxBox.max = String(maxT);
    uiNow.idxBox.value = String(minT);
    uiNow.idxBox.step = "1";

    uiNow.wrap.style.display = (maxT > minT) ? "block" : "none";

    setLabels();
    setTime(minT);
  }

  function reset() {
    stop();
    if (ui) ui.wrap.style.display = "none";

    ptsBySailor.clear();
    minT = 0;
    maxT = 0;
  }

  // Backwards-compat: if anything calls setIndex, treat it as time.
  function setIndex(i) {
    setTime(Number(i) || 0);
  }

  return { init, reset, setIndex };
})();

function clearTracks() {
  try { player.reset(); } catch (_) {}

  for (const [, layer] of layersBySailor) {
    try { map.removeLayer(layer); } catch (_) {}
  }
  layersBySailor.clear();

  // (Compatibility) We no longer draw start markers, but keep cleanup safe.
  for (const [, m] of markerBySailor) {
    try { map.removeLayer(m); } catch (_) {}
  }
  markerBySailor.clear();

  for (const [, arr] of timeMarksBySailor) {
    if (!Array.isArray(arr)) continue;
    for (const obj of arr) {
      try { map.removeLayer(obj); } catch (_) {}
    }
  }
  timeMarksBySailor.clear();

  if (geometryLayer) {
    try { geometryLayer.clearLayers(); } catch (_) {}
  }
}

export function refreshCourseGeometry(raceId) {
  try { drawCourseGeometry(map, raceId); } catch {}
}

// -------------------------------------------------
// Race metadata overlay helpers
// -------------------------------------------------
function ensureRaceMetadataControl() {
  if (!map || raceMetadataControl) return;

  raceMetadataControl = L.control({ position: "topleft" });

  raceMetadataControl.onAdd = function () {
    const div = L.DomUtil.create("div", "sa-race-metadata");
    div.style.background = "rgba(255,255,255,0.92)";
    div.style.padding = "8px 10px";
    div.style.fontSize = "12px";
    div.style.lineHeight = "1.35";
    div.style.borderRadius = "6px";
    div.style.boxShadow = "0 0 4px rgba(0,0,0,0.25)";
    div.style.maxWidth = "220px";
    div.style.whiteSpace = "normal";
    div.style.color = "#222";
    div.innerHTML = "Loading race info...";
    raceMetadataControlDiv = div;
    return div;
  };

  raceMetadataControl.addTo(map);
}

function setRaceMetadataHtml(html) {
  ensureRaceMetadataControl();
  if (!raceMetadataControlDiv) return;
  raceMetadataControlDiv.innerHTML = html;
}

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function csvSplitLine(line) {
  // Lightweight CSV splitter supporting quoted fields.
  const out = [];
  let cur = "";
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const ch = line[i];

    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') {
        cur += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (ch === "," && !inQuotes) {
      out.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  out.push(cur);
  return out;
}

function rowToObject(headers, cells) {
  const obj = {};
  for (let i = 0; i < headers.length; i++) {
    obj[headers[i]] = cells[i] ?? "";
  }
  return obj;
}

function normaliseMetaRow(r) {
  if (!r) return null;
  return {
    race_id: r.race_id ?? "",
    venue: r.venue ?? "",
    event: r.event ?? "",
    wind_dir_deg: r.wind_dir_deg ?? "",
    wind_knots: r.wind_knots ?? "",
    sea_state: r.sea_state ?? "",
    wind_type: r.wind_type ?? "",
  };
}

function renderRaceMetadata(meta) {
  if (!meta) {
    setRaceMetadataHtml("Race info unavailable");
    return;
  }

  const lines = [];

  if (meta.event) lines.push(`<b>${escapeHtml(meta.event)}</b>`);
  if (meta.venue) lines.push(`${escapeHtml(meta.venue)}`);

  const windParts = [];
  if (meta.wind_dir_deg !== "") windParts.push(`${escapeHtml(meta.wind_dir_deg)}°`);
  if (meta.wind_knots !== "") windParts.push(`${escapeHtml(meta.wind_knots)} kt`);
  if (windParts.length) lines.push(`Wind: ${windParts.join(" / ")}`);

  if (meta.sea_state) lines.push(`Sea: ${escapeHtml(meta.sea_state)}`);
  if (meta.wind_type) lines.push(`Type: ${escapeHtml(meta.wind_type)}`);

  if (lines.length === 0) {
    setRaceMetadataHtml("Race info unavailable");
    return;
  }

  setRaceMetadataHtml(lines.join("<br>"));
}

async function loadRaceMetadataViaApi(raceId) {
  try {
    const res = await fetch(`/api/race_metadata?race_id=${encodeURIComponent(raceId)}`, { cache: "no-store" });
    if (!res.ok) return null;
    const data = await res.json();
    if (!data || (typeof data === "object" && Object.keys(data).length === 0)) return null;
    return normaliseMetaRow(data);
  } catch (_) {
    return null;
  }
}

async function loadRaceMetadataViaCsv(raceId) {
  try {
    const res = await fetch("/data/race_metadata/race_metadata.csv", { cache: "no-store" });
    if (!res.ok) return null;

    const text = await res.text();
    const lines = text.split(/\r?\n/).filter(line => line.trim() !== "");
    if (lines.length < 2) return null;

    const headers = csvSplitLine(lines[0]);

    for (let i = 1; i < lines.length; i++) {
      const cells = csvSplitLine(lines[i]);
      const row = rowToObject(headers, cells);
      if (String(row.race_id || "").trim() === String(raceId).trim()) {
        return normaliseMetaRow(row);
      }
    }

    return null;
  } catch (_) {
    return null;
  }
}

async function loadAndRenderRaceMetadata(raceId) {
  ensureRaceMetadataControl();

  if (!raceId) {
    setRaceMetadataHtml("Race info unavailable");
    return;
  }

  setRaceMetadataHtml("Loading race info...");

  let meta = await loadRaceMetadataViaApi(raceId);
  if (!meta) {
    meta = await loadRaceMetadataViaCsv(raceId);
  }

  renderRaceMetadata(meta);
}

export function initViewer() {
  const ZOOM_STEP = 0.25;
  const WHEEL_PX_PER_ZOOM = 240;

  map = L.map("map", {
    zoomControl: false,
    zoomSnap: ZOOM_STEP,
    zoomDelta: ZOOM_STEP,
    wheelPxPerZoomLevel: WHEEL_PX_PER_ZOOM,
  });

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  const FineZoomControl = L.Control.Zoom.extend({
    _zoomIn: function (e) {
      L.DomEvent.stop(e);
      this._map.zoomIn(ZOOM_STEP);
    },
    _zoomOut: function (e) {
      L.DomEvent.stop(e);
      this._map.zoomOut(ZOOM_STEP);
    },
  });

  map.addControl(new FineZoomControl({ position: "topleft" }));

  geometryLayer = L.layerGroup().addTo(map);
  map.setView([0, 0], 2);

  ensureRaceMetadataControl();
}

// -------------------------------------------------
// Geometry API loader + renderer
// -------------------------------------------------
async function loadGeometry(raceId) {
  if (geometryCache[raceId]) return geometryCache[raceId];

  const res = await fetch(`/api/geometry?race_id=${raceId}`);
  if (!res.ok) return null;

  const data = await res.json();
  geometryCache[raceId] = data;
  return data;
}

/**
 * Choose a label location near the "to" mark that is:
 * - perpendicular to the rum line (screen space)
 * - on the side with greater clearance from nearby tracks (screen pixels)
 */
function chooseBearingLabelLatLng(fromLL, toLL, offsetPx) {
  const fromPt = map.latLngToLayerPoint(fromLL);
  const toPt = map.latLngToLayerPoint(toLL);

  const dx = toPt.x - fromPt.x;
  const dy = toPt.y - fromPt.y;
  const mag = Math.hypot(dx, dy) || 1;

  const ux = dx / mag;
  const uy = dy / mag;

  const px1 = -uy, py1 = ux;
  const px2 = uy, py2 = -ux;

  const cand1 = L.point(toPt.x + px1 * offsetPx, toPt.y + py1 * offsetPx);
  const cand2 = L.point(toPt.x + px2 * offsetPx, toPt.y + py2 * offsetPx);

  const nearby = [];
  const R = 140;
  const MAX_SAMPLE_PER_TRACK = 120;

  for (const [, latlngs] of trackLatLngsBySailor) {
    if (!Array.isArray(latlngs) || latlngs.length === 0) continue;
    const startIdx = Math.max(0, latlngs.length - MAX_SAMPLE_PER_TRACK);

    for (let i = startIdx; i < latlngs.length; i++) {
      const ll = latlngs[i];
      const p = map.latLngToLayerPoint(ll);
      const d = Math.hypot(p.x - toPt.x, p.y - toPt.y);
      if (d <= R) nearby.push(p);
    }
  }

  if (nearby.length === 0) return map.layerPointToLatLng(cand1);

  function score(candidatePt) {
    let minD = Infinity;
    for (const p of nearby) {
      const d = Math.hypot(p.x - candidatePt.x, p.y - candidatePt.y);
      if (d < minD) minD = d;
    }
    return minD;
  }

  const s1 = score(cand1);
  const s2 = score(cand2);
  return map.layerPointToLatLng(s2 > s1 ? cand2 : cand1);
}

function renderGeometry(geometry, selectedLeg) {
  if (!geometry || !geometryLayer) return;
  geometryLayer.clearLayers();

  geometry.marks.forEach(m => {
    L.circleMarker([m.lat, m.lon], {
      radius: 5,
      color: "red",
      weight: 2,
      fillColor: "red",
      fillOpacity: 0.9
    }).addTo(geometryLayer);
  });

  if (!selectedLeg || selectedLeg === "Total Race") return;

  const legId = Number(selectedLeg);
  const leg = geometry.legs.find(l => Number(l.leg_id) === legId);
  if (!leg) return;

  L.polyline([leg.from, leg.to], {
    color: "#777",
    weight: 2,
    opacity: 0.8,
    dashArray: "4,8"
  }).addTo(geometryLayer);

  const fromLL = L.latLng(leg.from[0], leg.from[1]);
  const toLL = L.latLng(leg.to[0], leg.to[1]);
  const labelLL = chooseBearingLabelLatLng(fromLL, toLL, 52);

  L.marker(labelLL, {
    interactive: false,
    icon: L.divIcon({
      className: "",
      html: `
        <div style="
          font-size:22px;
          font-weight:700;
          color:#444;
          background:transparent;
          padding:0;
          margin:0;
          border:none;
          white-space:nowrap;
          text-shadow: 0 0 3px rgba(255,255,255,0.95), 0 0 7px rgba(255,255,255,0.8);
          user-select:none;
          pointer-events:none;
        ">
          ${leg.bearing_deg}°
        </div>
      `,
      iconSize: [0, 0],
      iconAnchor: [0, 0],
    })
  }).addTo(geometryLayer);
}

export async function refreshViewer() {
  if (!map) return;

  const raceId = state.raceId;
  const sailors = Array.isArray(state.sailors) ? state.sailors : [];
  const leg = state.leg; // "Total Race" or "1"/"2"/...

  clearTracks();
  trackLatLngsBySailor = new Map();

  await loadAndRenderRaceMetadata(raceId);

  if (!raceId || sailors.length === 0) {
    map.setView([0, 0], 2);
    return;
  }

  let allLatLngs = [];
  const tracksBySailorPoints = {}; // sailor -> payload.points

  for (const sailor of sailors) {
    let url = `/api/races/${encodeURIComponent(raceId)}/track?sailor=${encodeURIComponent(sailor)}`;
    if (leg && leg !== "Total Race") {
      url += `&leg=${encodeURIComponent(String(leg))}`;
    }

    const payload = await apiGet(url);

    if (!payload || typeof payload.color !== "string") {
      throw new Error(`Track payload missing color for sailor=${sailor}`);
    }
    const color = payload.color;

    const pts = payload.points;
    if (!Array.isArray(pts) || pts.length === 0) continue;

    tracksBySailorPoints[sailor] = pts;

    const latlngs = [];
    for (const p of pts) {
      const lat = Number(p.lat);
      const lon = Number(p.lon);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
      latlngs.push([lat, lon]);
    }
    if (latlngs.length === 0) continue;

    trackLatLngsBySailor.set(sailor, latlngs);
    allLatLngs = allLatLngs.concat(latlngs);

    // Track line (THINNER): weight 2 (was 3)
    // Player will setLatLngs() as time advances.
    const line = L.polyline([], { color, weight: 2, opacity: 0.9 });
    line.addTo(map);
    layersBySailor.set(sailor, line);

    // Start marker removed intentionally (uncluttered growing tracks only)
  }

  if (allLatLngs.length > 0) {
    const bounds = L.latLngBounds(allLatLngs);
    map.fitBounds(bounds, { padding: [20, 20] });
  } else {
    map.setView([0, 0], 2);
  }

  // Init player AFTER layers exist
  try {
    player.init({
      map,
      layersBySailor,
      tracksBySailorPoints
    });
  } catch (e) {
    console.warn("player.init failed:", e);
  }

  // Draw geometry last
  const geometry = await loadGeometry(raceId);
  renderGeometry(geometry, leg);
}

// --- Compatibility export: table -> viewer cursor sync ---
let __sa_cursor_index = 0;

export function setCursorByIndex(i) {
  const n = Number(i);
  __sa_cursor_index = Number.isFinite(n) ? n : 0;
}

export function getCursorIndex() {
  return __sa_cursor_index;
}

// --- COURSE GEOMETRY OVERLAY (AUTO) ---
let _courseLayer = null;

function _deg2rad(d){ return d * Math.PI / 180; }
function _rad2deg(r){ return r * 180 / Math.PI; }

function _project(lat, lon, lat0){
  const R = 6371000.0;
  const x = _deg2rad(lon) * R * Math.cos(_deg2rad(lat0));
  const y = _deg2rad(lat) * R;
  return [x, y];
}
function _unproject(x, y, lat0){
  const R = 6371000.0;
  const lat = _rad2deg(y / R);
  const lon = _rad2deg(x / (R * Math.cos(_deg2rad(lat0))));
  return [lat, lon];
}

function _clearCourseLayer(map){
  if (_courseLayer) {
    try { _courseLayer.removeFrom(map); } catch {}
  }
  _courseLayer = L.layerGroup().addTo(map);
}

async function drawCourseGeometry(map, raceId){
  if (!map || !raceId) return;

  _clearCourseLayer(map);

  let geom = null;
  try {
    geom = await apiGet(`/api/geometry?race_id=${encodeURIComponent(raceId)}`);
  } catch (e) {
    return;
  }
  if (!geom || !geom.legs || !geom.marks) return;

  for (const m of geom.marks) {
    if (!m) continue;
    const lat = Number(m.lat), lon = Number(m.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
    L.circleMarker([lat, lon], {
      radius: 4,
      weight: 2,
      opacity: 1,
      fillOpacity: 1,
    }).addTo(_courseLayer);
  }

  for (const leg of geom.legs) {
    if (!leg || !leg.from || !leg.to) continue;
    const a = leg.from, b = leg.to;
    if (a.length !== 2 || b.length !== 2) continue;

    const from = [Number(a[0]), Number(a[1])];
    const to   = [Number(b[0]), Number(b[1])];
    if (!Number.isFinite(from[0]) || !Number.isFinite(from[1]) || !Number.isFinite(to[0]) || !Number.isFinite(to[1])) continue;

    L.polyline([from, to], { 
  color: "#a6c8ff",
  dashArray: "6,8", 
  weight: 2, 
  opacity: 0.9 
}).addTo(_courseLayer);

    try {
      const bdeg = Number(leg.bearing_deg);
      if (Number.isFinite(bdeg)) {
        const mid = [(from[0] + to[0]) / 2.0, (from[1] + to[1]) / 2.0];
        const icon = L.divIcon({
          className: "bearing-label",
          html: `<span class="bearing-text">${Math.round(bdeg)}°</span>`,
          iconSize: [0, 0],
        });
        L.marker(mid, { icon }).addTo(_courseLayer);
      }
    } catch (_) {}

    const fm = String(leg.from_mark || "").toLowerCase();
    const tm = String(leg.to_mark || "").toLowerCase();
    const isDown = fm.includes("wm") && tm.includes("gate");
    if (isDown) {
      const lat0 = (from[0] + to[0]) / 2.0;
      const [x1,y1] = _project(from[0], from[1], lat0);
      const [x2,y2] = _project(to[0], to[1], lat0);
      const dx = x2 - x1, dy = y2 - y1;
      const Lm = Math.hypot(dx, dy) || 1.0;

      const ext = Math.min(Lm * 0.35, 250.0);
      const ux = dx / Lm, uy = dy / Lm;

      const x3 = x2 + ux * ext;
      const y3 = y2 + uy * ext;
      const extPt = _unproject(x3, y3, lat0);

      L.polyline([to, extPt], { dashArray: "2,10", weight: 2, opacity: 0.8 }).addTo(_courseLayer);

      const m1 = _unproject(x2 + ux * ext * 0.33, y2 + uy * ext * 0.33, lat0);
      const m2 = _unproject(x2 + ux * ext * 0.66, y2 + uy * ext * 0.66, lat0);

      for (const pt of [m1, m2]) {
        L.circleMarker(pt, { radius: 3, weight: 2, opacity: 1, fillOpacity: 0.3 }).addTo(_courseLayer);
      }
    }
  }
}
// --- END COURSE GEOMETRY OVERLAY (AUTO) ---