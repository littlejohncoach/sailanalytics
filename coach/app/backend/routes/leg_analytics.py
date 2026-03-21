from pathlib import Path
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

ROOT = Path(__file__).resolve().parents[4]
TOTALRACES_DIR = ROOT / "data" / "totalraces"


# -------------------------------------------------
# HELPERS
# -------------------------------------------------

def fmt_mmss(seconds):
    sec = int(round(seconds))
    m = sec // 60
    s = sec % 60
    return f"{m}:{s:02d}"


def list_sailors(race_id: str):
    files = list(TOTALRACES_DIR.glob(f"*_{race_id}.csv"))
    return sorted([f.name.split("_")[0] for f in files])


# -------------------------------------------------
# LEG ANALYTICS — RANK + TIME ONLY
# -------------------------------------------------

@router.get("/api/leg_analytics")
def leg_analytics(
    race_id: str = Query(...),
    leg: str = Query(...)
):

    try:
        leg_id = int(leg)
    except:
        raise HTTPException(400, f"Invalid leg: {leg}")

    sailors = list_sailors(race_id)
    if not sailors:
        raise HTTPException(404, f"No sailors for race {race_id}")

    rows = []

    for sailor in sailors:
        path = TOTALRACES_DIR / f"{sailor}_{race_id}.csv"
        if not path.exists():
            continue

        df = pd.read_csv(path)

        if "geom_leg_id" not in df.columns or "timestamp_utc" not in df.columns:
            continue

        leg_df = df[df["geom_leg_id"] == leg_id]

        if leg_df.empty:
            rows.append({
                "sailor": sailor,
                "time_s": None,
                "finished": False
            })
            continue

        # ORDER BY TIME (CRITICAL)
        leg_df["timestamp_utc"] = pd.to_datetime(leg_df["timestamp_utc"], errors="coerce")
        leg_df = leg_df.dropna(subset=["timestamp_utc"]).sort_values("timestamp_utc")

        if leg_df.empty:
            rows.append({
                "sailor": sailor,
                "time_s": None,
                "finished": False
            })
            continue

        # CORE RULE
        t0 = leg_df.iloc[0]["timestamp_utc"]
        t1 = leg_df.iloc[-1]["timestamp_utc"]

        time_s = (t1 - t0).total_seconds()

        rows.append({
            "sailor": sailor,
            "time_s": time_s,
            "finished": True
        })

    # -------------------------
    # RANK
    # -------------------------

    finishers = [r for r in rows if r["finished"] and r["time_s"] is not None]
    dnfs = [r for r in rows if not r["finished"] or r["time_s"] is None]

    finishers.sort(key=lambda r: r["time_s"])

    out = []

    # FINISHERS
    for i, r in enumerate(finishers, start=1):
        out.append({
            "rank": i,
            "sailor": r["sailor"],
            "time_sailed": fmt_mmss(r["time_s"])
        })

    # DNFs
    for r in dnfs:
        out.append({
            "rank": None,
            "sailor": r["sailor"],
            "time_sailed": "DNF"
        })

    return {"rows": out}
