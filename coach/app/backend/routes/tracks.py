from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..loaders import (
    list_race_groups,
    load_group_df,
    sailors_in_group,
)

router = APIRouter(tags=["tracks"])


# Canonical fixed roster colors (stable, no run-to-run shifting)
_SAILOR_COLOR_HEX = {
    "yalcin":   "#1F77B4",
    "berkay":   "#FF7F0E",
    "lourenco": "#2CA02C",
    "joao":     "#D62728",
    "william":  "#9467BD",
    "edu":      "#17BECF",
}


@router.get("/races/{group_id}/track")
def api_track(
    group_id: str,
    sailor: str = Query(...),
    leg: str | None = Query(None),
):
    # ----------------------------
    # Validate race group
    # ----------------------------
    groups = list_race_groups()
    if group_id not in groups:
        raise HTTPException(status_code=404, detail=f"Race group not found: {group_id}")

    # ----------------------------
    # Validate sailor
    # ----------------------------
    sailor = (sailor or "").strip().lower()
    if not sailor:
        raise HTTPException(status_code=400, detail="Missing sailor")

    sailors = sailors_in_group(group_id)
    sailors_lc = [s.lower() for s in sailors]
    if sailor not in sailors_lc:
        raise HTTPException(status_code=404, detail=f"Sailor not in group: {sailor}")

    # ----------------------------
    # Resolve color
    # ----------------------------
    color = _SAILOR_COLOR_HEX.get(sailor, "#111111")

    # ----------------------------
    # Load sovereign dataset
    # ----------------------------
    df = load_group_df(group_id)

    # ----------------------------
    # Filter to this sailor
    # ----------------------------
    if "sailor" in df.columns:
        df = df[df["sailor"].astype(str).str.strip().str.lower() == sailor].copy()
    elif "sailor_id" in df.columns:
        df = df[df["sailor_id"].astype(str).str.strip().str.lower() == sailor].copy()
    elif "sailor_name" in df.columns:
        df = df[df["sailor_name"].astype(str).str.strip().str.lower() == sailor].copy()
    else:
        raise HTTPException(status_code=500, detail="No sailor column found in group dataframe")

    # ----------------------------
    # REQUIRE canonical time axis
    # ----------------------------
    if "elapsed_race_time_s" not in df.columns:
        raise HTTPException(status_code=500, detail="elapsed_race_time_s missing")

    # ----------------------------
    # Sort by TRUE race time (GLOBAL AXIS)
    # ----------------------------
    df = df.sort_values("elapsed_race_time_s").reset_index(drop=True)

    # ----------------------------
    # Optional leg filtering
    # IMPORTANT: does NOT change time
    # ----------------------------
    if leg and str(leg).lower() not in ("total", "total race", "total_race"):
        leg_col = None
        for c in ("geom_leg_id", "leg_instance_id", "leg", "leg_no"):
            if c in df.columns:
                leg_col = c
                break

        if leg_col is None:
            return {
                "race_id": group_id,
                "sailor": sailor,
                "color": color,
                "leg": leg,
                "points": [],
                "track": [],
            }

        try:
            leg_int = int(str(leg).strip())
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid leg value: {leg}")

        df = df[df[leg_col] == leg_int].copy()

    # ----------------------------
    # Empty safeguard
    # ----------------------------
    if df.empty:
        return {
            "race_id": group_id,
            "sailor": sailor,
            "color": color,
            "leg": leg,
            "points": [],
            "track": [],
        }

    # ----------------------------
    # Resolve latitude / longitude
    # ----------------------------
    lat_col = next((c for c in ("latitude", "lat", "latitude_deg") if c in df.columns), None)
    lon_col = next((c for c in ("longitude", "lon", "longitude_deg") if c in df.columns), None)

    if not lat_col or not lon_col:
        raise HTTPException(status_code=500, detail="Latitude/Longitude columns not found")

    # ----------------------------
    # BUILD TRACK — DIRECT PROJECTION (NO TIME RECONSTRUCTION)
    # ----------------------------
    pts = [
        {
            "lat": float(r[lat_col]),
            "lon": float(r[lon_col]),
            "t": int(r["elapsed_race_time_s"])   # 🔑 SINGLE SOURCE OF TIME
        }
        for _, r in df.iterrows()
        if r[lat_col] == r[lat_col] and r[lon_col] == r[lon_col]
    ]

    # ----------------------------
    # Return (viewer compatibility)
    # ----------------------------
    return {
        "race_id": group_id,
        "sailor": sailor,
        "color": color,
        "leg": leg,
        "points": pts,
        "track": pts,
    }