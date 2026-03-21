from pathlib import Path
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

ROOT = Path(__file__).resolve().parents[4]
TOTALRACES_DIR = ROOT / "data" / "totalraces"


def fmt_mmss(seconds):
    sec = int(round(seconds))
    m = sec // 60
    s = sec % 60
    return f"{m}:{s:02d}"


def fmt_delta(seconds):
    sec = int(round(seconds))
    m = sec // 60
    s = sec % 60
    return f"+{m}:{s:02d}"


@router.get("/leg_analytics")
def leg_analytics(
    race_id: str = Query(...),
    leg: int = Query(...)
):

    files = list(TOTALRACES_DIR.glob(f"*_{race_id}.csv"))
    if not files:
        raise HTTPException(404, "No sailors found")

    rows = []

    for f in files:
        sailor = f.name.split("_")[0]
        df = pd.read_csv(f)

        df["geom_leg_id"] = pd.to_numeric(df["geom_leg_id"], errors="coerce")

        leg_df = df[df["geom_leg_id"] == leg]

        if leg_df.empty:
            rows.append({
                "sailor": sailor,
                "time_s": None,
                "finished": False
            })
            continue

        leg_df["timestamp_utc"] = pd.to_datetime(
            leg_df["timestamp_utc"], errors="coerce"
        )
        leg_df = leg_df.dropna(subset=["timestamp_utc"]).sort_values("timestamp_utc")

        if leg_df.empty:
            rows.append({
                "sailor": sailor,
                "time_s": None,
                "finished": False
            })
            continue

        t0 = leg_df.iloc[0]["timestamp_utc"]
        t1 = leg_df.iloc[-1]["timestamp_utc"]

        time_s = (t1 - t0).total_seconds()

        rows.append({
            "sailor": sailor,
            "time_s": time_s,
            "finished": True
        })

    finishers = [r for r in rows if r["finished"] and r["time_s"] is not None]
    dnfs = [r for r in rows if not r["finished"] or r["time_s"] is None]

    finishers.sort(key=lambda r: r["time_s"])

    out = []

    winner_time = finishers[0]["time_s"] if finishers else None

    for i, r in enumerate(finishers, start=1):
        if i == 1:
            time_disp = fmt_mmss(r["time_s"])
        else:
            time_disp = fmt_delta(r["time_s"] - winner_time)

        out.append({
            "rank": i,
            "sailor": r["sailor"],
            "time_sailed": time_disp,
        })

    for r in dnfs:
        out.append({
            "rank": None,
            "sailor": r["sailor"],
            "time_sailed": "DNF",
        })

    return {"rows": out}