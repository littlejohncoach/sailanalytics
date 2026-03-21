from pathlib import Path
import pandas as pd
from fastapi import APIRouter, HTTPException

router = APIRouter()

ROOT = Path(__file__).resolve().parents[4]
TOTALRACES_DIR = ROOT / "data" / "totalraces"


# -------------------------------
# helpers
# -------------------------------

def fmt_mmss(seconds):
    sec = int(round(seconds))
    m = sec // 60
    s = sec % 60
    return f"{m}:{s:02d}"


# -------------------------------
# TOTAL RACE
# -------------------------------

@router.get("/api/races/{race_id}/total_race_analytics")
def total_race_analytics(race_id: str):

    files = list(TOTALRACES_DIR.glob(f"*_{race_id}.csv"))
    if not files:
        raise HTTPException(404, "No sailors found")

    rows = []

    for f in files:
        sailor = f.name.split("_")[0]
        df = pd.read_csv(f)

        time_s = float(df["elapsed_race_time_s"].iloc[0])
        finished = df["finished_flag"].max() == 1

        rows.append({
            "sailor": sailor,
            "time_s": time_s,
            "finished": finished
        })

    finishers = [r for r in rows if r["finished"]]
    dnfs = [r for r in rows if not r["finished"]]

    finishers.sort(key=lambda r: r["time_s"])

    out = []

    for i, r in enumerate(finishers, start=1):
        out.append({
            "rank": i,
            "sailor": r["sailor"],
            "time_sailed": fmt_mmss(r["time_s"])
        })

    for r in dnfs:
        out.append({
            "rank": None,
            "sailor": r["sailor"],
            "time_sailed": "DNF"
        })

    return out


# -------------------------------
# LEG RANK + TIME
# -------------------------------

@router.get("/api/leg_time_analytics")
def leg_time_analytics(race_id: str, leg: int):

    files = list(TOTALRACES_DIR.glob(f"*_{race_id}.csv"))
    if not files:
        raise HTTPException(404, "No sailors found")

    rows = []

    for f in files:
        sailor = f.name.split("_")[0]
        df = pd.read_csv(f)

        leg_df = df[df["geom_leg_id"] == leg]

        if leg_df.empty:
            rows.append({
                "sailor": sailor,
                "time_s": None,
                "finished": False
            })
            continue

        t0 = pd.to_datetime(leg_df.iloc[0]["timestamp_utc"])
        t1 = pd.to_datetime(leg_df.iloc[-1]["timestamp_utc"])

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

    for i, r in enumerate(finishers, start=1):
        out.append({
            "rank": i,
            "sailor": r["sailor"],
            "time_sailed": fmt_mmss(r["time_s"])
        })

    for r in dnfs:
        out.append({
            "rank": None,
            "sailor": r["sailor"],
            "time_sailed": "DNF"
        })

    return {"rows": out}