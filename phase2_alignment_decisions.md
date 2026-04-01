# Phase 2 alignment decisions

This document records the schema-unification and market-alignment rules used by `scripts/build_phase2_dataset.py`.

## Unified post schema

The phase 2 unified dataset is written to `data/processed/posts_unified.parquet` with these core columns:

- `post_id`
- `datetime` in UTC
- `text`
- `source_platform`
- `likes`
- `shares`
- `engagement`
- `device`
- `text_length`

The dataset also carries supporting fields used later in feature engineering and filtering:

- `is_repost`
- `has_meaningful_text`
- `is_media_or_share_only`
- `has_all_caps_words`
- `all_caps_word_count`
- `url`
- `raw_text`

## Filtering rules

- Timestamps are converted to timezone-aware UTC datetimes.
- Posts are sorted chronologically and the index is reset.
- Posts with fewer than 10 characters of cleaned text are dropped.
- Twitter retweets are dropped using `isRetweet`.
- Truth Social re-truths/reposts are dropped with a text heuristic: posts whose raw text starts with `RT` or whose cleaned text is only `RT` are treated as reposts.

## Daily market alignment rules

Daily alignment uses the SPY trading calendar as the reference calendar.

- If a post is made on a trading day before 9:30 AM America/New_York, it maps to that same trading day’s open.
- If a post is made during market hours, it maps to that same trading day.
- If a post is made at or after 4:00 PM America/New_York, it maps to the next trading day’s open.
- If a post is made on a weekend or market holiday, it maps to the next trading day’s open.

The aligned output stores:

- `effective_trade_date`
- `alignment_reason`
- `market_session`
- `aligned_market_open_utc`
- `aligned_market_close_utc`

It also merges daily VIX and SPY/QQQ/DIA market columns onto each aligned post.

## Intraday alignment rule

Intraday files are not in the repository yet, but the intended rule for phase 2 is fixed:

- Sort posts and intraday bars by timestamp.
- Use a forward `merge_asof` so each post is aligned to the nearest market timestamp at or after the post time.
- For posts outside market hours, first map the post to the next market open, then run the forward intraday alignment from that timestamp.

That rule matches the daily alignment behavior and is the rule to use once phase 1.4 intraday data is added.
