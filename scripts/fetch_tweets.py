import json
import sys
from pathlib import Path
from typing import Iterable, List

import pandas as pd
import requests

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"

COMPLETE_CSV_URLS = {
    "realDonaldTrump_in_office.csv": "https://raw.githubusercontent.com/MarkHershey/CompleteTrumpTweetsArchive/master/data/realDonaldTrump/realDonaldTrump_in_office.csv",
    "realDonaldTrump_bf_office.csv": "https://raw.githubusercontent.com/MarkHershey/CompleteTrumpTweetsArchive/master/data/realDonaldTrump/realDonaldTrump_bf_office.csv",
}

TRUMP_ARCHIVE_YEARS: Iterable[int] = range(2009, 2022)
TRUMP_ARCHIVE_TEMPLATE = (
    "https://raw.githubusercontent.com/bpb27/trump_tweet_data_archive/master/condensed_{year}.json"
)

KAGGLE_PLACEHOLDER = RAW_DIR / "kaggle" / "kaggle_trump_tweets.csv"


def download_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    print(f"downloaded {dest.name} -> {dest.stat().st_size/1024:.1f} KB")


def load_complete_archive() -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    for name, url in COMPLETE_CSV_URLS.items():
        dest = RAW_DIR / "complete_archive" / name
        if not dest.exists():
            download_file(url, dest)
        df = pd.read_csv(dest)
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df = df.rename(
        columns={
            "id": "id_str",
            "date": "created_at",
            "favorites": "favorite_count",
            "retweets": "retweet_count",
            "device": "source",
        }
    )
    df["source_platform"] = "twitter"
    return df


def load_trump_archive_json() -> pd.DataFrame:
    records: List[pd.DataFrame] = []
    for year in TRUMP_ARCHIVE_YEARS:
        url = TRUMP_ARCHIVE_TEMPLATE.format(year=year)
        dest = RAW_DIR / "trump_archive_json" / f"condensed_{year}.json"
        if not dest.exists():
            download_file(url, dest)
        with dest.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not data:
            continue
        df = pd.DataFrame(data)
        records.append(df)
    if not records:
        return pd.DataFrame()
    df = pd.concat(records, ignore_index=True)
    df = df.rename(columns={"source": "source_device"})
    df["source_platform"] = "twitter"
    return df


def load_kaggle_if_present() -> pd.DataFrame:
    if not KAGGLE_PLACEHOLDER.exists():
        print(f"skipping Kaggle (place file at {KAGGLE_PLACEHOLDER})")
        return pd.DataFrame()
    df = pd.read_csv(KAGGLE_PLACEHOLDER)
    df = df.rename(
        columns={
            "id": "id_str",
            "date": "created_at",
            "favorites": "favorite_count",
            "retweets": "retweet_count",
        }
    )
    df["source_platform"] = "twitter"
    return df


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    cols = {
        "id_str": None,
        "text": None,
        "created_at": None,
        "retweet_count": 0,
        "favorite_count": 0,
        "source_device": None,
        "source_platform": None,
        "isRetweet": False,
    }
    for col, default in cols.items():
        if col not in df.columns:
            df[col] = default
    df["id_str"] = df["id_str"].astype(str)
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True)
    df["retweet_count"] = pd.to_numeric(df["retweet_count"], errors="coerce").fillna(0).astype(int)
    df["favorite_count"] = pd.to_numeric(df["favorite_count"], errors="coerce").fillna(0).astype(int)
    df["text"] = df["text"].fillna("")
    return df[
        [
            "id_str",
            "created_at",
            "text",
            "retweet_count",
            "favorite_count",
            "source_device",
            "source_platform",
            "isRetweet",
        ]
    ]


def main() -> int:
    complete_df = normalize(load_complete_archive())
    archive_df = normalize(load_trump_archive_json())
    kaggle_df = normalize(load_kaggle_if_present())

    combined = pd.concat([complete_df, archive_df, kaggle_df], ignore_index=True)
    if combined.empty:
        print("No data loaded. Provide Kaggle file or check network.")
        return 1

    combined = combined.drop_duplicates(subset=["id_str"])
    combined = combined.sort_values("created_at")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "tweets_combined.parquet"
    combined.to_parquet(out_path, index=False)

    print(f"combined tweets: {len(combined):,} -> {out_path}")
    print("date range:", combined["created_at"].min(), "to", combined["created_at"].max())
    print("source breakdown:\n", combined["source_platform"].value_counts(dropna=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
