// viewer_marks.js
// Fully aligned with PROJECT STATE 2 (updated mark sequence)
// Includes full sequence: StartS → StartP → 1 → 1S → 1P → 2 → 2S → 2P → 
// 3 → 3S → 3P → 4 → 4S → 4P → 5 → 5S → 5P → FinishS → FinishP

(function () {
    const statusEl = document.getElementById("statusBar");
    const labelEl = document.getElementById("currentMarkLabel");
    const confirmBtn = document.getElementById("confirmMarkBtn");
    const rejectBtn = document.getElementById("rejectMarkBtn");
    const skipBtn = document.getElementById("skipMarkBtn");

    let activeMarker = null;

    // -----------------------------------------------------------
    // FIXED SEQUENCE — ABSOLUTE, FROM UPDATED PROJECT STATE
    // -----------------------------------------------------------

    window.viewerState.markSequence = [
        "StartS", "StartP",
        "1", "1S", "1P",
        "2", "2S", "2P",
        "3", "3S", "3P",
        "4", "4S", "4P",
        "5", "5S", "5P",
        "FinishS", "FinishP"
    ];

    // Prepare storage for all marks
    window.viewerState.marks = {};
    window.viewerState.currentMarkIndex = 0;

    // -----------------------------------------------------------
    // UI HELPERS
    // -----------------------------------------------------------

    function setStatus(msg) {
        if (statusEl) statusEl.textContent = msg;
    }

    function setCurrentMarkLabel(name) {
        if (labelEl) labelEl.textContent = "Mark: " + (name || "—");
    }

    function getCurrentMarkName() {
        const seq = window.viewerState.markSequence;
        return seq[window.viewerState.currentMarkIndex] || null;
    }

    function advanceToNextMark() {
        window.viewerState.currentMarkIndex += 1;
        const next = getCurrentMarkName();
        if (!next) {
            finishSequence();
        } else {
            createActiveMarker(next);
        }
    }

    // -----------------------------------------------------------
    // DOT ELEMENTS
    // -----------------------------------------------------------

    function makeDot(color) {
        const el = document.createElement("div");
        el.style.width = "10px";
        el.style.height = "10px";
        el.style.borderRadius = "50%";
        el.style.backgroundColor = color;
        el.style.pointerEvents = "auto";
        return el;
    }

    function greenDot() { return makeDot("#00aa00"); }
    function redDot() { return makeDot("#ff0000"); }

    // -----------------------------------------------------------
    // CREATE ACTIVE GREEN MARKER
    // -----------------------------------------------------------

    function createActiveMarker(markName) {
        if (!window.map) return;

        if (activeMarker) {
            activeMarker.remove();
            activeMarker = null;
        }

        setCurrentMarkLabel(markName);
        setStatus("Place mark: " + markName + " (drag green dot, then Yes/No/Skip)");

        const map = window.map;
        const center = map.getCenter();
        const el = greenDot();

        activeMarker = new maplibregl.Marker({
            element: el,
            draggable: true,
            anchor: "center"
        })
            .setLngLat([center.lng, center.lat])
            .addTo(map);
    }

    // -----------------------------------------------------------
    // CONFIRM CURRENT MARK
    // -----------------------------------------------------------

    function confirmCurrentMark() {
        const markName = getCurrentMarkName();
        if (!markName || !activeMarker) return;

        const lngLat = activeMarker.getLngLat();

        window.viewerState.marks[markName] = {
            name: markName,
            lon: lngLat.lng,
            lat: lngLat.lat,
            skipped: false
        };

        activeMarker.remove();
        activeMarker = null;

        new maplibregl.Marker({
            element: redDot(),
            draggable: false,
            anchor: "center"
        })
            .setLngLat([lngLat.lng, lngLat.lat])
            .addTo(window.map);

        advanceToNextMark();
    }

    // -----------------------------------------------------------
    // REJECT — KEEP GREEN MARKER ACTIVE
    // -----------------------------------------------------------

    function rejectCurrentMark() {
        if (!activeMarker) return;
        setStatus("Reposition the green dot for " + getCurrentMarkName() + " and press Yes.");
    }

    // -----------------------------------------------------------
    // SKIP MARK
    // -----------------------------------------------------------

    function skipCurrentMark() {
        const markName = getCurrentMarkName();
        if (!markName) return;

        window.viewerState.marks[markName] = {
            name: markName,
            lon: null,
            lat: null,
            skipped: true
        };

        if (activeMarker) {
            activeMarker.remove();
            activeMarker = null;
        }

        advanceToNextMark();
    }

    // -----------------------------------------------------------
    // ADD LABELS AFTER ALL MARKS COMPLETE (ULTRA-TRANSPARENT)
    // -----------------------------------------------------------

    function renderAllLabels() {
        const map = window.map;
        if (!map) return;

        const marks = window.viewerState.marks;

        Object.keys(marks).forEach(name => {
            const m = marks[name];
            if (!m || m.skipped || m.lon === null || m.lat === null) return;

            const label = document.createElement("div");
            label.textContent = name;
            label.style.position = "absolute";
            label.style.transform = "translate(-50%, -120%)";
            label.style.padding = "2px 4px";
            label.style.fontSize = "12px";
            label.style.fontWeight = "600";

          // >>> NEW STYLE — PURE TEXT, NO BACKGROUND, MICRO-SHADOW <<<
label.style.color = "white";

// No background at all
label.style.background = "none";
label.style.backgroundColor = "transparent";

label.style.borderRadius = "3px";
label.style.pointerEvents = "none";
label.style.whiteSpace = "nowrap";

// Micro shadow for clarity on bright tiles
label.style.textShadow = "0 0 2px rgba(0,0,0,0.9)";


            new maplibregl.Marker({
                element: label,
                anchor: "top"
            })
                .setLngLat([m.lon, m.lat])
                .addTo(map);
        });
    }

    // -----------------------------------------------------------
    // FINISH SEQUENCE
    // -----------------------------------------------------------

    function finishSequence() {
        setCurrentMarkLabel(null);
        setStatus("All marks placed. Adding labels…");

        requestAnimationFrame(() => {
            renderAllLabels();
            setStatus("Marks complete. Ready to save.");
            window.dispatchEvent(new Event("viewer:marksComplete"));
        });
    }

    // -----------------------------------------------------------
    // INITIALISATION
    // -----------------------------------------------------------

    function initMarks() {
        if (!window.map || !window.viewerState) return;

        if (!window.viewerState.tracksLoaded) {
            window.addEventListener(
                "viewer:tracksLoaded",
                () => {
                    const first = getCurrentMarkName();
                    if (first) createActiveMarker(first);
                },
                { once: true }
            );
        } else {
            const first = getCurrentMarkName();
            if (first) createActiveMarker(first);
        }
    }

    // -----------------------------------------------------------
    // BUTTON EVENT BINDINGS
    // -----------------------------------------------------------

    if (confirmBtn) confirmBtn.addEventListener("click", confirmCurrentMark);
    if (rejectBtn) rejectBtn.addEventListener("click", rejectCurrentMark);
    if (skipBtn) skipBtn.addEventListener("click", skipCurrentMark);

    window.addEventListener("viewer:mapReady", initMarks);

})();
