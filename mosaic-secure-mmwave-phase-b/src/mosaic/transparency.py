import hashlib
import json
from pathlib import Path

def merkle_root_hex(records) -> str:
    level = [hashlib.sha256(r).digest() for r in records]
    if not level:
        return hashlib.sha256(b"").hexdigest()
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [hashlib.sha256(level[i]+level[i+1]).digest()
                 for i in range(0, len(level), 2)]
    return level[0].hex()

class AppendOnlyLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict) -> str:
        previous = "0"*64
        if self.path.exists() and self.path.stat().st_size:
            previous = json.loads(self.path.read_text().splitlines()[-1])["entry_hash"]
        envelope = {"previous_hash": previous, "record": record}
        canonical = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
        entry_hash = hashlib.sha256(canonical.encode()).hexdigest()
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"entry_hash": entry_hash, **envelope}, sort_keys=True)+"\n")
        return entry_hash

    def verify(self) -> bool:
        previous = "0"*64
        if not self.path.exists():
            return True
        for line in self.path.read_text().splitlines():
            item = json.loads(line)
            if item["previous_hash"] != previous:
                return False
            envelope = {"previous_hash": item["previous_hash"], "record": item["record"]}
            canonical = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
            if hashlib.sha256(canonical.encode()).hexdigest() != item["entry_hash"]:
                return False
            previous = item["entry_hash"]
        return True
