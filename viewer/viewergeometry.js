// viewergeometry.js
// Geometry rendering layer (NO MAP CREATION, NO TRACK LOADING)

(function () {

  // --------------------------------------------------
  // HELPERS
  // --------------------------------------------------
  function getGeometryPathFromURL() {
    const params = new URLSearchParams(window.location.search);
    return params.get("geometry");
  }

  async function fetchText(path) {
    const res = await fetch(path);
    if (!res.ok) throw new Error("Failed to load " + path);
    return res.text();
  }

  // --------------------------------------------------
  // LOAD + PARSE GEOMETRY CSV
  // --------------------------------------------------
  function parseGeometryCSV(csv) {
    const lines = csv.trim().split(/\r?\n/);
    const header = lines[0].split(",");

    return lines.slice(1).map(line => {
      const cols = line.split(",");
      const row = {};
      header.forEach((h, i) => row[h] = cols[i]);

      return {
        from_mark: row.from_mark,
        to_mark: row.to_mark,
        from: [parseFloat(row.from_lon_deg), parseFloat(row.from_lat_deg)],
        to:   [parseFloat(row.to_lon_deg),   parseFloat(row.to_lat_deg)],
        bearing: parseInt(row.bearing_deg, 10)
      };
    });
  }

  // --------------------------------------------------
  // DRAW GEOMETRY
  // --------------------------------------------------
  function drawGeometry(legs) {
    // Remove if already exists (prevents duplicates if event fires twice)
    if (map.getSource("geometry")) {
      if (map.getLayer("geometry-layer")) map.removeLayer("geometry-layer");
      map.removeSource("geometry");
    }

    const features = legs.map(l => ({
      type: "Feature",
      geometry: {
        type: "LineString",
        coordinates: [l.from, l.to]
      },
      properties: { from: l.from_mark, to: l.to_mark }
    }));

    map.addSource("geometry", {
      type: "geojson",
      data: { type: "FeatureCollection", features }
    });

    map.addLayer({
      id: "geometry-layer",
      type: "line",
      source: "geometry",
      paint: {
        "line-color": "#888",
        "line-width": 2,
        "line-opacity": 0.7
      }
    });
  }

  // --------------------------------------------------
  // DRAW BUOYS (PHYSICAL MARKS)
  // --------------------------------------------------
  function drawBuoys(legs) {
    if (map.getSource("buoys")) {
      if (map.getLayer("buoy-circles")) map.removeLayer("buoy-circles");
      map.removeSource("buoys");
    }

    const seen = new Map();
    legs.forEach(l => {
      [
        { name: l.from_mark, coord: l.from },
        { name: l.to_mark,   coord: l.to }
      ].forEach(m => {
        if (!seen.has(m.name)) seen.set(m.name, m.coord);
      });
    });

    const features = Array.from(seen.entries()).map(([name, coord]) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: coord },
      properties: { name }
    }));

    map.addSource("buoys", {
      type: "geojson",
      data: { type: "FeatureCollection", features }
    });

    map.addLayer({
      id: "buoy-circles",
      type: "circle",
      source: "buoys",
      paint: {
        "circle-radius": 6,
        "circle-color": "#ffffff",
        "circle-stroke-width": 2,
        "circle-stroke-color": "#000000"
      }
    });
  }

  // --------------------------------------------------
  // MARK LABELS (NUMBERS / NAMES)
  // --------------------------------------------------
  function drawMarkLabels(legs) {
    // Note: markers are DOM elements; we won't remove old ones here.
    // If you ever see duplicates, we can store and clear them explicitly.

    const seen = new Set();
    legs.forEach(l => {
      [
        { name: l.from_mark, coord: l.from },
        { name: l.to_mark,   coord: l.to }
      ].forEach(m => {
        if (seen.has(m.name)) return;
        seen.add(m.name);

        const el = document.createElement("div");
        el.textContent = m.name;
        el.style.color = "white";
        el.style.fontSize = "12px";
        el.style.fontWeight = "600";
        el.style.textShadow = "0 0 3px rgba(0,0,0,0.9)";
        el.style.whiteSpace = "nowrap";

        new maplibregl.Marker({ element: el, anchor: "top" })
          .setLngLat(m.coord)
          .addTo(map);
      });
    });
  }

  // --------------------------------------------------
  // BEARING LABEL (AT MARK "1")
  // --------------------------------------------------
  function drawFirstLegBearing(legs) {
    let mark1 = null;
    let bearing = null;

    for (const l of legs) {
      if (l.from_mark === "1") { mark1 = l.from; bearing = l.bearing; break; }
      if (l.to_mark === "1")   { mark1 = l.to;   bearing = l.bearing; break; }
    }
    if (!mark1 || bearing === null) return;

    const el = document.createElement("div");
    el.innerHTML = `1<br>${bearing}°`;
    el.style.color = "white";
    el.style.fontSize = "16px";
    el.style.fontWeight = "600";
    el.style.textAlign = "center";
    el.style.lineHeight = "1.2";
    el.style.textShadow = "0 0 4px rgba(0,0,0,0.9)";
    el.style.whiteSpace = "nowrap";

    new maplibregl.Marker({ element: el, anchor: "bottom" })
      .setLngLat(mark1)
      .addTo(map);
  }

  // --------------------------------------------------
  // MAIN ENTRY
  // --------------------------------------------------
  window.addEventListener("viewer:mapReady", async () => {
    const geometryPath = getGeometryPathFromURL();
    if (!geometryPath) return;

    const csv = await fetchText(geometryPath);
    const legs = parseGeometryCSV(csv);

    drawGeometry(legs);
    drawBuoys(legs);
    drawMarkLabels(legs);
    drawFirstLegBearing(legs);

    window.viewerState.geometryLoaded = true;
  });

})();
