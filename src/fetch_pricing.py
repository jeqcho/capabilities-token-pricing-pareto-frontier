"""Fetch current token pricing from the Artificial Analysis API."""
from __future__ import annotations

import os

import pandas as pd
import requests

AA_URL = "https://artificialanalysis.ai/api/v2/data/llms/models"


def fetch_aa_pricing(api_key: str | None = None) -> pd.DataFrame:
    """Return DataFrame[name, creator, price_input, price_output, price_blended]."""
    api_key = api_key or os.environ.get("ARTIFICIAL_ANALYSIS_API_KEY")
    if not api_key:
        raise RuntimeError("ARTIFICIAL_ANALYSIS_API_KEY not set")

    resp = requests.get(AA_URL, headers={"x-api-key": api_key}, timeout=60)
    resp.raise_for_status()
    payload = resp.json()
    rows = payload.get("data", payload) if isinstance(payload, dict) else payload

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
