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
      <table id="dataTable">
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
    await renderTotal();
  } else {
    await renderLeg();
  }
}

// ------------------------------------------------------------
// HEADERS
// ------------------------------------------------------------

function setHeaderAnalytics() {
  const thead = document.querySelector("#dataTable thead");
  if (!thead) return;

  thead.innerHTML = `
    <tr>
      <th>Rank</th>
      <th>Sailor</th>
      <th>Time sailed</th>
      <th>Distance sailed (m)</th>
      <th>Avg heart rate (bpm)</th>
      <th>Average boat speed (m/min)</th>
      <th>Average course speed (m/min)</th>
    </tr>
  `;
}

// ------------------------------------------------------------
// TOTAL RACE
// ------------------------------------------------------------

async function renderTotal() {
  const data = await apiGet(
    `/api/races/${encodeURIComponent(state.raceId)}/total_race_analytics`
  );

  const tbody = document.querySelector("#dataTable tbody");
  if (!tbody) return;

  setTitle("Total Race Analytics");
  setHeaderAnalytics();

  tbody.innerHTML = "";

  data.forEach((r, i) => {
    const tr = document.createElement("tr");

    tr.innerHTML = `
      <td>${r.rank ?? i + 1}</td>
      <td>${r.sailor ?? ""}</td>
      <td>${r.time_sailed ?? ""}</td>
      <td>${r.distance_sailed_m ?? ""}</td>
      <td>${r.avg_hr_bpm ?? ""}</td>
      <td>${r.avg_boat_speed_mpm ?? ""}</td>
      <td>${r.avg_course_speed_mpm ?? ""}</td>
    `;

    tbody.appendChild(tr);
  });
}

// ------------------------------------------------------------
// LEG
// ------------------------------------------------------------

async function renderLeg() {
  const res = await apiGet(
    `/api/leg_analytics?race_id=${encodeURIComponent(state.raceId)}&leg=${encodeURIComponent(state.leg)}`
  );

  const rows = res?.rows || [];

  const tbody = document.querySelector("#dataTable tbody");
  if (!tbody) return;

  const legLength = rows?.[0]?.length_leg_m ?? "";
  setTitle(`Analytics — Leg ${state.leg} (${legLength} m)`);

  setHeaderAnalytics();
  tbody.innerHTML = "";

  rows.forEach((r, i) => {
    const tr = document.createElement("tr");

    tr.innerHTML = `
      <td>${r.rank ?? i + 1}</td>
      <td>${r.sailor ?? ""}</td>
      <td>${r.time_sailed ?? ""}</td>
      <td>${r.distance_sailed_m ?? ""}</td>
      <td>${r.avg_hr_bpm ?? ""}</td>
      <td>${r.avg_boat_speed_mpm ?? ""}</td>
      <td>${r.avg_course_speed_mpm ?? ""}</td>
    `;

    tbody.appendChild(tr);
  });
}

// ------------------------------------------------------------
// TITLE
// ------------------------------------------------------------

function setTitle(txt) {
  const el = document.getElementById("analyticsTitle");
  if (el) el.textContent = txt;
}