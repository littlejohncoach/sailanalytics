// coach/app/frontend/ui_sidebar_legs.js
import { legsState } from "./state_legs.js";

/**
 * Legs sidebar module (isolated):
 * - reads DOM controls
 * - maintains legsState
 * - triggers onLegsRefresh() when refresh button is pressed or race/leg changes
 */
export function initSidebarLegs(onLegsRefresh) {
  const raceSelect = document.getElementById("raceSelect");
  const legSelect = document.getElementById("legSelect");
  const refreshBtn = document.getElementById("refreshBtn");

  // If controls missing, do nothing
  if (!raceSelect || !legSelect || !refreshBtn) return;

  function syncLegsState() {
    legsState.raceId = raceSelect.value || "";

    const rawLeg = String(legSelect.value || "").trim();
    if (!rawLeg) {
      legsState.legId = "";
      return;
    }

    if (rawLeg.toLowerCase().includes("total")) {
      legsState.legId = "";
      return;
    }

    // keep only numeric legs
    const n = parseInt(rawLeg, 10);
    legsState.legId = Number.isFinite(n) ? String(n) : "";
  }

  function triggerLegsRefresh() {
    syncLegsState();
    if (typeof onLegsRefresh === "function") onLegsRefresh();
  }

  // We refresh legs analytics when:
  // - race changes
  // - leg changes
  // - refresh button pressed
  raceSelect.addEventListener("change", triggerLegsRefresh);
  legSelect.addEventListener("change", triggerLegsRefresh);
  refreshBtn.addEventListener("click", triggerLegsRefresh);

  // initialize state once
  syncLegsState();
}
