# coach/app/backend/routes/leg_analytics.py
from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any

from fastapi import APIRouter, Query, HTTPException

from ..LegAnalytics import compute_leg_analytics

router = APIRouter(tags=["analytics"])


def _list_sailors_for_race_from_totalraces(project_root: Path, race_id: str) -> List[str]:
    """
    Deterministic discovery from:
      data/totalraces/<sailor>_<race_id>.csv
    """
    totalraces_dir = project_root / "data" / "totalraces"
    if not totalraces_dir.exists():
        return []

    suffix = f"_{race_id}.csv"
    sailors: List[str] = []
    for p in totalraces_dir.glob(f"*{suffix}"):
        name = p.name
        sailor = name[: -len(suffix)]
        if sailor:
            sailors.append(sailor)

    return sorted(set(sailors))


@router.get("/leg_analytics")
def leg_analytics(
    race_id: str = Query(..., description="e.g. 301125_R1_yellow"),
    leg: str = Query(..., description='geom_leg_id as "1".."6"'),
) -> Dict[str, Any]:
    # .../SailAnalytics/coach/app/backend/routes/leg_analytics.py -> parents[4] == .../SailAnalytics
    project_root = Path(__file__).resolve().parents[4]

    # Enforce: leg is integer geom_leg_id
    lv = (leg or "").strip()
    try:
        geom_leg_id = int(lv)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid leg='{leg}'. Must be integer geom_leg_id 1..6")

    sailors = _list_sailors_for_race_from_totalraces(project_root, race_id)
    if not sailors:
        raise HTTPException(
            status_code=404,
            detail=f"No sailors found in data/totalraces for race_id={race_id}",
        )

    rows = compute_leg_analytics(
        project_root=project_root,
        race_id=race_id,
        leg_value=str(geom_leg_id),
        sailors=sailors,
    )

    return {
        "race_id": race_id,
        "leg": str(geom_leg_id),
        "rows": [
            {
                "rank": r.rank,
                "sailor": r.sailor,
                "length_leg_m": None if r.length_leg_m is None else int(round(float(r.length_leg_m))),
                "time_sailed": r.time_sailed_str,
                "distance_sailed_m": None if r.distance_sailed_m is None else int(round(float(r.distance_sailed_m))),
                "avg_hr_bpm": None if r.avg_hr_bpm is None else int(round(float(r.avg_hr_bpm))),
                "avg_boat_speed_mpm": None if r.avg_boat_speed_mpm is None else int(round(float(r.avg_boat_speed_mpm))),
                "avg_course_speed_mpm": None if r.avg_course_speed_mpm is None else int(round(float(r.avg_course_speed_mpm))),
                "efficiency_pct": None if r.efficiency_pct is None else round(float(r.efficiency_pct), 1),
            }
            for r in rows
        ],
    }
