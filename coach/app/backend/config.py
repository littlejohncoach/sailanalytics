#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
config.py
------------------------------------------------------------
SailAnalytics Coach App — Configuration (deterministic)

- Anchors all paths relative to repository root (no CWD reliance)
- Points truth layer at data/totalraces (read-only)
------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

# This file lives at:
#   SailAnalytics/coach/app/backend/config.py
# parents[3] => SailAnalytics/
SAILANALYTICS_ROOT = Path(__file__).resolve().parents[3]

TOTALRACES_DIR = SAILANALYTICS_ROOT / "data" / "totalraces"

# coach/app/
COACH_APP_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = COACH_APP_DIR / "frontend"

API_PREFIX = "/api"
MAX_ROWS_DEFAULT = 5000  # safety for slice endpoints
