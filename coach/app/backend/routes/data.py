from __future__ import annotations

from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from ..loaders import list_race_groups, load_group_df

router = APIRouter(tags=["data"])


def _detect(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    cols = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in cols:
            return cols[cand.lower()]
    return None


@router.get("/races/{group_id}/slice")
def api_slice(
    group_id: str,
    sailors: Optional[str] = Query(default=None, description="Comma-separated sailor ids, e.g. william,lourenco"),
    leg: Optional[str] = Query(default=None, description="Leg instance id. Omit or 'Total Race' for full race."),
    max_rows: int = Query(default=2000, ge=1, le=50000),
):
    if group_id not in list_race_groups():
        raise HTTPException(status_code=404, detail=f"Race group not found: {group_id}")

    sailor_list = [s.strip() for s in sailors.split(",")] if sailors else None
    df = load_group_df(group_id, sailors=sailor_list)
    if df.empty:
        return []

    # leg filter (Total Race = no filter)
    if leg and leg not in ("Total Race", "—"):
        df_leg = df[pd.to_numeric(df["leg_instance_id"], errors="coerce") == int(leg)]
    else:
        df_leg = df

    ptm_col = _detect(df_leg, ["PTM_mpm", "ptm", "ptm_mpm"])
    sog_col = _detect(df_leg, ["SOG_smooth_mpm", "sog", "sog_mpm"])
    hr_col  = _detect(df_leg, ["HR_smooth_bpm", "HR_raw_bpm", "hr", "hr_bpm"])
    atb_col = _detect(df_leg, ["ATB_angle_deg", "atb", "atb_deg"])

    out = []
    for _, r in df_leg.head(max_rows).iterrows():
        out.append(
            {
                "t": r.get("t"),
                "sailor": r.get("sailor_name"),
                "leg": r.get("leg_instance_id"),
                "ptm": (r.get(ptm_col) if ptm_col else None),
                "sog": (r.get(sog_col) if sog_col else None),
                "hr":  (r.get(hr_col) if hr_col else None),
                "atb": (r.get(atb_col) if atb_col else None),
            }
        )
    return out
