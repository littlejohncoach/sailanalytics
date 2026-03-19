from __future__ import annotations

from fastapi import APIRouter
from pathlib import Path
import csv

router = APIRouter()

# --------------------------------------------------
# PATHS (LOCKED — NO RELATIVE DRIFT)
# --------------------------------------------------
BASE_DIR = Path("/Users/marklittlejohn/Desktop/SailAnalytics")
META_FILE = BASE_DIR / "data" / "race_metadata" / "race_metadata.csv"

# --------------------------------------------------
# SCHEMA (LOCKED TO YOUR REAL FILE)
# --------------------------------------------------
FIELDNAMES = [
    "race_id",
    "date",
    "race_number",
    "fleet",
    "venue",
    "event",
    "wind_dir_deg",
    "wind_knots",
    "sea_state",
    "wind_type"
]

# --------------------------------------------------
# PURE FUNCTION
# --------------------------------------------------
def load_metadata(race_id: str) -> dict:
    if not META_FILE.exists():
        print("METADATA FILE NOT FOUND:", META_FILE)
        return {}

    with open(META_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            row_id = (row.get("race_id") or "").strip()

            if row_id == race_id:
                print("MATCH FOUND:", row_id)
                return {k: row.get(k, "") for k in FIELDNAMES}

    print("NO MATCH FOR:", race_id)
    return {}

# --------------------------------------------------
# API
# --------------------------------------------------
@router.get("/race_metadata")
def get_metadata(race_id: str):
    print("API RECEIVED:", repr(race_id))
    return load_metadata(race_id)
