// viewer_save.js
// Creates marks_<date>_R<race>_<group>.csv and downloads it (CSV only)

(function () {
    const statusEl = document.getElementById("statusBar");

    function setStatus(msg) {
        if (statusEl) statusEl.textContent = msg;
    }

    function buildMarksArray() {
        const seq = window.viewerState.markSequence;
        const out = [];

        for (const name of seq) {
            const m = window.viewerState.marks[name] || {
                name,
                lon: null,
                lat: null,
                skipped: true
            };

            out.push({
                name: m.name,
                lat: m.lat,
                lon: m.lon,
                skipped: !!m.skipped
            });
        }
        return out;
    }

    function buildCsvPayload(marks) {
        const lines = [];
        lines.push("name,lat,lon,skipped");

        for (const m of marks) {
            lines.push(
                [
                    m.name,
                    m.lat !== null ? m.lat.toFixed(7) : "",
                    m.lon !== null ? m.lon.toFixed(7) : "",
                    m.skipped ? "1" : "0"
                ].join(",")
            );
        }
        return lines.join("\n");
    }

    function triggerDownload(filename, mimeType, content) {
        const blob = new Blob([content], { type: mimeType });
        const url = URL.createObjectURL(blob);

        const a = document.createElement("a");
        a.href = url;
        a.download = filename;

        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);

        URL.revokeObjectURL(url);
    }

    function saveMarks() {
        // Build raceId explicitly from URL
        const params = new URLSearchParams(window.location.search);

        const date  = params.get("date") || "000000";
        const race  = params.get("race_number") || "0";
        const group = params.get("group_color") || "unknown";

        const raceId = `${date}_R${race}_${group}`;

        const marks = buildMarksArray();
        const csvPayload = buildCsvPayload(marks);

        const csvName = `marks_${raceId}.csv`;

        triggerDownload(csvName, "text/csv", csvPayload);

        setStatus("Marks saved to Downloads as " + csvName + ".");
    }

    function onMarksComplete() {
        const proceed = window.confirm("All marks placed. Save?");
        if (proceed) {
            saveMarks();
        } else {
            setStatus("Save cancelled. You can still adjust by reloading viewer.");
        }
    }

    window.addEventListener("viewer:marksComplete", onMarksComplete);
})();
