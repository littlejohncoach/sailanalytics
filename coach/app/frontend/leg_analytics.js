// coach/app/frontend/leg_analytics.js
// -----------------------------------------------------------------------------
// DISK LOCATION (repo):
//   /Users/marklittlejohn/Desktop/SailAnalytics/coach/app/frontend/leg_analytics.js
//
// BROWSER URL (served by FastAPI StaticFiles mount):
//   /static/leg_analytics.js
//
// NOTE:
//   "/static" is a URL prefix, not a disk folder you should create.
// -----------------------------------------------------------------------------

import { apiGet } from "./api_client.js";

/**
 * Backend endpoint (URL):
 *   GET /api/leg_analytics?race_id=...&leg=...
 *
 * Returns JSON payload:
 *   { race_id: string, leg: string, rows: Array<...> }
 *
 * This module does NOT touch global state.
 * It is a pure fetch wrapper.
 */
export async function fetchLegAnalytics(raceId, legId) {
  const rid = String(raceId || "").trim();
  const lid = String(legId || "").trim();

  if (!rid || !lid) {
    return { race_id: rid, leg: lid, rows: [] };
  }

  const url =
    `/api/leg_analytics` +
    `?race_id=${encodeURIComponent(rid)}` +
    `&leg=${encodeURIComponent(lid)}`;

  const payload = await apiGet(url);

  // Normalize shape defensively, but do not invent data.
  const rows = payload && Array.isArray(payload.rows) ? payload.rows : [];
  return {
    race_id: payload?.race_id ?? rid,
    leg: payload?.leg ?? lid,
    rows,
  };
}
