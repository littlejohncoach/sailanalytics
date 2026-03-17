// coach/app/frontend/ui_tables_legs.js

function cell(v) {
  if (v === null || v === undefined || v === "") return "—";
  return String(v);
}

export function clearLegAnalyticsTable(message = "") {
  const tbody = document.querySelector("#dataTable tbody");
  if (!tbody) return;

  tbody.innerHTML = "";
  if (message) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="9">${cell(message)}</td>`;
    tbody.appendChild(tr);
  }
}

/**
 * Set the leg analytics title.
 *
 * @param {string} legId - "1".."6" or ""/null for Total Race
 * @param {number|null|undefined} bearingDeg - mark bearing (degrees), optional
 */
export function setLegAnalyticsTitle(legId, bearingDeg) {
  const h = document.querySelector("#tableSection > h3");
  if (!h) return;

  if (!legId) {
    h.textContent = "Analytics";
    return;
  }

  const b = Number.isFinite(Number(bearingDeg)) ? String(Math.round(Number(bearingDeg))) : "—";
  h.textContent = `Analytics — Leg ${legId} — Mark Bearing: ${b}`;
}

export function renderLegAnalyticsRows(rows) {
  const tbody = document.querySelector("#dataTable tbody");
  if (!tbody) return;

  tbody.innerHTML = "";

  if (!Array.isArray(rows) || rows.length === 0) {
    clearLegAnalyticsTable("No leg analytics returned");
    return;
  }

  rows.forEach((r) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${cell(r.rank)}</td>
      <td>${cell(r.sailor)}</td>
      <td>${cell(r.length_leg_m)}</td>
      <td>${cell(r.time_sailed)}</td>
      <td>${cell(r.distance_sailed_m)}</td>
      <td>${cell(r.avg_hr_bpm)}</td>
      <td>${cell(r.avg_boat_speed_mpm)}</td>
      <td>${cell(r.avg_course_speed_mpm)}</td>
      <td>${cell(r.efficiency_pct)}</td>
    `;
    tbody.appendChild(tr);
  });
}
