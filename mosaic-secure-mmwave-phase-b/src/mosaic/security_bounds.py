import itertools
import math

def active_forgery_bound(*, anchor_ids, quorum_l, controlled_anchor_ids,
                         beta_by_anchor, alpha_f_star) -> float:
    total = 0.0
    for size in range(quorum_l, len(anchor_ids)+1):
        for quorum in itertools.combinations(anchor_ids, size):
            local = 1.0
            for anchor_id in quorum:
                if anchor_id not in controlled_anchor_ids:
                    local *= beta_by_anchor[anchor_id]
            total += alpha_f_star * local
    return min(1.0, total)

def homogeneous_bound(*, k, quorum_l, controlled_count,
                      beta, alpha_f_star) -> float:
    n_l = sum(math.comb(k, size) for size in range(quorum_l, k+1))
    exponent = max(0, quorum_l-controlled_count)
    return min(1.0, n_l*alpha_f_star*(beta**exponent))
