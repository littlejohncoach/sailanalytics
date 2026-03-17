import { apiGet } from "./api_client.js";
// coach/app/frontend/main.js
// ------------------------------------------------------------
// SailAnalytics Frontend Boot (with visible error overlay)
// Correct wiring:
//  - calls initSidebar(onRefresh)  ✅ (loads /api/races and populates Race dropdown)
//  - initializes viewer + tables if they expose init functions
//  - onRefresh triggers refreshViewer + refreshTables (+ total race analytics)
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
  font:13px/1.4 ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono","Courier New",monospace;
  padding:16px;
  display:none;
  overflow:auto;
  white-space:pre-wrap;
}
#${elId} .title{font-size:14px; font-weight:700; margin-bottom:8px;}
#${elId} button{
  appearance:none; border:1px solid rgba(255,255,255,.25);
  background:rgba(255,255,255,.08); color:#fff;
  padding:6px 10px; border-radius:8px; cursor:pointer; margin-right:8px;
}
#${elId} button:hover{background:rgba(255,255,255,.14);}
`;
      document.head.appendChild(style);
    }

    const text = `SailAnalytics UI Failure\n\n${title}\n\n${detail}\n\n---\nCopy this and paste it back into ChatGPT.`;
    el.style.display = "block";
    el.innerHTML = `
<div class="title">${esc("SailAnalytics UI Failure (visible debug)")}</div>
<div style="margin:10px 0 14px 0;">
  <button id="saDbgCopy">Copy</button>
  <button id="saDbgHide">Hide</button>
  <button id="saDbgReload">Reload</button>
</div>
<div id="saDbgText">${esc(text)}</div>
`;

    document.getElementById("saDbgHide").onclick = () => (el.style.display = "none");
    document.getElementById("saDbgReload").onclick = () => location.reload();
    document.getElementById("saDbgCopy").onclick = async () => {
      try {
        await navigator.clipboard.writeText(document.getElementById("saDbgText").textContent || "");
      } catch {}
    };
  } catch {}
}

window.addEventListener("error", (ev) => {
  const msg = ev?.message || "Unknown error";
  const src = ev?.filename ? `File: ${ev.filename}:${ev.lineno || "?"}:${ev.colno || "?"}` : "";
  const stack = ev?.error?.stack ? `\n\nStack:\n${ev.error.stack}` : "";
  showOverlay("Uncaught error", `${msg}\n${src}${stack}`.trim());
});

window.addEventListener("unhandledrejection", (ev) => {
  const r = ev?.reason;
  const msg = r?.message || String(r || "Unknown rejection");
  const stack = r?.stack ? `\n\nStack:\n${r.stack}` : "";
  showOverlay("Unhandled promise rejection", `${msg}${stack}`);
});

function getFn(mod, names) {
  for (const name of names) {
    const fn = mod?.[name];
    if (typeof fn === "function") return fn;
  }
  return null;
}

/**
 * Update the "Analytics" heading so it reflects the current leg selection.
 * Safe: if DOM elements are not found, it does nothing.
 *
 * Expected UI:
 *  - Leg select typically has id="legSelect" (but we try a few fallbacks).
 *  - Analytics heading is typically "#tableSection > h3".
 */
function setAnalyticsTitleFromLegSelect() {
  try {
    const legEl =
      document.getElementById("legSelect") ||
      document.getElementById("leg_select") ||
      document.getElementById("leg") ||
      document.querySelector('select[name="leg"]');

    const h =
      document.getElementById("analyticsTitle") ||
      document.querySelector("#tableSection > h3");

    if (!legEl || !h) return;

    const legValue = String(legEl.value || "").trim();
    if (!legValue) return;

    if (legValue.toLowerCase().includes("total")) {
      h.textContent = "Analytics — Total Race";
    } else {
      h.textContent = `Analytics — Leg ${legValue}`;
    }
  } catch {
    // no-op on purpose
  }
}

// Boot sequence
(async () => {
  try {
    // Verify backend is alive
    const races = await apiGet("/api/races");

    // Import modules
    const sidebar = await import("./ui_sidebar.js");
    const tables = await import("./ui_tables.js");
    const viewer = await import("./viewer_leaflet.js");
    try { if (viewer?.refreshCourseGeometry) viewer.refreshCourseGeometry(state.raceId); } catch {}

    // OPTIONAL: Total Race Analytics module (safe import)
    let refreshTotalRaceAnalytics = null;
    try {
      const totalRace = await import("./total_race_analytics.js");
      refreshTotalRaceAnalytics = getFn(totalRace, ["refreshTotalRaceAnalytics"]);
    } catch {
      // If the file doesn't exist yet, do nothing (keeps tracks stable).
    }

    // OPTIONAL: Leg Analytics subsystem (safe import)
    // This is your isolated pipeline: ui_sidebar_legs + ui_tables_legs + leg_analytics(fetch) + main_leg_analytics(orchestrator)
    try {
      const legs = await import("./main_leg_analytics.js");
      const initLegs = getFn(legs, ["initLegAnalyticsSubsystem"]);
      if (initLegs) initLegs();
    } catch {
      // If legs subsystem files don't exist yet, do nothing.
    }

    // Init viewer (Leaflet)
    const initViewer = getFn(viewer, ["initViewer"]);
    if (initViewer) initViewer();

    // Init tables (if present)
    const initTables = getFn(tables, ["initTables", "initTable"]);
    if (initTables) initTables();

    // Refresh hooks (called after race change / refresh button)
    const refreshViewer = getFn(viewer, ["refreshViewer"]);
    const refreshTables = getFn(tables, ["refreshTables", "refreshTable"]);

    const onRefresh = async () => {
      // Keep the Analytics header aligned with the leg selection
      setAnalyticsTitleFromLegSelect();

      if (refreshViewer) await refreshViewer();
      try { if (viewer?.refreshCourseGeometry) viewer.refreshCourseGeometry(state.raceId); } catch {}
      if (refreshTables) await refreshTables();
      if (refreshTotalRaceAnalytics) await refreshTotalRaceAnalytics();
    };

    // *** KEY FIX: run the sidebar loader ***
    if (typeof sidebar.initSidebar !== "function") {
      throw new Error("ui_sidebar.js does not export initSidebar(onRefresh).");
    }
    await sidebar.initSidebar(onRefresh);

    // Note: initSidebar() already loads races, selects first race, and triggers refresh.
  } catch (e) {
    showOverlay("Boot failure", String(e?.stack || e));
  }
})();
