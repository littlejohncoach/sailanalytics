import { apiGet } from "./api_client.js";
import { state } from "./state.js";

/**
 * ui_sidebar.js
 * ------------------------------------------------------------
 * Robust behavior:
 * - Race dropdown populates from GET /api/races
 * - START BLANK (no auto-select)
 * - Sailors multi-select toggles on click (no Cmd/Ctrl required)
 * - Refresh button triggers reload
 * - If user ends up with zero selected sailors, treat as ALL (once sailors exist)
 * ------------------------------------------------------------
 */

// Canonical fixed roster colors (MUST match backend tracks.py)
const SAILOR_COLOR_HEX = {
  yalcin:   "#1F77B4",
  berkay:   "#FF7F0E",
  lourenco: "#2CA02C",
  joao:     "#D62728",
  william:  "#9467BD",
  edu:      "#17BECF",
};

function colorForSailor(name) {
  const k = String(name || "").trim().toLowerCase();
  return SAILOR_COLOR_HEX[k] || "#111111";
}

// Parse race_id like "200126_R1_yellow" -> sortable key (YYYYMMDD + raceNo + fleet)
// We sort newest date first, then race number desc, then fleet asc.
function sortKeyForRaceId(raceId) {
  const rid = String(raceId || "").trim();
  const m = rid.match(/^(\d{6})_R(\d+)_?(.*)$/i);
  if (!m) return { dateKey: 0, raceNo: 0, fleet: rid.toLowerCase() };

  const ddmmyy = m[1];
  const raceNo = parseInt(m[2], 10) || 0;
  const fleet = String(m[3] || "").toLowerCase();

  // ddmmyy -> yymmdd -> YYYYMMDD (assume 20yy)
  const dd = ddmmyy.slice(0, 2);
  const mm = ddmmyy.slice(2, 4);
  const yy = ddmmyy.slice(4, 6);
  const yyyymmdd = parseInt(`20${yy}${mm}${dd}`, 10) || 0;

  return { dateKey: yyyymmdd, raceNo, fleet };
}

function compareRacesNewestFirst(a, b) {
  const ida = a?.id ?? a?.race_id ?? a?.name ?? "";
  const idb = b?.id ?? b?.race_id ?? b?.name ?? "";

  const ka = sortKeyForRaceId(ida);
  const kb = sortKeyForRaceId(idb);

  // date desc
  if (ka.dateKey !== kb.dateKey) return kb.dateKey - ka.dateKey;
  // race number desc
  if (ka.raceNo !== kb.raceNo) return kb.raceNo - ka.raceNo;
  // fleet asc
  if (ka.fleet < kb.fleet) return -1;
  if (ka.fleet > kb.fleet) return 1;

  // final tie-breaker: label/name asc
  const la = String(a?.label ?? a?.name ?? ida).toLowerCase();
  const lb = String(b?.label ?? b?.name ?? idb).toLowerCase();
  if (la < lb) return -1;
  if (la > lb) return 1;
  return 0;
}

export async function initSidebar(onRefresh) {
  const raceSelect = document.getElementById("raceSelect");
  const sailorSelect = document.getElementById("sailorSelect");
  const legSelect = document.getElementById("legSelect");
  const refreshBtn = document.getElementById("refreshBtn");
  const status = document.getElementById("status");
  const meta = document.getElementById("meta");

  // If critical controls are missing, silently do nothing (avoid breaking dashboard)
  if (!raceSelect || !sailorSelect || !legSelect || !refreshBtn) return;

  function setStatus(msg) {
    if (status) status.textContent = msg || "";
  }

  function allSailors() {
    return Array.from(sailorSelect.options).map((o) => o.value);
  }

  function selectedSailors() {
    return Array.from(sailorSelect.selectedOptions).map((o) => o.value);
  }

  function selectedSailorsOrAll() {
    const sel = selectedSailors();
    return sel.length ? sel : allSailors();
  }

  function syncState() {
    state.raceId = raceSelect.value || "";
    state.sailors = selectedSailorsOrAll();

    // Keep existing contract (other modules may read state.leg)
    const v = String(legSelect.value || "").trim();
    state.leg = v || "Total Race";

    // New contract for leg_analytics.js:
    // - state.legId must be "1".."6" when a leg is selected
    // - state.legId must be "" when Total Race is selected (disables leg analytics fetch)
    if (v && v !== "Total Race") {
      state.legId = v; // "1".."6"
    } else {
      state.legId = "";
    }
  }

  function triggerRefresh() {
    syncState();
    if (typeof onRefresh === "function") onRefresh();
  }

  // ------------------------------------------------------------
  // Multi-select behaves like checkboxes (toggle on click)
  // ------------------------------------------------------------
  sailorSelect.addEventListener("mousedown", (e) => {
    const opt = e.target;
    if (!opt || opt.tagName !== "OPTION") return;

    e.preventDefault();
    opt.selected = !opt.selected;

    sailorSelect.dispatchEvent(new Event("change", { bubbles: true }));
  });

  sailorSelect.addEventListener("change", () => {
    syncState();
  });

  legSelect.addEventListener("change", () => {
    syncState();
  });

  // ------------------------------------------------------------
  // Helper: normalize apiGet return shapes
  // ------------------------------------------------------------
  function normalizeArray(x) {
    if (Array.isArray(x)) return x;
    if (x && Array.isArray(x.data)) return x.data;
    if (x && Array.isArray(x.items)) return x.items;
    if (x && Array.isArray(x.races)) return x.races;
    return null;
  }

  // ------------------------------------------------------------
  // Load races (sorted newest date first)
  // ------------------------------------------------------------
  async function loadRaces() {
    setStatus("Loading races…");
    raceSelect.innerHTML = "<option value=''>—</option>";

    const raw = await apiGet("/api/races");
    const racesRaw = normalizeArray(raw);
    if (!racesRaw) {
      // Don’t crash the whole UI; just show status.
      setStatus("Could not parse /api/races response.");
      return [];
    }

    // IMPORTANT: sort newest first (by race_id "DDMMYY_Rn_fleet")
    const races = [...racesRaw].sort(compareRacesNewestFirst);

    for (const r of races) {
      if (!r) continue;
      const id = r.id ?? r.race_id ?? r.name;
      if (!id) continue;

      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = r.label || r.name || String(id);
      raceSelect.appendChild(opt);
    }

    setStatus("Select a race.");
    return races;
  }

  // ------------------------------------------------------------
  // Load race info -> populate sailors + legs
  // ------------------------------------------------------------
  async function loadRaceInfo(groupId) {
    // Reset UI
    sailorSelect.innerHTML = "";
    legSelect.innerHTML = "<option value=''>—</option>";
    if (meta) meta.textContent = "";

    state.raceId = groupId || "";
    state.sailors = [];
    state.leg = "Total Race";
    state.legId = ""; // keep leg analytics disabled until a numeric leg is selected

    if (!groupId) {
      setStatus("Select a race.");
      return;
    }

    setStatus("Loading race info…");
    const info = await apiGet(`/api/races/${encodeURIComponent(groupId)}/info`);

    // Keep this if other modules rely on it, but DO NOT use it for colors anymore.
    state.colors = info && info.colors ? info.colors : {};

    if (meta && info) {
      const d = info.date ?? "";
      const rn = info.race_number ?? "";
      const f = info.fleet ?? "";
      meta.textContent = `Date: ${d} | Race: ${rn} | Fleet: ${f}`;
    }

    // Sailors: add all and select all by default (color names using canonical palette)
    const sailors = info && Array.isArray(info.sailors) ? info.sailors : [];
    for (const s of sailors) {
      const opt = document.createElement("option");
      opt.value = s;
      opt.textContent = s;
      opt.selected = true;

      // Canonical color (matches tracks.py)
      opt.style.color = colorForSailor(s);

      sailorSelect.appendChild(opt);
    }

    // Legs: Total Race + numeric legs
    const totalOpt = document.createElement("option");
    totalOpt.value = "Total Race";
    totalOpt.textContent = "Total Race";
    legSelect.appendChild(totalOpt);

    const legs = info && Array.isArray(info.legs) ? info.legs : [];
    for (const L of legs) {
      const opt = document.createElement("option");
      opt.value = String(L);
      opt.textContent = String(L);
      legSelect.appendChild(opt);
    }

    legSelect.value = "Total Race";

    syncState();
    setStatus("");
  }

  // ------------------------------------------------------------
  // Events
  // ------------------------------------------------------------
  raceSelect.addEventListener("change", async () => {
    await loadRaceInfo(raceSelect.value);
    triggerRefresh();
  });

  refreshBtn.addEventListener("click", () => {
    triggerRefresh();
  });

  // ------------------------------------------------------------
  // Initial load (START BLANK)
  // ------------------------------------------------------------
  await loadRaces();

  // leave blank/unselected until user chooses
  raceSelect.value = "";
  sailorSelect.innerHTML = "";
  legSelect.innerHTML = "<option value=''>—</option>";
  if (meta) meta.textContent = "";

  state.raceId = "";
  state.sailors = [];
  state.leg = "Total Race";
  state.legId = ""; // disable leg analytics fetch on blank start
  state.colors = {};

  setStatus("Select a race.");
}
