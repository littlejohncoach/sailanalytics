// viewer_course.js
// ---------------------------------------------------------
// Draws course geometry (legs + bearings + marks) on map.
// Geometry selection is driven externally (Workflow GUI).
// Track scoping is handled separately by viewer_tracks.js
// via URL ?trimmed=... parameters.
// ---------------------------------------------------------

(async function () {

  // ---------------------------------------------------------
  // Load geometry CSV
  // ---------------------------------------------------------
  async function loadGeometryCSV(path) {
    const response = await fetch(path);
    if (!response.ok) {
      throw new Error("Cannot load geometry CSV: " + path);
    }

    const text = await response.text();
    const rows = text.trim().split(/\r?\n/);
    if (rows.length < 2) return [];

    const headers = rows[0].split(",").map(h => h.trim());
    const idx = {};
    headers.forEach((h, i) => idx[h] = i);

    function get(r, key) {
      const i = idx[key];
      return i === undefined ? "" : r[i];
    }

    const legs = [];

    for (let i = 1; i < rows.length; i++) {
      const cols = rows[i].split(",");

      legs.push({
        from_mark: get(cols, "from_mark"),
        to_mark: get(cols, "to_mark"),
        from_lat: parseFloat(get(cols, "from_lat_deg")),
        from_lon: parseFloat(get(cols, "from_lon_deg")),
        to_lat: parseFloat(get(cols, "to_lat_deg")),
        to_lon: parseFloat(get(cols, "to_lon_deg")),
        bearing: parseInt(get(cols, "bearing_deg"), 10)
      });
    }

    return legs;
  }

  // ---------------------------------------------------------
  // Simple XY rotation
  // ---------------------------------------------------------
  function rotateXY(x, y, cx, cy, angleDeg) {
    const a = angleDeg * Math.PI / 180;
    const dx = x - cx;
    const dy = y - cy;

    const rx = dx * Math.cos(a) - dy * Math.sin(a);
    const ry = dx * Math.sin(a) + dy * Math.cos(a);

    return [cx + rx, cy + ry];
  }

  // ---------------------------------------------------------
  // MAIN: Draw course geometry
  // ---------------------------------------------------------
  async function drawCourse(geometryPath) {
    if (!geometryPath) return;
    if (!window.map) return;

    const legs = await loadGeometryCSV(geometryPath);
    if (!legs.length) return;

    // Rotate so Start→WM1 bearing becomes vertical
    const rotation = -legs[0].bearing;

    // Project marks to screen space
    const xy = {};

    for (const leg of legs) {
      if (!xy[leg.from_mark]) {
        const p = map.project([leg.from_lon, leg.from_lat]);
        xy[leg.from_mark] = [p.x, p.y];
      }
      if (!xy[leg.to_mark]) {
        const p = map.project([leg.to_lon, leg.to_lat]);
        xy[leg.to_mark] = [p.x, p.y];
      }
    }

    // Rotation origin = Start
    const start = xy["Start"];
    if (!start) return;

    const [cx, cy] = start;

    const rotated = {};
    for (const key in xy) {
      rotated[key] = rotateXY(xy[key][0], xy[key][1], cx, cy, rotation);
    }

    // Remove existing course layers
    if (map.getSource("course")) {
      if (map.getLayer("course-lines")) map.removeLayer("course-lines");
      if (map.getLayer("course-marks")) map.removeLayer("course-marks");
      map.removeSource("course");
    }

    // Build GeoJSON
    const features = [];

    // Legs
    for (const leg of legs) {
      const f = rotated[leg.from_mark];
      const t = rotated[leg.to_mark];

      features.push({
        type: "Feature",
        geometry: {
          type: "LineString",
          coordinates: [
            map.unproject(f).toArray(),
            map.unproject(t).toArray()
          ]
        },
        properties: { type: "leg" }
      });
    }

    // Marks
    for (const name in rotated) {
      const p = rotated[name];
      features.push({
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: map.unproject(p).toArray()
        },
        properties: {
          type: "mark",
          name: name
        }
      });
    }

    const courseGeoJSON = {
      type: "FeatureCollection",
      features: features
    };

    map.addSource("course", {
      type: "geojson",
      data: courseGeoJSON
    });

    map.addLayer({
      id: "course-lines",
      type: "line",
      source: "course",
      filter: ["==", "type", "leg"],
      paint: {
        "line-color": "#ffcc00",
        "line-width": 3
      }
    });

    map.addLayer({
      id: "course-marks",
      type: "circle",
      source: "course",
      filter: ["==", "type", "mark"],
      paint: {
        "circle-radius": 5,
        "circle-color": "#ff0000"
      }
    });
  }

  // ---------------------------------------------------------
  // Auto-run from URL
  // ---------------------------------------------------------
  window.addEventListener("load", () => {
    const params = new URLSearchParams(window.location.search);
    const geometry = params.get("geometry");
    if (geometry) {
      drawCourse(geometry);
    }
  });

})();
