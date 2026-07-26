import math
import numpy as np

def wrap_angle(x: float) -> float:
    return (x + math.pi) % (2 * math.pi) - math.pi

def predict(anchor, position, velocity):
    a = np.asarray(anchor, dtype=float)
    p = np.asarray(position, dtype=float)
    v = np.asarray(velocity, dtype=float)
    d = p - a
    r = float(np.linalg.norm(d))
    if r <= 1e-9:
        raise ValueError("target coincides with anchor")
    return r, float(np.dot(d / r, v)), float(math.atan2(d[1], d[0]))

def geometry_score(anchor_positions, position) -> float:
    p = np.asarray(position, dtype=float)
    rows = []
    for anchor in anchor_positions:
        d = np.asarray(anchor, dtype=float) - p
        n = np.linalg.norm(d)
        if n <= 1e-9:
            return 0.0
        rows.append(d / n)
    if len(rows) < 2:
        return 0.0
    u = np.asarray(rows)
    return float(np.linalg.eigvalsh((u.T @ u) / len(rows)).min())
