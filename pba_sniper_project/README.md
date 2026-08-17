# PBA Sniper Project

Goal: build and evaluate a TradingView indicator that finds PBA-style watch/setup levels from a Focus/Strong watchlist.

## Current Artifacts

- `pine/PBA_watchlist_sniper_v2.pine`
  - Current TradingView indicator.
  - Only visible input is `Debug Mode`.
  - Debug on: shows `PBA SETUP`, `WATCH ONLY`, or `NO EDGE`.
  - Debug off: only shows real `PBA SETUP`.

- `eval/eval_pba_rules.py`
  - Replays rules against historical PBA `FL` and `Bought` posts.
  - Scores whether FL tickers become watch candidates.
  - Scores whether next-day buy prices are close to predicted levels.

- `eval/parse_x_text.py`
  - Converts copied X post text into `posts.csv` format.

- `eval/posts_example.csv`
  - Example input schema for real PBA posts.

## Eval Loop

1. Collect real PBA posts:
   - Previous-day `FL` posts.
   - Next-day `Bought` posts with buy price and stop.

2. Put copied X post text into:
   - `eval/raw_x_posts.txt`

3. Parse posts:

```bash
python3 eval/parse_x_text.py --date "2026-08-14 09:35:58"
```

4. Add daily price files:
   - `eval/prices/SPY.csv`
   - `eval/prices/TICKER.csv`

5. Run eval:

```bash
python3 eval/eval_pba_rules.py
```

## Interpretation

- `PBA SETUP`: strong enough and not extended; tomorrow levels are actionable watch zones.
- `WATCH ONLY`: likely FL-style candidate, but no clean buy level yet.
- `NO EDGE`: currently not enough RS/trend structure.

The next iteration should tune rules only after reviewing eval misses:

- FL miss: ticker should have been watch-only/setup but was rejected.
- False watch: ticker was not in FL but rules included it.
- Buy-level miss: ticker was right, but predicted level was far from PBA's actual buy.
