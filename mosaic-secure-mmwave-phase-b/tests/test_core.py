import numpy as np
from mosaic.challenge import ChallengeCodebook, derive_challenge
from mosaic.decision import decide_epoch, fail_safe_track_loss
from mosaic.evidence import create_evidence, verify_evidence
from mosaic.models import AnchorConfig, Decision, Observation
from mosaic.security_bounds import homogeneous_bound
from mosaic.simulator import genuine_epoch, inconsistent_phantom_epoch

def fixture():
    anchors = {
        "A1": AnchorConfig(anchor_id="A1", position_m=(0,0), key_hex="11"*32),
        "A2": AnchorConfig(anchor_id="A2", position_m=(5,0), key_hex="22"*32),
        "A3": AnchorConfig(anchor_id="A3", position_m=(2.5,4), key_hex="33"*32)}
    keys = {k: bytes.fromhex(v.key_hex) for k,v in anchors.items()}
    cb = ChallengeCodebook((-2e7,0,2e7),(5.5e13,6e13),((0,1),(1,0)))
    return anchors, keys, cb

def test_challenge_determinism():
    _, keys, cb = fixture()
    a = derive_challenge(key=keys["A1"], anchor_id="A1", epoch=2, codebook=cb)
    b = derive_challenge(key=keys["A1"], anchor_id="A1", epoch=2, codebook=cb)
    assert a == b

def test_evidence_tamper_detection():
    _, keys, cb = fixture()
    c = derive_challenge(key=keys["A1"], anchor_id="A1", epoch=1, codebook=cb)
    o = Observation(range_m=2, radial_velocity_mps=.1, bearing_rad=.2,
                    range_std_m=.05, radial_velocity_std_mps=.05,
                    bearing_std_rad=.02)
    e = create_evidence(key=keys["A1"], anchor_id="A1", epoch=1,
                        challenge=c, observation=o, binding_statistic=.95,
                        quality=.9, sample_buffer=b"x")
    assert verify_evidence(key=keys["A1"], evidence=e)
    bad = e.model_copy(update={"observation": o.model_copy(update={"range_m": 9})})
    assert not verify_evidence(key=keys["A1"], evidence=bad)

def test_genuine_and_phantom_decisions():
    anchors, keys, cb = fixture()
    common = dict(rng=np.random.default_rng(3), epoch=0, position=(2,1.5),
                  velocity=(.3,.1), anchors=anchors, keys=keys, codebook=cb,
                  range_std=.04, velocity_std=.06, bearing_std=.025)
    genuine = genuine_epoch(**common)
    phantom = inconsistent_phantom_epoch(**common)
    kwargs = dict(epoch=0, anchors=anchors, keys=keys, quorum_l=3,
                  binding_threshold=.8, geometry_threshold=.1,
                  verified_cost_threshold=12, uncertainty_margin=4)
    assert decide_epoch(evidence=genuine, **kwargs).decision == Decision.VERIFIED
    assert decide_epoch(evidence=phantom, **kwargs).decision != Decision.VERIFIED

def test_fail_safe_and_bound():
    assert fail_safe_track_loss(True, False, False) == Decision.UNAVAILABLE
    assert homogeneous_bound(k=4, quorum_l=3, controlled_count=3,
                             beta=.05, alpha_f_star=.1) > homogeneous_bound(
                             k=4, quorum_l=3, controlled_count=1,
                             beta=.05, alpha_f_star=.1)
