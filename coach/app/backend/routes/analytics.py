from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

ROOT = Path(__file__).resolve().parents[4]
TOTALRACES_DIR = ROOT / "data" / "totalraces"


# -------------------------------------------------
# FORMATTERS
# -------------------------------------------------

def fmt_mmss(seconds: float) -> str:
    sec = int(round(seconds))
    m = sec // 60
    s = sec % 60
    return f"{m}:{s:02d}"


def fmt_delta(seconds: float) -> str:
    sec = int(round(seconds))
    sign = "+" if sec >= 0 else "-"
    sec = abs(sec)
    m = sec // 60
    s = sec % 60
    return f"{sign}{m}:{s:02d}"


def fmt_signed(value: float) -> str:
    v = int(round(value))
    if v > 0:
        return f"+{v}"
    if v < 0:
        return f"{v}"
    return "0"


def fmt_abs(value: Optional[float]):
    if value is None:
        return None
    return str(int(round(value)))


# -------------------------------------------------
# CORE METRICS
# -------------------------------------------------

def compute_metrics(df: pd.DataFrame, leg: Optional[int]):

    # -----------------------------
    # SLICE LEG
    # -----------------------------

    if leg is not None:
        df = df[df["geom_leg_id"] == leg]

    if df.empty:
        return None

    # -----------------------------
    # TIME
    # -----------------------------

    if leg is None:
        # total race uses finish_time_utc
        t0 = df["timestamp_utc"].iloc[0]
        t1 = pd.to_datetime(df["finish_time_utc"].iloc[0])
    else:
        # leg uses geom_leg_id boundaries
        t0 = df.iloc[0]["timestamp_utc"]
        t1 = df.iloc[-1]["timestamp_utc"]

    time_s = (t1 - t0).total_seconds()

    # -----------------------------
    # DISTANCE SAILED (TRACK LENGTH)
    # -----------------------------

    dist = (
        df["dist_from_start_m"].iloc[-1]
        - df["dist_from_start_m"].iloc[0]
    )

    # -----------------------------
    # HEART RATE (ABSOLUTE)
    # -----------------------------

    hr = df["heart_rate"].mean()

    # -----------------------------
    # AVERAGE BOAT SPEED
    # -----------------------------

    boat = dist / (time_s / 60)

    # -----------------------------
    # COURSE PROGRESS (PTM)
    # -----------------------------

    course_progress = (
        df["dist_to_target_m"].iloc[0]
        - df["dist_to_target_m"].iloc[-1]
    )

    course_speed = course_progress / (time_s / 60)

    # -----------------------------
    # LEG LENGTH (DISPLAY ONLY)
    # -----------------------------

    leg_len = course_progress if leg is not None else None

    return {
        "time_s": time_s,
        "distance": dist,
        "hr": hr,
        "boat": boat,
        "course": course_speed,
        "leg_len": leg_len
    }


# -------------------------------------------------
# UNIFIED ANALYTICS
# -------------------------------------------------

@router.get("/races/{race_id}/analytics")
def analytics(
    race_id: str,
    leg: str | None = Query(default=None)
):

    files = list(TOTALRACES_DIR.glob(f"*_{race_id}.csv"))

    if not files:
        raise HTTPException(404, "No sailors found")

    # -----------------------------
    # LEG MODE
    # -----------------------------

    leg_id = None
    if leg and leg.lower() != "total race":
        leg_id = int(leg)

    rows = []

    for f in files:

        sailor = f.name.split("_")[0]

        df = pd.read_csv(f)

        df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"])
        df["geom_leg_id"] = pd.to_numeric(df["geom_leg_id"], errors="coerce")

        m = compute_metrics(df, leg_id)

        if m is None:
            continue

        rows.append({
            "sailor": sailor,
            **m
        })

    # -----------------------------
    # SORT (WINNER FIRST)
    # -----------------------------

    rows = sorted(rows, key=lambda r: r["time_s"])

    winner = rows[0]

    out = []

    # -----------------------------
    # BUILD OUTPUT
    # -----------------------------

    for i, r in enumerate(rows, start=1):

        if i == 1:
            time_disp = fmt_mmss(r["time_s"])
            dist_disp = fmt_abs(r["distance"])
            boat_disp = fmt_abs(r["boat"])
            course_disp = fmt_abs(r["course"])
        else:
            time_disp = fmt_delta(r["time_s"] - winner["time_s"])
            dist_disp = fmt_signed(r["distance"] - winner["distance"])
            boat_disp = fmt_signed(r["boat"] - winner["boat"])
            course_disp = fmt_signed(r["course"] - winner["course"])

        out.append({
            "rank": i,
            "sailor": r["sailor"],
            "time_sailed": time_disp,
            "length_leg_m": fmt_abs(r["leg_len"]),
            "distance_sailed_m": dist_disp,
            "avg_hr_bpm": fmt_abs(r["hr"]),
            "avg_boat_speed_mpm": boat_disp,
            "avg_course_speed_mpm": course_disp,
        })

    return out


# -------------------------------------------------
# BACKWARD COMPATIBILITY
# -------------------------------------------------

@router.get("/races/{race_id}/total_race_analytics")
def total_race_analytics(
    race_id: str,
    leg: str | None = Query(default=None)
):
    return analytics(race_id, leg)


@router.get("/leg_analytics")
def leg_analytics(
    race_id: str = Query(...),
    leg: str = Query(...)
):
    rows = analytics(race_id, leg)
    return {"rows": rows}