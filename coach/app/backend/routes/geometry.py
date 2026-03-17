from __future__ import annotations

import csv
from pathlib import Path
from fastapi import APIRouter, HTTPException

router = APIRouter()

# ---------------------------------------------------------
# Paths (locked to project root)
# ---------------------------------------------------------
BASE_DIR = Path(__file__).resolve()
# geometry.py lives at: SailAnalytics/coach/app/backend/routes/geometry.py
# so project root (SailAnalytics) is BASE_DIR.parents[4]
PROJECT_ROOT = BASE_DIR.parents[4]
GEOMETRY_DIR = PROJECT_ROOT / "data" / "geometry"


@router.get("/geometry")
def get_geometry(race_id: str):
    """
    READ-ONLY truth endpoint.
    Reads:  data/geometry/geometry_<race_id>.csv
    Returns: JSON mirroring the CSV contents (no recompute, no inference).
    """
    geom_path = GEOMETRY_DIR / f"geometry_{race_id}.csv"
    if not geom_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Geometry file not found: {geom_path.name}"
        )

    legs = []
    marks = {}

    with geom_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # CSV truth fields (verbatim mapping)
            leg_id = int(row["leg_id"])
            from_mark = row["from_mark"]
            to_mark = row["to_mark"]

            from_lat = float(row["from_lat_deg"])
            from_lon = float(row["from_lon_deg"])
            to_lat = float(row["to_lat_deg"])
            to_lon = float(row["to_lon_deg"])

            bearing = int(row["bearing_deg"])
            leg_length_m = float(row["leg_length_m"])
            cumulative_length_m = float(row["cumulative_length_m"])

            legs.append({
                "leg_id": leg_id,
                "from_mark": from_mark,
                "to_mark": to_mark,
                "from": [from_lat, from_lon],
                "to": [to_lat, to_lon],
                "bearing_deg": bearing,
                "leg_length_m": leg_length_m,
                "cumulative_length_m": cumulative_length_m,
            })

            # for red dots (dedupe by mark name)
            marks[from_mark] = [from_lat, from_lon]
            marks[to_mark] = [to_lat, to_lon]

    return {
        "race_id": race_id,
        "marks": [{"id": k, "lat": v[0], "lon": v[1]} for k, v in marks.items()],
        "legs": legs
    }
