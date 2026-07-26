import hashlib
import numpy as np
from mosaic.challenge import derive_challenge
from mosaic.evidence import create_evidence
from mosaic.geometry import predict
from mosaic.models import Observation

def _buffer(anchor_id, epoch, position):
    return hashlib.sha256(
        f"{anchor_id}|{epoch}|{position[0]:.5f}|{position[1]:.5f}".encode()
    ).digest()*8

def genuine_epoch(*, rng, epoch, position, velocity, anchors, keys, codebook,
                  range_std, velocity_std, bearing_std):
    result = []
    for aid, cfg in anchors.items():
        c = derive_challenge(key=keys[aid], anchor_id=aid,
                             epoch=epoch, codebook=codebook)
        r, v, th = predict(cfg.position_m, position, velocity)
        obs = Observation(
            range_m=max(0.001, r+rng.normal(0, range_std)),
            radial_velocity_mps=v+rng.normal(0, velocity_std),
            bearing_rad=th+rng.normal(0, bearing_std),
            range_std_m=range_std,
            radial_velocity_std_mps=velocity_std,
            bearing_std_rad=bearing_std)
        result.append(create_evidence(
            key=keys[aid], anchor_id=aid, epoch=epoch, challenge=c,
            observation=obs, binding_statistic=float(rng.uniform(.92,.99)),
            quality=float(rng.uniform(.85,.98)),
            sample_buffer=_buffer(aid, epoch, position)))
    return result

def inconsistent_phantom_epoch(**kwargs):
    evidence = genuine_epoch(**kwargs)
    offsets = {"A1": .8, "A2": -.6, "A3": 1.1}
    out = []
    keys = kwargs["keys"]
    position = kwargs["position"]
    epoch = kwargs["epoch"]
    for e in evidence:
        obs = e.observation.model_copy(
            update={"range_m": max(.001, e.observation.range_m+offsets[e.anchor_id])})
        out.append(create_evidence(
            key=keys[e.anchor_id], anchor_id=e.anchor_id, epoch=epoch,
            challenge=e.challenge, observation=obs,
            binding_statistic=.95, quality=.9,
            sample_buffer=_buffer(e.anchor_id, epoch, position)))
    return out
