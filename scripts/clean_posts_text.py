"""Clean Trump post text for phase 2.1 and write normalized parquet outputs."""

import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"

TWITTER_INPUT = PROCESSED_DIR / "tweets_combined.parquet"
TRUTH_INPUT = PROCESSED_DIR / "truth_social_posts.parquet"
TWITTER_OUTPUT = PROCESSED_DIR / "tweets_cleaned.parquet"
TRUTH_OUTPUT = PROCESSED_DIR / "truth_social_posts_cleaned.parquet"

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
MENTION_RE = re.compile(r"(?<!\w)@([A-Za-z0-9_]+)")
HASHTAG_RE = re.compile(r"(?<!\w)#([A-Za-z0-9_]+)")
NON_ASCII_RE = re.compile(r"[^\x00-\x7F]+")
NON_TEXT_RE = re.compile(r"[^A-Za-z0-9\s]")
WHITESPACE_RE = re.compile(r"\s+")
ALL_CAPS_WORD_RE = re.compile(r"\b[A-Z]{2,}\b")
MEANINGFUL_ALPHA_RE = re.compile(r"[A-Za-z]{3,}")


def strip_outer_quotes(text: str) -> str:
    stripped = text.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {'"', "'"}:
        return stripped[1:-1].strip()
    return stripped


def normalize_unicode_to_ascii(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return normalized.encode("ascii", "ignore").decode("ascii")


def clean_text(text: str) -> str:
    if not isinstance(text, str):
        return ""

    cleaned = strip_outer_quotes(text)
    cleaned = cleaned.replace("’", "'").replace("“", '"').replace("”", '"')
    cleaned = normalize_unicode_to_ascii(cleaned)
    cleaned = URL_RE.sub(" ", cleaned)
    cleaned = MENTION_RE.sub(r"\1", cleaned)
    cleaned = HASHTAG_RE.sub(r"\1", cleaned)
    cleaned = cleaned.replace("&amp;", "and")
    cleaned = NON_TEXT_RE.sub(" ", cleaned)
    cleaned = WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned


def has_meaningful_text(text: str) -> bool:
    if not text:
        return False
    return bool(MEANINGFUL_ALPHA_RE.search(text))


def classify_empty_or_share_post(row: pd.Series) -> bool:
    text = row["text_clean"]
    has_media = bool(row.get("has_media", False))
    if not has_meaningful_text(text):
        return True
    if has_media and len(text) < 10:
        return True
    return False


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    enriched = df.copy()
    enriched["text_raw"] = enriched["text"].fillna("").astype(str)
    enriched["text_clean"] = enriched["text_raw"].map(clean_text)
    enriched["text_lower"] = enriched["text_clean"].str.lower()
    enriched["text_length_clean"] = enriched["text_clean"].str.len()
    enriched["all_caps_word_count"] = enriched["text_clean"].str.count(ALL_CAPS_WORD_RE)
    enriched["has_all_caps_words"] = enriched["all_caps_word_count"] > 0
    enriched["has_meaningful_text"] = enriched["text_clean"].map(has_meaningful_text)
    enriched["is_media_or_share_only"] = enriched.apply(classify_empty_or_share_post, axis=1)
    return enriched


def log_summary(name: str, df: pd.DataFrame) -> None:
    print(f"\n{name}")
    print(f"records: {len(df):,}")
    print("empty/non-meaningful:", int((~df["has_meaningful_text"]).sum()))
    print("media/share only:", int(df["is_media_or_share_only"].sum()))
    print("all caps posts:", int(df["has_all_caps_words"].sum()))


def main() -> int:
    twitter = pd.read_parquet(TWITTER_INPUT)
    truth = pd.read_parquet(TRUTH_INPUT)

    twitter_clean = enrich(twitter)
    truth_clean = enrich(truth)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    twitter_clean.to_parquet(TWITTER_OUTPUT, index=False)
    truth_clean.to_parquet(TRUTH_OUTPUT, index=False)

    log_summary("twitter", twitter_clean)
    log_summary("truthsocial", truth_clean)
    print(f"\nsaved -> {TWITTER_OUTPUT}")
    print(f"saved -> {TRUTH_OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
