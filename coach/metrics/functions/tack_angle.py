import pandas as pd
import numpy as np

def compute_tack_angle(df, params):
    """
    Computes:
    - average tacking angle
    - average angle to wind (half)

    Uses:
    - COG_raw_deg only
    - rotation-based tack detection
    """

    leg_id = params.get("leg_id")
    if leg_id is None:
        return {"status": "error", "message": "leg_id required"}

    df = df[df["geom_leg_id"] == leg_id].reset_index(drop=True)

    WINDOW = 10
    POST_START = 10
    POST_END = 15
    MIN_ROT = 80
    MAX_ROT = 100
    COOLDOWN = 20

    def angle_diff(a, b):
        d = (a - b + 180) % 360 - 180
        return abs(d)

    def circular_mean(angles):
        angles = np.deg2rad(angles)
        sin_mean = np.mean(np.sin(angles))
        cos_mean = np.mean(np.cos(angles))
        return (np.rad2deg(np.arctan2(sin_mean, cos_mean)) + 360) % 360

    # --- detect tacks
    tacks = []
    current_group = []

    for i in range(WINDOW, len(df) - POST_END):
        cog_before = df.iloc[i - WINDOW]["COG_raw_deg"]
        cog_after  = df.iloc[i + WINDOW]["COG_raw_deg"]

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

    # --- compute tack angles
    tack_angles = []

    for group in tacks:
        mid_i = group[len(group)//2]

        cog_before = df.iloc[mid_i - WINDOW]["COG_raw_deg"]

        post_angles = [
            df.iloc[j]["COG_raw_deg"]
            for j in range(mid_i + POST_START, mid_i + POST_END + 1)
            if j < len(df)
        ]

        if len(post_angles) == 0:
            continue

        cog_after_mean = circular_mean(post_angles)

        tack_angle = angle_diff(cog_after_mean, cog_before)
        tack_angles.append(tack_angle)

    if len(tack_angles) == 0:
        return {
            "status": "ok",
            "metric_id": "tack_angle",
            "value": None
        }

    avg_tack_angle = float(round(sum(tack_angles) / len(tack_angles), 1))
    avg_angle_to_wind = float(round(avg_tack_angle / 2, 1))

    return {
        "status": "ok",
        "metric_id": "tack_angle",
        "value": {
            "avg_tack_angle": avg_tack_angle,
            "avg_angle_to_wind": avg_angle_to_wind
        }
    }
