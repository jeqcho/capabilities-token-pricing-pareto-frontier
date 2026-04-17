"""Download Epoch's all_ai_models.csv for release dates + organization."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import requests

METADATA_URL = "https://epoch.ai/data/all_ai_models.csv"
CACHE_PATH = Path(__file__).parent.parent / "outputs" / "all_ai_models.csv"

_REASONING_PATTERNS = [
    re.compile(r"\bo[1-9](-mini|-preview|-pro)?\b", re.IGNORECASE),
    re.compile(r"\br1\b", re.IGNORECASE),
    re.compile(r"\bqwq\b", re.IGNORECASE),
    re.compile(r"thinking", re.IGNORECASE),
    re.compile(r"reasoning", re.IGNORECASE),
]


def _is_reasoning(name: str) -> bool:
    return any(p.search(name) for p in _REASONING_PATTERNS)


def fetch_metadata() -> pd.DataFrame:
    resp = requests.get(METADATA_URL, timeout=60)
    resp.raise_for_status()
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_bytes(resp.content)

    df = pd.read_csv(CACHE_PATH)
    keep = ["Model", "Organization", "Publication date", "Domain"]
    df = df[[c for c in keep if c in df.columns]].copy()
    df = df.rename(columns={
        "Model": "model",
        "Organization": "org",
        "Publication date": "release_date",
        "Domain": "domain",
    })
    df["reasoning"] = df["model"].fillna("").apply(_is_reasoning)
    df = df.dropna(subset=["model"]).drop_duplicates(subset=["model"], keep="last")
    return df
