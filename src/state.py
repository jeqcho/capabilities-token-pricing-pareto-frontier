"""Persist the hash of the last processed ECI benchmarks CSV."""
from pathlib import Path

HASH_FILE = Path(__file__).parent.parent / "outputs" / "last_eci_hash.txt"


def read_last_hash() -> str:
    if not HASH_FILE.exists():
        return ""
    return HASH_FILE.read_text().strip()


def write_hash(h: str) -> None:
    HASH_FILE.parent.mkdir(parents=True, exist_ok=True)
    HASH_FILE.write_text(h + "\n")
