from __future__ import annotations

from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException

from ..loaders import (
    list_race_groups,
    list_race_groups_public,
    sailors_in_group,
    load_group_df,
    legs_in_df,
    roster_colors,
)

router = APIRouter(tags=["races"])

# -----------------------------
# Paths (DO NOT CHANGE)
# -----------------------------
# /Users/marklittlejohn/Desktop/SailAnalytics/coach/app/backend/routes/races.py
#   -> parents[4] == /Users/marklittlejohn/Desktop/SailAnalytics
SAILANALYTICS_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = SAILANALYTICS_ROOT / "data"
GEOMETRY_DIR = DATA_DIR / "geometry"


def _load_leg_bearings(group_id: str) -> dict[str, int]:
    """
    Source of truth: data/geometry/geometry_<race_id>.csv
    Returns mapping: { "1": 329, "2": 220, ... } (leg_id -> bearing_deg)
    """
    gpath = GEOMETRY_DIR / f"geometry_{group_id}.csv"
    if not gpath.exists():
        return {}

    gdf = pd.read_csv(gpath)

    if "leg_id" not in gdf.columns or "bearing_deg" not in gdf.columns:
        return {}

    out: dict[str, int] = {}
    for _, r in gdf.iterrows():
        try:
            leg_id = int(r["leg_id"])
            brg = int(round(float(r["bearing_deg"])))
            out[str(leg_id)] = brg
        except Exception:
            continue

    return out


@router.get("/races")
def api_list_races():
    return list_race_groups_public()


@router.get("/races/{group_id}/info")
def api_race_info(group_id: str):
    groups = list_race_groups()
    g = groups.get(group_id)
    if not g:
        raise HTTPException(status_code=404, detail=f"Race group not found: {group_id}")

    sailors = sailors_in_group(group_id)
    df = load_group_df(group_id)  # load all sailors to determine legs
    legs = legs_in_df(df)

    cmap = roster_colors()
    colors = {s: cmap.get(s) for s in sailors}  # missing -> None (frontend can fallback)

    # NEW: fixed geometry bearing per leg (authoritative)
    leg_bearings = _load_leg_bearings(group_id)

    return {
        "race_id": group_id,
        "date": g.race_date,
        "race_number": g.race_number,
        "fleet": g.fleet,
        "sailors": sailors,
        "legs": legs,
        "colors": colors,
        "leg_bearings": leg_bearings,  # <--- NEW
        "row_count": int(len(df)),
    }
