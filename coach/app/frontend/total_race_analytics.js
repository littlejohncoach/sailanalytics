// coach/app/frontend/total_race_analytics.js

import { apiGet } from "./api_client.js";
import { state } from "./state.js";

function asNumber(x) {
  const n = Number(x);
  return Number.isFinite(n) ? n : NaN;
}

function cell(v) {
  if (v === null || v === undefined || v === "") return "—";
  return String(v);
}

export async function refreshTotalRaceAnalytics() {
  const tbody = document.querySelector("#dataTable tbody");
  const thead = document.querySelector("#dataTable thead");

  if (!tbody || !thead) return;

  // Clear table
  thead.innerHTML = `
    <tr>
      <th>Rank</th>
      <th>Sailor</th>
      <th>Length of course (m)</th>
      <th>Time sailed</th>
      <th>Distance sailed (m)</th>
      <th>Average boat speed (m/min)</th>
      <th>Average course speed (m/min)</th>
      <th>Efficiency (%)</th>
    </tr>
  `;
  tbody.innerHTML = "";

  const raceId = state.raceId;
  if (!raceId) return;

  let rows;
  try {
    rows = await apiGet(`/api/races/${encodeURIComponent(raceId)}/total_race_analytics`);
  } catch (e) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="8">Error loading analytics</td>`;
    tbody.appendChild(tr);
    return;
  }

  if (!Array.isArray(rows) || rows.length === 0) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="8">No analytics returned</td>`;
    tbody.appendChild(tr);
    return;
  }

  rows.forEach((r, idx) => {
    const rank = r.rank ?? (idx + 1);

    const courseLen = asNumber(r.length_of_course_m);
    const distSailed = asNumber(r.distance_sailed_m);
    const boatSpd = asNumber(r.avg_boat_speed_mpm);
    const courseSpd = asNumber(r.avg_course_speed_mpm);
    const eff = asNumber(r.efficiency_pct);

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${cell(rank)}</td>
      <td>${cell(r.sailor)}</td>
      <td>${Number.isFinite(courseLen) ? Math.round(courseLen) : "—"}</td>
      <td>${cell(r.time_sailed)}</td>
      <td>${Number.isFinite(distSailed) ? Math.round(distSailed) : "—"}</td>
      <td>${Number.isFinite(boatSpd) ? Math.round(boatSpd) : "—"}</td>
      <td>${Number.isFinite(courseSpd) ? Math.round(courseSpd) : "—"}</td>
      <td>${Number.isFinite(eff) ? eff.toFixed(1) : "—"}</td>
    `;
    tbody.appendChild(tr);
  });
}