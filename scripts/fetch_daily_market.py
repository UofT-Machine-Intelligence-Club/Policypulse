"""Download daily OHLCV for core ETFs and VIX, save per-ticker parquet."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd
import yfinance as yf

BASE_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = BASE_DIR / "data" / "processed" / "market" / "daily"

START_DATE = "2009-01-01"

CORE_TICKERS: Iterable[str] = ["SPY", "QQQ", "DIA"]
SECTOR_TICKERS: Iterable[str] = ["XLU", "XLB", "XLK", "XLI", "XLF", "XLE", "XLP", "XLY", "XLC", "SMH"]
VOL_TICKER = "^VIX"


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df.columns, pd.MultiIndex):
        return df
    flattened = []
    for col in df.columns:
        parts = [str(part) for part in col if str(part) != ""]
        flattened.append(parts[0] if len(parts) == 1 else parts[0])
    out = df.copy()
    out.columns = flattened
    return out


def fetch_one(ticker: str) -> pd.DataFrame:
    df = yf.download(ticker, start=START_DATE, progress=False, auto_adjust=False)
    if df.empty:
        return df
    df = flatten_columns(df)
    df = df.reset_index().rename(columns={
        "Date": "date",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Adj Close": "adj_close",
        "Volume": "volume",
    })
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df["ticker"] = ticker
    return df[["ticker", "date", "open", "high", "low", "close", "adj_close", "volume"]]


def save(df: pd.DataFrame, ticker: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{ticker.replace('^', '')}.parquet"
    df.to_parquet(path, index=False)
    print(f"saved {ticker}: {len(df):,} rows -> {path}")
    print("range:", df["date"].min(), "to", df["date"].max())


def main() -> int:
    tickers = list(CORE_TICKERS) + list(SECTOR_TICKERS) + [VOL_TICKER]
    today = date.today().isoformat()
    print(f"fetching {len(tickers)} tickers from {START_DATE} to {today}")

    failures = []
    for t in tickers:
        try:
            df = fetch_one(t)
        except Exception as exc:  # log and continue on errors
            print(f"error {t}: {exc}")
            failures.append(t)
            continue
        if df.empty:
            print(f"empty {t}")
            failures.append(t)
            continue
        save(df, t)

    if failures:
        print("failed tickers:", failures)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
