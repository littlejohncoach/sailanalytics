// coach/app/frontend/ui_tables.js

import { apiGet } from "./api_client.js";
import { state } from "./state.js";

// ------------------------------------------------------------
// INIT (single box only)
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
// REFRESH ENTRY POINT
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
// TOTAL RACE (WITH HR, NO EFFICIENCY)
// ------------------------------------------------------------

async function renderTotalRace() {
  const data = await apiGet(
    `/api/races/${encodeURIComponent(state.raceId)}/total_race_analytics`
  );

  const thead = document.querySelector("#analyticsTable thead");
  const tbody = document.querySelector("#analyticsTable tbody");

  if (!thead || !tbody) return;

  // HEADER (clean + aligned)
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

  data.forEach((row, idx) => {
    const tr = document.createElement("tr");

    const hr =
      row.avg_heart_rate_bpm ??
      row.avg_hr_bpm ??
      "—";

    tr.innerHTML = `
      <td>${row.rank ?? idx + 1}</td>
      <td style="text-align:left">${row.sailor ?? ""}</td>
      <td>${round(row.length_of_course_m)}</td>
      <td>${row.time_sailed ?? ""}</td>
      <td>${round(row.distance_sailed_m)}</td>
      <td>${round(hr)}</td>
      <td>${round(row.avg_boat_speed_mpm)}</td>
      <td>${round(row.avg_course_speed_mpm)}</td>
    `;

    tbody.appendChild(tr);
  });
}

// ------------------------------------------------------------
// LEG ANALYTICS (WITH HR, NO EFFICIENCY)
// ------------------------------------------------------------

async function renderLegAnalytics() {
  const thead = document.querySelector("#analyticsTable thead");
  const tbody = document.querySelector("#analyticsTable tbody");

  if (!thead || !tbody) return;

  const sailorsParam = state.sailors?.length
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

  // HEADER
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

  const tKey = rows[0].t !== undefined ? "t" : "t_idx";

  tbody.innerHTML = "";

  rows.forEach((r) => {
    const tr = document.createElement("tr");

    tr.innerHTML = `
      <td>${r[tKey] ?? ""}</td>
      <td style="text-align:left">${r.sailor ?? ""}</td>
      <td>${r.leg ?? ""}</td>
      <td>${r.ptm ?? ""}</td>
      <td>${r.sog ?? ""}</td>
      <td>${r.hr ?? ""}</td>
      <td>${r.atb ?? ""}</td>
    `;

    tbody.appendChild(tr);
  });
}

// ------------------------------------------------------------
// HELPERS
// ------------------------------------------------------------

function round(v) {
  const n = Number(v);
  return Number.isFinite(n) ? Math.round(n) : "—";
}