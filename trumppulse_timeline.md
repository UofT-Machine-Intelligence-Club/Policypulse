# TrumpPulse — Model development timeline

## Phase 1: Data collection

### 1.1 Historical tweets (2009–2021)
- [x] Download the CompleteTrumpTweetsArchive from GitHub (CSV format, pre-office and in-office splits)
- [x] Download the Kaggle Trump tweets dataset as a secondary source for cross-validation
- [x] Pull the thetrumparchive.com JSON dump as a third source
- [x] Reconcile all three sources — deduplicate by tweet ID, resolve any missing/conflicting records
- [x] Verify final tweet count is in the ~56K range
- [x] Confirm key fields are present and clean: tweet ID, timestamp (UTC), full text, retweet count, favorite count, source device, isRetweet flag

### 1.2 Truth Social posts (2022–present)
- [x] Pull the CNN auto-updating archive from ix.cnn.io/data/truth-social/truth_archive.json
- [x] Pull the same archive in CSV and parquet formats to compare schema consistency
- [ ] Clone the stiles/trump-truth-social-archive GitHub repo and review the scraper code for understanding the data pipeline
- [x] Strip HTML tags and decode HTML entities from the content field
- [ ] Handle edge cases: image-only posts (no text), reblogs/re-truths, deleted posts
- [x] Verify key fields: post ID, created_at (UTC), clean text, replies_count, reblogs_count, favourites_count, media URLs

### 1.3 Market data — daily
- [x] Download daily OHLCV for SPY, QQQ, DIA using yfinance (2009–present)
- [x] Download daily VIX close using yfinance (^VIX)
- [x] Download S&P sector ETFs for sector-level analysis: XLU, XLB, XLK, XLI, XLF, XLE, XLP, XLY, XLC, SMH
- [x] Verify no gaps in trading day coverage, handle holidays and market closures
- [x] Save all daily data as parquet files with consistent datetime indexing

### 1.4 Market data — intraday
- [x] Choose a no-paid-API path: use `yfinance` for free rolling intraday bars and accumulate locally over time
- [ ] Pull minute-level or 5-minute-level SPY data for the available rolling window and keep appending locally under `data/processed/market/intraday/`
- [ ] Pull equivalent intraday data for QQQ and DIA
- [x] Build a `yfinance`-based intraday caching script to accumulate free data going forward
- [ ] Validate intraday data: check for gaps, after-hours coverage, pre-market coverage
- [x] Save intraday data partitioned by month for manageable file sizes

### 1.5 Supplementary data
- [ ] Get a FRED API key and pull: federal funds rate (FEDFUNDS), CPI (CPIAUCSL), unemployment rate (UNRATE)
- [ ] Compile a complete list of FOMC meeting dates from 2009–present from the Federal Reserve website
- [ ] Compile a list of major known market events (COVID crash, trade war escalation dates, tariff announcements) for use as reference points in EDA
- [ ] Collect earnings season date ranges (typically 2 weeks after each quarter end) for feature engineering later

---

## Phase 2: Data cleaning and unification

### 2.1 Text cleaning
- [x] Remove URLs from all post text
- [x] Remove @mentions and hashtag symbols (keep the text after # and @)
- [x] Remove special characters, emojis, and non-ASCII noise
- [x] Normalize whitespace (collapse multiple spaces, strip leading/trailing)
- [x] Handle ALL CAPS posts — decide whether to lowercase everything or keep case as a feature
- [x] Flag and handle posts that are just media shares with no meaningful text (drop or label separately)

### 2.2 Schema unification
- [x] Create a unified post schema: post_id, datetime (UTC), text, source_platform (twitter/truthsocial), likes, shares, engagement (likes + shares), device, text_length
- [x] Convert all timestamps to UTC with timezone-aware datetime objects
- [x] Sort chronologically and reset index
- [x] Drop posts with fewer than 10 characters of text
- [x] Filter out retweets and re-truths (keep original posts only)
- [x] Log the final count and date range of the unified dataset

### 2.3 Market data alignment
- [x] Merge daily VIX data onto the post dataset by date
- [x] Merge daily SPY/QQQ/DIA close prices onto the post dataset by date
- [x] For intraday data: align each post to the nearest market timestamp at or after post time using merge_asof
- [x] Handle posts outside market hours: map to next market open
- [x] Handle weekend/holiday posts: map to the following trading day's open
- [x] Document every alignment decision for reproducibility

---

## Phase 3: Exploratory data analysis

### 3.1 Post-level EDA
- [ ] Plot posting frequency over time (daily, weekly, monthly) — identify high-activity periods
- [ ] Compare posting patterns across platforms (Twitter vs Truth Social)
- [ ] Analyze time-of-day distribution — when does Trump post most? How does this overlap with market hours?
- [ ] Day-of-week analysis — any patterns in weekend vs weekday posting?
- [ ] Text length distribution — are longer posts more substantive?
- [ ] Device source analysis (Twitter era) — confirm iPhone vs staff device patterns
- [ ] Engagement distribution — how skewed is it? What does the top 1% look like?
- [ ] Word frequency analysis — most common words, bigrams, trigrams
- [ ] Topic clustering — run a quick LDA or BERTopic to see what natural topic groups emerge
- [ ] Identify the most-engaged posts and manually inspect them — are they the ones that moved markets?

### 3.2 Market-level EDA
- [ ] Plot daily returns for SPY, QQQ, DIA over the full period — mark known Trump-related events
- [ ] Plot VIX over time — mark the same events
- [ ] Calculate rolling 20-day realized volatility for SPY — visualize volatility regimes
- [ ] Compare sector ETF returns on days with high-urgency posts vs all other days
- [ ] Distribution of 5min, 30min, 60min SPY returns after posts vs unconditional distribution — are they statistically different?
- [ ] Run a simple t-test: do returns after posts with financial keywords (tariff, china, fed, trade) differ from returns after non-financial posts?

### 3.3 Relationship EDA
- [ ] Scatter plots: post engagement vs absolute market return at various windows
- [ ] Correlation matrix: text_length, engagement, keyword_count, VIX, hour_of_day vs absolute abnormal returns
- [ ] Time series overlay: daily average post sentiment (using a simple off-the-shelf sentiment like VADER or TextBlob as a baseline) vs SPY daily returns
- [ ] Event study plots: average SPY return path in the [-5, +5] day window around the top 50 most-engaged posts
- [ ] Replicate a simplified version of the Zheng & Lucey event study: compute AAR and CAAR for high-urgency posting days across sector ETFs
- [ ] Check if the asymmetry finding holds in our data: do negative-sentiment posts produce larger abnormal returns than positive ones?
- [ ] Analyze whether posts during high-VIX periods produce larger market reactions than posts during calm periods

### 3.4 Baseline model sanity checks
- [ ] Run a simple logistic regression using only keyword flags and VIX to predict market impact — establish a floor for model performance
- [ ] Run VADER sentiment on all posts and check if VADER score alone has any predictive power for returns
- [ ] Check class balance: what percentage of posts are no_move / minor / major under different labeling thresholds?
- [ ] Test different labeling thresholds (0.3σ, 0.5σ, 1.0σ, 1.5σ) and see how class balance and baseline accuracy change
- [ ] Determine if daily returns or intraday returns provide a cleaner signal for labeling

---

## Phase 4: Feature engineering

### 4.1 Text features
- [ ] Generate FinBERT embeddings ([CLS] token, 768-d) for all posts — save as a matrix for reuse
- [ ] Also generate baseline embeddings with regular BERT and sentence-transformers for comparison
- [ ] Extract financial keyword flags: tariff, china, fed, trade, ban, tax, market, sanctions, tariffs, duties
- [ ] Compute keyword density (keyword count / total word count)
- [ ] Flag posts that mention specific companies or tickers by name
- [ ] Flag posts that contain numbers or percentages (often policy-specific)
- [ ] Extract named entities using spaCy (countries, organizations, people) — count of entity types as features

### 4.2 Temporal features
- [ ] is_market_hours (boolean): 9:30 AM – 4:00 PM ET
- [ ] is_premarket (boolean): 4:00 AM – 9:30 AM ET
- [ ] is_afterhours (boolean): 4:00 PM – 8:00 PM ET
- [ ] is_weekend (boolean)
- [ ] hour_of_day (0–23, ET)
- [ ] day_of_week (0–6)
- [ ] days_to_next_FOMC
- [ ] is_earnings_season (boolean)
- [ ] days_since_last_post (captures posting gaps that might signal something brewing)

### 4.3 Market context features
- [ ] VIX level at post time (or most recent close)
- [ ] VIX percentile rank over trailing 60 days
- [ ] SPY return over trailing 5 days (recent market trend)
- [ ] SPY return over trailing 1 day
- [ ] Current SPY distance from 20-day moving average (overbought/oversold proxy)
- [ ] Intraday SPY return so far today at post time (if during market hours)

### 4.4 Behavioral features
- [ ] Posting velocity: number of posts in the prior 1 hour, 6 hours, 24 hours
- [ ] Engagement velocity: likes + shares in first 60 minutes (only available for recent posts, may need to approximate for historical)
- [ ] is_personal_device (iPhone vs other, Twitter era only)
- [ ] Post contains media (image/video) vs text-only
- [ ] Post is a reply vs standalone
- [ ] Post contains ALL CAPS words (count of fully capitalized words)
- [ ] Exclamation mark count (Trump's exclamation usage correlates with intensity)

### 4.5 Feature validation
- [ ] Compute feature importance using a quick random forest on the labeled dataset
- [ ] Check for multicollinearity — drop features with >0.9 correlation
- [ ] Verify no features leak future information (anything derived from post-publication data)
- [ ] Standardize all numerical features using StandardScaler fit only on training data
- [ ] Save the fitted scaler for production inference

---

## Phase 5: Labeling

### 5.1 Return calculation
- [ ] Compute SPY returns at 5min, 30min, 60min, and 1-day windows after each post
- [ ] Compute the same for QQQ and DIA
- [ ] Compute sector ETF returns for sector-level models (later phase)
- [ ] Calculate rolling 20-day daily volatility for normalization
- [ ] Compute abnormal returns: raw return / rolling daily volatility
- [ ] Take the maximum absolute abnormal return across the 5min, 30min, 60min windows as the primary impact measure

### 5.2 Label creation
- [ ] Experiment with multiple threshold configurations and document class distributions for each:
  - Conservative: <0.5σ / 0.5–1.5σ / >1.5σ
  - Moderate: <0.3σ / 0.3–1.0σ / >1.0σ
  - Aggressive: <0.2σ / 0.2–0.8σ / >0.8σ
- [ ] Choose the threshold that gives roughly 85–90% / 8–10% / 2–5% class distribution
- [ ] Also create a binary label (moved / didn't move) as a simpler alternative to test first
- [ ] Also create a continuous regression target (raw abnormal return magnitude) for potential regression approach
- [ ] Assign labels to all posts that have valid return data

### 5.3 Train/val/test split
- [ ] Split chronologically: 70% train, 15% validation, 15% test
- [ ] Verify no temporal leakage: train end date < val start date < test start date
- [ ] Check class distribution is roughly similar across all three splits (it won't be identical because market regimes shift — document any differences)
- [ ] Save train.parquet, val.parquet, test.parquet
- [ ] Log exact date boundaries for reproducibility

---

## Phase 6: Model training

### 6.1 Baseline models
- [ ] Logistic regression on keyword flags + numerical features only (no text embeddings) — establish a non-neural floor
- [ ] Random forest on keyword flags + numerical features — compare to logistic regression
- [ ] Logistic regression on pre-computed FinBERT [CLS] embeddings only (no extra features) — isolate the value of text understanding
- [ ] Logistic regression on FinBERT embeddings + all features — see if features add value over text alone
- [ ] Document precision, recall, F1 (macro), and confusion matrix for every baseline

### 6.2 FinBERT fine-tuning
- [ ] Load ProsusAI/finbert with a fresh 3-class classification head (ignore_mismatched_sizes=True)
- [ ] Build the TrumpPulseModel that concatenates [CLS] embedding with numerical features before the classifier
- [ ] Freeze layers 0–7, train layers 8–11 + classifier head
- [ ] Implement focal loss with inverse-frequency class weights
- [ ] Set up differential learning rates: 2e-5 for BERT layers, 1e-3 for classifier
- [ ] Set up linear warmup scheduler (10% of total steps)
- [ ] Train for 5 epochs with early stopping on validation macro F1
- [ ] Log training loss, validation loss, and validation F1 at each epoch
- [ ] Save best model checkpoint

### 6.3 Hyperparameter tuning
- [ ] Experiment with number of frozen layers (freeze 6 vs 8 vs 10)
- [ ] Experiment with dropout rate (0.1, 0.2, 0.3, 0.5)
- [ ] Experiment with classifier architecture (single linear layer vs two-layer MLP)
- [ ] Experiment with focal loss gamma (1.0, 2.0, 3.0)
- [ ] Experiment with class weight strategies (inverse frequency vs square root inverse frequency vs uniform)
- [ ] Try the binary label (moved vs didn't move) and compare to 3-class performance
- [ ] Try a regression head (predict abnormal return magnitude) instead of classification
- [ ] Document all experiments in a results table

### 6.4 Alternative models to compare
- [ ] Fine-tune regular BERT (bert-base-uncased) with the same setup — quantify the value of FinBERT's financial pre-training
- [ ] Try a GPT-4 zero-shot baseline: send each test post to GPT-4 with a scoring prompt, parse the response, compare precision/recall to FinBERT
- [ ] Try distilbert-base-uncased for a smaller/faster alternative
- [ ] If time permits, try a simple LSTM or CNN on tokenized text as a non-transformer baseline

---

## Phase 7: Evaluation and validation

### 7.1 Classification metrics
- [ ] Generate full classification report on the held-out test set (precision, recall, F1 per class + macro)
- [ ] Generate confusion matrix and visualize
- [ ] Compute ROC-AUC for each class (one-vs-rest)
- [ ] Compare all models side by side in a single table

### 7.2 Scoring and threshold calibration
- [ ] Convert model outputs to continuous impact scores: 0×P(no_move) + 50×P(minor) + 100×P(major)
- [ ] Plot precision-recall curve across notification thresholds (20, 30, 40, ... 90)
- [ ] For each threshold, compute: precision, recall on major class, alerts per day, false alarm rate
- [ ] Select the threshold that balances recall >0.70 on major events with <5 alerts per day
- [ ] Visualize the threshold tradeoff curve

### 7.3 Backtest
- [ ] Simulate the alerting system on the test set: for each post above threshold, record the SPY return in the next 30min and 1 day
- [ ] Compare average absolute return after alerted posts vs average absolute return after all posts — compute lift
- [ ] Check if the model successfully identifies the known big events (tariff announcements, trade deal tweets, COVID-era posts)
- [ ] Compute a simple PnL simulation: if you bought SPY on every "major positive" alert and shorted on every "major negative" alert, what would the returns be?
- [ ] Compute Sharpe ratio of the alert-based strategy vs buy-and-hold

### 7.4 Robustness checks
- [ ] Test on Twitter-era data only vs Truth Social-era data only — does the model generalize across platforms?
- [ ] Test on market-hours posts only vs all posts — does after-hours prediction quality differ?
- [ ] Test on high-VIX periods only vs low-VIX periods — does the model work in both regimes?
- [ ] Permutation test: shuffle the labels and retrain — confirm the model is learning signal, not noise
- [ ] Check for look-ahead bias one final time: manually inspect the top 20 highest-scored posts and verify no feature uses future information

---

## Phase 8: Model packaging and documentation

### 8.1 Artifacts
- [ ] Save final model weights (trumppulse_model.pt)
- [ ] Save tokenizer (trumppulse_tokenizer/ directory)
- [ ] Save fitted StandardScaler (feature_scaler.pkl)
- [ ] Save model config JSON (feature columns, label map, chosen threshold, model name, architecture details)
- [ ] Save the full training/validation/test split metadata (date boundaries, sample counts, class distributions)

### 8.2 Inference function
- [ ] Write a standalone score_post() function that takes raw text + market context dict and returns score, label, probabilities, and should_notify flag
- [ ] Write unit tests: verify known high-impact posts score above threshold, known low-impact posts score below
- [ ] Benchmark inference latency (target: <100ms per post on GPU, <500ms on CPU)
- [ ] Test the function with edge cases: empty text, very long text, non-English text, emoji-only posts

### 8.3 Documentation
- [ ] Write a model card: training data, architecture, performance metrics, known limitations, intended use
- [ ] Document the full data pipeline: sources, cleaning steps, alignment logic, labeling thresholds
- [ ] Document all hyperparameter choices and the experiments that led to them
- [ ] Create a reproducibility guide: exact commands to recreate the dataset, train the model, and evaluate
- [ ] Write a changelog for model versions as retraining happens
