# coach/app/backend/routes/leg_analytics.py
from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

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


def _parse_mmss_to_seconds(mmss: str) -> Optional[int]:
    """
    Parse 'M:SS' into total seconds (int). Returns None on failure.
    """
    try:
        t = (mmss or "").strip()
        if ":" not in t:
            return None
        m_str, s_str = t.split(":", 1)
        m = int(m_str)
        s = int(s_str)
        if m < 0 or s < 0 or s >= 60:
            return None
        return m * 60 + s
    except Exception:
        return None


def _fmt_mmss(seconds: int) -> str:
    m = seconds // 60
    s = seconds % 60
    return f"{m}:{s:02d}"


def _fmt_mmss_signed(delta_s: Optional[int]) -> str:
    """
    Signed delta seconds -> '+M:SS' / '-M:SS' / '0:00' / '—'
    """
    if delta_s is None:
        return "—"
    if delta_s == 0:
        return "0:00"
    sign = "+" if delta_s > 0 else "-"
    sec = abs(int(delta_s))
    m = sec // 60
    s = sec % 60
    return f"{sign}{m}:{s:02d}"


def _fmt_int_signed(delta: Optional[float]) -> str:
    """
    Signed numeric delta -> '+N' / '-N' / '0' / '—'
    """
    if delta is None:
        return "—"
    val = int(round(float(delta)))
    if val > 0:
        return f"+{val}"
    return str(val)


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

    # If backend returns nothing, keep shape stable
    if not rows:
        return {"race_id": race_id, "leg": str(geom_leg_id), "rows": []}

    # Winner baselines (rank 1 row)
    winner = rows[0]

    winner_time_s: Optional[int] = _parse_mmss_to_seconds(getattr(winner, "time_sailed_str", "") or "")
    winner_dist_m = getattr(winner, "distance_sailed_m", None)
    winner_boat_mpm = getattr(winner, "avg_boat_speed_mpm", None)
    winner_course_mpm = getattr(winner, "avg_course_speed_mpm", None)

    out_rows: List[Dict[str, Any]] = []

    for idx, r in enumerate(rows, start=1):
        # Always absolute fields (all ranks)
        length_leg_m = None if r.length_leg_m is None else int(round(float(r.length_leg_m)))
        avg_hr_bpm = None if r.avg_hr_bpm is None else int(round(float(r.avg_hr_bpm)))
        eff_pct = None if r.efficiency_pct is None else round(float(r.efficiency_pct), 1)

        # Display fields: winner absolute, others deltas (like Total Race)
        if idx == 1:
            # Winner: absolute
            time_disp = (
                _fmt_mmss(winner_time_s) if winner_time_s is not None else (getattr(r, "time_sailed_str", "") or "—")
            )
            dist_disp: Any = None if r.distance_sailed_m is None else int(round(float(r.distance_sailed_m)))
            boat_disp: Any = None if r.avg_boat_speed_mpm is None else int(round(float(r.avg_boat_speed_mpm)))
            course_disp: Any = None if r.avg_course_speed_mpm is None else int(round(float(r.avg_course_speed_mpm)))
        else:
            # Others: deltas vs winner
            r_time_s = _parse_mmss_to_seconds(getattr(r, "time_sailed_str", "") or "")
            time_disp = _fmt_mmss_signed((r_time_s - winner_time_s) if (r_time_s is not None and winner_time_s is not None) else None)

            dist_disp = _fmt_int_signed(
                (r.distance_sailed_m - winner_dist_m) if (r.distance_sailed_m is not None and winner_dist_m is not None) else None
            )
            boat_disp = _fmt_int_signed(
                (r.avg_boat_speed_mpm - winner_boat_mpm) if (r.avg_boat_speed_mpm is not None and winner_boat_mpm is not None) else None
            )
            course_disp = _fmt_int_signed(
                (r.avg_course_speed_mpm - winner_course_mpm) if (r.avg_course_speed_mpm is not None and winner_course_mpm is not None) else None
            )

        out_rows.append(
            {
                "rank": r.rank,
                "sailor": r.sailor,

                # absolute for all
                "length_leg_m": length_leg_m,
                "avg_hr_bpm": avg_hr_bpm,
                "efficiency_pct": eff_pct,

                # winner absolute / others deltas
                "time_sailed": time_disp,
                "distance_sailed_m": dist_disp,
                "avg_boat_speed_mpm": boat_disp,
                "avg_course_speed_mpm": course_disp,
            }
        )

    return {
        "race_id": race_id,
        "leg": str(geom_leg_id),
        "rows": out_rows,
    }
