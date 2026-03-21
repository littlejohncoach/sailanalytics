# coach/app/backend/routes/analytics.py

from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

ROOT = Path(__file__).resolve().parents[4]
TOTALRACES_DIR = ROOT / "data" / "totalraces"


# -------------------------------------------------
# HELPERS
# -------------------------------------------------

def fmt_mmss(seconds: float) -> str:
    sec = int(round(float(seconds)))
    m = sec // 60
    s = sec % 60
    return f"{m}:{s:02d}"


def fmt_delta(seconds: float) -> str:
    sec = int(round(float(seconds)))
    sign = "+" if sec >= 0 else "-"
    sec = abs(sec)
    m = sec // 60
    s = sec % 60
    return f"{sign}{m}:{s:02d}"


def fmt_signed_int(value: float) -> str:
    v = int(round(float(value)))
    if v > 0:
        return f"+{v}"
    if v < 0:
        return f"{v}"
    return "0"


def fmt_abs_int(value: float | None) -> Optional[str]:
    if value is None or pd.isna(value):
        return None
    return str(int(round(float(value))))


def list_sailor_files(race_id: str) -> list[Path]:
    return sorted(TOTALRACES_DIR.glob(f"*_{race_id}.csv"))


def read_totalrace_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)

    required = {
        "timestamp_utc",
        "dist_from_start_m",
        "heart_rate",
    }
    missing = required - set(df.columns)
    if missing:
        raise HTTPException(
            status_code=500,
            detail=f"{path.name} missing required columns: {sorted(missing)}",
        )

    df = df.copy()
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], errors="coerce", utc=True)
    df["dist_from_start_m"] = pd.to_numeric(df["dist_from_start_m"], errors="coerce")
    df["heart_rate"] = pd.to_numeric(df["heart_rate"], errors="coerce")

    if "geom_leg_id" in df.columns:
        df["geom_leg_id"] = pd.to_numeric(df["geom_leg_id"], errors="coerce")
    else:
        df["geom_leg_id"] = pd.NA

    if "finished_flag" in df.columns:
        df["finished_flag"] = pd.to_numeric(df["finished_flag"], errors="coerce")
    else:
        df["finished_flag"] = 0

    df = df.dropna(subset=["timestamp_utc", "dist_from_start_m"]).sort_values("timestamp_utc")
    return df


def slice_df_for_leg(df: pd.DataFrame, leg_id: Optional[int]) -> pd.DataFrame:
    if leg_id is None:
        return df.copy()
    return df[df["geom_leg_id"] == leg_id].copy()


def compute_course_length_total(df: pd.DataFrame) -> float | None:
    leg_lengths = []
    grouped = df.dropna(subset=["geom_leg_id"]).groupby("geom_leg_id", sort=True)

    for _, leg_df in grouped:
        if leg_df.empty:
            continue
        leg_len = float(leg_df["dist_from_start_m"].max() - leg_df["dist_from_start_m"].min())
        if leg_len >= 0:
            leg_lengths.append(leg_len)

    if not leg_lengths:
        return None

    return float(sum(leg_lengths))


def compute_leg_length(leg_df: pd.DataFrame) -> float | None:
    if leg_df.empty:
        return None
    return float(leg_df["dist_from_start_m"].max() - leg_df["dist_from_start_m"].min())


def compute_metrics_for_slice(
    full_df: pd.DataFrame,
    sliced_df: pd.DataFrame,
    is_total: bool,
) -> dict:
    if sliced_df.empty:
        return {
            "finished": False,
            "time_s": None,
            "distance_sailed_m_raw": None,
            "avg_hr_bpm_raw": None,
            "avg_boat_speed_mpm_raw": None,
            "avg_course_speed_mpm_raw": None,
            "length_leg_m": None,
        }

    t0 = sliced_df["timestamp_utc"].iloc[0]
    t1 = sliced_df["timestamp_utc"].iloc[-1]
    time_s = float((t1 - t0).total_seconds())

    if time_s <= 0:
        return {
            "finished": False,
            "time_s": None,
            "distance_sailed_m_raw": None,
            "avg_hr_bpm_raw": None,
            "avg_boat_speed_mpm_raw": None,
            "avg_course_speed_mpm_raw": None,
            "length_leg_m": None,
        }

    distance_sailed_m = float(
        sliced_df["dist_from_start_m"].iloc[-1] - sliced_df["dist_from_start_m"].iloc[0]
    )

    avg_hr_bpm = None
    hr_series = sliced_df["heart_rate"].dropna()
    if not hr_series.empty:
        avg_hr_bpm = float(hr_series.mean())

    avg_boat_speed_mpm = distance_sailed_m / (time_s / 60.0)

    if is_total:
        course_length_m = compute_course_length_total(full_df)
        length_leg_m = None
    else:
        course_length_m = compute_leg_length(sliced_df)
        length_leg_m = course_length_m

    avg_course_speed_mpm = None
    if course_length_m is not None:
        avg_course_speed_mpm = float(course_length_m / (time_s / 60.0))

    finished = True
    if is_total and "finished_flag" in full_df.columns:
        finished = bool(pd.to_numeric(full_df["finished_flag"], errors="coerce").fillna(0).max() == 1)

    return {
        "finished": finished,
        "time_s": time_s,
        "distance_sailed_m_raw": distance_sailed_m,
        "avg_hr_bpm_raw": avg_hr_bpm,
        "avg_boat_speed_mpm_raw": avg_boat_speed_mpm,
        "avg_course_speed_mpm_raw": avg_course_speed_mpm,
        "length_leg_m": length_leg_m,
    }


def build_ranked_rows(race_id: str, leg: Optional[str]) -> tuple[list[dict], bool]:
    files = list_sailor_files(race_id)
    if not files:
        raise HTTPException(status_code=404, detail=f"No sailors found for race {race_id}")

    is_total = (
        leg is None
        or str(leg).strip() == ""
        or str(leg).strip().lower() == "total race"
    )

    leg_id = None
    if not is_total:
        try:
            leg_id = int(str(leg).strip())
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid leg: {leg}")

    rows = []

    for path in files:
        sailor = path.name.split("_")[0]
        df = read_totalrace_csv(path)
        sliced_df = slice_df_for_leg(df, leg_id)

        metrics = compute_metrics_for_slice(
            full_df=df,
            sliced_df=sliced_df,
            is_total=is_total,
        )

        rows.append({
            "sailor": sailor,
            **metrics,
        })

    finishers = [r for r in rows if r["finished"] and r["time_s"] is not None]
    dnfs = [r for r in rows if not (r["finished"] and r["time_s"] is not None)]

    finishers.sort(key=lambda r: r["time_s"])

    if not finishers:
        out = []
        for r in dnfs:
            out.append({
                "rank": None,
                "sailor": r["sailor"],
                "time_sailed": "DNF",
                "length_leg_m": None,
                "distance_sailed_m": None,
                "avg_hr_bpm": None,
                "avg_boat_speed_mpm": None,
                "avg_course_speed_mpm": None,
            })
        return out, is_total

    leader = finishers[0]

    out = []
    for i, r in enumerate(finishers, start=1):
        if i == 1:
            time_disp = fmt_mmss(r["time_s"])
            distance_disp = fmt_abs_int(r["distance_sailed_m_raw"])
            boat_disp = fmt_abs_int(r["avg_boat_speed_mpm_raw"])
            course_disp = fmt_abs_int(r["avg_course_speed_mpm_raw"])
        else:
            time_disp = fmt_delta(r["time_s"] - leader["time_s"])
            distance_disp = fmt_signed_int(r["distance_sailed_m_raw"] - leader["distance_sailed_m_raw"])
            boat_disp = fmt_signed_int(r["avg_boat_speed_mpm_raw"] - leader["avg_boat_speed_mpm_raw"])
            course_disp = fmt_signed_int(r["avg_course_speed_mpm_raw"] - leader["avg_course_speed_mpm_raw"])

        out.append({
            "rank": i,
            "sailor": r["sailor"],
            "time_sailed": time_disp,
            "length_leg_m": fmt_abs_int(r["length_leg_m"]),
            "distance_sailed_m": distance_disp,
            "avg_hr_bpm": fmt_abs_int(r["avg_hr_bpm_raw"]),
            "avg_boat_speed_mpm": boat_disp,
            "avg_course_speed_mpm": course_disp,
        })

    for r in dnfs:
        out.append({
            "rank": None,
            "sailor": r["sailor"],
            "time_sailed": "DNF",
            "length_leg_m": None,
            "distance_sailed_m": None,
            "avg_hr_bpm": None,
            "avg_boat_speed_mpm": None,
            "avg_course_speed_mpm": None,
        })

    return out, is_total


# -------------------------------------------------
# UNIFIED ENDPOINT
# -------------------------------------------------

@router.get("/races/{race_id}/analytics")
def analytics(
    race_id: str,
    leg: str | None = Query(default=None),
):
    rows, is_total = build_ranked_rows(race_id=race_id, leg=leg)

    if is_total:
        return rows

    return {"rows": rows}


# -------------------------------------------------
# BACKWARD-COMPATIBLE ENDPOINTS
# -------------------------------------------------

@router.get("/races/{race_id}/total_race_analytics")
def total_race_analytics(
    race_id: str,
    leg: str | None = Query(default=None),
):
    rows, is_total = build_ranked_rows(race_id=race_id, leg=leg)

    if is_total:
        return rows

    return {"rows": rows}


@router.get("/leg_analytics")
def leg_analytics(
    race_id: str = Query(...),
    leg: str = Query(...),
):
    rows, _ = build_ranked_rows(race_id=race_id, leg=leg)
    return {"rows": rows}