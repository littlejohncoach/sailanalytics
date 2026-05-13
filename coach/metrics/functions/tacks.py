import pandas as pd

def compute_tack_count(df, params):
    """
    Count tacks using rotation-based detection.

    Required params:
    - leg_id (int) → which geometry leg to analyse (e.g. 1 or 4)

    Optional params:
    - window (int) → seconds before/after (default 10)
    - min_rot (float) → minimum rotation (default 80)
    - max_rot (float) → maximum rotation (default 100)
    - cooldown (int) → grouping threshold (default 20)
    """

    # -------------------------
    # PARAMS
    # -------------------------
    leg_id = params.get("leg_id")
    if leg_id is None:
        return {"status": "error", "message": "leg_id required"}

    WINDOW = params.get("window", 10)
    MIN_ROT = params.get("min_rot", 80)
    MAX_ROT = params.get("max_rot", 100)
    COOLDOWN = params.get("cooldown", 20)

    # -------------------------
    # FILTER LEG
    # -------------------------
    df_leg = df[df["geom_leg_id"] == leg_id].reset_index(drop=True)

    if len(df_leg) < (WINDOW * 2 + 5):
        return {
            "status": "ok",
            "metric_id": "tack_count",
            "value": 0
        }

    # -------------------------
    # HELPER
    # -------------------------
    def angle_diff(a, b):
        d = (a - b + 180) % 360 - 180
        return abs(d)

    # -------------------------
    # DETECTION
    # -------------------------
    tacks = []
    current_group = []

    for i in range(WINDOW, len(df_leg) - WINDOW):

        cog_before = df_leg.iloc[i - WINDOW]["COG_raw_deg"]
        cog_after  = df_leg.iloc[i + WINDOW]["COG_raw_deg"]

        rotation = angle_diff(cog_after, cog_before)

        if MIN_ROT <= rotation <= MAX_ROT:

            if len(current_group) == 0:
                current_group = [i]

            elif i - current_group[-1] <= COOLDOWN:
                current_group.append(i)

            else:
                tacks.append(current_group)
                current_group = [i]

    if current_group:
        tacks.append(current_group)

    # -------------------------
    # OUTPUT
    # -------------------------
    return {
        "status": "ok",
        "metric_id": "tack_count",
        "value": len(tacks)
    }
