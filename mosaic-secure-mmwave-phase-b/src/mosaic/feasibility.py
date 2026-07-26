from dataclasses import dataclass
import numpy as np
from scipy.optimize import least_squares
from mosaic.geometry import predict, wrap_angle

@dataclass(frozen=True)
class FeasibilityResult:
    position_m: tuple[float, float]
    velocity_mps: tuple[float, float]
    robust_cost: float
    success: bool

def solve_one_target(*, evidence, anchors) -> FeasibilityResult:
    if len(evidence) < 2:
        raise ValueError("at least two observations required")
    initial_p = np.mean([anchors[e.anchor_id].position_m for e in evidence], axis=0)
    x0 = np.asarray([initial_p[0], initial_p[1], 0.0, 0.0])

    def residuals(x):
        out = []
        for e in evidence:
            o = e.observation
            r, rv, th = predict(anchors[e.anchor_id].position_m, x[:2], x[2:])
            out.extend([
                (o.range_m-r)/o.range_std_m,
                (o.radial_velocity_mps-rv)/o.radial_velocity_std_mps,
                wrap_angle(o.bearing_rad-th)/o.bearing_std_rad])
        return np.asarray(out)

    fit = least_squares(residuals, x0, loss="huber", f_scale=1.0, max_nfev=300)
    return FeasibilityResult(
        position_m=(float(fit.x[0]), float(fit.x[1])),
        velocity_mps=(float(fit.x[2]), float(fit.x[3])),
        robust_cost=float(2*fit.cost),
        success=bool(fit.success))
