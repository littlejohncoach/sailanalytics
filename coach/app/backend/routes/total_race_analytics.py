from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

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
    return f"+{val}" if val > 0 else str(val)


# -------------------------------------------------
# Geometry
# -------------------------------------------------

def _geometry_path(race_id: str) -> Path:
    return GEOMETRY_DIR / f"geometry_{race_id}.csv"


def _load_course_length_m(race_id: str) -> float:
    gdf = pd.read_csv(_geometry_path(race_id))
    if "cumulative_length_m" in gdf.columns:
        return float(gdf["cumulative_length_m"].max())
    return float(gdf["seg_length_m"].sum())


# -------------------------------------------------
# Core analytics engine (SAME FOR TOTAL + LEG)
# -------------------------------------------------

def _compute_from_df(df: pd.DataFrame, ref_length_m: float):

    if df.empty:
        return None

    # TIME (robust)
    t0 = df["elapsed_race_time_s"].min()
    t1 = df["elapsed_race_time_s"].max()
    time_s = float(t1 - t0)

    # DISTANCE (robust)
    d0 = df["dist_from_start_m"].min()
    d1 = df["dist_from_start_m"].max()
    dist_m = float(d1 - d0)

    minutes = time_s / 60 if time_s else 0

    boat = dist_m / minutes if minutes else 0
    course = ref_length_m / minutes if minutes else 0

    # HEART RATE
    avg_hr = None
    if "heart_rate" in df.columns:
        hr = df["heart_rate"].dropna()
        if not hr.empty:
            avg_hr = float(hr.mean())

    return time_s, dist_m, boat, course, avg_hr


# -------------------------------------------------
# Shared loader
# -------------------------------------------------

def _list_sailors(race_id: str) -> List[str]:
    pattern = f"_{race_id}.csv"
    return sorted(set(p.name[:-len(pattern)] for p in TOTALRACES_DIR.glob(f"*{pattern}")))


# -------------------------------------------------
# TOTAL RACE API (UNCHANGED LOGIC)
# -------------------------------------------------

@router.get("/races/{race_id}/total_race_analytics")
def total_race_analytics(race_id: str):

    course_length_m = _load_course_length_m(race_id)
    sailors = _list_sailors(race_id)

    if not sailors:
        raise HTTPException(404, "No sailors found")

    rows = []

    for sailor in sailors:
        df = pd.read_csv(TOTALRACES_DIR / f"{sailor}_{race_id}.csv")

        # FULL DF
        result = _compute_from_df(df, course_length_m)

        if not result:
            continue

        time_s, dist_m, boat, course, hr = result

        rows.append(dict(
            sailor=sailor,
            time_s=time_s,
            dist_m=dist_m,
            boat=boat,
            course=course,
            hr=hr,
        ))

    rows.sort(key=lambda x: x["time_s"])
    winner = rows[0]

    out = []

    for i, r in enumerate(rows, 1):

        if i == 1:
            time_disp = _fmt_mmss(r["time_s"])
            dist_disp = int(round(r["dist_m"]))
            boat_disp = int(round(r["boat"]))
            course_disp = int(round(r["course"]))
        else:
            time_disp = _fmt_mmss_signed(r["time_s"] - winner["time_s"])
            dist_disp = _fmt_int_signed(r["dist_m"] - winner["dist_m"])
            boat_disp = _fmt_int_signed(r["boat"] - winner["boat"])
            course_disp = _fmt_int_signed(r["course"] - winner["course"])

        out.append({
            "rank": i,
            "sailor": r["sailor"],
            "length_of_course_m": int(round(course_length_m)),
            "time_sailed": time_disp,
            "distance_sailed_m": dist_disp,
            "avg_heart_rate_bpm": int(round(r["hr"])) if r["hr"] else "—",
            "avg_boat_speed_mpm": boat_disp,
            "avg_course_speed_mpm": course_disp,
        })

    return out


# -------------------------------------------------
# LEG API (NEW — SAME ENGINE)
# -------------------------------------------------

@router.get("/leg_analytics")
def leg_analytics(
    race_id: str = Query(...),
    leg: int = Query(...)
):

    sailors = _list_sailors(race_id)

    if not sailors:
        raise HTTPException(404, "No sailors found")

    rows = []

    for sailor in sailors:
        df = pd.read_csv(TOTALRACES_DIR / f"{sailor}_{race_id}.csv")

        # SLICE
        leg_df = df[df["geom_leg_id"] == leg]

        if leg_df.empty:
            continue

        # LEG LENGTH
        d0 = leg_df["dist_from_start_m"].min()
        d1 = leg_df["dist_from_start_m"].max()
        leg_len = float(d1 - d0)

        result = _compute_from_df(leg_df, leg_len)

        if not result:
            continue

        time_s, dist_m, boat, course, hr = result

        rows.append(dict(
            sailor=sailor,
            time_s=time_s,
            dist_m=dist_m,
            boat=boat,
            course=course,
            hr=hr,
            length=leg_len
        ))

    rows.sort(key=lambda x: x["time_s"])
    winner = rows[0]

    out = []

    for i, r in enumerate(rows, 1):

        if i == 1:
            time_disp = _fmt_mmss(r["time_s"])
            dist_disp = int(round(r["dist_m"]))
            boat_disp = int(round(r["boat"]))
            course_disp = int(round(r["course"]))
        else:
            time_disp = _fmt_mmss_signed(r["time_s"] - winner["time_s"])
            dist_disp = _fmt_int_signed(r["dist_m"] - winner["dist_m"])
            boat_disp = _fmt_int_signed(r["boat"] - winner["boat"])
            course_disp = _fmt_int_signed(r["course"] - winner["course"])

        out.append({
            "rank": i,
            "sailor": r["sailor"],
            "length_of_leg_m": int(round(r["length"])),
            "time_sailed": time_disp,
            "distance_sailed_m": dist_disp,
            "avg_heart_rate_bpm": int(round(r["hr"])) if r["hr"] else "—",
            "avg_boat_speed_mpm": boat_disp,
            "avg_course_speed_mpm": course_disp,
        })

    return {"rows": out}