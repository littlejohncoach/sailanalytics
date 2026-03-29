from __future__ import annotations

from fastapi import APIRouter
from pathlib import Path
import glob
import math
import csv

router = APIRouter()

BASE_DIR = Path.cwd()
META_FILE = BASE_DIR / "data" / "race_metadata" / "race_metadata.csv"
TOTAL_RACES_DIR = BASE_DIR / "data" / "totalraces"

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


def circ_mean(values):
    sin_sum = sum(math.sin(math.radians(v)) for v in values)
    cos_sum = sum(math.cos(math.radians(v)) for v in values)
    return math.degrees(math.atan2(sin_sum, cos_sum)) % 360


def derive_wind_from_totalraces(race_id: str):

    port = []
    stbd = []

    files = glob.glob(str(TOTAL_RACES_DIR / "*.csv"))

    for file in files:

        if race_id not in file:
            continue

        try:
            with open(file, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)

                for r in reader:

                    if r.get("geom_leg_id") != "1":
                        continue

                    if r.get("is_upwind") != "1":
                        continue

                    try:
                        cog = float(r["COG_deg"])
                        axis = float(r["axis_angle_signed_deg"])
                    except:
                        continue

                    if axis > 0:
                        port.append(cog)
                    elif axis < 0:
                        stbd.append(cog)

        except Exception:
            continue

    if not port or not stbd:
        return None

    port_mean = circ_mean(port)
    stbd_mean = circ_mean(stbd)

    return int(round(circ_mean([port_mean, stbd_mean])))


def update_metadata_csv():

    if not META_FILE.exists():
        return

    rows = []

    with open(META_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:

            race_id = row.get("race_id")

            wind = derive_wind_from_totalraces(race_id)

            if wind is not None:
                row["wind_dir_deg"] = str(wind)
                print(race_id, "->", wind)

            rows.append(row)

    with open(META_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print("metadata updated")


def load_metadata(race_id: str) -> dict:
    if not META_FILE.exists():
        return {}

    race_id = (race_id or "").strip().lower()

    with open(META_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            if (row.get("race_id") or "").strip().lower() == race_id:
                return {k: row.get(k, "") for k in FIELDNAMES}

    return {}


@router.get("/race_metadata")
def get_metadata(race_id: str):
    return load_metadata(race_id)


if __name__ == "__main__":
    update_metadata_csv()