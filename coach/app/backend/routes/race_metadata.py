from __future__ import annotations

from fastapi import APIRouter
from pathlib import Path
import glob
import math
import csv

router = APIRouter()

# --------------------------------------------------
# PATHS (FIXED FOR LOCAL + SERVER)
# --------------------------------------------------
BASE_DIR = Path.cwd()
META_FILE = BASE_DIR / "data" / "race_metadata" / "race_metadata.csv"
TOTAL_RACES_DIR = BASE_DIR / "data" / "totalraces"

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
# DERIVE WIND FROM TOTALRACES (LEG 1 ALL SAILORS)
# --------------------------------------------------
def derive_wind_from_totalraces(race_id: str):

    pattern = str(TOTAL_RACES_DIR / f"*_{race_id}.csv")
    files = glob.glob(pattern)

    if not files:
        return None

    port = []
    stbd = []

    for file in files:
        try:
            with open(file, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)

                for r in reader:

                    # leg 1 only
                    if r.get("geom_leg_id") != "1":
                        continue

                    # upwind only
                    if r.get("is_upwind") != "1":
                        continue

                    try:
                        cog = float(r["COG_deg"])
                        axis = float(r["axis_angle_signed_deg"])
                    except Exception:
                        continue

                    if axis > 0:
                        port.append(cog)
                    elif axis < 0:
                        stbd.append(cog)

        except Exception:
            continue

    if not port or not stbd:
        return None

    # circular mean helper
    def circ_mean(values):
        sin_sum = sum(math.sin(math.radians(v)) for v in values)
        cos_sum = sum(math.cos(math.radians(v)) for v in values)
        return math.degrees(math.atan2(sin_sum, cos_sum)) % 360

    port_mean = circ_mean(port)
    stbd_mean = circ_mean(stbd)

    wind = circ_mean([port_mean, stbd_mean])

    return int(round(wind))


# --------------------------------------------------
# PURE FUNCTION
# --------------------------------------------------
def load_metadata(race_id: str) -> dict:
    if not META_FILE.exists():
        return {}

    race_id_clean = (race_id or "").strip().lower()

    with open(META_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            row_id = (row.get("race_id") or "").strip().lower()

            if row_id == race_id_clean:

                result = {k: row.get(k, "") for k in FIELDNAMES}

                # override wind direction from totalraces
                derived = derive_wind_from_totalraces(race_id)

                if derived is not None:
                    result["wind_dir_deg"] = str(derived)

                return result

    return {}


# --------------------------------------------------
# API
# --------------------------------------------------
@router.get("/race_metadata")
def get_metadata(race_id: str):
    return load_metadata(race_id)
