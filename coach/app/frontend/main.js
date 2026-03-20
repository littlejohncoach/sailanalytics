// coach/app/frontend/main.js

import { apiGet } from "./api_client.js";
import { state } from "./state.js";

// ------------------------------------------------------------
// Helpers
// ------------------------------------------------------------

function esc(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function showOverlay(title, detail) {
  try {
    const elId = "sa-debug-overlay";
    let el = document.getElementById(elId);

    if (!el) {
      el = document.createElement("div");
      el.id = elId;
      document.documentElement.appendChild(el);

      const style = document.createElement("style");
      style.textContent = `
#${elId}{
  position:fixed; inset:0; z-index:2147483647;
  background:rgba(10,10,10,.92);
  color:#f2f2f2;
  font:13px/1.4 ui-monospace,monospace;
  padding:16px;
  display:none;
  overflow:auto;
  white-space:pre-wrap;
}`;
      document.head.appendChild(style);
    }

    el.style.display = "block";
    el.textContent = `SailAnalytics UI Failure\n\n${title}\n\n${detail}`;
  } catch {}
}

function getFn(mod, names) {
  for (const name of names) {
    const fn = mod?.[name];
    if (typeof fn === "function") return fn;
  }
  return null;
}

// ------------------------------------------------------------
// Leg selection helper
// ------------------------------------------------------------

function getSelectedLeg() {
  const el =
    document.getElementById("legSelect") ||
    document.getElementById("leg_select") ||
    document.getElementById("leg") ||
    document.querySelector('select[name="leg"]');

  return String(el?.value || "").toLowerCase();
}

function setAnalyticsTitle() {
  const el =
    document.getElementById("analyticsTitle") ||
    document.querySelector("#tableSection > h3");

  if (!el) return;

  const leg = getSelectedLeg();

  if (!leg || leg.includes("total")) {
    el.textContent = "Analytics — Total Race";
  } else {
    el.textContent = `Analytics — Leg ${leg}`;
  }
}

// ------------------------------------------------------------
// Boot
// ------------------------------------------------------------

(async () => {
  try {
    // verify backend
    await apiGet("/api/races");

    const sidebar = await import("./ui_sidebar.js");
    const tables = await import("./ui_tables.js");
    const viewer = await import("./viewer_leaflet.js");

    // optional modules
    let refreshTotalRaceAnalytics = null;
    try {
      const total = await import("./total_race_analytics.js");
      refreshTotalRaceAnalytics = getFn(total, ["refreshTotalRaceAnalytics"]);
    } catch {}

    let refreshLegAnalytics = null;
    try {
      const legs = await import("./main_leg_analytics.js");
      refreshLegAnalytics = getFn(legs, ["refreshLegAnalytics"]);
      const initLegs = getFn(legs, ["initLegAnalyticsSubsystem"]);
      if (initLegs) initLegs();
    } catch {}

    const initViewer = getFn(viewer, ["initViewer"]);
    if (initViewer) initViewer();

    const initTables = getFn(tables, ["initTables", "initTable"]);
    if (initTables) initTables();

    const refreshViewer = getFn(viewer, ["refreshViewer"]);

    // ------------------------------------------------------------
    // CORE CONTROL: SINGLE ANALYTICS CONTEXT
    // ------------------------------------------------------------

    const onRefresh = async () => {
      setAnalyticsTitle();

      if (refreshViewer) await refreshViewer();
      try {
        if (viewer?.refreshCourseGeometry) {
          viewer.refreshCourseGeometry(state.raceId);
        }
      } catch {}

      const leg = getSelectedLeg();

      if (!leg || leg.includes("total")) {
        // TOTAL ONLY
        if (refreshTotalRaceAnalytics) {
          await refreshTotalRaceAnalytics();
        }
      } else {
        // LEG ONLY
        if (refreshLegAnalytics) {
          await refreshLegAnalytics();
        }
      }
    };

    // sidebar boot
    await sidebar.initSidebar(onRefresh);

  } catch (e) {
    showOverlay("Boot failure", String(e?.stack || e));
  }
})();