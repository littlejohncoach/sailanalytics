#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TapeBuilder.py
----------------------------------------------------------
Builds SailAnalytics Tape CSVs (truth layer) for one race.

CHANGE (HR):
- Tape now includes ONE column: heart_rate
- heart_rate is lifted directly from the trimmed file at tape-build time (UTC-locked)
- Missing HR samples are filled deterministically:
    - internal gaps: linear interpolation between the two bracketing valid samples
    - leading gaps: forward-fill from first valid
    - trailing gaps: back-fill from last valid
----------------------------------------------------------
"""

import csv
import math
import argparse
from pathlib import Path
from datetime import datetime, timezone
import subprocess
import sys

# ---------------------------------------------------------
# PATHS (LOCKED)
# ---------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RACETIMES_PATH = DATA_DIR / "racetimes" / "RaceTimes.csv"
MARKS_DIR = DATA_DIR / "marks"
TRIMMED_DIR = DATA_DIR / "trimmed"
GEOM_DIR = DATA_DIR / "geometry"
OUT_DIR = DATA_DIR / "tapes"

# ---------------------------------------------------------
# SAILOR COLORS (LOCKED)
# ---------------------------------------------------------
SAILOR_COLOR_HEX = {
    "yalcin":   "#1F77B4",
    "berkay":   "#FF7F0E",
    "lourenco": "#2CA02C",
    "joao":     "#D62728",
    "william":  "#9467BD",
    "edu":      "#17BECF",
}

# ---------------------------------------------------------
# GEO HELPERS (UNCHANGED)
# ---------------------------------------------------------
EARTH_R = 6371000.0

def haversine_m(lat1, lon1, lat2, lon2):
    p1 = math.radians(lat1); p2 = math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*EARTH_R*math.asin(math.sqrt(a))

def bearing_deg(lat1, lon1, lat2, lon2):
    phi1 = math.radians(lat1); phi2 = math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(phi2)
    x = math.cos(phi1)*math.sin(phi2) - math.sin(phi1)*math.cos(phi2)*math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0

def ang_diff_deg(a, b):
    d = abs((a - b) % 360.0)
    return 360.0 - d if d > 180.0 else d

def parse_iso_utc(s):
    """
    Parse an ISO timestamp string and return a timezone-aware UTC datetime.
    Accepts:
      - ...Z
      - ...+00:00 (or any offset)
      - naive ISO timestamps (treated as UTC deterministically)
    """
    dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

# ---------------------------------------------------------
# LOADERS
# ---------------------------------------------------------
def load_racetimes_row(date_ddmmyy, race_number, group_color):
    with open(RACETIMES_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (
                r["date"] == date_ddmmyy and
                str(r["race_number"]) == str(race_number) and
                r["group_color"] == group_color
            ):
                if not r.get("verified_start_utc"):
                    raise RuntimeError("verified_start_utc missing")
                return r
    raise RuntimeError("RaceTimes row not found")

# ---------------------------------------------------------
# MARKS LOADER (MINIMAL SURGICAL PATCH)
# - Allow integer marks to be omitted if they are skipped.
# - Only require StartS/StartP and FinishS/FinishP always.
# - Build midpoints/aliases only for marks that are present (and not skipped).
# - Keep return shape stable, but set absent elements to None.
# ---------------------------------------------------------
def load_marks(marks_path):
    marks = {}

    with open(marks_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            # keep only non-skipped rows (skipped==0)
            if str(r.get("skipped", "")).strip() != "0":
                continue

            name = r["name"].strip()
            lat = float(r["lat"])
            lon = float(r["lon"])
            marks[name] = (lat, lon)

    # HARD requirements (always)
    required_hard = ["StartS", "StartP", "FinishS", "FinishP"]
    missing_hard = [m for m in required_hard if m not in marks]
    if missing_hard:
        raise RuntimeError(f"Required marks missing: {missing_hard}")

    def mid(a, b):
        return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)

    # Optional marks (present only if non-skipped rows exist)
    out = {}

    out["Start_mid"] = mid(marks["StartS"], marks["StartP"])
    out["Finish_mid"] = mid(marks["FinishS"], marks["FinishP"])

    # Optional integers (1..5) if they exist
    out["WM1"] = marks.get("1")
    out["WM2"] = marks.get("4")

    # Gate midpoints only if both endpoints exist
    out["Gate1_mid"] = mid(marks["2"], marks["3"]) if ("2" in marks and "3" in marks) else None

    # Gate2: keep original intent but only if 5 exists; otherwise None
    out["Gate2_mid"] = mid(marks["5"], marks["5"]) if ("5" in marks) else None

    return out

def load_geometry(path):
    with open(path, newline="", encoding="utf-8") as f:
        list(csv.DictReader(f))

def _pick_first_key(row, keys):
    for k in keys:
        if k in row and str(row[k]).strip() != "":
            return k
    return None

def load_trimmed_track(path):
    """
    Returns list of dict samples:
      { t (UTC datetime), lat (float), lon (float), hr (int or None) }
    """
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    out = []
    for r in rows:
        ts_key = _pick_first_key(r, ["timestamp_iso", "timestamp_utc", "timestamp"])
        if ts_key is None:
            raise RuntimeError(f"{Path(path).name}: missing timestamp column (timestamp_iso/utc)")

        lat_key = _pick_first_key(r, ["latitude_raw", "latitude_deg", "latitude", "lat"])
        lon_key = _pick_first_key(r, ["longitude_raw", "longitude_deg", "longitude", "lon"])
        if lat_key is None or lon_key is None:
            raise RuntimeError(f"{Path(path).name}: missing latitude/longitude columns")

        hr_key = _pick_first_key(r, ["heart_rate", "HR_raw_bpm", "hr", "HR"])
        hr_val = None
        if hr_key is not None:
            v = str(r.get(hr_key, "")).strip()
            if v != "":
                try:
                    hr_val = int(round(float(v)))
                except Exception:
                    hr_val = None

        out.append({
            "t": parse_iso_utc(r[ts_key]),
            "lat": float(r[lat_key]),
            "lon": float(r[lon_key]),
            "hr": hr_val
        })

    return out

def fill_hr(samples):
    """
    Deterministic fill of missing HR in-place (one column only):
      - internal gaps: linear interpolation between two bracketing valid HR points
      - start gaps: forward-fill
      - end gaps: back-fill
    """
    n = len(samples)
    if n == 0:
        return

    hr = [s["hr"] for s in samples]
    unix_s = [int(s["t"].timestamp()) for s in samples]

    valid = [i for i, v in enumerate(hr) if v is not None]
    if not valid:
        # No HR at all -> leave as None
        return

    first = valid[0]
    last = valid[-1]

    # forward-fill start
    for i in range(0, first):
        hr[i] = hr[first]

    # back-fill end
    for i in range(last + 1, n):
        hr[i] = hr[last]

    # interpolate internal gaps
    for a, b in zip(valid[:-1], valid[1:]):
        if b == a + 1:
            continue
        t0 = unix_s[a]
        t1 = unix_s[b]
        v0 = float(hr[a])
        v1 = float(hr[b])
        dt = (t1 - t0)

        for i in range(a + 1, b):
            ti = unix_s[i]
            if dt <= 0:
                hr[i] = int(round(v0))
            else:
                frac = (ti - t0) / dt
                hr[i] = int(round(v0 + (v1 - v0) * frac))

    # write back
    for i in range(n):
        samples[i]["hr"] = hr[i]

# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geometry", default="")
    args = ap.parse_args()

    geom_path = Path(args.geometry) if args.geometry else next(GEOM_DIR.glob("geometry_*.csv"))
    stem = geom_path.stem.replace("geometry_", "")
    date_ddmmyy, rpart, group_color = stem.split("_")
    race_number = rpart.replace("R", "")

    marks_path = MARKS_DIR / f"marks_{date_ddmmyy}_R{race_number}_{group_color}.csv"

    race = load_racetimes_row(date_ddmmyy, race_number, group_color)
    t0 = parse_iso_utc(race["verified_start_utc"])

    _ = load_marks(marks_path)
    load_geometry(geom_path)

    tracks = sorted(TRIMMED_DIR.glob(f"*_{date_ddmmyy}_R{race_number}_{group_color}_trimmed.csv"))
    if not tracks:
        raise RuntimeError("No trimmed tracks")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for tf in tracks:
        sailor = tf.name.split("_")[0].lower()

        raw = load_trimmed_track(tf)
        samples = [s for s in raw if s["t"] >= t0]
        if len(samples) < 2:
            continue

        # HR fill is done here (UTC-locked, same rows)
        fill_hr(samples)

        # OUTPUT NAMING (LOCKED): <sailor>_<dateDDMMYY>_R<race#>_<group>.csv
        tape_path = OUT_DIR / f"{sailor}_{date_ddmmyy}_R{race_number}_{group_color}.csv"
        with open(tape_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["timestamp_utc", "latitude", "longitude", "heart_rate"])
            for s in samples:
                # heart_rate must exist as one column only; blank if still None
                hr_out = "" if s["hr"] is None else str(int(s["hr"]))
                w.writerow([s["t"].isoformat(), s["lat"], s["lon"], hr_out])

    print("Tape build complete")

    # -----------------------------------------------------
    # PIPELINE CONTINUATION → Finish Line Finder
    # -----------------------------------------------------
    race_id = f"{date_ddmmyy}_R{race_number}_{group_color}"

    print("Launching TapeFinishFinder...")
    # HR is already in the tape. Force FinishFinder to skip its HR append stage.
    res = subprocess.run(
        [sys.executable, "TapeFinishFinder.py", "--race_id", race_id, "--skip_hr"],
        cwd=BASE_DIR
    )

    if res.returncode != 0:
        raise RuntimeError("TapeFinishFinder failed")

    print("TapeFinishFinder completed successfully")

if __name__ == "__main__":
    main()
