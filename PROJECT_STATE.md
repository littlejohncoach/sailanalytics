# SailAnalytics — Project State: Stage 1

## Purpose

Stage 1 exists to **prepare, verify, and visually confirm** that all race inputs are correct and analysis‑ready.

This stage ends when the coach can look at the screen and say:

> “Yes. Tracks, marks, and course geometry are correct. Proceed to analysis.”

Stage 1 is **non‑analytic**. It produces **no coaching conclusions**.

---

## Core Principle

**Human‑in‑the‑loop confirmation, fast.**

* Time budget: **≤ 5 minutes** from sitting down to confirmation
* Context: café, laptop, coffee
* Goal: eliminate setup friction and prevent garbage‑in analytics

---

## Inputs

### 1. Raw activity files

* Source: Garmin / watch uploads via TrainingPeaks
* Format: FIT (only supported input at this stage)
* Downloaded locally by coach

### 2. Race metadata (manual)

* Race date
* Race number
* Fleet / group colour
* Gun time
* Finish time

---

## Stage‑1 Pipeline (Canonical Order)

1. **FIT Import**

   * FIT files selected via GUI
   * No assumptions, no inference

2. **FIT Decode (Stage 0)**

   * FIT decoded to in‑memory telemetry
   * No geometry, no smoothing, no trimming

3. **Race‑time Trim**

   * Telemetry trimmed strictly to gun → finish
   * Output: one trimmed CSV per sailor

4. **Trimmed Track Storage**

   * Deterministic filenames
   * Stored in `data/trimmed/`

5. **Viewer Launch (Stage 1 Viewer)**

   * Viewer receives **explicit list** of trimmed tracks
   * No directory scanning

6. **Track Display**

   * All trimmed tracks rendered
   * Base layer: red tracks
   * View auto‑fitted to race extents

7. **Manual Mark Placement**

   * Fixed, canonical mark sequence:

     * StartS → StartP → 1 → 1S → 1P → … → FinishS → FinishP
   * One active mark at a time
   * Actions: Yes / No / Skip
   * No geometry logic in viewer

8. **Mark Save (Stage‑2 Boundary)**

   * Viewer POSTs marks to backend
   * Backend writes to `data/marks/`
   * Never overwrites existing marks

9. **Geometry Build**

   * GeometryBuilder reads saved marks
   * Builds deterministic course geometry
   * Output: `geometry_<race_id>.csv`

10. **Final Visual Verification (Stage 1 End State)**

    * Tracks displayed
    * Course geometry displayed
    * Marks and labels visible
    * **Camera rotated so Start → 1 is vertical (up‑screen)**
    * Read‑only view

---

## Stage‑1 Viewer (Final State)

### What it shows

* All trimmed tracks
* Final marks (labels visible)
* Course legs
* Bearings already computed upstream
* Camera‑style rotation so Start→1 is vertical

### What it does NOT do

* ❌ No mark editing
* ❌ No geometry computation
* ❌ No bearing math
* ❌ No analytics
* ❌ No file writing

This viewer exists solely to answer:

> “Is everything correct?”

---

## Output of Stage 1

* Confirmed trimmed tracks
* Confirmed marks
* Confirmed geometry
* Coach confidence that analysis can begin

No analytical judgments are made here.

---

## Exit Condition

Stage 1 is complete when:

* Geometry is visually correct
* Orientation is correct (Start→1 vertical)
* Coach explicitly proceeds to Stage 2

---

## Notes for Stage 2 (Preview Only)

* Stage 2 consumes **only** Stage‑1 outputs
* No re‑processing of raw data
* All analytics derive from the Tape (truth layer)
* Stage‑2 UI focuses on insight, not setup

(Stage 2 will be defined in a separate project state.)
