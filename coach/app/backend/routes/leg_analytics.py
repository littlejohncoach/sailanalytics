from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

import pandas as pd
from fastapi import APIRouter, HTTPException

router = APIRouter()


# -------------------------------------------------
# Paths
# -------------------------------------------------

SAILANALYTICS_ROOT = Path(__file__).resolve().parents[4]

DATA_DIR = SAILANALYTICS_ROOT / "data"
TOTALRACES_DIR = DATA_DIR / "totalraces"
GEOMETRY_DIR = DATA_DIR / "geometry"


# -------------------------------------------------
# Helpers
# -------------------------------------------------

def _fmt_mmss(seconds: float) -> str:
    sec = int(round(seconds))
    m = sec // 60
    s = sec % 60
    return f"{m}:{s:02d}"


def _fmt_mmss_signed(delta_s: float) -> str:
    if delta_s == 0:
        return "0:00"

    sign = "+" if delta_s > 0 else "-"
    sec = int(round(abs(delta_s)))
    m = sec // 60
    s = sec % 60

    return f"{sign}{m}:{s:02d}"


def _fmt_int_signed(delta: float) -> str:
    val = int(round(delta))
    if val > 0:
        return f"+{val}"
    return str(val)


# -------------------------------------------------
# Geometry (leg lengths)
# -------------------------------------------------

def _geometry_path(race_id: str) -> Path:
    return GEOMETRY_DIR / f"geometry_{race_id}.csv"


def _load_leg_length_m(race_id: str, leg_id: int) -> float:
    gpath = _geometry_path(race_id)

    if not gpath.exists():
        raise FileNotFoundError(f"Missing geometry file {gpath}")

    gdf = pd.read_csv(gpath)

    if "leg_id" not in gdf.columns:
        raise ValueError("Geometry missing leg_id")

    leg = gdf[gdf["leg_id"] == leg_id]

    if leg.empty:
        raise ValueError(f"No geometry for leg {leg_id}")

    if "leg_length_m" in leg.columns:
        return float(leg.iloc[0]["leg_length_m"])

    if "cumulative_length_m" in gdf.columns:
        return float(leg["cumulative_length_m"].max() - leg["cumulative_length_m"].min())

    raise ValueError("Geometry missing leg length")


# -------------------------------------------------
# Data structure
# -------------------------------------------------

@dataclass
class LegRow:
    sailor: str
    time_sailed_s: float | None
    distance_sailed_m: float | None
    avg_boat_speed_mpm: float | None
    avg_course_speed_mpm: float | None
    avg_heart_rate_bpm: float | None
    dnf: bool


# -------------------------------------------------
# Compute one sailor / one leg
# -------------------------------------------------

def _compute_leg(race_id: str, sailor: str, leg_id: int, leg_length_m: float) -> LegRow:

    path = TOTALRACES_DIR / f"{sailor}_{race_id}.csv"

    df = pd.read_csv(path)

    # --- FILTER LEG ---
    leg_df = df[df["geom_leg_id"] == leg_id]

    if leg_df.empty:
        return LegRow(
            sailor=sailor,
            time_sailed_s=None,
            distance_sailed_m=None,
            avg_boat_speed_mpm=None,
            avg_course_speed_mpm=None,
            avg_heart_rate_bpm=None,
            dnf=True,
        )

    # --- TIME ---
    t0 = leg_df.iloc[0]["elapsed_race_time_s"]
    t1 = leg_df.iloc[-1]["elapsed_race_time_s"]
    time_s = float(t1 - t0)

    # --- DISTANCE ---
    d0 = leg_df.iloc[0]["dist_from_start_m"]
    d1 = leg_df.iloc[-1]["dist_from_start_m"]
    dist_m = float(d1 - d0)

    minutes = time_s / 60 if time_s else 0

    # --- SPEEDS ---
    boat_speed = dist_m / minutes if minutes else 0
    course_speed = leg_length_m / minutes if minutes else 0

    # --- HEART RATE ---
    avg_hr = None
    if "heart_rate" in leg_df.columns:
        hr_series = leg_df["heart_rate"].dropna()
        if not hr_series.empty:
            avg_hr = float(hr_series.mean())

    return LegRow(
        sailor=sailor,
        time_sailed_s=time_s,
        distance_sailed_m=dist_m,
        avg_boat_speed_mpm=boat_speed,
        avg_course_speed_mpm=course_speed,
        avg_heart_rate_bpm=avg_hr,
        dnf=False,
    )


# -------------------------------------------------
# API
# -------------------------------------------------

@router.get("/leg_analytics")
def leg_analytics(race_id: str, leg: int):

    leg_id = int(leg)

    leg_length_m = _load_leg_length_m(race_id, leg_id)

    sailors = sorted({
        p.name.split("_")[0]
        for p in TOTALRACES_DIR.glob(f"*_{race_id}.csv")
    })

    if not sailors:
        raise HTTPException(404, "No sailors found")

    rows = []

    for sailor in sailors:
        rows.append(_compute_leg(race_id, sailor, leg_id, leg_length_m))

    finishers = [r for r in rows if not r.dnf]
    dnfs = [r for r in rows if r.dnf]

    finishers.sort(key=lambda r: r.time_sailed_s)

    results = finishers + dnfs

    out = []

    winner = finishers[0] if finishers else None

    for rank, r in enumerate(results, start=1):

        if r.dnf:
            out.append({
                "rank": rank,
                "sailor": r.sailor,
                "length_of_leg_m": int(round(leg_length_m)),
                "time_sailed": "DNF",
                "distance_sailed_m": "—",
                "avg_heart_rate_bpm": "—",
                "avg_boat_speed_mpm": "—",
                "avg_course_speed_mpm": "—",
            })
            continue

        if rank == 1:
            time_disp = _fmt_mmss(r.time_sailed_s)
            dist_disp = int(round(r.distance_sailed_m))
            hr_disp = int(round(r.avg_heart_rate_bpm)) if r.avg_heart_rate_bpm else "—"
            boat_disp = int(round(r.avg_boat_speed_mpm))
            course_disp = int(round(r.avg_course_speed_mpm))
        else:
            time_disp = _fmt_mmss_signed(r.time_sailed_s - winner.time_sailed_s)
            dist_disp = _fmt_int_signed(r.distance_sailed_m - winner.distance_sailed_m)
            hr_disp = int(round(r.avg_heart_rate_bpm)) if r.avg_heart_rate_bpm else "—"
            boat_disp = _fmt_int_signed(r.avg_boat_speed_mpm - winner.avg_boat_speed_mpm)
            course_disp = _fmt_int_signed(r.avg_course_speed_mpm - winner.avg_course_speed_mpm)

        out.append({
            "rank": rank,
            "sailor": r.sailor,
            "length_of_leg_m": int(round(leg_length_m)),
            "time_sailed": time_disp,
            "distance_sailed_m": dist_disp,
            "avg_heart_rate_bpm": hr_disp,
            "avg_boat_speed_mpm": boat_disp,
            "avg_course_speed_mpm": course_disp,
        })

    return {"rows": out}