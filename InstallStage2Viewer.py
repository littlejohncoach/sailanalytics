#!/usr/bin/env python3
# InstallStage2Viewer.py
# ------------------------------------------------------------
# Bootstraps the Stage-2 Course Viewer (HTML + JS)
# Safe: never overwrites existing files
# ------------------------------------------------------------

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
VIEWER_DIR = BASE_DIR / "viewer_course"

FILES = {

"index.html": """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>SailAnalytics — Course Validation</title>

<script src="https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.js"></script>
<link href="https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.css" rel="stylesheet"/>

<style>
body { margin:0; padding:0; }
#map { position:absolute; top:0; bottom:0; width:100%; }
#toolbar {
    position:absolute;
    top:10px;
    left:10px;
    background:white;
    padding:6px 10px;
    border-radius:6px;
    font-family:sans-serif;
    font-size:13px;
    z-index:10;
}
</style>
</head>

<body>

<div id="toolbar">
<label>
<input type="checkbox" id="toggleBearings" checked>
Show bearings
</label>
</div>

<div id="map"></div>

<script>
mapboxgl.accessToken = "pk.eyJ1IjoiZHVtbXkiLCJhIjoiY2xkdW1teSJ9.dummy";
</script>

<script src="viewer_course_geometry.js"></script>
<script src="viewer_course_tracks.js"></script>
<script src="viewer_course.js"></script>

</body>
</html>
""",

"viewer_course.js": """window.viewerState = {
    geometryLoaded: false,
    tracksLoaded: false
};

window.map = new mapboxgl.Map({
    container: "map",
    style: "mapbox://styles/mapbox/light-v11",
    center: [0, 0],
    zoom: 2
});

map.on("load", () => {
    window.dispatchEvent(new Event("viewer:mapReady"));
});

document.getElementById("toggleBearings").addEventListener("change", e => {
    const visible = e.target.checked ? "visible" : "none";
    map.setLayoutProperty("bearings-layer", "visibility", visible);
});
""",

"viewer_course_geometry.js": """async function loadGeometry() {
    const res = await fetch("../data/geometry/" + findGeometryFile());
    const text = await res.text();
    return parseGeometry(text);
}

function findGeometryFile() {
    return "geometry.csv";
}

function parseGeometry(csv) {
    const lines = csv.trim().split(/\\r?\\n/);
    const header = lines[0].split(",");

    return lines.slice(1).map(l => {
        const r = l.split(",");
        const o = {};
        header.forEach((h,i)=>o[h]=r[i]);
        return {
            from:[parseFloat(o.from_lon_deg),parseFloat(o.from_lat_deg)],
            to:[parseFloat(o.to_lon_deg),parseFloat(o.to_lat_deg)],
            bearing:parseFloat(o.bearing_deg)
        };
    });
}

function rotate(pt, ang, o) {
    const r = ang*Math.PI/180;
    const dx = pt[0]-o[0], dy = pt[1]-o[1];
    return [
        o[0]+dx*Math.cos(r)-dy*Math.sin(r),
        o[1]+dx*Math.sin(r)+dy*Math.cos(r)
    ];
}

window.addEventListener("viewer:mapReady", async () => {
    const legs = await loadGeometry();
    const start = legs[0].from;
    const rot = -legs[0].bearing;

    const lines = legs.map(l => ({
        type:"Feature",
        geometry:{
            type:"LineString",
            coordinates:[
                rotate(l.from,rot,start),
                rotate(l.to,rot,start)
            ]
        }
    }));

    map.addSource("geometry",{type:"geojson",data:{type:"FeatureCollection",features:lines}});
    map.addLayer({
        id:"geometry-layer",
        type:"line",
        source:"geometry",
        paint:{ "line-color":"#222","line-width":2 }
    });

    window.viewerState.geometryLoaded = true;
});
""",

"viewer_course_tracks.js": """async function loadTracks() {
    const files = await fetch("../data/trimmed/trimmed_tracks_index.json").then(r=>r.json());
    const feats = [];

    for (const f of files) {
        const txt = await fetch("../data/trimmed/"+f).then(r=>r.text());
        const l = txt.trim().split(/\\r?\\n/);
        const h = l[0].split(",");
        const lat=h.indexOf("latitude_raw"), lon=h.indexOf("longitude_raw");

        const c = l.slice(1).map(r=>{
            const p=r.split(",");
            return [parseFloat(p[lon]),parseFloat(p[lat])];
        }).filter(x=>isFinite(x[0])&&isFinite(x[1]));

        feats.push({type:"Feature",geometry:{type:"LineString",coordinates:c}});
    }

    map.addSource("tracks",{type:"geojson",data:{type:"FeatureCollection",features:feats}});
    map.addLayer({
        id:"tracks-layer",
        type:"line",
        source:"tracks",
        paint:{ "line-color":"#d00","line-width":1.5 }
    });
}

window.addEventListener("viewer:mapReady", loadTracks);
"""
}

# ------------------------------------------------------------

def main():
    VIEWER_DIR.mkdir(exist_ok=True)
    print(f"[OK] viewer_course directory ready")

    for name, content in FILES.items():
        path = VIEWER_DIR / name
        if path.exists():
            print(f"[SKIP] {name} already exists")
            continue
        path.write_text(content, encoding="utf-8")
        print(f"[CREATE] {name}")

    print("\\n[DONE] Stage-2 Course Viewer installed.")

if __name__ == "__main__":
    main()
