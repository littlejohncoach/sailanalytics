// coach/app/frontend/main_leg_analytics.js
import { legsState } from "./state_legs.js";
import { initSidebarLegs } from "./ui_sidebar_legs.js";
import { fetchLegAnalytics } from "./leg_analytics.js";
import {
  clearLegAnalyticsTable,
  renderLegAnalyticsRows,
  setLegAnalyticsTitle,
} from "./ui_tables_legs.js";

/**
 * Legs subsystem init:
 * - sidebar legs wiring
 * - fetch + render pipeline
 * - never touches viewer pipeline, slice pipeline, or total race pipeline
 */
export function initLegAnalyticsSubsystem() {
  async function refreshLegs() {
    const raceId = legsState.raceId;
    const legId = legsState.legId;

    // Total Race (or unset) -> do not fetch leg analytics
    if (!raceId || !legId) {
      setLegAnalyticsTitle("");
      clearLegAnalyticsTable(""); // leave blank rather than showing stale values
      return;
    }

    setLegAnalyticsTitle(legId);
    clearLegAnalyticsTable("Loading…");

    let payload;
    try {
      payload = await fetchLegAnalytics(raceId, legId);
    } catch (e) {
      clearLegAnalyticsTable("Error loading leg analytics");
      return;
    }

    const rows = payload && Array.isArray(payload.rows) ? payload.rows : [];
    renderLegAnalyticsRows(rows);
  }

  initSidebarLegs(refreshLegs);
}
