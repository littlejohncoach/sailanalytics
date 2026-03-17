from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

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
# Geometry
# -------------------------------------------------

def _geometry_path(race_id: str) -> Path:
    return GEOMETRY_DIR / f"geometry_{race_id}.csv"


def _load_course_length_m(race_id: str) -> float:

    gpath = _geometry_path(race_id)

    if not gpath.exists():
        raise FileNotFoundError(f"Missing geometry file {gpath}")

    gdf = pd.read_csv(gpath)

    if "cumulative_length_m" in gdf.columns:
        return float(gdf["cumulative_length_m"].max())

    if "seg_length_m" in gdf.columns:
        return float(gdf["seg_length_m"].sum())

    raise ValueError("Geometry file missing length columns")


# -------------------------------------------------
# TotalRace loading
# -------------------------------------------------

def _totalrace_path(sailor: str, race_id: str) -> Path:
    return TOTALRACES_DIR / f"{sailor}_{race_id}.csv"


def _list_sailors_for_race(race_id: str) -> List[str]:

    sailors = []

    pattern = f"_{race_id}.csv"

    for p in TOTALRACES_DIR.glob(f"*{pattern}"):
        sailor = p.name[: -len(pattern)]
        sailors.append(sailor)

    return sorted(set(sailors))


def _load_finish_snapshot(path: Path):

    df = pd.read_csv(path)

    if "finished_flag" not in df.columns:
        raise ValueError(f"{path.name} missing finished_flag")

    finished = df[df["finished_flag"] == 1]

    if finished.empty:
        return None

    row = finished.iloc[-1]

    time_sailed = float(row["elapsed_race_time_s"])
    distance_sailed = float(row["dist_from_start_m"])

    return time_sailed, distance_sailed


# -------------------------------------------------
# Data structure
# -------------------------------------------------

@dataclass
class TotalRaceRow:

    sailor: str
    time_sailed_s: float | None
    distance_sailed_m: float | None
    avg_boat_speed_mpm: float | None
    avg_course_speed_mpm: float | None
    efficiency_pct: float | None
    dnf: bool


# -------------------------------------------------
# Compute one sailor
# -------------------------------------------------

def _compute_one(race_id: str, sailor: str, course_length_m: float) -> TotalRaceRow:

    path = _totalrace_path(sailor, race_id)

    snapshot = _load_finish_snapshot(path)

    if snapshot is None:

        return TotalRaceRow(
            sailor=sailor,
            time_sailed_s=None,
            distance_sailed_m=None,
            avg_boat_speed_mpm=None,
            avg_course_speed_mpm=None,
            efficiency_pct=None,
            dnf=True,
        )

    time_s, dist_m = snapshot

    minutes = time_s / 60

    boat_speed = dist_m / minutes if minutes else 0
    course_speed = course_length_m / minutes if minutes else 0

    efficiency = (course_length_m / dist_m * 100) if dist_m else 0

    return TotalRaceRow(
        sailor=sailor,
        time_sailed_s=time_s,
        distance_sailed_m=dist_m,
        avg_boat_speed_mpm=boat_speed,
        avg_course_speed_mpm=course_speed,
        efficiency_pct=efficiency,
        dnf=False,
    )


# -------------------------------------------------
# API
# -------------------------------------------------

@router.get("/races/{race_id}/total_race_analytics")

def total_race_analytics(race_id: str):

    course_length_m = _load_course_length_m(race_id)

    sailors = _list_sailors_for_race(race_id)

    if not sailors:
        raise HTTPException(404, "No sailors found")

    rows = []

    for sailor in sailors:
        rows.append(_compute_one(race_id, sailor, course_length_m))

    # split finishers / DNF
    finishers = [r for r in rows if not r.dnf]
    dnfs = [r for r in rows if r.dnf]

    finishers.sort(key=lambda r: r.time_sailed_s)

    results = finishers + dnfs

    out = []

    winner = finishers[0] if finishers else None

    for rank, r in enumerate(results, start=1):

        if r.dnf:

            out.append(
                {
                    "rank": rank,
                    "sailor": r.sailor,
                    "length_of_course_m": int(round(course_length_m)),
                    "time_sailed": "DNF",
                    "time_sailed_s": None,
                    "distance_sailed_m": "—",
                    "avg_boat_speed_mpm": "—",
                    "avg_course_speed_mpm": "—",
                    "efficiency_pct": "—",
                }
            )

            continue

        if rank == 1:

            time_disp = _fmt_mmss(r.time_sailed_s)
            dist_disp = int(round(r.distance_sailed_m))
            boat_disp = int(round(r.avg_boat_speed_mpm))
            course_disp = int(round(r.avg_course_speed_mpm))

        else:

            time_disp = _fmt_mmss_signed(r.time_sailed_s - winner.time_sailed_s)
            dist_disp = _fmt_int_signed(r.distance_sailed_m - winner.distance_sailed_m)
            boat_disp = _fmt_int_signed(r.avg_boat_speed_mpm - winner.avg_boat_speed_mpm)
            course_disp = _fmt_int_signed(r.avg_course_speed_mpm - winner.avg_course_speed_mpm)

        out.append(
            {
                "rank": rank,
                "sailor": r.sailor,
                "length_of_course_m": int(round(course_length_m)),
                "time_sailed": time_disp,
                "time_sailed_s": int(round(r.time_sailed_s)),
                "distance_sailed_m": dist_disp,
                "avg_boat_speed_mpm": boat_disp,
                "avg_course_speed_mpm": course_disp,
                "efficiency_pct": round(r.efficiency_pct, 1),
            }
        )

    return out