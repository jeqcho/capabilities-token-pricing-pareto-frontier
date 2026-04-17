"""End-to-end pipeline: fetch ECI, metadata, pricing; join; compute Pareto; write JSON."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from fetch_eci import fetch_and_compute_eci
from fetch_metadata import fetch_metadata
from fetch_pricing import fetch_aa_pricing
from join import compute_pareto, join_all
from state import read_last_hash, write_hash

OUTPUTS = Path(__file__).parent.parent / "outputs"
MODELS_JSON = OUTPUTS / "models.json"
MISSING_JSON = OUTPUTS / "missing_pricing.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("build_data")


def _json_safe(v):
    if pd.isna(v):
        return None
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.isoformat()
    if hasattr(v, "item"):
        return v.item()
    return v


def main() -> int:
    OUTPUTS.mkdir(parents=True, exist_ok=True)

    log.info("Fetching ECI benchmarks and computing scores...")
    eci_df, eci_hash = fetch_and_compute_eci()
    log.info("Got ECI scores for %d models (csv sha256=%s)", len(eci_df), eci_hash[:12])

    prev_hash = read_last_hash()
    eci_changed = eci_hash != prev_hash
    log.info("ECI changed since last run: %s", eci_changed)

    log.info("Fetching model metadata...")
    meta_df = fetch_metadata()
    log.info("Got metadata for %d models", len(meta_df))

    log.info("Fetching pricing from Artificial Analysis...")
    price_df = fetch_aa_pricing()
    log.info("Got pricing for %d models", len(price_df))

    joined, missing = join_all(eci_df, meta_df, price_df)
    log.info("Joined: %d total rows, %d missing pricing", len(joined), len(missing))

    joined["on_frontier_blended"] = compute_pareto(joined, "price_blended")
    joined["on_frontier_input"] = compute_pareto(joined, "price_input")
    joined["on_frontier_output"] = compute_pareto(joined, "price_output")

    models = []
    for _, row in joined.iterrows():
        if pd.isna(row["price_blended"]):
            # Keep models without pricing out of the site; they're tracked via issues instead.
            continue
        models.append({
            "name": row["name"],
            "org": _json_safe(row.get("org")),
            "release_date": _json_safe(row.get("release_date")),
            "reasoning": bool(row.get("reasoning", False)),
            "eci": _json_safe(row["eci"]),
            "price_input": _json_safe(row["price_input"]),
            "price_output": _json_safe(row["price_output"]),
            "price_blended": _json_safe(row["price_blended"]),
            "on_frontier_blended": bool(row["on_frontier_blended"]),
            "on_frontier_input": bool(row["on_frontier_input"]),
            "on_frontier_output": bool(row["on_frontier_output"]),
        })

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "eci_changed": eci_changed,
        "eci_sha256": eci_hash,
        "model_count": len(models),
        "missing_pricing_count": len(missing),
        "models": models,
    }
    MODELS_JSON.write_text(json.dumps(out, indent=2, default=str))
    log.info("Wrote %s (%d models on site)", MODELS_JSON, len(models))

    MISSING_JSON.write_text(json.dumps({"missing": missing}, indent=2, default=str))
    log.info("Wrote %s (%d missing)", MISSING_JSON, len(missing))

    write_hash(eci_hash)
    log.info("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
