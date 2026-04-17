"""Download Epoch's ECI benchmark CSV and fit ECI scores."""
import hashlib
from pathlib import Path

import pandas as pd
import requests
from eci import compute_eci_scores, fit_eci_model, load_benchmark_data

ECI_CSV_URL = "https://epoch.ai/data/eci_benchmarks.csv"
CACHE_PATH = Path(__file__).parent.parent / "outputs" / "eci_benchmarks.csv"


def _download_csv() -> tuple[bytes, str]:
    resp = requests.get(ECI_CSV_URL, timeout=60)
    resp.raise_for_status()
    body = resp.content
    digest = hashlib.sha256(body).hexdigest()
    return body, digest


def fetch_and_compute_eci(bootstrap_samples: int = 100) -> tuple[pd.DataFrame, str]:
    """Download ECI benchmarks, fit the IRT model, return (df[Model, eci], csv_sha256)."""
    body, digest = _download_csv()
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_bytes(body)

    bench_df = load_benchmark_data(str(CACHE_PATH))
    model_params, bench_params = fit_eci_model(bench_df, bootstrap_samples=bootstrap_samples)
    eci_df, _ = compute_eci_scores(model_params, bench_params)

    return eci_df[["Model", "eci"]].copy(), digest
