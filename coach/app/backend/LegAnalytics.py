# coach/app/backend/LegAnalytics.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict, Any

import pandas as pd


# -----------------------------
# Sovereign contracts
# -----------------------------
# Source of truth for leg analytics (samples, legs, finish boundary):
#   data/totalraces/<sailor>_<race_id>.csv
LEG_ID_COL = "geom_leg_id"
TS_COL = "timestamp_utc"
DIST_COL = "dist_from_start_m"

# Finish boundary (still from totalraces only)
FINISHED_FLAG_COL = "finished_flag"
FINISH_TIME_COL = "finish_time_utc"

# Geometry (course leg length truth)
GEOM_LEG_ID_COL = "leg_id"
GEOM_LEG_LEN_COL = "leg_length_m"

HR_COL_CANDIDATES = ["heart_rate", "hr", "HR_raw_bpm", "HR"]


@dataclass(frozen=True)
class LegRow:
    rank: int
    sailor: str
    length_leg_m: Optional[float]
    time_sailed_str: str
    distance_sailed_m: Optional[float]
    avg_hr_bpm: Optional[float]
    avg_boat_speed_mpm: Optional[float]
    avg_course_speed_mpm: Optional[float]
    efficiency_pct: Optional[float]


def _format_time_mmss(total_seconds: float) -> str:
    if total_seconds is None or pd.isna(total_seconds):
        return "—"
    s = int(round(max(0.0, float(total_seconds))))
    m = s // 60
    ss = s % 60
    return f"{m}:{ss:02d}"


def _first_existing_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    cols = set(df.columns)
    for c in candidates:
        if c in cols:
            return c
    return None


def _find_totalrace_csv(project_root: Path, sailor: str, race_id: str) -> Optional[Path]:
    d = project_root / "data" / "totalraces"
    matches = sorted(d.glob(f"{sailor}_{race_id}*.csv"))
    return matches[0] if matches else None


def _load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def _load_leg_length_m(project_root: Path, race_id: str, geom_leg_id: int) -> Optional[float]:
    """
    geometry_<race_id>.csv provides leg_length_m directly.
    """
    gpath = project_root / "data" / "geometry" / f"geometry_{race_id}.csv"
    if not gpath.exists():
        return None

    try:
        g = pd.read_csv(gpath)
    except Exception:
        return None

    if GEOM_LEG_ID_COL not in g.columns or GEOM_LEG_LEN_COL not in g.columns:
        return None

    leg_ids = pd.to_numeric(g[GEOM_LEG_ID_COL], errors="coerce")
    gg = g[leg_ids == int(geom_leg_id)]
    if gg.empty:
        return None

    v = pd.to_numeric(gg[GEOM_LEG_LEN_COL].iloc[0], errors="coerce")
    return None if pd.isna(v) else float(v)


def _finish_time_from_totalraces(df: pd.DataFrame) -> Optional[pd.Timestamp]:
    """
    Finish boundary derived ONLY from totalraces.

    Order:
      1) if finished_flag==1 rows exist and finish_time_utc parses -> max(finish_time_utc)
      2) else if finished_flag==1 rows exist -> max(timestamp_utc) within finished rows
      3) else -> max(timestamp_utc) overall
    """
    if TS_COL not in df.columns:
        return None

    ts_all = pd.to_datetime(df[TS_COL].astype(str), utc=True, errors="coerce")
    if ts_all.isna().all():
        return None

    if FINISHED_FLAG_COL in df.columns:
        f = pd.to_numeric(df[FINISHED_FLAG_COL], errors="coerce").fillna(0).astype(int)
        finished = df[f == 1].copy()

        if not finished.empty:
            if FINISH_TIME_COL in finished.columns:
                ft = pd.to_datetime(
                    finished[FINISH_TIME_COL].astype(str), utc=True, errors="coerce"
                ).max()
                if pd.notna(ft):
                    return ft

            ts_fin = pd.to_datetime(
                finished[TS_COL].astype(str), utc=True, errors="coerce"
            ).max()
            if pd.notna(ts_fin):
                return ts_fin

    return ts_all.max()


def _select_last_contiguous_instance_up_to_finish(
    df: pd.DataFrame,
    geom_leg_id: int,
    finish_time_utc: Optional[pd.Timestamp],
) -> pd.DataFrame:
    """
    Deterministic leg selection:
      - Sort by timestamp_utc
      - Clip to <= finish_time_utc (if available)
      - Build leg_instance_id by transitions of geom_leg_id
      - Select LAST instance where geom_leg_id == X
    """
    if LEG_ID_COL not in df.columns or TS_COL not in df.columns:
        return df.iloc[0:0].copy()

    work = df[[TS_COL, LEG_ID_COL, DIST_COL] + [c for c in HR_COL_CANDIDATES if c in df.columns]].copy()

    # Parse safely (do NOT drop everything unless truly unparseable)
    work["_ts"] = pd.to_datetime(work[TS_COL].astype(str), utc=True, errors="coerce")
    work["_leg"] = pd.to_numeric(work[LEG_ID_COL], errors="coerce")

    work = work.dropna(subset=["_ts", "_leg"]).sort_values("_ts")
    if work.empty:
        return work

    if finish_time_utc is not None:
        work = work[work["_ts"] <= finish_time_utc].copy()
        if work.empty:
            return work

    trans = work["_leg"].ne(work["_leg"].shift(1)).astype(int)
    work["_leg_instance_id"] = trans.cumsum()

    target = work[work["_leg"] == int(geom_leg_id)].copy()
    if target.empty:
        return target

    ends = target.groupby("_leg_instance_id")["_ts"].max()
    chosen = int(ends.idxmax())

    return target[target["_leg_instance_id"] == chosen].copy()


def compute_leg_analytics(
    project_root: Path,
    race_id: str,
    leg_value: str,
    sailors: List[str],
) -> List[LegRow]:
    """
    Sovereign leg analytics:
      - ONLY reads data/totalraces/ for slicing + finish boundary + time/distance
      - Uses geometry for leg_length_m (leg_length_m column)
    """
    try:
        geom_leg_id = int((leg_value or "").strip())
    except Exception:
        return []

    length_leg_m = _load_leg_length_m(project_root, race_id, geom_leg_id)

    rows: List[Dict[str, Any]] = []

    for sailor_raw in sailors:
        sailor = (sailor_raw or "").strip()
        if not sailor:
            continue

        src = _find_totalrace_csv(project_root, sailor, race_id)
        if src is None:
            continue

        df = _load_csv(src)

        # Hard requirements (totalraces truth)
        if LEG_ID_COL not in df.columns or TS_COL not in df.columns or DIST_COL not in df.columns:
            continue

        finish_time_utc = _finish_time_from_totalraces(df)

        df_leg = _select_last_contiguous_instance_up_to_finish(df, geom_leg_id, finish_time_utc)
        if df_leg.empty:
            continue

        ts = pd.to_datetime(df_leg[TS_COL].astype(str), utc=True, errors="coerce").dropna()
        if ts.empty:
            continue

        time_sailed_s = float((ts.iloc[-1] - ts.iloc[0]).total_seconds())

        d = pd.to_numeric(df_leg[DIST_COL], errors="coerce").dropna()
        if d.empty:
            continue

        dist_sailed_m = float(d.iloc[-1] - d.iloc[0])

        avg_hr = None
        hr_col = _first_existing_col(df_leg, HR_COL_CANDIDATES)
        if hr_col:
            hr = pd.to_numeric(df_leg[hr_col], errors="coerce").dropna()
            if not hr.empty:
                avg_hr = float(hr.mean())

        avg_boat_speed_mpm = None
        if time_sailed_s > 0:
            avg_boat_speed_mpm = (dist_sailed_m / time_sailed_s) * 60.0

        avg_course_speed_mpm = None
        if length_leg_m is not None and time_sailed_s > 0:
            avg_course_speed_mpm = (float(length_leg_m) / time_sailed_s) * 60.0

        efficiency_pct = None
        if (
            avg_course_speed_mpm is not None
            and avg_boat_speed_mpm is not None
            and avg_boat_speed_mpm != 0
        ):
            efficiency_pct = (avg_course_speed_mpm / avg_boat_speed_mpm) * 100.0

        rows.append(
            dict(
                sailor=sailor,
                time_sailed_s=time_sailed_s,
                length_leg_m=length_leg_m,
                time_sailed_str=_format_time_mmss(time_sailed_s),
                distance_sailed_m=dist_sailed_m,
                avg_hr_bpm=avg_hr,
                avg_boat_speed_mpm=avg_boat_speed_mpm,
                avg_course_speed_mpm=avg_course_speed_mpm,
                efficiency_pct=efficiency_pct,
            )
        )

    if not rows:
        return []

    rows.sort(key=lambda r: (r["time_sailed_s"], r["sailor"]))

    out: List[LegRow] = []
    for i, r in enumerate(rows, start=1):
        out.append(
            LegRow(
                rank=i,
                sailor=r["sailor"],
                length_leg_m=r["length_leg_m"],
                time_sailed_str=r["time_sailed_str"],
                distance_sailed_m=r["distance_sailed_m"],
                avg_hr_bpm=r["avg_hr_bpm"],
                avg_boat_speed_mpm=r["avg_boat_speed_mpm"],
                avg_course_speed_mpm=r["avg_course_speed_mpm"],
                efficiency_pct=r["efficiency_pct"],
            )
        )

    return out
