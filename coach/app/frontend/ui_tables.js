// coach/app/frontend/ui_tables.js

import { apiGet } from "./api_client.js";
import { state } from "./state.js";

// ------------------------------------------------------------
// INIT
// ------------------------------------------------------------

export function initTables() {
  const container = document.getElementById("tableSection");
  if (!container) return;

  container.innerHTML = `
    <h3 id="analyticsTitle">Analytics</h3>
    <div id="tableWrap">
      <table id="analyticsTable">
        <thead></thead>
        <tbody></tbody>
      </table>
    </div>
  `;
}

// ------------------------------------------------------------
// MAIN REFRESH
// ------------------------------------------------------------

export async function refreshTables() {
  if (!state.raceId) return;

  const leg = state.leg;

  if (!leg || leg === "" || leg === "Total Race") {
    setTitle("Total Race Analytics");
    await renderTotalRace();
  } else {
    setTitle(`Analytics — Leg ${leg}`);
    await renderLegAnalytics();
  }
}

// ------------------------------------------------------------
// TOTAL RACE
// ------------------------------------------------------------

async function renderTotalRace() {
  const data = await apiGet(
    `/api/races/${encodeURIComponent(state.raceId)}/total_race_analytics`
  );

  const thead = document.querySelector("#analyticsTable thead");
  const tbody = document.querySelector("#analyticsTable tbody");

  if (!thead || !tbody) return;

  thead.innerHTML = `
    <tr>
      <th>Rank</th>
      <th style="text-align:left">Sailor</th>
      <th>Length (m)</th>
      <th>Time</th>
      <th>Distance (m)</th>
      <th>HR (bpm)</th>
      <th>Boat (m/min)</th>
      <th>Course (m/min)</th>
    </tr>
  `;

  tbody.innerHTML = "";

  data.forEach((r, i) => {
    const tr = document.createElement("tr");

    const hr =
      r.avg_heart_rate_bpm ??
      r.avg_hr_bpm ??
      "—";

    tr.innerHTML = `
      <td>${r.rank ?? i + 1}</td>
      <td style="text-align:left">${r.sailor}</td>
      <td>${round(r.length_of_course_m)}</td>
      <td>${r.time_sailed}</td>
      <td>${round(r.distance_sailed_m)}</td>
      <td>${round(hr)}</td>
      <td>${round(r.avg_boat_speed_mpm)}</td>
      <td>${round(r.avg_course_speed_mpm)}</td>
    `;

    tbody.appendChild(tr);
  });
}

// ------------------------------------------------------------
// LEG ANALYTICS (CORRECT SOURCE)
// ------------------------------------------------------------

async function renderLegAnalytics() {
  const thead = document.querySelector("#analyticsTable thead");
  const tbody = document.querySelector("#analyticsTable tbody");

  if (!thead || !tbody) return;

  const data = await apiGet(
    `/api/leg_analytics?race_id=${encodeURIComponent(state.raceId)}&leg=${encodeURIComponent(state.leg)}`
  );

  const rows = data?.rows || [];

  if (!rows.length) {
    tbody.innerHTML = "<tr><td colspan='8'>No data</td></tr>";
    return;
  }

  thead.innerHTML = `
    <tr>
      <th>Rank</th>
      <th style="text-align:left">Sailor</th>
      <th>Length (m)</th>
      <th>Time</th>
      <th>Distance (m)</th>
      <th>HR (bpm)</th>
      <th>Boat (m/min)</th>
      <th>Course (m/min)</th>
    </tr>
  `;

  tbody.innerHTML = "";

  rows.forEach((r, i) => {
    const tr = document.createElement("tr");

    tr.innerHTML = `
      <td>${r.rank ?? i + 1}</td>
      <td style="text-align:left">${r.sailor}</td>
      <td>${round(r.length_of_leg_m)}</td>
      <td>${r.time_sailed}</td>
      <td>${round(r.distance_sailed_m)}</td>
      <td>${round(r.avg_heart_rate_bpm)}</td>
      <td>${round(r.avg_boat_speed_mpm)}</td>
      <td>${round(r.avg_course_speed_mpm)}</td>
    `;

    tbody.appendChild(tr);
  });
}

// ------------------------------------------------------------
// HELPERS
// ------------------------------------------------------------

function setTitle(txt) {
  const el = document.getElementById("analyticsTitle");
  if (el) el.textContent = txt;
}

function round(v) {
  const n = Number(v);
  return Number.isFinite(n) ? Math.round(n) : "—";
}