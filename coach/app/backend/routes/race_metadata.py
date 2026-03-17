from fastapi import APIRouter
from pathlib import Path
import csv

router = APIRouter()

# Project root
BASE_DIR = Path(__file__).resolve().parents[4]

# Metadata file location
META_FILE = BASE_DIR / "data" / "race_metadata" / "race_metadata.csv"


@router.get("/race_metadata")
def get_metadata(race_id: str):

    if not META_FILE.exists():
        return {}

    with open(META_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            if row.get("race_id") == race_id:
                return row

    return {}