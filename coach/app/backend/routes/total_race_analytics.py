from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional

import pandas as pd
from fastapi import APIRouter, Query, HTTPException

router = APIRouter(tags=["analytics"])


# -------------------------------------------------
# Paths
# -------------------------------------------------

SAILANALYTICS_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = SAILANALYTICS_ROOT / "data"
TOTALRACES_DIR = DATA_DIR / "totalraces"


# -------------------------------------------------
# Helpers
# -------------------------------------------------

def _list_sailors_for_race(race_id: str) -> List[str]:
    totalraces_dir = TOTALRACES_DIR
    if not totalraces_dir.exists():
        return []

    suffix = f"_{race_id}.csv"
    sailors: List[str] = []

    for p in totalraces_dir.glob(f"*{suffix}"):
        sailor = p.name[: -len(suffix)]
        if sailor:
            sailors.append(sailor)

    return sorted(set(sailors))


def _fmt_mmss(seconds: float) -> str:
    sec = int(round(seconds))
    m = sec // 60
    s = sec % 60
    return f"{m}:{s:02d}"


def _fmt_mmss_signed(delta_s: Optional[float]) -> str:
    if delta_s is None:
        return "—"
    if abs(delta_s) < 0.5:
        return "0:00"

    sign = "+" if delta_s > 0 else "-"
    sec = int(round(abs(delta_s)))
    m = sec // 60
    s = sec % 60
    return f"{sign}{m}:{s:02d}"


def _fmt_int_signed(delta: Optional[float]) -> str:
    if delta is None:
        return "—"
    val = int(round(float(delta)))
    if val > 0:
        return f"+{val}"
    return str(val)


# -------------------------------------------------
# Data structure
# -------------------------------------------------

@dataclass
class LegRow:
    sailor: str
    length_leg_m: float | None
    time_sailed_s: float | None
    distance_sailed_m: float | None
    avg_heart_rate_bpm: float | None
    avg_boat_speed_mpm: float | None
    avg_course_speed_mpm: float | None
    dnf: bool


# -------------------------------------------------
# Core compute
# -------------------------------------------------

def _compute_one_leg(race_id: str, sailor: str, leg_id: int) -> LegRow:
    path = TOTALRACES_DIR / f"{sailor}_{race_id}.csv"
    if not path.exists():
        return LegRow(
            sailor=sailor,
            length_leg_m=None,
            time_sailed_s=None,
            distance_sailed_m=None,
            avg_heart_rate_bpm=None,
            avg_boat_speed_mpm=None,
            avg_course_speed_mpm=None,
            dnf=True,
        )

    df = pd.read_csv(path)

    required = {"timestamp_utc", "dist_from_start_m", "geom_leg_id"}
    missing = required - set(df.columns)
    if missing:
        raise HTTPException(
            status_code=500,
            detail=f"{path.name} missing required columns: {sorted(missing)}",
        )

    leg_df = df[df["geom_leg_id"] == leg_id].copy()

    if leg_df.empty:
        return LegRow(
            sailor=sailor,
            length_leg_m=None,
            time_sailed_s=None,
            distance_sailed_m=None,
            avg_heart_rate_bpm=None,
            avg_boat_speed_mpm=None,
            avg_course_speed_mpm=None,
            dnf=True,
        )

    # deterministic ordering
    leg_df["timestamp_utc"] = pd.to_datetime(leg_df["timestamp_utc"], utc=True, errors="coerce")
    leg_df = leg_df.dropna(subset=["timestamp_utc"]).sort_values("timestamp_utc")

    if leg_df.empty:
        return LegRow(
            sailor=sailor,
            length_leg_m=None,
            time_sailed_s=None,
            distance_sailed_m=None,
            avg_heart_rate_bpm=None,
            avg_boat_speed_mpm=None,
            avg_course_speed_mpm=None,
            dnf=True,
        )

    # leg time = end timestamp - start timestamp
    t0 = leg_df["timestamp_utc"].iloc[0]
    t1 = leg_df["timestamp_utc"].iloc[-1]
    time_s = float((t1 - t0).total_seconds())

    # leg distance / length = end cumulative distance - start cumulative distance
    d0 = float(leg_df["dist_from_start_m"].iloc[0])
    d1 = float(leg_df["dist_from_start_m"].iloc[-1])
    leg_length_m = float(d1 - d0)
    distance_sailed_m = leg_length_m

    minutes = time_s / 60 if time_s > 0 else 0.0

    avg_boat_speed_mpm = distance_sailed_m / minutes if minutes > 0 else 0.0
    avg_course_speed_mpm = leg_length_m / minutes if minutes > 0 else 0.0

    avg_hr = None
    if "heart_rate" in leg_df.columns:
        hr_series = pd.to_numeric(leg_df["heart_rate"], errors="coerce").dropna()
        if not hr_series.empty:
            avg_hr = float(hr_series.mean())

    return LegRow(
        sailor=sailor,
        length_leg_m=leg_length_m,
        time_sailed_s=time_s,
        distance_sailed_m=distance_sailed_m,
        avg_heart_rate_bpm=avg_hr,
        avg_boat_speed_mpm=avg_boat_speed_mpm,
        avg_course_speed_mpm=avg_course_speed_mpm,
        dnf=False,
    )


# -------------------------------------------------
# API
# -------------------------------------------------

@router.get("/leg_analytics")
def leg_analytics(
    race_id: str = Query(..., description="e.g. 180326_R7_yellow"),
    leg: str = Query(..., description='geom_leg_id as "1".."6"'),
) -> Dict[str, Any]:
    lv = (leg or "").strip()
    try:
        leg_id = int(lv)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid leg='{leg}'. Must be integer geom_leg_id.")

    sailors = _list_sailors_for_race(race_id)
    if not sailors:
        raise HTTPException(
            status_code=404,
            detail=f"No sailors found in data/totalraces for race_id={race_id}",
        )

    rows: List[LegRow] = []
    for sailor in sailors:
        rows.append(_compute_one_leg(race_id, sailor, leg_id))

    finishers = [r for r in rows if not r.dnf]
    dnfs = [r for r in rows if r.dnf]

    finishers.sort(key=lambda r: r.time_sailed_s if r.time_sailed_s is not None else float("inf"))
    results = finishers + dnfs

    out_rows: List[Dict[str, Any]] = []

    winner = finishers[0] if finishers else None

    for rank, r in enumerate(results, start=1):
        if r.dnf:
            out_rows.append(
                {
                    "rank": rank,
                    "sailor": r.sailor,
                    "length_of_leg_m": "—",
                    "time_sailed": "DNF",
                    "distance_sailed_m": "—",
                    "avg_heart_rate_bpm": "—",
                    "avg_boat_speed_mpm": "—",
                    "avg_course_speed_mpm": "—",
                }
            )
            continue

        if rank == 1:
            time_disp = _fmt_mmss(r.time_sailed_s or 0)
            dist_disp = int(round(r.distance_sailed_m)) if r.distance_sailed_m is not None else "—"
            hr_disp = int(round(r.avg_heart_rate_bpm)) if r.avg_heart_rate_bpm is not None else "—"
            boat_disp = int(round(r.avg_boat_speed_mpm)) if r.avg_boat_speed_mpm is not None else "—"
            course_disp = int(round(r.avg_course_speed_mpm)) if r.avg_course_speed_mpm is not None else "—"
        else:
            time_disp = _fmt_mmss_signed(
                (r.time_sailed_s - winner.time_sailed_s)
                if (r.time_sailed_s is not None and winner and winner.time_sailed_s is not None)
                else None
            )
            dist_disp = _fmt_int_signed(
                (r.distance_sailed_m - winner.distance_sailed_m)
                if (r.distance_sailed_m is not None and winner and winner.distance_sailed_m is not None)
                else None
            )
            hr_disp = int(round(r.avg_heart_rate_bpm)) if r.avg_heart_rate_bpm is not None else "—"
            boat_disp = _fmt_int_signed(
                (r.avg_boat_speed_mpm - winner.avg_boat_speed_mpm)
                if (r.avg_boat_speed_mpm is not None and winner and winner.avg_boat_speed_mpm is not None)
                else None
            )
            course_disp = _fmt_int_signed(
                (r.avg_course_speed_mpm - winner.avg_course_speed_mpm)
                if (r.avg_course_speed_mpm is not None and winner and winner.avg_course_speed_mpm is not None)
                else None
            )

        out_rows.append(
            {
                "rank": rank,
                "sailor": r.sailor,
                "length_of_leg_m": int(round(r.length_leg_m)) if r.length_leg_m is not None else "—",
                "time_sailed": time_disp,
                "distance_sailed_m": dist_disp,
                "avg_heart_rate_bpm": hr_disp,
                "avg_boat_speed_mpm": boat_disp,
                "avg_course_speed_mpm": course_disp,
            }
        )

    return {
        "race_id": race_id,
        "leg": str(leg_id),
        "rows": out_rows,
    }