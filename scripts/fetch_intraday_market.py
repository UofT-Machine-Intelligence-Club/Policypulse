"""Download free rolling intraday OHLCV data and cache it by month."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd
import yfinance as yf
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = BASE_DIR / "data" / "processed" / "market" / "intraday"

DEFAULT_TICKERS: Iterable[str] = ["SPY", "QQQ", "DIA"]
DEFAULT_INTERVAL = "5m"
DEFAULT_PERIOD = "60d"

ET = ZoneInfo("America/New_York")


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df.columns, pd.MultiIndex):
        return df
    out = df.copy()
    out.columns = [str(col[0]) for col in df.columns]
    return out


def classify_session(ts_utc: pd.Timestamp) -> str:
    ts_et = ts_utc.tz_convert(ET)
    minute_of_day = ts_et.hour * 60 + ts_et.minute
    if 4 * 60 <= minute_of_day < 9 * 60 + 30:
        return "pre_market"
    if 9 * 60 + 30 <= minute_of_day < 16 * 60:
        return "market_hours"
    if 16 * 60 <= minute_of_day < 20 * 60:
        return "after_hours"
    return "off_session"


def expected_bars_per_session(interval: str) -> dict[str, int]:
    interval_minutes = {
        "1m": 1,
        "2m": 2,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "60m": 60,
        "90m": 90,
        "1h": 60,
    }
    step = interval_minutes.get(interval)
    if step is None:
        raise ValueError(f"unsupported interval: {interval}")
    return {
        "pre_market": (330 // step),
        "market_hours": (390 // step),
        "after_hours": (240 // step),
    }


def fetch_one(ticker: str, interval: str, period: str, prepost: bool) -> pd.DataFrame:
    df = yf.download(
        ticker,
        period=period,
        interval=interval,
        prepost=prepost,
        progress=False,
        auto_adjust=False,
        threads=False,
    )
    if df.empty:
        return df

    df = flatten_columns(df).reset_index()
    timestamp_col = "Datetime" if "Datetime" in df.columns else "Date"
    rename_map = {
        timestamp_col: "timestamp",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Adj Close": "adj_close",
        "Volume": "volume",
    }
    df = df.rename(columns=rename_map)
    if "adj_close" not in df.columns:
        df["adj_close"] = df["close"]

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"]).copy()
    df["ticker"] = ticker
    df["session"] = df["timestamp"].map(classify_session)
    ts_et = df["timestamp"].dt.tz_convert(ET)
    df["trading_date"] = ts_et.dt.date.astype("string")
    df["year_month"] = ts_et.dt.strftime("%Y-%m")
    return df[[
        "ticker",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "adj_close",
        "volume",
        "session",
        "trading_date",
        "year_month",
    ]].sort_values("timestamp").reset_index(drop=True)


def month_partition_path(ticker: str, year_month: str) -> Path:
    return OUT_DIR / ticker / f"{year_month}.parquet"


def merge_with_existing(path: Path, incoming: pd.DataFrame) -> pd.DataFrame:
    if path.exists():
        existing = pd.read_parquet(path)
        combined = pd.concat([existing, incoming], ignore_index=True)
    else:
        combined = incoming.copy()
    combined["timestamp"] = pd.to_datetime(combined["timestamp"], utc=True, errors="coerce")
    combined = combined.dropna(subset=["timestamp"])
    combined = combined.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
    return combined.reset_index(drop=True)


def save_partitioned(df: pd.DataFrame, ticker: str) -> None:
    for year_month, month_df in df.groupby("year_month", sort=True):
        path = month_partition_path(ticker, year_month)
        path.parent.mkdir(parents=True, exist_ok=True)
        merged = merge_with_existing(path, month_df.drop(columns=["year_month"]))
        merged.to_parquet(path, index=False)
        print(f"saved {ticker} {year_month}: {len(merged):,} rows -> {path}")


def detect_gaps(day_df: pd.DataFrame, expected_step: pd.Timedelta) -> list[pd.Timestamp]:
    timestamps = day_df["timestamp"].sort_values()
    gaps = timestamps.diff()
    return timestamps[gaps > expected_step].tolist()


def validate_intraday(df: pd.DataFrame, ticker: str, interval: str, prepost: bool) -> None:
    expected = expected_bars_per_session(interval)
    step = pd.Timedelta(interval.replace("m", "min").replace("h", "H"))
    grouped = (
        df[df["session"] != "off_session"]
        .groupby(["trading_date", "session"])
        .size()
        .unstack(fill_value=0)
        .sort_index()
    )
    for session in ["pre_market", "market_hours", "after_hours"]:
        if session not in grouped.columns:
            grouped[session] = 0
    grouped = grouped[["pre_market", "market_hours", "after_hours"]]

    missing_market = grouped[grouped["market_hours"] == 0]
    partial_market = grouped[
        (grouped["market_hours"] > 0) & (grouped["market_hours"] < expected["market_hours"])
    ]
    if prepost:
        no_extended = grouped[
            (grouped["pre_market"] == 0) & (grouped["after_hours"] == 0)
        ]
    else:
        no_extended = pd.DataFrame()

    session_gaps: list[tuple[str, str, pd.Timestamp]] = []
    for (trading_date, session), day_df in df[df["session"] != "off_session"].groupby(["trading_date", "session"]):
        for gap_end in detect_gaps(day_df, step):
            session_gaps.append((str(trading_date), str(session), gap_end))

    print(f"validation {ticker}: {len(df):,} rows across {df['trading_date'].nunique():,} trading dates")
    print("regular-session expected bars per day:", expected["market_hours"])
    print("days with zero market-hours bars:", len(missing_market))
    print("days with partial market-hours coverage:", len(partial_market))
    if prepost:
        print("days with no pre/after-hours bars:", len(no_extended))
    print("detected intra-session timestamp gaps:", len(session_gaps))

    if not missing_market.empty:
        print("sample missing market-hours dates:", ", ".join(missing_market.index.astype(str)[:5]))
    if not partial_market.empty:
        print("sample partial market-hours dates:", ", ".join(partial_market.index.astype(str)[:5]))
    if prepost and not no_extended.empty:
        print("sample no-extended-hours dates:", ", ".join(no_extended.index.astype(str)[:5]))
    if session_gaps:
        preview = [f"{d} {s} -> {ts.isoformat()}" for d, s, ts in session_gaps[:5]]
        print("sample timestamp gaps:")
        for item in preview:
            print(" ", item)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch recent intraday ETF bars from yfinance's free rolling window and "
            "cache them into month-sized parquet files."
        )
    )
    parser.add_argument("--tickers", nargs="+", default=list(DEFAULT_TICKERS))
    parser.add_argument("--interval", default=DEFAULT_INTERVAL)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--no-prepost", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    prepost = not args.no_prepost
    print(
        f"fetching intraday data for {', '.join(args.tickers)} "
        f"interval={args.interval} period={args.period} prepost={prepost}"
    )
    print("note: yfinance intraday history is limited to a recent rolling window, so this script is for ongoing local accumulation.")

    failures: list[str] = []
    for ticker in args.tickers:
        try:
            df = fetch_one(ticker, interval=args.interval, period=args.period, prepost=prepost)
        except Exception as exc:
            print(f"error {ticker}: {exc}")
            failures.append(ticker)
            continue
        if df.empty:
            print(f"empty {ticker}")
            failures.append(ticker)
            continue
        validate_intraday(df, ticker=ticker, interval=args.interval, prepost=prepost)
        save_partitioned(df, ticker=ticker)

    if failures:
        print("failed tickers:", failures)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
