"""Build unified post and market-aligned datasets for phase 2."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pandas as pd
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
MARKET_DIR = PROCESSED_DIR / "market" / "daily"

TWITTER_INPUT = PROCESSED_DIR / "tweets_cleaned.parquet"
TRUTH_INPUT = PROCESSED_DIR / "truth_social_posts_cleaned.parquet"

UNIFIED_OUTPUT = PROCESSED_DIR / "posts_unified.parquet"
ALIGNED_OUTPUT = PROCESSED_DIR / "posts_market_aligned_daily.parquet"

ET = ZoneInfo("America/New_York")
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16


def parse_market_column(col: object) -> str:
    if isinstance(col, tuple):
        return str(col[0]).lower()
    text = str(col)
    if text.startswith("(") and text.endswith(")"):
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, tuple) and parsed:
                return str(parsed[0]).lower()
        except (ValueError, SyntaxError):
            pass
    return text.lower()


def load_market_daily(ticker: str) -> pd.DataFrame:
    path = MARKET_DIR / f"{ticker}.parquet"
    df = pd.read_parquet(path).copy()
    df.columns = [parse_market_column(col) for col in df.columns]
    df = df.rename(columns={"('date', '')": "date"})
    required = ["ticker", "date", "open", "high", "low", "close", "adj_close", "volume"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"{path} missing columns: {missing}")
    df["date"] = pd.to_datetime(df["date"], utc=True)
    # Daily parquet stores the trade date at midnight UTC as a label, not a market timestamp.
    df["trade_date"] = df["date"].dt.date
    return df[required + ["trade_date"]].sort_values("date").reset_index(drop=True)


def build_twitter_posts(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({
        "post_id": df["id_str"].astype(str),
        "datetime": pd.to_datetime(df["created_at"], utc=True, errors="coerce"),
        "text": df["text_clean"].fillna("").astype(str),
        "source_platform": "twitter",
        "likes": df["favorite_count"].fillna(0),
        "shares": df["retweet_count"].fillna(0),
        "device": df["source_device"].astype("string"),
        "text_length": df["text_length_clean"].fillna(0).astype(int),
        "is_repost": df["isRetweet"].fillna(False).astype(bool),
        "has_meaningful_text": df["has_meaningful_text"].fillna(False).astype(bool),
        "is_media_or_share_only": df["is_media_or_share_only"].fillna(False).astype(bool),
        "has_all_caps_words": df["has_all_caps_words"].fillna(False).astype(bool),
        "all_caps_word_count": df["all_caps_word_count"].fillna(0).astype(int),
        "url": pd.Series(pd.NA, index=df.index, dtype="string"),
        "raw_text": df["text_raw"].fillna("").astype(str),
    })
    out["engagement"] = out["likes"] + out["shares"]
    return out


def detect_truthsocial_repost(df: pd.DataFrame) -> pd.Series:
    raw = df["text_raw"].fillna("").astype(str)
    cleaned = df["text_clean"].fillna("").astype(str)
    return raw.str.startswith("RT") | cleaned.eq("RT")


def build_truth_posts(df: pd.DataFrame) -> pd.DataFrame:
    repost = detect_truthsocial_repost(df)
    out = pd.DataFrame({
        "post_id": df["post_id"].astype(str),
        "datetime": pd.to_datetime(df["created_at"], utc=True, errors="coerce"),
        "text": df["text_clean"].fillna("").astype(str),
        "source_platform": "truthsocial",
        "likes": df["favourites_count"].fillna(0),
        "shares": df["reblogs_count"].fillna(0),
        "device": pd.Series(pd.NA, index=df.index, dtype="string"),
        "text_length": df["text_length_clean"].fillna(0).astype(int),
        "is_repost": repost.astype(bool),
        "has_meaningful_text": df["has_meaningful_text"].fillna(False).astype(bool),
        "is_media_or_share_only": df["is_media_or_share_only"].fillna(False).astype(bool),
        "has_all_caps_words": df["has_all_caps_words"].fillna(False).astype(bool),
        "all_caps_word_count": df["all_caps_word_count"].fillna(0).astype(int),
        "url": df["url"].astype("string"),
        "raw_text": df["text_raw"].fillna("").astype(str),
    })
    out["engagement"] = out["likes"] + out["shares"]
    return out


def next_trading_date(current_date, trading_dates: list) -> object:
    idx = trading_dates.searchsorted(current_date)
    if idx >= len(trading_dates):
        return pd.NaT
    return trading_dates[idx]


def effective_market_date(datetimes: pd.Series, trading_dates: pd.Index) -> pd.DataFrame:
    local = datetimes.dt.tz_convert(ET)
    local_dates = pd.Index(local.dt.date)
    local_times = local.dt.time
    trading_set = set(trading_dates.tolist())

    aligned_dates = []
    reasons = []
    sessions = []

    for dt_local, local_date, local_time in zip(local, local_dates, local_times):
        if pd.isna(dt_local):
            aligned_dates.append(pd.NaT)
            reasons.append(pd.NA)
            sessions.append(pd.NA)
            continue

        if local_date in trading_set:
            if (local_time.hour, local_time.minute) < (MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE):
                aligned_dates.append(local_date)
                reasons.append("same_trading_day_preopen")
                sessions.append("pre_market")
            elif (local_time.hour, local_time.minute) < (MARKET_CLOSE_HOUR, 0):
                aligned_dates.append(local_date)
                reasons.append("same_trading_day_market_hours")
                sessions.append("market_hours")
            else:
                next_date = next_trading_date(local_date, trading_dates)
                next_idx = trading_dates.searchsorted(local_date) + 1
                aligned_dates.append(trading_dates[next_idx] if next_idx < len(trading_dates) else pd.NaT)
                reasons.append("next_trading_day_after_close")
                sessions.append("after_hours")
        else:
            aligned_dates.append(next_trading_date(local_date, trading_dates))
            reasons.append("next_trading_day_weekend_or_holiday")
            sessions.append("market_closed")

    return pd.DataFrame({
        "post_datetime_et": local,
        "post_date_et": local.dt.date.astype("string"),
        "post_time_et": local.dt.strftime("%H:%M:%S"),
        "market_session": sessions,
        "effective_trade_date": pd.Series(aligned_dates, dtype="object").astype("string"),
        "alignment_reason": reasons,
    })


def add_market_open_close_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    trade_dt = pd.to_datetime(out["effective_trade_date"], errors="coerce")
    out["effective_trade_date"] = trade_dt.dt.date.astype("string")
    open_local = pd.to_datetime(out["effective_trade_date"] + " 09:30:00").dt.tz_localize(ET, nonexistent="shift_forward", ambiguous="NaT")
    close_local = pd.to_datetime(out["effective_trade_date"] + " 16:00:00").dt.tz_localize(ET, nonexistent="shift_forward", ambiguous="NaT")
    out["aligned_market_open_utc"] = open_local.dt.tz_convert("UTC")
    out["aligned_market_close_utc"] = close_local.dt.tz_convert("UTC")
    return out


def align_intraday_forward(posts: pd.DataFrame, intraday: pd.DataFrame, timestamp_col: str = "timestamp") -> pd.DataFrame:
    """Align posts to the nearest intraday market timestamp at or after each post time."""
    left = posts.sort_values("aligned_market_open_utc").copy()
    right = intraday.sort_values(timestamp_col).copy()
    left["intraday_lookup_ts_utc"] = left["datetime"].where(
        left["market_session"] == "market_hours",
        left["aligned_market_open_utc"],
    )
    right[timestamp_col] = pd.to_datetime(right[timestamp_col], utc=True, errors="coerce")
    return pd.merge_asof(
        left,
        right,
        left_on="intraday_lookup_ts_utc",
        right_on=timestamp_col,
        direction="forward",
    )


def prepare_unified_posts() -> pd.DataFrame:
    twitter = build_twitter_posts(pd.read_parquet(TWITTER_INPUT))
    truth = build_truth_posts(pd.read_parquet(TRUTH_INPUT))
    posts = pd.concat([twitter, truth], ignore_index=True)
    posts["datetime"] = pd.to_datetime(posts["datetime"], utc=True, errors="coerce")
    posts = posts.dropna(subset=["datetime"]).copy()
    posts = posts[~posts["is_repost"]].copy()
    posts = posts[posts["text_length"] >= 10].copy()
    posts = posts.sort_values("datetime").reset_index(drop=True)
    return posts


def merge_daily_market(posts: pd.DataFrame) -> pd.DataFrame:
    spy = load_market_daily("SPY")
    qqq = load_market_daily("QQQ")
    dia = load_market_daily("DIA")
    vix = load_market_daily("VIX")

    trade_dates = pd.Index(spy["trade_date"].sort_values().unique())
    alignment = effective_market_date(posts["datetime"], trade_dates)
    aligned = pd.concat([posts.reset_index(drop=True), alignment], axis=1)
    aligned = add_market_open_close_timestamps(aligned)

    def suffix_market(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
        renamed = df.rename(columns={
            "open": f"{prefix}_open",
            "high": f"{prefix}_high",
            "low": f"{prefix}_low",
            "close": f"{prefix}_close",
            "adj_close": f"{prefix}_adj_close",
            "volume": f"{prefix}_volume",
        }).copy()
        renamed["effective_trade_date"] = renamed["trade_date"].astype("string")
        return renamed.drop(columns=["ticker", "date", "trade_date"])

    aligned = aligned.merge(suffix_market(vix, "vix"), on="effective_trade_date", how="left")
    aligned = aligned.merge(suffix_market(spy, "spy"), on="effective_trade_date", how="left")
    aligned = aligned.merge(suffix_market(qqq, "qqq"), on="effective_trade_date", how="left")
    aligned = aligned.merge(suffix_market(dia, "dia"), on="effective_trade_date", how="left")
    return aligned


def log_summary(unified: pd.DataFrame, aligned: pd.DataFrame) -> None:
    print("unified posts:", len(unified))
    print("date range:", unified["datetime"].min(), "to", unified["datetime"].max())
    print("platform counts:")
    print(unified["source_platform"].value_counts().to_string())
    print("alignment reasons:")
    print(aligned["alignment_reason"].value_counts(dropna=False).to_string())
    print("missing SPY close:", int(aligned["spy_close"].isna().sum()))


def main() -> int:
    unified = prepare_unified_posts()
    aligned = merge_daily_market(unified)

    unified.to_parquet(UNIFIED_OUTPUT, index=False)
    aligned.to_parquet(ALIGNED_OUTPUT, index=False)

    log_summary(unified, aligned)
    print(f"saved -> {UNIFIED_OUTPUT}")
    print(f"saved -> {ALIGNED_OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
