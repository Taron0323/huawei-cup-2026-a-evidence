# Educational interface example; no contest data are loaded.
# AI tool: PENDING
# Version/model: PENDING
# Developer: PENDING
# Release date: PENDING
import math


def edge_risk(distance_m, risk_start, risk_end):
    values = (distance_m, risk_start, risk_end)
    if not all(math.isfinite(x) and x >= 0 for x in values):
        raise ValueError("Distance and risks must be finite and nonnegative")
    return distance_m * (risk_start + risk_end) / 2
