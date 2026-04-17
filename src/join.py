"""Normalize model names, join ECI/metadata/pricing, compute Pareto frontier."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

OVERRIDES_PATH = Path(__file__).parent.parent / "data" / "name_overrides.json"


_CLAUDE_VERSION_FIRST = re.compile(
    r"^claude-(\d+(?:\.\d+)?)-(opus|sonnet|haiku)(.*)$"
)


def normalize_name(name: str) -> str:
    """Collapse a model name to a join key. Kept permissive; manual overrides cover edge cases."""
    if name is None:
        return ""
    s = str(name).strip().lower()
    # strip provider/org prefixes
    if "/" in s:
        s = s.split("/", 1)[1]
    # unify separators
    s = s.replace("_", "-").replace(" ", "-")
    # collapse repeated dashes
    s = re.sub(r"-+", "-", s)
    # drop parenthetical qualifiers
    s = re.sub(r"\(.*?\)", "", s).strip("-")
    # AA uses "claude-4.5-haiku"; Epoch uses "claude-haiku-4.5". Normalize to name-first.
    m = _CLAUDE_VERSION_FIRST.match(s)
    if m:
        version, tier, rest = m.groups()
        s = f"claude-{tier}-{version}{rest}"
    return s


def load_overrides() -> dict[str, str]:
    if not OVERRIDES_PATH.exists():
        return {}
    data = json.loads(OVERRIDES_PATH.read_text())
    return {normalize_name(k): normalize_name(v) for k, v in data.get("overrides", {}).items()}


def _resolve_prefix_match(eci_key: str, price_keys: list[str]) -> str | None:
    """If no exact match, accept a price key that extends eci_key by a suffix like
    '-preview' or '-reasoning' — common AA naming convention. Only resolve when the
    prefix is unambiguous up to variant suffix."""
    prefix = eci_key + "-"
    candidates = [k for k in price_keys if k.startswith(prefix)]
    if not candidates:
        return None
    # Choose the shortest candidate (closest to the ECI name).
    return min(candidates, key=len)


def join_all(
    eci_df: pd.DataFrame,
    meta_df: pd.DataFrame,
    price_df: pd.DataFrame,
) -> tuple[pd.DataFrame, list[dict]]:
    overrides = load_overrides()

    eci = eci_df.copy()
    eci["join_key"] = eci["Model"].apply(normalize_name).map(lambda k: overrides.get(k, k))

    meta = meta_df.copy()
    meta["join_key"] = meta["model"].apply(normalize_name)

    price = price_df.copy()
    price["join_key"] = price["name"].apply(normalize_name)
    # AA returns multiple config variants per base model (e.g. "(xhigh)", "(medium)").
    # Collapse to the cheapest blended-price variant per join key so each ECI model
    # maps to at most one pricing row.
    price = (
        price.sort_values("price_blended", ascending=True, na_position="last")
        .drop_duplicates(subset=["join_key"], keep="first")
    )

    # Prefix fallback: for ECI keys with no exact AA match, look for an AA key that
    # extends the ECI key by a variant suffix.
    price_key_set = set(price["join_key"])
    all_price_keys = price["join_key"].tolist()
    fallback_map: dict[str, str] = {}
    for k in eci["join_key"].unique():
        if k in price_key_set:
            continue
        match = _resolve_prefix_match(k, all_price_keys)
        if match:
            fallback_map[k] = match
    if fallback_map:
        extra_rows = price[price["join_key"].isin(fallback_map.values())].copy()
        inverse = {v: k for k, v in fallback_map.items()}
        extra_rows["join_key"] = extra_rows["join_key"].map(inverse)
        price = pd.concat([price, extra_rows], ignore_index=True)

    # Same dedup on metadata side so one ECI name doesn't fan out into multiple rows.
    meta = meta.drop_duplicates(subset=["join_key"], keep="last")

    merged = eci.merge(meta, on="join_key", how="left", suffixes=("", "_meta"))
    merged = merged.merge(price, on="join_key", how="left", suffixes=("", "_price"))

    missing_mask = merged["price_blended"].isna()
    missing = [
        {
            "model": row["Model"],
            "normalized": row["join_key"],
            "eci": float(row["eci"]) if pd.notna(row["eci"]) else None,
        }
        for _, row in merged[missing_mask].iterrows()
    ]

    out = pd.DataFrame({
        "name": merged["Model"],
        "normalized": merged["join_key"],
        "org": merged.get("org"),
        "release_date": merged.get("release_date"),
        "domain": merged.get("domain"),
        "reasoning": merged.get("reasoning", False).fillna(False) if "reasoning" in merged else False,
        "eci": merged["eci"],
        "price_input": merged["price_input"],
        "price_output": merged["price_output"],
        "price_blended": merged["price_blended"],
    })
    return out, missing


def compute_pareto(df: pd.DataFrame, price_col: str) -> pd.Series:
    """Return a boolean Series marking Pareto-frontier rows for the given price axis.

    A row is on the frontier if no other row has both lower price and higher ECI.
    """
    valid = df[[price_col, "eci"]].dropna()
    if valid.empty:
        return pd.Series(False, index=df.index)

    sorted_idx = valid.sort_values([price_col, "eci"], ascending=[True, False]).index
    on_frontier: dict[int, bool] = {}
    best_eci = float("-inf")
    for idx in sorted_idx:
        eci = valid.loc[idx, "eci"]
        if eci > best_eci:
            on_frontier[idx] = True
            best_eci = eci
        else:
            on_frontier[idx] = False

    return pd.Series(
        {i: on_frontier.get(i, False) for i in df.index},
        index=df.index,
    ).fillna(False)
