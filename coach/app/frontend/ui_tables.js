// coach/app/frontend/ui_tables.js

import { apiGet } from "./api_client.js";
import { state } from "./state.js";

// ------------------------------------------------------------
// INIT
// ------------------------------------------------------------

export function initTables() {
  const container = document.getElementById("tableSection");
  if (!container) return;

  // Ensure a single table exists
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
// REFRESH ENTRY POINT (CALLED FROM main.js)
// ------------------------------------------------------------

export async function refreshTables() {
  if (!state.raceId) return;

  const leg = String(state.leg || "").toLowerCase();

  if (!leg || leg.includes("total")) {
    await renderTotalRace();
  } else {
    await renderLegAnalytics();
  }
}

// ------------------------------------------------------------
// TOTAL RACE
// ------------------------------------------------------------

async function renderTotalRace() {
  const data = await apiGet(`/api/races/${encodeURIComponent(state.raceId)}/total_race_analytics`);

  const thead = document.querySelector("#analyticsTable thead");
  const tbody = document.querySelector("#analyticsTable tbody");

  if (!thead || !tbody) return;

  // Header
  thead.innerHTML = `
    <tr>
      <th>Rank</th>
      <th>Sailor</th>
      <th>Time</th>
      <th>Distance</th>
      <th>Boat Speed</th>
      <th>Course Speed</th>
      <th>Efficiency</th>
    </tr>
  `;

  // Body
  tbody.innerHTML = "";

  data.forEach(row => {
    const tr = document.createElement("tr");

    tr.innerHTML = `
      <td>${row.rank ?? ""}</td>
      <td>${row.sailor ?? ""}</td>
      <td>${row.time_sailed ?? ""}</td>
      <td>${row.distance_sailed_m ?? ""}</td>
      <td>${row.avg_boat_speed_mpm ?? ""}</td>
      <td>${row.avg_course_speed_mpm ?? ""}</td>
      <td>${row.efficiency_pct ?? ""}</td>
    `;

    tbody.appendChild(tr);
  });
}

// ------------------------------------------------------------
// LEG ANALYTICS (USES EXISTING SLICE DATA)
// ------------------------------------------------------------

async function renderLegAnalytics() {
  const tbody = document.querySelector("#analyticsTable tbody");
  const thead = document.querySelector("#analyticsTable thead");

  if (!thead || !tbody) return;

  const sailorsParam = state.sailors && state.sailors.length
    ? `&sailors=${encodeURIComponent(state.sailors.join(","))}`
    : "";

  const legParam = state.leg
    ? `&leg=${encodeURIComponent(state.leg)}`
    : "";

  const rows = await apiGet(
    `/api/races/${encodeURIComponent(state.raceId)}/slice?max_rows=5000${sailorsParam}${legParam}`
  );

  if (!rows || !rows.length) {
    tbody.innerHTML = "";
    return;
  }

  const tKey = (rows[0].t !== undefined) ? "t" : "t_idx";

  // Header
  thead.innerHTML = `
    <tr>
      <th>Time</th>
      <th>Sailor</th>
      <th>Leg</th>
      <th>PTM</th>
      <th>SOG</th>
      <th>HR</th>
      <th>ATB</th>
    </tr>
  `;

  // Body
  tbody.innerHTML = "";

  rows.forEach((r) => {
    const tr = document.createElement("tr");

    tr.innerHTML = `
      <td>${r[tKey] ?? ""}</td>
      <td>${r.sailor ?? ""}</td>
      <td>${r.leg ?? ""}</td>
      <td>${r.ptm ?? ""}</td>
      <td>${r.sog ?? ""}</td>
      <td>${r.hr ?? ""}</td>
      <td>${r.atb ?? ""}</td>
    `;

    tbody.appendChild(tr);
  });
}