// coach/app/frontend/main.js
// ------------------------------------------------------------
// SailAnalytics Frontend Boot
// ------------------------------------------------------------

function esc(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

/* ------------------------------------------------------------
DEBUG OVERLAY
------------------------------------------------------------ */

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
font:13px/1.4 ui-monospace;
padding:16px;
display:none;
overflow:auto;
white-space:pre-wrap;
}
`;
      document.head.appendChild(style);
    }

    el.style.display = "block";
    el.innerHTML = `<b>${esc(title)}</b>\n\n${esc(detail)}`;
  } catch {}
}

window.addEventListener("error", (ev) => {
  showOverlay("Uncaught error", ev.message);
});

window.addEventListener("unhandledrejection", (ev) => {
  showOverlay("Unhandled rejection", String(ev.reason));
});


/* ------------------------------------------------------------
METADATA SYSTEM
------------------------------------------------------------ */

let raceMetadata = null;

async function loadRaceMetadata(raceId) {

  try {

    const res = await fetch("/data/race_metadata/race_metadata.csv");
    const txt = await res.text();

    const rows = txt.trim().split("\n").map(r => r.split(","));
    const header = rows[0];

    for (let i = 1; i < rows.length; i++) {

      const r = rows[i];

      if (r[0] === raceId) {

        raceMetadata = {
          venue: r[4],
          event: r[5],
          wind_dir: r[6],
          wind_knots: r[7],
          sea_state: r[8],
          wind_type: r[9]
        };

        renderMetadata();
        return;
      }
    }

  } catch (e) {
    console.log("Metadata load failed", e);
  }
}

function renderMetadata() {

  if (!raceMetadata) return;

  const div = document.getElementById("raceMetadataBox");
  if (!div) return;

  div.innerHTML = `
<b>${raceMetadata.event}</b><br>
${raceMetadata.venue}<br>
Wind ${raceMetadata.wind_dir}° / ${raceMetadata.wind_knots} kt<br>
Sea: ${raceMetadata.sea_state}<br>
Type: ${raceMetadata.wind_type}
`;
}

function createMetadataBox() {

  const box = document.createElement("div");

  box.id = "raceMetadataBox";

  box.style.position = "absolute";
  box.style.top = "12px";
  box.style.left = "12px";
  box.style.background = "rgba(255,255,255,0.9)";
  box.style.padding = "8px 12px";
  box.style.fontSize = "12px";
  box.style.borderRadius = "6px";
  box.style.boxShadow = "0 0 6px rgba(0,0,0,0.3)";
  box.style.zIndex = "500";

  box.innerHTML = "Loading race data...";

  const map = document.getElementById("map");
  if (map) map.appendChild(box);
}


/* ------------------------------------------------------------
UTILITY
------------------------------------------------------------ */

function getFn(mod, names) {
  for (const name of names) {
    const fn = mod?.[name];
    if (typeof fn === "function") return fn;
  }
  return null;
}


/* ------------------------------------------------------------
ANALYTICS TITLE
------------------------------------------------------------ */

function setAnalyticsTitleFromLegSelect() {

  try {

    const legEl =
      document.getElementById("legSelect") ||
      document.querySelector('select[name="leg"]');

    const h =
      document.getElementById("analyticsTitle") ||
      document.querySelector("#tableSection > h3");

    if (!legEl || !h) return;

    const legValue = String(legEl.value || "").trim();

    if (legValue.toLowerCase().includes("total"))
      h.textContent = "Analytics — Total Race";
    else
      h.textContent = `Analytics — Leg ${legValue}`;

  } catch {}
}


/* ------------------------------------------------------------
BOOT SEQUENCE
------------------------------------------------------------ */

(async () => {

  try {

    const r = await fetch("/api/races", { cache: "no-store" });
    if (!r.ok) throw new Error(`/api/races HTTP ${r.status}`);

    await r.json();

    const sidebar = await import("./ui_sidebar.js");
    const tables = await import("./ui_tables.js");
    const viewer = await import("./viewer_leaflet.js");

    let refreshTotalRaceAnalytics = null;

    try {
      const totalRace = await import("./total_race_analytics.js");
      refreshTotalRaceAnalytics = getFn(totalRace, ["refreshTotalRaceAnalytics"]);
    } catch {}

    const initViewer = getFn(viewer, ["initViewer"]);
    if (initViewer) initViewer();

    const initTables = getFn(tables, ["initTables", "initTable"]);
    if (initTables) initTables();

    createMetadataBox();

    const refreshViewer = getFn(viewer, ["refreshViewer"]);
    const refreshTables = getFn(tables, ["refreshTables"]);

    const onRefresh = async () => {

      setAnalyticsTitleFromLegSelect();

      if (refreshViewer) await refreshViewer();
      if (refreshTables) await refreshTables();
      if (refreshTotalRaceAnalytics) await refreshTotalRaceAnalytics();

      /* load metadata after race changes */

      const state = await import("./state.js");

      const raceId =
        state?.state?.race_id ||
        state?.race_id ||
        null;

      if (raceId) loadRaceMetadata(raceId);
    };

    if (typeof sidebar.initSidebar !== "function") {
      throw new Error("ui_sidebar.js does not export initSidebar()");
    }

    await sidebar.initSidebar(onRefresh);

  } catch (e) {

    showOverlay("Boot failure", String(e?.stack || e));

  }

})();


/* ------------------------------------------------------------
FULLSCREEN BUTTON
------------------------------------------------------------ */

function saBindFullscreenToggle() {

  try {

    const btn = document.getElementById("btnFullscreen");
    const app = document.getElementById("app");

    if (!btn || !app) return;

    btn.addEventListener("click", async () => {

      try {

        if (document.fullscreenElement) {
          await document.exitFullscreen();
          return;
        }

        await app.requestFullscreen({ navigationUI: "hide" });

      } catch (e) {
        console.log("Fullscreen failed:", e);
      }

    });

  } catch {}

}

saBindFullscreenToggle();