import hashlib
import hmac
import struct
from dataclasses import dataclass
from mosaic.models import Challenge

@dataclass(frozen=True)
class ChallengeCodebook:
    start_frequency_offsets_hz: tuple[float, ...]
    chirp_slopes_hz_per_s: tuple[float, ...]
    chirp_permutations: tuple[tuple[int, ...], ...]

    @property
    def cardinality(self) -> int:
        return (len(self.start_frequency_offsets_hz)
                * len(self.chirp_slopes_hz_per_s)
                * len(self.chirp_permutations))

def derive_challenge(*, key: bytes, anchor_id: str, epoch: int,
                     codebook: ChallengeCodebook) -> Challenge:
    msg = b"MOSAIC-v1|" + anchor_id.encode() + b"|" + struct.pack(">Q", epoch)
    d = hmac.new(key, msg, hashlib.sha256).digest()
    return Challenge(
        anchor_id=anchor_id,
        epoch=epoch,
        start_frequency_offset_hz=codebook.start_frequency_offsets_hz[
            int.from_bytes(d[0:8], "big") % len(codebook.start_frequency_offsets_hz)],
        chirp_slope_hz_per_s=codebook.chirp_slopes_hz_per_s[
            int.from_bytes(d[8:16], "big") % len(codebook.chirp_slopes_hz_per_s)],
        chirp_permutation=codebook.chirp_permutations[
            int.from_bytes(d[16:24], "big") % len(codebook.chirp_permutations)],
    )
