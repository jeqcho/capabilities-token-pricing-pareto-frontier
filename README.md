# Capabilities × Token Price Pareto Frontier

Plots AI models on two axes — Epoch Capabilities Index (ECI) vs price per token (log) — and highlights the Pareto frontier. Data pulled daily from Epoch AI and Artificial Analysis.

**Live site:** http://chojeq.com/capabilities-token-pricing-pareto-frontier/ (auto-deployed from `docs/` by the daily Action).

## What's here

- `src/` — data pipeline (Python, uv-managed).
- `docs/` — static site (Plotly via CDN, no build step).
- `.github/workflows/daily-pricing-update.yml` — daily Action that refreshes data, manages missing-pricing issues, and deploys the site.
- `outputs/models.json` — the joined dataset the site consumes.
- `data/name_overrides.json` — manual ECI↔AA name mappings for join misses.
- `reference/` — original project spec (do not edit).

## Running locally

```bash
uv sync
export ARTIFICIAL_ANALYSIS_API_KEY=...  # free-tier key from artificialanalysis.ai
uv run python src/build_data.py
python -m http.server -d docs 8000
open http://localhost:8000
```

Logs go to `logs/<timestamp>-build.log` when the pipeline is run via the tmux wrapper.

## GitHub Action

Runs daily at 13:00 UTC and on manual dispatch. Required secret: `ARTIFICIAL_ANALYSIS_API_KEY`.

Issue behaviour:
- Every run first re-checks open `missing-pricing` issues; closes any for which pricing is now available.
- After joining ECI with pricing, opens a `missing-pricing` issue per model that lacks a price (dedup'd by the `<!-- model:<name> -->` tag in the body).
- If the pipeline itself errors out (and ECI changed this run), opens a single `pipeline-failure` issue; skips if one is already open.

## Data sources

- ECI benchmarks — `https://epoch.ai/data/eci_benchmarks.csv` (composite scores via the `eci` package).
- Model metadata — `https://epoch.ai/data/all_ai_models.csv`.
- Pricing — Artificial Analysis API `/api/v2/data/llms/models`.
