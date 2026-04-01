# TrumpPulse

Predict market impact of Donald Trump posts (Twitter era + Truth Social) by fine-tuning FinBERT with structured features and intraday market alignment.

## What’s here
- `trumppulse_timeline.md` — end-to-end project plan and checklist.
- `overview.ipynb` — detailed model training guide (FinBERT + features, labeling, evaluation).
- `scripts/fetch_truth_social.py` — fetch and normalize the CNN Truth Social archive into CSV/parquet.
- `scripts/fetch_daily_market.py` — download daily OHLCV for core ETFs, sector ETFs, and VIX into parquet.
- `scripts/clean_posts_text.py` — phase 2.1 text cleaning for Twitter and Truth Social posts.

## Data note
- Twitter corpus is intentionally limited to the in-office period (2017-01-20 to 2021-01-08); pre-office tweets are out of scope for this project.
- Truth Social corpus is pulled from the CNN archive (2022-02-14 onward) and stored as `data/processed/truth_social_posts.parquet`.

## Quick start
1) Clone: `git clone git@github.com:Brinda301/trumppulse.git`
2) (Optional) Create a Python env: `python -m venv .venv && source .venv/bin/activate`
3) Open `overview.ipynb` in VS Code/ Jupyter to review the full training workflow.

### Run phase 1.2 Truth Social fetch
- `pip install pandas requests`
- `python scripts/fetch_truth_social.py`
	- Downloads CNN Truth Social archive JSON and writes raw CSV at `data/raw/truth_social/truth_archive.csv`.
	- Writes normalized parquet at `data/processed/truth_social_posts.parquet` with cleaned text, counts, and media flags.

### Run phase 1.3 daily market data
- `pip install yfinance pandas`
- `python scripts/fetch_daily_market.py`
	- Downloads daily OHLCV starting 2009-01-01 for SPY, QQQ, DIA; sector ETFs XLU/XLB/XLK/XLI/XLF/XLE/XLP/XLY/XLC/SMH; and ^VIX.
	- Saves per-ticker parquet files under `data/processed/market/daily/` with columns ticker, date (UTC), open/high/low/close/adj_close/volume.

### Run phase 2.1 text cleaning
- `pip install pandas`
- `python scripts/clean_posts_text.py`
	- Removes URLs, strips `@`/`#` symbols while keeping token text, drops non-ASCII noise, and normalizes whitespace.
	- Preserves cleaned original case in `text_clean`, adds lowercase companion `text_lower`, and flags ALL CAPS usage.
	- Writes `data/processed/tweets_cleaned.parquet` and `data/processed/truth_social_posts_cleaned.parquet`.

## Project scope (high level)
- Collect and clean Trump tweets (2009–2021) and Truth Social posts (2022–present).
- Align posts to market data (SPY/QQQ/DIA, VIX; intraday and daily) and compute abnormal returns.
- Label market impact; engineer text, temporal, market, and behavioral features.
- Fine-tune FinBERT (with auxiliary features) and benchmark against baselines.
- Evaluate, backtest alert thresholds, and package for inference.

## Roadmap & tasks
See `trumppulse_timeline.md` for the full phased checklist (data, EDA, labeling, training, evaluation, packaging).

## Contributing
- Open a branch off `main` (or `master` if you keep it) and submit PRs.
- Keep notebooks clean (restart & run all before committing if possible).
- Document decisions and data sources in PR descriptions.
