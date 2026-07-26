from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

class Decision(str, Enum):
    VERIFIED = "verified"
    UNCERTAIN = "uncertain"
    UNAVAILABLE = "unavailable"

class Challenge(BaseModel):
    model_config = ConfigDict(frozen=True)
    anchor_id: str
    epoch: int = Field(ge=0)
    start_frequency_offset_hz: float
    chirp_slope_hz_per_s: float
    chirp_permutation: tuple[int, ...]

class Observation(BaseModel):
    model_config = ConfigDict(frozen=True)
    range_m: float = Field(ge=0)
    radial_velocity_mps: float
    bearing_rad: float
    range_std_m: float = Field(gt=0)
    radial_velocity_std_mps: float = Field(gt=0)
    bearing_std_rad: float = Field(gt=0)

class Evidence(BaseModel):
    model_config = ConfigDict(frozen=True)
    anchor_id: str
    epoch: int
    challenge: Challenge
    observation: Observation
    binding_statistic: float = Field(ge=0, le=1)
    quality: float = Field(ge=0, le=1)
    sample_commitment_hex: str
    auth_tag_hex: str

class AnchorConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    anchor_id: str
    position_m: tuple[float, float]
    key_hex: str

class DecisionResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    epoch: int
    decision: Decision
    accepted_anchor_ids: tuple[str, ...]
    estimated_position_m: tuple[float, float] | None
    feasibility_cost: float | None
    geometry_score: float | None
    reason: str
