// viewer_base.js
// Base environment: MapLibre + global viewer state

(function () {
    const statusEl = document.getElementById("statusBar");

    window.viewerState = {
        tracks: [],
        marks: {},
        markSequence: [
            "StartS", "StartP",
            "1", "1S", "1P",
            "2", "2S", "2P",
            "3", "3S", "3P",
            "FinishS", "FinishP"
        ],
        currentMarkIndex: 0,
        raceId: null,
        tracksLoaded: false
    };

    (function initRaceIdFromURL() {
        const params = new URLSearchParams(window.location.search);
        const date  = params.get("date") || "000000";
        const race  = params.get("race_number") || "0";
        const group = params.get("group_color") || "unknown";
        window.viewerState.raceId = `${date}_R${race}_${group}`;
    })();

    function setStatus(msg) {
        if (statusEl) statusEl.textContent = msg;
    }

    document.addEventListener("DOMContentLoaded", () => {

        const map = new maplibregl.Map({
            container: "map",
            style: {
                version: 8,
                sources: {
                    "osm-tiles": {
                        type: "raster",
                        tiles: [
                            "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
                            "https://b.tile.openstreetmap.org/{z}/{x}/{y}.png",
                            "https://c.tile.openstreetmap.org/{z}/{x}/{y}.png"
                        ],
                        tileSize: 256,
                        attribution: "© OpenStreetMap contributors"
                    }
                },
                layers: [
                    {
                        id: "osm-tiles",
                        type: "raster",
                        source: "osm-tiles"
                    }
                ]
            },
            center: [0, 0],
            zoom: 2
        });

        window.map = map;
        setStatus("Map loaded. Waiting for tracks…");

        map.on("load", () => {

            // ✅ ADD ROTATOR HERE (guaranteed to work)
            map.addControl(
                new maplibregl.NavigationControl({
                    showZoom: true,
                    showCompass: true
                }),
                "top-right"
            );

            setStatus("Map ready. Loading tracks…");
            window.dispatchEvent(new Event("viewer:mapReady"));
        });
    });
})();
