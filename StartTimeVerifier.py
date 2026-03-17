#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
StartTimeVerifier.py
----------------------------------------------------------
Stage-2 pipeline entry point.

UPDATED LOGIC:
- If only ONE sailor is present, use that sailor's start-line crossing time.
- If multiple sailors are present, use the median crossing time (unchanged).
- If no sailors are found → error.

WORLD-PROOF TIME:
- Uses unix_s (UTC epoch seconds) from trimmed files.
----------------------------------------------------------
"""

import argparse
import csv
import math
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from statistics import median


# ---------------------------------------------------------
# PROJECT PATHS
# ---------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

RACETIMES_PATH = DATA_DIR / "racetimes" / "RaceTimes.csv"
MARKS_DIR = DATA_DIR / "marks"
TRIMMED_DIR = DATA_DIR / "trimmed"
GEOM_DIR = DATA_DIR / "geometry"

TAPEBUILDER_PATH = BASE_DIR / "TapeBuilder.py"


# ---------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------
def project(lat, lon, lat0, lon0):
    R = 6371000.0
    x = math.radians(lon - lon0) * R * math.cos(math.radians(lat0))
    y = math.radians(lat - lat0) * R
    return x, y


def segment_intersection(A, B, P, Q):
    ax, ay = A
    bx, by = B
    px, py = P
    qx, qy = Q

    rx, ry = bx - ax, by - ay
    sx, sy = qx - px, qy - py

    denom = rx * sy - ry * sx
    if abs(denom) < 1e-12:
        return None

    qpx, qpy = px - ax, py - ay
    u = (qpx * ry - qpy * rx) / denom

    if 0.0 <= u <= 1.0:
        return u
    return None


# ---------------------------------------------------------
# Load start line
# ---------------------------------------------------------
def load_start_line(marks_path: Path):

    startS = startP = None

    with open(marks_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for r in reader:
            if r.get("name") == "StartS":
                startS = (float(r["lat"]), float(r["lon"]))
            elif r.get("name") == "StartP":
                startP = (float(r["lat"]), float(r["lon"]))

    if startS is None or startP is None:
        raise RuntimeError("Marks file must contain StartS and StartP")

    return startS, startP


# ---------------------------------------------------------
# Load trimmed tracks
# ---------------------------------------------------------
def load_tracks(date_ddmmyy: str, race_number: str, group_color: str):

    tracks = []

    pattern = f"*_{date_ddmmyy}_R{race_number}_{group_color}_trimmed.csv"
    candidates = sorted(TRIMMED_DIR.glob(pattern))

    print("Trimmed pattern:", str(TRIMMED_DIR / pattern))
    print("Trimmed candidates:", [p.name for p in candidates])

    if not candidates:
        raise RuntimeError(
            f"No trimmed tracks found for {date_ddmmyy} R{race_number} {group_color}"
        )

    for p in candidates:

        rows = []

        with open(p, newline="", encoding="utf-8") as f:

            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []

            if "unix_s" not in fieldnames:
                raise RuntimeError(f"{p.name}: missing unix_s")

            if "latitude_raw" not in fieldnames or "longitude_raw" not in fieldnames:
                raise RuntimeError(f"{p.name}: missing latitude_raw/longitude_raw")

            for r in reader:

                us = int(round(float(r["unix_s"])))

                rows.append(
                    {
                        "t": datetime.fromtimestamp(us, tz=timezone.utc),
                        "lat": float(r["latitude_raw"]),
                        "lon": float(r["longitude_raw"]),
                    }
                )

        if rows:
            tracks.append(rows)

    if len(tracks) == 0:
        raise RuntimeError("No valid trimmed tracks loaded")

    print(f"[START VERIFY] Sailors detected: {len(tracks)}")

    return tracks


# ---------------------------------------------------------
# Detect crossing time
# ---------------------------------------------------------
def first_crossing_time(track, startS, startP):

    lat0 = (startS[0] + startP[0]) / 2
    lon0 = (startS[1] + startP[1]) / 2

    A = project(startS[0], startS[1], lat0, lon0)
    B = project(startP[0], startP[1], lat0, lon0)

    pts = []

    for r in track:
        x, y = project(r["lat"], r["lon"], lat0, lon0)
        pts.append((r["t"], x, y))

    for i in range(len(pts) - 1):

        t0, x0, y0 = pts[i]
        t1, x1, y1 = pts[i + 1]

        u = segment_intersection(A, B, (x0, y0), (x1, y1))

        if u is not None:

            dt = (t1 - t0).total_seconds()

            return t0 + timedelta(seconds=dt * u)

    return None


# ---------------------------------------------------------
# Write verified start time
# ---------------------------------------------------------
def write_verified_start(date_ddmmyy, race_number, group_color, verified_start_iso):

    if not RACETIMES_PATH.exists():
        raise RuntimeError("RaceTimes.csv not found")

    rows_out = []
    updated = False

    with open(RACETIMES_PATH, newline="", encoding="utf-8") as f:

        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        if "verified_start_utc" not in fieldnames:
            fieldnames.append("verified_start_utc")

        for r in reader:

            if (
                r.get("date") == date_ddmmyy
                and str(r.get("race_number")) == str(race_number)
                and str(r.get("group_color", "")).lower() == group_color.lower()
            ):
                r["verified_start_utc"] = verified_start_iso
                updated = True

            rows_out.append(r)

    if not updated:
        raise RuntimeError("RaceTimes row not found")

    with open(RACETIMES_PATH, "w", newline="", encoding="utf-8") as f:

        writer = csv.DictWriter(f, fieldnames=fieldnames)

        writer.writeheader()
        writer.writerows(rows_out)


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
def main():

    ap = argparse.ArgumentParser()

    ap.add_argument("--date", required=True)
    ap.add_argument("--race", required=True)
    ap.add_argument("--group", required=True)

    args = ap.parse_args()

    date_ddmmyy = str(args.date).strip()
    race_number = str(args.race).strip()
    group_color = str(args.group).strip().lower()

    marks_path = MARKS_DIR / f"marks_{date_ddmmyy}_R{race_number}_{group_color}.csv"

    geom_path = GEOM_DIR / f"geometry_{date_ddmmyy}_R{race_number}_{group_color}.csv"

    if not marks_path.exists():
        raise RuntimeError(f"Marks file not found: {marks_path}")

    if not geom_path.exists():
        raise RuntimeError(f"Geometry file not found: {geom_path}")

    startS, startP = load_start_line(marks_path)

    tracks = load_tracks(date_ddmmyy, race_number, group_color)

    crossings = []

    for tr in tracks:

        tc = first_crossing_time(tr, startS, startP)

        if tc:
            crossings.append(tc.timestamp())

    if not crossings:
        raise RuntimeError("No valid start-line crossings detected")

    # ---------------------------------------------------------
    # START TIME LOGIC
    # ---------------------------------------------------------
    if len(crossings) == 1:

        print("[START VERIFY] Single sailor detected — using direct crossing time")

        verified_time = crossings[0]

    else:

        print("[START VERIFY] Multiple sailors detected — using median crossing")

        verified_time = median(crossings)

    t0 = datetime.fromtimestamp(verified_time, tz=timezone.utc)

    verified_iso = t0.isoformat()

    write_verified_start(date_ddmmyy, race_number, group_color, verified_iso)

    print("Start Time Verified")
    print("verified_start_utc =", verified_iso)

    # ---------------------------------------------------------
    # Launch TapeBuilder
    # ---------------------------------------------------------
    print("Launching TapeBuilder...")

    result = subprocess.run(
        [sys.executable, str(TAPEBUILDER_PATH), "--geometry", str(geom_path)],
        cwd=str(BASE_DIR),
    )

    if result.returncode != 0:
        raise RuntimeError("TapeBuilder failed")

    print("TapeBuilder completed successfully")


if __name__ == "__main__":
    main()