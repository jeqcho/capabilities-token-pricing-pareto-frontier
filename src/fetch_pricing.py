"""Fetch current token pricing from the Artificial Analysis API."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pandas as pd
import requests

AA_URL = "https://artificialanalysis.ai/api/v2/data/llms/models"
CACHE_PATH = Path(__file__).parent.parent / "outputs" / "aa_pricing.json"


def _fetch_raw(api_key: str, retries: int = 3) -> list:
    delay = 2
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        resp = requests.get(AA_URL, headers={"x-api-key": api_key}, timeout=60)
        if resp.status_code == 429 and attempt < retries:
            time.sleep(delay)
            delay *= 2
            continue
        try:
            resp.raise_for_status()
        except requests.HTTPError as exc:
            last_exc = exc
            if attempt >= retries:
                raise
            time.sleep(delay)
            delay *= 2
            continue
        payload = resp.json()
        return payload.get("data", payload) if isinstance(payload, dict) else payload
    raise last_exc or RuntimeError("AA fetch failed")


def fetch_aa_pricing(api_key: str | None = None, use_cache: bool = False) -> pd.DataFrame:
    """Return DataFrame[name, creator, price_input, price_output, price_blended].

    When use_cache=True, read outputs/aa_pricing.json if it exists (written by a
    prior fetch) — this lets the workflow share one live API call across the
    build and issue-management steps without hitting rate limits.
    """
    rows: list | None = None
    if use_cache and CACHE_PATH.exists():
        try:
            rows = json.loads(CACHE_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            rows = None

    if rows is None:
        api_key = api_key or os.environ.get("ARTIFICIAL_ANALYSIS_API_KEY")
        if not api_key:
            raise RuntimeError("ARTIFICIAL_ANALYSIS_API_KEY not set")
        rows = _fetch_raw(api_key)
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(rows))

    records = []
    for item in rows:
        pricing = item.get("pricing") or {}
        records.append({
            "name": item.get("name") or item.get("model_id") or item.get("id"),
            "creator": (item.get("model_creator") or {}).get("name") if isinstance(item.get("model_creator"), dict) else item.get("creator"),
            "price_input": pricing.get("price_1m_input_tokens"),
            "price_output": pricing.get("price_1m_output_tokens"),
            "price_blended": pricing.get("price_1m_blended_3_to_1"),
        })

    df = pd.DataFrame.from_records(records)
    df = df.dropna(subset=["name"]).drop_duplicates(subset=["name"], keep="last")

    # AA sometimes reports 0 for models whose current price isn't tracked; log-scale
    # plots can't render 0 and a $0 row would dominate every Pareto frontier. Treat
    # non-positive prices as missing.
    for col in ("price_input", "price_output", "price_blended"):
        df.loc[df[col].fillna(0) <= 0, col] = None

    return df
