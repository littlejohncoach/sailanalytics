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
// REFRESH
// ------------------------------------------------------------

export async function refreshTables() {
  if (!state.raceId) return;

  const leg = state.leg;

  if (!leg || leg === "" || leg === "Total Race") {
    setTitle("Total Race Analytics");
    await renderTotal();
  } else {
    setTitle(`Analytics — Leg ${leg}`);
    await renderLeg();
  }
}

// ------------------------------------------------------------
// TOTAL (MATCHES YOUR GOOD TABLE STYLE)
// ------------------------------------------------------------

async function renderTotal() {
  const data = await apiGet(
    `/api/races/${encodeURIComponent(state.raceId)}/total_race_analytics`
  );

  const thead = document.querySelector("#analyticsTable thead");
  const tbody = document.querySelector("#analyticsTable tbody");

  if (!thead || !tbody) return;

  thead.innerHTML = `
    <tr>
      <th>Rank</th>
      <th>Sailor</th>
      <th>Length of course (m)</th>
      <th>Time sailed</th>
      <th>Distance sailed (m)</th>
      <th>Avg heart rate (bpm)</th>
      <th>Average boat speed (m/min)</th>
      <th>Average course speed (m/min)</th>
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
      <td class="left">${r.sailor}</td>
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
// LEG (IDENTICAL STRUCTURE + HR INCLUDED)
// ------------------------------------------------------------

async function renderLeg() {
  const res = await apiGet(
    `/api/leg_analytics?race_id=${encodeURIComponent(state.raceId)}&leg=${encodeURIComponent(state.leg)}`
  );

  const rows = res?.rows || [];

  const thead = document.querySelector("#analyticsTable thead");
  const tbody = document.querySelector("#analyticsTable tbody");

  if (!thead || !tbody) return;

  thead.innerHTML = `
    <tr>
      <th>Rank</th>
      <th>Sailor</th>
      <th>Length of leg (m)</th>
      <th>Time sailed</th>
      <th>Distance sailed (m)</th>
      <th>Avg heart rate (bpm)</th>
      <th>Average boat speed (m/min)</th>
      <th>Average course speed (m/min)</th>
    </tr>
  `;

  tbody.innerHTML = "";

  rows.forEach((r, i) => {
    const tr = document.createElement("tr");

    tr.innerHTML = `
      <td>${r.rank ?? i + 1}</td>
      <td class="left">${r.sailor}</td>
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