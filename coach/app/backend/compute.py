#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
compute.py
------------------------------------------------------------
Deterministic computations for summaries.

Phase 1 keeps this minimal. We provide:
- column detection helpers
- filtering primitives
------------------------------------------------------------
"""

from __future__ import annotations

from typing import Iterable, Optional, Dict, List
import pandas as pd


def pick_col(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def detect_columns(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    """Detect key columns with flexible naming."""
    sailor = pick_col(df, ["sailor_name", "sailor", "name", "athlete", "sailor_id"])
    leg = pick_col(df, ["leg_instance_id", "leg", "leg_id", "leg_instance", "leg_no"])
    t = pick_col(df, ["timestamp", "t", "time_s", "time", "sample_idx", "idx", "seconds"])
    lat = pick_col(df, ["latitude_deg", "lat", "latitude"])
    lon = pick_col(df, ["longitude_deg", "lon", "longitude", "lng"])
    return {"sailor": sailor, "leg": leg, "t": t, "lat": lat, "lon": lon}


def filter_df(df: pd.DataFrame, sailors: Optional[List[str]], leg_value: Optional[str]) -> pd.DataFrame:
    cols = detect_columns(df)
    out = df

    if sailors and cols["sailor"]:
        out = out[out[cols["sailor"]].astype(str).isin([str(s) for s in sailors])]

    if leg_value is not None and leg_value not in ("", "—") and cols["leg"]:
        out = out[out[cols["leg"]].astype(str) == str(leg_value)]

    return out
