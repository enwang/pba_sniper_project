# PBA Eval

This folder is for testing PBA-style rules against actual X posts instead of tuning by feel.

## Inputs

`posts.csv`

Use the same columns as `posts_example.csv`:

- `datetime_et`: X post time in Eastern time.
- `kind`: `FL` for focus-list posts, `BUY` for execution posts.
- `tickers`: space-separated tickers for FL posts.
- `buy_ticker`, `buy_price`, `stop_price`: filled for BUY posts.
- `text`: original post text.

`prices/TICKER.csv`

One CSV per ticker, plus `prices/SPY.csv`. Columns:

- `Date`
- `Open`
- `High`
- `Low`
- `Close`
- `Volume` optional

Daily data is enough. The evaluator uses the close of the FL post date to judge next-day watch/setup levels.

## Quick Text Import

If browser extraction is flaky, paste copied X posts into:

`pba_eval/raw_x_posts.txt`

Separate posts with blank lines, then run:

```bash
python3 pba_eval/parse_x_text.py --date "2026-08-14 09:35:58"
```

The parser is intentionally conservative. After it creates `posts.csv`, fix any missing timestamps or tickers manually before running the eval.

## Run

```bash
python3 pba_eval/eval_pba_rules.py
```

## Metrics

- `FL recall`: among tickers in PBA FL posts, how many our rules would at least classify as watch candidates.
- `Buy match`: for next-day BUY posts, whether the actual buy price was near one of our prior-day levels:
  - `PD low reclaim`
  - `10MA retest`
  - `20MA retest`
  - `50MA reclaim`

This separates candidate selection from execution timing.
