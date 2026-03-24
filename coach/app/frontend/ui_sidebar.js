import { apiGet } from "./api_client.js";
import { state } from "./state.js";

/* =========================================================
   COLORS
========================================================= */

const SAILOR_COLOR_HEX = {
  yalcin: "#1F77B4",
  berkay: "#FF7F0E",
  lourenco: "#2CA02C",
  joao: "#D62728",
  william: "#9467BD",
  edu: "#17BECF",
};

function colorForSailor(name) {
  const k = String(name || "").trim().toLowerCase();
  return SAILOR_COLOR_HEX[k] || "#111111";
}

/* =========================================================
   SORTING
========================================================= */

function sortKeyForRaceId(raceId) {
  const rid = String(raceId || "").trim();
  const m = rid.match(/^(\d{6})_R(\d+)_?(.*)$/i);

  if (!m) return { dateKey: 0, raceNo: 0, fleet: rid };

  const dd = m[1].slice(0, 2);
  const mm = m[1].slice(2, 4);
  const yy = m[1].slice(4, 6);

  const dateKey = parseInt(`20${yy}${mm}${dd}`, 10);
  const raceNo = parseInt(m[2], 10);
  const fleet = m[3] || "";

  return { dateKey, raceNo, fleet };
}

function compareRacesNewestFirst(a, b) {
  const ida = a?.id ?? a?.race_id ?? a?.name ?? "";
  const idb = b?.id ?? b?.race_id ?? b?.name ?? "";

  const ka = sortKeyForRaceId(ida);
  const kb = sortKeyForRaceId(idb);

  if (ka.dateKey !== kb.dateKey) return kb.dateKey - ka.dateKey;
  if (ka.raceNo !== kb.raceNo) return kb.raceNo - ka.raceNo;
  if (ka.fleet < kb.fleet) return -1;
  if (ka.fleet > kb.fleet) return 1;

  return 0;
}

/* =========================================================
   INIT
========================================================= */

export async function initSidebar(onRefresh) {

  const raceSelect = document.getElementById("raceSelect");
  const sailorSelect = document.getElementById("sailorSelect");
  const legSelect = document.getElementById("legSelect");
  const refreshBtn = document.getElementById("refreshBtn");
  const meta = document.getElementById("meta");

  function allSailors() {
    return Array.from(sailorSelect.options).map(o => o.value);
  }

  function selectedSailors() {
    return Array.from(sailorSelect.selectedOptions).map(o => o.value);
  }

  function selectedSailorsOrAll() {
    const sel = selectedSailors();
    return sel.length ? sel : allSailors();
  }

  function syncState() {
    state.raceId = raceSelect.value || "";
    state.sailors = selectedSailorsOrAll();

    const v = String(legSelect.value || "").trim();
    state.leg = v || "Total Race";
    state.legId = (v && v !== "Total Race") ? v : "";
  }

  function triggerRefresh() {
    syncState();
    if (typeof onRefresh === "function") onRefresh();
  }

  /* =========================================================
     MULTI SELECT
  ========================================================= */

  sailorSelect.addEventListener("mousedown", (e) => {
    const opt = e.target;
    if (!opt || opt.tagName !== "OPTION") return;

    e.preventDefault();
    opt.selected = !opt.selected;

    sailorSelect.dispatchEvent(
      new Event("change", { bubbles: true })
    );
  });

  sailorSelect.addEventListener("change", syncState);
  legSelect.addEventListener("change", syncState);

  /* =========================================================
     HELPERS
  ========================================================= */

  function normalizeArray(x) {
    if (Array.isArray(x)) return x;
    if (x?.data) return x.data;
    if (x?.items) return x.items;
    if (x?.races) return x.races;
    return [];
  }

  /* =========================================================
     LOAD RACES
  ========================================================= */

  async function loadRaces() {

    raceSelect.innerHTML = "";

    const raw = await apiGet("/api/races");
    const races = normalizeArray(raw).sort(compareRacesNewestFirst);

    if (!races.length) return;

    const firstId = races[0].id ?? races[0].race_id ?? races[0].name;
    const latestDate = String(firstId).slice(0,6);

    const latest = [];
    const older = [];

    for (const r of races) {
      const id = r.id ?? r.race_id ?? r.name;

      if (String(id).startsWith(latestDate))
        latest.push(r);
      else
        older.push(r);
    }

    // latest only
    for (const r of latest) {
      const id = r.id ?? r.race_id ?? r.name;

      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = r.label || r.name || id;

      raceSelect.appendChild(opt);
    }

    // show more
    if (older.length) {

      const divider = document.createElement("option");
      divider.disabled = true;
      divider.textContent = "────────────";
      raceSelect.appendChild(divider);

      const more = document.createElement("option");
      more.value = "__more__";
      more.textContent = "▼ Show previous races";
      raceSelect.appendChild(more);
    }
  }

  async function expandAllRaces() {

    const raw = await apiGet("/api/races");
    const races = normalizeArray(raw).sort(compareRacesNewestFirst);

    raceSelect.innerHTML = "";

    for (const r of races) {
      const id = r.id ?? r.race_id ?? r.name;

      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = r.label || r.name || id;

      raceSelect.appendChild(opt);
    }
  }

  /* =========================================================
     LOAD RACE INFO
  ========================================================= */

  async function loadRaceInfo(groupId) {

    sailorSelect.innerHTML = "";
    legSelect.innerHTML = "";

    const info =
      await apiGet(`/api/races/${groupId}/info`);

    if (meta && info) {
      meta.textContent =
        `Date: ${info.date} | Race: ${info.race_number} | Fleet: ${info.fleet}`;
    }

    const sailors = info?.sailors || [];

    for (const s of sailors) {

      const opt = document.createElement("option");
      opt.value = s;
      opt.textContent = s;
      opt.selected = true;
      opt.style.color = colorForSailor(s);

      sailorSelect.appendChild(opt);
    }

    const totalOpt = document.createElement("option");
    totalOpt.value = "Total Race";
    totalOpt.textContent = "Total Race";
    legSelect.appendChild(totalOpt);

    for (const L of info?.legs || []) {
      const opt = document.createElement("option");
      opt.value = String(L);
      opt.textContent = String(L);
      legSelect.appendChild(opt);
    }

    legSelect.value = "Total Race";
  }

  /* =========================================================
     EVENTS
  ========================================================= */

  raceSelect.addEventListener("change", async () => {

    if (raceSelect.value === "__more__") {
      await expandAllRaces();
      return;
    }

    await loadRaceInfo(raceSelect.value);
    triggerRefresh();
  });

  refreshBtn.addEventListener("click", triggerRefresh);

  /* =========================================================
     INIT
  ========================================================= */

  await loadRaces();

  if (raceSelect.options.length > 0) {

    raceSelect.selectedIndex = 0;

    const first = raceSelect.options[0].value;

    await loadRaceInfo(first);

    syncState();

    if (typeof onRefresh === "function") {
      onRefresh();
    }
  }
}