from abc import ABC, abstractmethod
from dataclasses import dataclass
from mosaic.models import Challenge, Observation

@dataclass(frozen=True)
class CapturedFrame:
    anchor_id: str
    epoch: int
    challenge: Challenge
    timestamp_ns: int
    sample_buffer: bytes

class RadarAnchorAdapter(ABC):
    @abstractmethod
    def configure_challenge(self, challenge: Challenge) -> None: ...
    @abstractmethod
    def capture_frame(self, epoch: int) -> CapturedFrame: ...
    @abstractmethod
    def compute_binding_statistic(self, frame: CapturedFrame) -> float: ...
    @abstractmethod
    def estimate_observation(self, frame: CapturedFrame) -> Observation: ...

class TimingAdapter(ABC):
    @abstractmethod
    def worst_case_sync_error_ns(self) -> float: ...
