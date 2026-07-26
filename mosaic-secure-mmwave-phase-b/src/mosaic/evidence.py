import hashlib
import hmac
import json
from mosaic.models import Challenge, Evidence, Observation

def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

def _payload(anchor_id: str, epoch: int, challenge: Challenge,
             observation: Observation, binding_statistic: float,
             quality: float, commitment: str) -> dict:
    return {
        "anchor_id": anchor_id,
        "epoch": epoch,
        "challenge": challenge.model_dump(mode="json"),
        "observation": observation.model_dump(mode="json"),
        "binding_statistic": binding_statistic,
        "quality": quality,
        "sample_commitment_hex": commitment,
    }

def create_evidence(*, key: bytes, anchor_id: str, epoch: int,
                    challenge: Challenge, observation: Observation,
                    binding_statistic: float, quality: float,
                    sample_buffer: bytes) -> Evidence:
    if challenge.anchor_id != anchor_id or challenge.epoch != epoch:
        raise ValueError("challenge/anchor/epoch mismatch")
    commitment = hashlib.sha256(sample_buffer).hexdigest()
    payload = _payload(anchor_id, epoch, challenge, observation,
                       binding_statistic, quality, commitment)
    tag = hmac.new(key, _canonical(payload), hashlib.sha256).hexdigest()
    return Evidence(**payload, auth_tag_hex=tag)

def verify_evidence(*, key: bytes, evidence: Evidence) -> bool:
    payload = _payload(
        evidence.anchor_id, evidence.epoch, evidence.challenge,
        evidence.observation, evidence.binding_statistic,
        evidence.quality, evidence.sample_commitment_hex)
    expected = hmac.new(key, _canonical(payload), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, evidence.auth_tag_hex)
