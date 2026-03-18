from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pathlib import Path
import pandas as pd

# Import metadata loader (your existing route function)
from .race_metadata import get_metadata

router = APIRouter()

# --------------------------------------------------
# PATHS
# --------------------------------------------------
BASE_DIR = Path(__file__).resolve().parents[4]
TOTAL_DIR = BASE_DIR / "data" / "totalraces"


# --------------------------------------------------
# INTERNAL: LOAD TOTALRACE CSV
# --------------------------------------------------
def _load_totalrace_data(race_id: str):

    pattern = f"*_{race_id}.csv"
    files = list(TOTAL_DIR.glob(pattern))

    if not files:
        raise HTTPException(status_code=404, detail=f"No totalraces found for {race_id}")

    # If multiple sailors → concatenate
    dfs = []
    for f in files:
        df = pd.read_csv(f)
        dfs.append(df)

    df_all = pd.concat(dfs, ignore_index=True)

    return df_all.to_dict(orient="records")


# --------------------------------------------------
# API ENDPOINT
# --------------------------------------------------
@router.get("/data")
def get_data(race_id: str):
    """
    Returns BOTH:
    - time-series data (totalraces)
    - metadata (race-level)
    """

    # Load time-series data
    data = _load_totalrace_data(race_id)

    # Load metadata (safe — returns {} if not found)
    metadata = get_metadata(race_id)

    return {
        "data": data,
        "metadata": metadata
    }