// viewer_tracks.js
// Multi-track loader & red base layer + timed X markers (T+10 / T+20 / T+30)
// NEW: "Tracks to timer" (15-second steps) clipper for mark placement

(function () {
  const statusEl = document.getElementById("statusBar");

  const TRIMMED_DIR_URL = "../data/trimmed/";
  const TRACK_INDEX_URL = TRIMMED_DIR_URL + "trimmed_tracks_index.json";
  const RACETIMES_URL = "../data/racetimes/RaceTimes.csv";

  function setStatus(msg) {
    if (statusEl) statusEl.textContent = msg;
  }

  // -------------------------------
  // URL trimmed override
  // -------------------------------
  function getTrimmedFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const arr = params.getAll("trimmed");
    if (!arr || arr.length === 0) return [];

    const normalized = arr
      .map((s) => (s || "").trim())
      .filter(Boolean)
      .map((s) => {
        const clean = s.split("#")[0].split("?")[0];
        const parts = clean.split("/");
        return parts[parts.length - 1];
      })
      .filter((f) => f.endsWith("_trimmed.csv"));

    const seen = new Set();
    const out = [];
    for (const f of normalized) {
      if (!seen.has(f)) {
        seen.add(f);
        out.push(f);
      }
    }
    return out;
  }

  // -------------------------------
  // Track list selection (AUTHORITATIVE trimmed=)
  // -------------------------------
  async function fetchTrackList() {
    const params = new URLSearchParams(window.location.search);
    const hasTrimmedParam = params.has("trimmed");

    const fromUrl = getTrimmedFromUrl();

    // ✅ FIX #1: If trimmed= exists, it is authoritative.
    // Never silently fall back to trimmed_tracks_index.json.
    if (hasTrimmedParam) {
      if (!fromUrl.length) {
        const raw = params.getAll("trimmed");
        throw new Error(
          "URL contains trimmed= but none were accepted as *_trimmed.csv.\n" +
            "Raw trimmed params:\n" +
            raw.join("\n")
        );
      }
      return fromUrl;
    }

    // Only allowed when NO trimmed= is present
    const res = await fetch(TRACK_INDEX_URL);
    if (!res.ok) throw new Error("Cannot load trimmed_tracks_index.json");
    return res.json();
  }

  async function fetchText(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error("Cannot load " + url);
    return res.text();
  }

  // -------------------------------
  // RACE TIMES (robust CSV/TSV)
  // -------------------------------
  async function fetchRaceTimes() {
    const text = await fetchText(RACETIMES_URL);

    const lines = text.trim().split(/\r?\n/);
    if (lines.length < 2) return [];

    const delim = lines[0].includes("\t") ? "\t" : ",";
    const header = lines[0].split(delim).map((h) => h.trim());
    const idx = {};
    header.forEach((h, i) => (idx[h] = i));

    function get(r, key) {
      const i = idx[key];
      return i === undefined ? "" : (r[i] ?? "").trim();
    }

    return lines.slice(1).map((l) => {
      const r = l.split(delim);
      return {
        date: get(r, "date"),
        race_number: get(r, "race_number"),
        group_color: get(r, "group_color"),
        x_10_unix: Number(get(r, "x_10_unix")),
        x_20_unix: Number(get(r, "x_20_unix")),
        x_30_unix: Number(get(r, "x_30_unix")),
      };
    });
  }

  // -------------------------------
  // TRACK PARSING (UNIX TIME)
  // -------------------------------
  function parseCsvWithUnix(csvText) {
    const lines = csvText.trim().split(/\r?\n/);
    if (lines.length < 2) return [];

    const header = lines[0].split(",").map((h) => h.trim());
    const latIdx = header.indexOf("latitude_raw");
    const lonIdx = header.indexOf("longitude_raw");
    const unixIdx = header.indexOf("unix_s");

    if (latIdx === -1 || lonIdx === -1 || unixIdx === -1) return [];

    const pts = [];
    for (let i = 1; i < lines.length; i++) {
      const r = lines[i].split(",");
      const lat = parseFloat(r[latIdx]);
      const lon = parseFloat(r[lonIdx]);
      const unix = Number(r[unixIdx]);

      if (Number.isFinite(lat) && Number.isFinite(lon) && Number.isFinite(unix)) {
        pts.push({ lat, lon, unix });
      }
    }
    return pts;
  }

  function pointsToLineCoords(points) {
    const coords = [];
    for (const p of points) coords.push([p.lon, p.lat]);
    return coords;
  }

  function findPointAtUnix(points, targetUnix) {
    for (const p of points) {
      if (p.unix >= targetUnix) return p;
    }
    return null;
  }

  function computeBbox(allCoords) {
    let minX = Infinity,
      minY = Infinity,
      maxX = -Infinity,
      maxY = -Infinity;
    allCoords.forEach(([x, y]) => {
      minX = Math.min(minX, x);
      maxX = Math.max(maxX, x);
      minY = Math.min(minY, y);
      maxY = Math.max(maxY, y);
    });
    return [minX, minY, maxX, maxY];
  }

  // -------------------------------
  // X GEOMETRY (tiny, fine-line)
  // -------------------------------
  function xLinesAt(lon, lat, size_m) {
    const dLat = size_m / 111320.0;
    const cos = Math.cos((lat * Math.PI) / 180.0) || 1e-9;
    const dLon = size_m / (111320.0 * cos);

    const a = [
      [lon - dLon, lat - dLat],
      [lon + dLon, lat + dLat],
    ];
    const b = [
      [lon - dLon, lat + dLat],
      [lon + dLon, lat - dLat],
    ];

    return [a, b];
  }

  // -------------------------------
  // timer UI + helpers
  // -------------------------------
  function unixToHmsUTC(u) {
    const d = new Date(u * 1000);
    const hh = String(d.getUTCHours()).padStart(2, "0");
    const mm = String(d.getUTCMinutes()).padStart(2, "0");
    const ss = String(d.getUTCSeconds()).padStart(2, "0");
    return `${hh}:${mm}:${ss}`;
  }

  function secondsToMmSs(seconds) {
    const s = Math.max(0, Math.floor(seconds));
    const m = Math.floor(s / 60);
    const r = s % 60;
    return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
  }

  function makeTimerPanel() {
    let panel = document.getElementById("tracksTimerPanel");
    if (panel) return panel;

    panel = document.createElement("div");
    panel.id = "tracksTimerPanel";
    panel.style.position = "absolute";

    // bottom-left
    panel.style.top = "";
    panel.style.right = "";
    panel.style.left = "10px";
    panel.style.bottom = "10px";

    panel.style.zIndex = "9999";
    panel.style.background = "rgba(255,255,255,0.92)";
    panel.style.border = "1px solid #ccc";
    panel.style.borderRadius = "8px";
    panel.style.padding = "10px";
    panel.style.fontFamily = "system-ui, -apple-system, Segoe UI, Roboto, Arial";
    panel.style.fontSize = "12px";
    panel.style.minWidth = "240px";

    panel.innerHTML = `
      <div style="font-weight:600; margin-bottom:6px;">Tracks to timer</div>
      <div style="margin-bottom:6px;">
        <div>Start: <span id="timerStart">--:--:--</span></div>
        <div>Finish: <span id="timerFinish">--:--:--</span></div>
      </div>
      <div style="display:flex; align-items:center; gap:8px;">
        <input id="timerSeconds" type="range" min="0" max="3600" step="15" value="3600" style="flex:1;">
        <input id="timerSecondsNum" type="number" min="0" max="3600" step="15" value="3600" style="width:78px;">
      </div>
      <div style="margin-top:6px;">
        Showing: <span id="timerLabel">T+${secondsToMmSs(3600)}</span>
      </div>
    `;

    document.body.appendChild(panel);
    return panel;
  }

  function setTimerPanelTimes(gunUnix, finishUnix) {
    const a = document.getElementById("timerStart");
    const b = document.getElementById("timerFinish");
    if (a) a.textContent = gunUnix ? unixToHmsUTC(gunUnix) : "--:--:--";
    if (b) b.textContent = finishUnix ? unixToHmsUTC(finishUnix) : "--:--:--";
  }

  function setTimerLabel(seconds) {
    const el = document.getElementById("timerLabel");
    if (el) el.textContent = `T+${secondsToMmSs(seconds)}`;
  }

  // -------------------------------
  // MAIN
  // -------------------------------
  async function initTracks() {
    if (!window.map) return;

    // ✅ FIX #2: hard guard against double-init (this is what your server log showed)
    if (!window.viewerState) window.viewerState = {};
    if (window.viewerState.tracksInitStarted || window.viewerState.tracksLoaded) return;
    window.viewerState.tracksInitStarted = true;

    const map = window.map;

    try {
      setStatus("Loading trimmed tracks…");

      const filenames = await fetchTrackList();
      if (!filenames.length) return;

      const raceTimes = await fetchRaceTimes();

      // Track store for clipping: sourceId -> full points[]
      const trackStore = []; // [{ fname, sourceId, pts }]
      const sources = [];
      const allTrackCoords = [];
      const allXFeatures = [];

      // Determine race meta from first filename (all files are same race in your launcher)
      const firstMeta = filenames[0].match(/(\d{6})_R(\d+)_([a-zA-Z]+)_trimmed/);
      const metaDate = firstMeta ? firstMeta[1] : null;
      const metaRace = firstMeta ? firstMeta[2] : null;
      const metaGroup = firstMeta ? firstMeta[3] : null;

      // gun_unix derived from x_10/x_20/x_30 (written by your trim pipeline)
      let gunUnix = null;
      if (metaDate && metaRace && metaGroup) {
        const raceRow = raceTimes.find(
          (r) =>
            r.date === metaDate &&
            r.race_number === metaRace &&
            r.group_color === metaGroup
        );
        if (raceRow) {
          if (Number.isFinite(raceRow.x_10_unix)) gunUnix = raceRow.x_10_unix - 10;
          else if (Number.isFinite(raceRow.x_20_unix)) gunUnix = raceRow.x_20_unix - 20;
          else if (Number.isFinite(raceRow.x_30_unix)) gunUnix = raceRow.x_30_unix - 30;
        }
      }

      // finishUnix from max unix across loaded tracks
      let finishUnix = null;

      for (const fname of filenames) {
        const csvText = await fetchText(TRIMMED_DIR_URL + fname);

        const pts = parseCsvWithUnix(csvText);
        if (pts.length < 2) continue;

        const lastUnix = pts[pts.length - 1].unix;
        if (Number.isFinite(lastUnix)) {
          finishUnix = finishUnix == null ? lastUnix : Math.max(finishUnix, lastUnix);
        }

        // initial draw = full track (later clipped by timer)
        const coords = pointsToLineCoords(pts);
        if (coords.length < 2) continue;

        allTrackCoords.push(...coords);

        const sourceId = "track-" + fname.replace(/[^a-zA-Z0-9]/g, "_");

        map.addSource(sourceId, {
          type: "geojson",
          data: {
            type: "Feature",
            geometry: { type: "LineString", coordinates: coords },
          },
        });

        map.addLayer({
          id: sourceId + "-layer",
          type: "line",
          source: sourceId,
          paint: { "line-color": "#ff0000", "line-width": 2 },
        });

        sources.push(sourceId);
        trackStore.push({ fname, sourceId, pts });

        // ---- X MARKERS (UNIX-BASED) ----
        const meta = fname.match(/(\d{6})_R(\d+)_([a-zA-Z]+)_trimmed/);
        if (!meta) continue;

        const raceRow = raceTimes.find(
          (r) =>
            r.date === meta[1] &&
            r.race_number === meta[2] &&
            r.group_color === meta[3]
        );
        if (!raceRow) continue;

        const targets = [raceRow.x_10_unix, raceRow.x_20_unix, raceRow.x_30_unix].filter(
          Number.isFinite
        );
        if (!targets.length) continue;

        for (const t of targets) {
          const p = findPointAtUnix(pts, t);
          if (!p) continue;

          const segs = xLinesAt(p.lon, p.lat, 2.0);
          for (const lineCoords of segs) {
            allXFeatures.push({
              type: "Feature",
              geometry: { type: "LineString", coordinates: lineCoords },
              properties: { t: t, file: fname },
            });
          }
        }
      }

      // draw all Xs in one layer
      if (allXFeatures.length) {
        map.addSource("timed-x", {
          type: "geojson",
          data: {
            type: "FeatureCollection",
            features: allXFeatures,
          },
        });

        map.addLayer({
          id: "timed-x-layer",
          type: "line",
          source: "timed-x",
          paint: {
            "line-color": "#000000",
            "line-width": 1,
          },
        });
      }

      // Fit bounds
      if (allTrackCoords.length) {
        const bbox = computeBbox(allTrackCoords);
        map.fitBounds(
          [
            [bbox[0], bbox[1]],
            [bbox[2], bbox[3]],
          ],
          { padding: 40, duration: 0 }
        );
      }

      // Timer panel wiring
      makeTimerPanel();

      // If gunUnix missing, fallback to first sample unix
      if (gunUnix == null && trackStore.length) {
        gunUnix = trackStore[0].pts[0].unix;
      }
      if (finishUnix == null && trackStore.length) {
        finishUnix = trackStore[0].pts[trackStore[0].pts.length - 1].unix;
      }

      setTimerPanelTimes(gunUnix, finishUnix);

      // Slider max based on duration (SECONDS snapped to 15s)
      const durationSec =
        gunUnix != null && finishUnix != null
          ? Math.max(15, Math.ceil((finishUnix - gunUnix) / 15) * 15)
          : 3600;

      const slider = document.getElementById("timerSeconds");
      const num = document.getElementById("timerSecondsNum");
      if (slider) slider.max = String(durationSec);
      if (num) num.max = String(durationSec);

      // Default show full race
      const defaultSec = durationSec;
      if (slider) slider.value = String(defaultSec);
      if (num) num.value = String(defaultSec);
      setTimerLabel(defaultSec);

      function applyClip(seconds) {
        if (gunUnix == null) return;
        const cutoff = gunUnix + seconds;

        for (const t of trackStore) {
          const clipped = [];
          for (const p of t.pts) {
            if (p.unix <= cutoff) clipped.push(p);
            else break; // time-ordered
          }

          const coords = pointsToLineCoords(clipped);
          const safeCoords = coords.length >= 2 ? coords : coords;

          const src = map.getSource(t.sourceId);
          if (src && src.setData) {
            src.setData({
              type: "Feature",
              geometry: { type: "LineString", coordinates: safeCoords },
            });
          }
        }
      }

      function onChangeSeconds(valStr) {
        let s = Number(valStr);
        if (!Number.isFinite(s)) s = 0;

        // snap to 15-second steps
        s = Math.round(s / 15) * 15;
        s = Math.max(0, Math.min(durationSec, s));

        if (slider) slider.value = String(s);
        if (num) num.value = String(s);
        setTimerLabel(s);
        applyClip(s);
      }

      if (slider) slider.addEventListener("input", (e) => onChangeSeconds(e.target.value));
      if (num) num.addEventListener("change", (e) => onChangeSeconds(e.target.value));

      // Apply default clip
      applyClip(defaultSec);

      setStatus("Tracks + timed Xs loaded.");

      window.viewerState.tracks = sources;
      window.viewerState.tracksLoaded = true;
      window.dispatchEvent(new Event("viewer:tracksLoaded"));
    } catch (err) {
      console.error(err);
      const msg = err && err.message ? err.message : String(err);
      setStatus("Error loading tracks: " + msg);

      // allow retry if you reload page
      if (window.viewerState) {
        window.viewerState.tracksInitStarted = false;
      }
    }
  }

  window.addEventListener("viewer:mapReady", initTracks);
})();
