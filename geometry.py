#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
geometry.py — HEADLESS (robust skipped-mark handling)
-------------------------------------------------------
Builds geometry_<raceID>.csv from a provided marks CSV file.

Reads:
    data/marks/marks_<date>_R<race>_<colour>.csv

Writes:
    data/geometry/geometry_<date>_R<race>_<colour>.csv

Key rule:
- Integer marks (e.g., 1,2,3,4,5...) are INCLUDED ONLY if they are usable.
  "Usable" means:
    A) They can be resolved from iS/iP midpoint (both exist, NOT skipped, coords present), OR
    B) The direct integer mark i exists, NOT skipped, coords present.
- If an integer mark is skipped (skipped=1) and/or has blank coords, it is ignored.
- StartS/StartP and FinishS/FinishP are always required and must have coords.

NEW (Gate endpoints for downstream leg-arrival logic):
- When an integer mark i is resolved via iS/iP, geometry still uses the MIDPOINT as to_lat/to_lon
  for bearings and lengths, BUT it also writes the gate endpoints:
      to_is_gate = 1
      to_gate_s_lat_deg / to_gate_s_lon_deg
      to_gate_p_lat_deg / to_gate_p_lon_deg
- When i is resolved via a direct integer mark, to_is_gate = 0 and gate endpoint columns are blank.
-------------------------------------------------------
"""

import csv
import math
import argparse
from pathlib import Path


# ---------------------------------------------------------
# Geo helpers
# ---------------------------------------------------------
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (math.sin(dphi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def bearing_deg(lat1, lon1, lat2, lon2):
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlon = math.radians(lon2 - lon1)

    x = math.sin(dlon) * math.cos(phi2)
    y = (math.cos(phi1) * math.sin(phi2) -
         math.sin(phi1) * math.cos(phi2) * math.cos(dlon))

    brng = math.degrees(math.atan2(x, y))
    return int(round((brng + 360) % 360))


def midpoint(latS, lonS, latP, lonP):
    phi1 = math.radians(latS)
    lam1 = math.radians(lonS)
    phi2 = math.radians(latP)
    lam2 = math.radians(lonP)

    bx = math.cos(phi2) * math.cos(lam2 - lam1)
    by = math.cos(phi2) * math.sin(lam2 - lam1)

    phi3 = math.atan2(
        math.sin(phi1) + math.sin(phi2),
        math.sqrt((math.cos(phi1) + bx) ** 2 + by ** 2)
    )
    lam3 = lam1 + math.atan2(by, math.cos(phi1) + bx)

    return math.degrees(phi3), ((math.degrees(lam3) + 540) % 360) - 180


# ---------------------------------------------------------
# IO / validation
# ---------------------------------------------------------
def load_marks_csv(path: Path):
    marks = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            name = (r.get("name") or "").strip()
            if not name:
                continue
            lat_raw = (r.get("lat") or "").strip()
            lon_raw = (r.get("lon") or "").strip()
            skipped_raw = (r.get("skipped") or "0").strip()

            marks[name] = {
                "lat": float(lat_raw) if lat_raw else None,
                "lon": float(lon_raw) if lon_raw else None,
                "skipped": skipped_raw == "1"
            }
    return marks


def require_mark(marks, name: str):
    if name not in marks:
        raise RuntimeError(f"Missing required mark '{name}' in marks file.")
    return marks[name]


def require_coords(mark_name: str, lat, lon):
    if lat is None or lon is None:
        raise RuntimeError(
            f"Missing lat/lon for mark '{mark_name}'. "
            f"Provide coordinates or ensure it is not used (skipped=1 and not part of sequence)."
        )


# ---------------------------------------------------------
# Integer mark selection + resolution
# ---------------------------------------------------------
def integer_is_usable(i: int, marks: dict) -> bool:
    name = str(i)
    s = f"{i}S"
    p = f"{i}P"

    # usable via S/P midpoint
    if s in marks and p in marks:
        ms = marks[s]
        mp = marks[p]
        if (not ms["skipped"]) and (not mp["skipped"]):
            if (ms["lat"] is not None and ms["lon"] is not None and
                mp["lat"] is not None and mp["lon"] is not None):
                return True

    # usable via direct integer mark
    if name in marks:
        m = marks[name]
        if (not m["skipped"]) and (m["lat"] is not None) and (m["lon"] is not None):
            return True

    return False


def resolve_integer(i: int, marks: dict) -> dict:
    """
    Returns a dict describing the resolved mark.
    Always returns the integer name str(i) as "name".
    If resolved via iS/iP, lat/lon are the MIDPOINT but gate endpoints are populated.
    """
    name = str(i)
    s = f"{i}S"
    p = f"{i}P"

    # Prefer midpoint if explicitly provided and not skipped
    if s in marks and p in marks:
        ms = marks[s]
        mp = marks[p]
        if (not ms["skipped"]) and (not mp["skipped"]):
            require_coords(s, ms["lat"], ms["lon"])
            require_coords(p, mp["lat"], mp["lon"])
            lat_mid, lon_mid = midpoint(ms["lat"], ms["lon"], mp["lat"], mp["lon"])
            return {
                "name": name,
                "lat": lat_mid,
                "lon": lon_mid,
                "is_gate": True,
                "gate_s_lat": ms["lat"],
                "gate_s_lon": ms["lon"],
                "gate_p_lat": mp["lat"],
                "gate_p_lon": mp["lon"],
            }

    # Fallback: direct integer mark
    m = require_mark(marks, name)
    require_coords(name, m["lat"], m["lon"])
    return {
        "name": name,
        "lat": m["lat"],
        "lon": m["lon"],
        "is_gate": False,
        "gate_s_lat": None,
        "gate_s_lon": None,
        "gate_p_lat": None,
        "gate_p_lon": None,
    }


def sorted_usable_integers(marks: dict):
    ints = sorted({int(k) for k in marks.keys() if k.isdigit()})
    return [i for i in ints if integer_is_usable(i, marks)]


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--marks", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    marks_path = Path(args.marks)
    out_path = Path(args.out)

    marks = load_marks_csv(marks_path)

    # Required Start midpoint
    m_start_s = require_mark(marks, "StartS")
    m_start_p = require_mark(marks, "StartP")
    require_coords("StartS", m_start_s["lat"], m_start_s["lon"])
    require_coords("StartP", m_start_p["lat"], m_start_p["lon"])
    start_lat, start_lon = midpoint(
        m_start_s["lat"], m_start_s["lon"],
        m_start_p["lat"], m_start_p["lon"]
    )

    # Required Finish midpoint
    m_fin_s = require_mark(marks, "FinishS")
    m_fin_p = require_mark(marks, "FinishP")
    require_coords("FinishS", m_fin_s["lat"], m_fin_s["lon"])
    require_coords("FinishP", m_fin_p["lat"], m_fin_p["lon"])
    finish_lat, finish_lon = midpoint(
        m_fin_s["lat"], m_fin_s["lon"],
        m_fin_p["lat"], m_fin_p["lon"]
    )

    # Build effective mark sequence as dicts
    effective = [
        {
            "name": "Start",
            "lat": start_lat,
            "lon": start_lon,
            "is_gate": False,
            "gate_s_lat": None,
            "gate_s_lon": None,
            "gate_p_lat": None,
            "gate_p_lon": None,
        }
    ]

    usable_ints = sorted_usable_integers(marks)
    for i in usable_ints:
        effective.append(resolve_integer(i, marks))

    effective.append(
        {
            "name": "Finish",
            "lat": finish_lat,
            "lon": finish_lon,
            "is_gate": False,
            "gate_s_lat": None,
            "gate_s_lon": None,
            "gate_p_lat": None,
            "gate_p_lon": None,
        }
    )

    # Build legs
    legs = []
    cumulative = 0.0

    for i in range(len(effective) - 1):
        f = effective[i]
        t = effective[i + 1]

        dist = haversine(f["lat"], f["lon"], t["lat"], t["lon"])
        brg = bearing_deg(f["lat"], f["lon"], t["lat"], t["lon"])
        cumulative += dist

        legs.append({
            "leg_id": i + 1,
            "from_mark": f["name"],
            "to_mark": t["name"],
            "from_lat_deg": f["lat"],
            "from_lon_deg": f["lon"],
            "to_lat_deg": t["lat"],
            "to_lon_deg": t["lon"],
            "bearing_deg": brg,
            "leg_length_m": dist,
            "cumulative_length_m": cumulative,

            # NEW: gate endpoints for the TO mark (used by downstream leg-arrival logic)
            "to_is_gate": 1 if t["is_gate"] else 0,
            "to_gate_s_lat_deg": t["gate_s_lat"],
            "to_gate_s_lon_deg": t["gate_s_lon"],
            "to_gate_p_lat_deg": t["gate_p_lat"],
            "to_gate_p_lon_deg": t["gate_p_lon"],
        })

    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=legs[0].keys())
        writer.writeheader()
        writer.writerows(legs)

    print(f"Geometry written: {out_path}")
    if usable_ints:
        print(f"Included integer marks: {', '.join(map(str, usable_ints))}")
    else:
        print("Included integer marks: (none)")
    # Optional debug: show which integers were gates
    gates = [m["name"] for m in effective if m.get("is_gate")]
    if gates:
        print(f"Gate midpoints used for: {', '.join(gates)}")


if __name__ == "__main__":
    main()