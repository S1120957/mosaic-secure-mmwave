from mosaic.evidence import verify_evidence
from mosaic.feasibility import solve_one_target
from mosaic.geometry import geometry_score
from mosaic.models import Decision, DecisionResult

def decide_epoch(*, epoch, evidence, anchors, keys, quorum_l,
                 binding_threshold, geometry_threshold,
                 verified_cost_threshold, uncertainty_margin):
    admitted, seen = [], set()
    for e in evidence:
        if e.epoch != epoch or e.anchor_id in seen:
            continue
        if e.anchor_id not in anchors or e.anchor_id not in keys:
            continue
        if not verify_evidence(key=keys[e.anchor_id], evidence=e):
            continue
        if e.binding_statistic < binding_threshold:
            continue
        admitted.append(e)
        seen.add(e.anchor_id)

    if len(admitted) < quorum_l:
        return DecisionResult(
            epoch=epoch, decision=Decision.UNAVAILABLE,
            accepted_anchor_ids=tuple(sorted(seen)),
            estimated_position_m=None, feasibility_cost=None,
            geometry_score=None, reason="insufficient admitted quorum")

    fit = solve_one_target(evidence=admitted, anchors=anchors)
    g = geometry_score([anchors[e.anchor_id].position_m for e in admitted],
                       fit.position_m)
    if g < geometry_threshold:
        d, reason = Decision.UNCERTAIN, "insufficient anchor diversity"
    elif fit.robust_cost <= verified_cost_threshold:
        d, reason = Decision.VERIFIED, "all acceptance conditions passed"
    elif fit.robust_cost <= verified_cost_threshold + uncertainty_margin:
        d, reason = Decision.UNCERTAIN, "inside uncertainty margin"
    else:
        d, reason = Decision.UNCERTAIN, "not one-target feasible"

    return DecisionResult(
        epoch=epoch, decision=d,
        accepted_anchor_ids=tuple(sorted(seen)),
        estimated_position_m=fit.position_m,
        feasibility_cost=fit.robust_cost,
        geometry_score=g, reason=reason)

def fail_safe_track_loss(previously_verified: bool,
                         quorum_available: bool,
                         physical_exit_observed: bool) -> Decision:
    if previously_verified and not quorum_available and not physical_exit_observed:
        return Decision.UNAVAILABLE
    if previously_verified and not physical_exit_observed:
        return Decision.UNCERTAIN
    return Decision.VERIFIED
