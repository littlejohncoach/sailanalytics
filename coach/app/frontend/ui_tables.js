import { apiGet } from "./api_client.js";
import { state } from "./state.js";
import { setCursorByIndex } from "./viewer_leaflet.js";

export async function loadSliceAndRender() {
  const tbody = document.querySelector("#dataTable tbody");
  tbody.innerHTML = "";

  if (!state.raceId) return;

  const sailorsParam = state.sailors && state.sailors.length ? `&sailors=${encodeURIComponent(state.sailors.join(","))}` : "";
  const legParam = state.leg ? `&leg=${encodeURIComponent(state.leg)}` : "";

  const rows = await apiGet(`/api/races/${encodeURIComponent(state.raceId)}/slice?max_rows=5000${sailorsParam}${legParam}`);
  if (!rows.length) return;

  const tKey = (rows[0].t !== undefined) ? "t" : "t_idx";

  rows.forEach((r, idx) => {
    const tr = document.createElement("tr");
    tr.dataset.idx = String(idx);
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

  const wrap = document.getElementById("tableWrap");

  function updateCursorFromScroll() {
    const trs = Array.from(tbody.querySelectorAll("tr"));
    if (!trs.length) return;

    const wrapTop = wrap.getBoundingClientRect().top;
    let active = trs[0];

    for (const tr of trs) {
      const r = tr.getBoundingClientRect();
      if (r.top >= wrapTop + 5) { active = tr; break; }
    }

    trs.forEach(x => x.classList.remove("active"));
    active.classList.add("active");

    const i = parseInt(active.dataset.idx || "0", 10);
    state.cursorIndex = i;

    // Phase 1: align cursor to row index (later: by timestamp)
    setCursorByIndex(i);
  }

  wrap.addEventListener("scroll", updateCursorFromScroll, { passive: true });
  updateCursorFromScroll();
}
