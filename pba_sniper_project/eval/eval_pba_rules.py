#!/usr/bin/env python3
import argparse
import csv
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


RS_NEAR_HIGH_PCT = 10.0
MIN_WEIGHTED_RP = 0.0
MAX_BELOW_63D_HIGH_PCT = 15.0
MAX_ABOVE_10MA_PCT = 5.0
MAX_ABOVE_20MA_PCT = 9.0
LEVEL_BUFFER_PCT = 0.15
BUY_MATCH_TOLERANCE_PCT = 1.25
BUY_LOOSE_MATCH_TOLERANCE_PCT = 2.0
RECLAIM_WATCH_DISTANCE_PCT = 3.0
PD_LOW_WATCH_DISTANCE_PCT = 2.0


@dataclass
class Bar:
    date: str
    open: float
    high: float
    low: float
    close: float


def read_prices(path: Path) -> list[Bar]:
    rows: list[Bar] = []
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            try:
                rows.append(
                    Bar(
                        date=row["Date"],
                        open=float(row["Open"]),
                        high=float(row["High"]),
                        low=float(row["Low"]),
                        close=float(row["Close"]),
                    )
                )
            except (KeyError, ValueError):
                continue
    rows.sort(key=lambda x: x.date)
    return rows


def sma(vals: list[float], end: int, length: int) -> float | None:
    if end + 1 < length:
        return None
    return sum(vals[end + 1 - length : end + 1]) / length


def ema_series(vals: list[float], length: int) -> list[float | None]:
    out: list[float | None] = [None] * len(vals)
    if len(vals) < length:
        return out
    alpha = 2.0 / (length + 1.0)
    seed = sum(vals[:length]) / length
    out[length - 1] = seed
    prev = seed
    for i in range(length, len(vals)):
        prev = vals[i] * alpha + prev * (1 - alpha)
        out[i] = prev
    return out


def roc(vals: list[float], end: int, length: int) -> float | None:
    if end < length or vals[end - length] == 0:
        return None
    return (vals[end] / vals[end - length] - 1.0) * 100.0


def pct_dist(a: float, b: float) -> float:
    return abs(a / b - 1.0) * 100.0 if b else math.inf


def trading_date_on_or_before(rows: list[Bar], date: str) -> int | None:
    idx = None
    for i, bar in enumerate(rows):
        if bar.date <= date:
            idx = i
        else:
            break
    return idx


def next_trading_idx(rows: list[Bar], idx: int) -> int | None:
    nxt = idx + 1
    return nxt if nxt < len(rows) else None


def state_for(ticker_rows: list[Bar], spy_rows: list[Bar], idx: int) -> dict:
    closes = [x.close for x in ticker_rows]
    highs = [x.high for x in ticker_rows]
    lows = [x.low for x in ticker_rows]
    spy_closes = [x.close for x in spy_rows]
    date = ticker_rows[idx].date
    spy_idx = trading_date_on_or_before(spy_rows, date)
    if spy_idx is None:
        return {"state": "MISSING_SPY"}

    ema10 = ema_series(closes, 10)[idx]
    ema20 = ema_series(closes, 20)[idx]
    ema50 = ema_series(closes, 50)[idx]
    sma10_v = sma(closes, idx, 10)
    sma20_v = sma(closes, idx, 20)
    sma50_v = sma(closes, idx, 50)
    sma50_old = sma(closes, idx - 10, 50) if idx >= 10 else None
    if None in (ema10, ema20, ema50, sma10_v, sma20_v, sma50_v, sma50_old):
        return {"state": "INSUFFICIENT_HISTORY"}

    rocs = []
    for length, weight in ((63, 0.40), (126, 0.20), (189, 0.20), (252, 0.20)):
        stock_roc = roc(closes, idx, length)
        spy_roc = roc(spy_closes, spy_idx, length)
        if stock_roc is None or spy_roc is None:
            return {"state": "INSUFFICIENT_HISTORY"}
        rocs.append(weight * (stock_roc - spy_roc))
    weighted_rp = sum(rocs)

    rs_vals = []
    for offset in range(62, -1, -1):
        ti = idx - offset
        si = trading_date_on_or_before(spy_rows, ticker_rows[ti].date)
        if ti < 0 or si is None:
            return {"state": "INSUFFICIENT_HISTORY"}
        rs_vals.append(ticker_rows[ti].close / spy_rows[si].close)
    rs_now = rs_vals[-1]
    rs_near_high = rs_now >= max(rs_vals) * (1.0 - RS_NEAR_HIGH_PCT / 100.0)
    rs_ok = weighted_rp >= MIN_WEIGHTED_RP or rs_near_high
    rs_power_ok = weighted_rp >= 50.0

    high_63 = max(highs[idx - 62 : idx + 1])
    near_63d_high = closes[idx] >= high_63 * (1.0 - MAX_BELOW_63D_HIGH_PCT / 100.0)
    ma20_high = max(float(ema20), float(sma20_v))
    ma50_high = max(float(ema50), float(sma50_v))
    ma20_low = min(float(ema20), float(sma20_v))
    ma50_low = min(float(ema50), float(sma50_v))
    above_20ma = closes[idx] > ma20_high
    above_50ma = closes[idx] > ma50_high
    near_20ma = pct_dist(closes[idx], ma20_high) <= RECLAIM_WATCH_DISTANCE_PCT or ma20_low <= closes[idx] <= ma20_high
    near_50ma = pct_dist(closes[idx], ma50_high) <= RECLAIM_WATCH_DISTANCE_PCT or ma50_low <= closes[idx] <= ma50_high
    near_pd_low = pct_dist(closes[idx], lows[idx]) <= PD_LOW_WATCH_DISTANCE_PCT
    sma50_rising = float(sma50_v) > float(sma50_old)
    pba_recent_ok = above_20ma and above_50ma and sma50_rising and near_63d_high
    reclaim_watch_ok = rs_ok and (near_20ma or near_50ma)
    ma50_reclaim_watch_ok = above_20ma and near_50ma
    power_leader_watch_ok = rs_power_ok
    level_setup_ok = near_pd_low or near_20ma or near_50ma

    ma10_ref = max(float(ema10), float(sma10_v))
    ma20_ref = max(float(ema20), float(sma20_v))
    dist10 = (closes[idx] / ma10_ref - 1.0) * 100.0
    dist20 = (closes[idx] / ma20_ref - 1.0) * 100.0
    too_extended = pba_recent_ok and rs_ok and (dist10 > MAX_ABOVE_10MA_PCT or dist20 > MAX_ABOVE_20MA_PCT)

    if (pba_recent_ok and rs_ok and not too_extended) or level_setup_ok:
        state = "SETUP"
    elif (rs_ok and above_20ma) or reclaim_watch_ok or ma50_reclaim_watch_ok or power_leader_watch_ok:
        state = "WATCH_ONLY"
    else:
        state = "NO_EDGE"

    buffer = LEVEL_BUFFER_PCT / 100.0
    levels = {
        "PD low reclaim": (lows[idx], lows[idx] * (1.0 - buffer)),
        "10MA retest": (min(float(ema10), float(sma10_v)), max(float(ema10), float(sma10_v))),
        "20MA retest": (min(float(ema20), float(sma20_v)), max(float(ema20), float(sma20_v))),
        "50MA reclaim": (min(float(ema50), float(sma50_v)), max(float(ema50), float(sma50_v))),
    }
    return {
        "state": state,
        "weighted_rp": weighted_rp,
        "rs_near_high": rs_near_high,
        "rs_power_ok": rs_power_ok,
        "above_20ma": above_20ma,
        "above_50ma": above_50ma,
        "near_20ma": near_20ma,
        "near_50ma": near_50ma,
        "near_pd_low": near_pd_low,
        "sma50_rising": sma50_rising,
        "near_63d_high": near_63d_high,
        "too_extended": too_extended,
        "dist10": dist10,
        "dist20": dist20,
        "levels": levels,
    }


def closest_level(levels: dict, buy_price: float) -> tuple[str, float]:
    best_name = ""
    best_dist = math.inf
    for name, vals in levels.items():
        if name == "PD low reclaim":
            ref = vals[0]
            dist = pct_dist(buy_price, ref)
        else:
            low, high = vals
            if low <= buy_price <= high:
                dist = 0.0
            else:
                dist = min(pct_dist(buy_price, low), pct_dist(buy_price, high))
        if dist < best_dist:
            best_name = name
            best_dist = dist
    return best_name, best_dist


def parse_date(datetime_et: str) -> str:
    return datetime.strptime(datetime_et[:19], "%Y-%m-%d %H:%M:%S").date().isoformat()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--posts", default="pba_eval/posts.csv")
    ap.add_argument("--prices", default="pba_eval/prices")
    ap.add_argument("--out", default="pba_eval/eval_report.csv")
    args = ap.parse_args()

    posts_path = Path(args.posts)
    prices_dir = Path(args.prices)
    if not posts_path.exists():
        raise SystemExit(f"Missing {posts_path}. Copy posts_example.csv to posts.csv and fill real X posts.")

    with posts_path.open(newline="") as f:
        posts = list(csv.DictReader(f))

    price_cache: dict[str, list[Bar]] = {}

    def prices(ticker: str) -> list[Bar] | None:
        ticker = ticker.upper()
        if ticker not in price_cache:
            path = prices_dir / f"{ticker}.csv"
            if not path.exists():
                return None
            price_cache[ticker] = read_prices(path)
        return price_cache[ticker]

    spy = prices("SPY")
    if not spy:
        raise SystemExit("Missing pba_eval/prices/SPY.csv")

    report = []
    fl_total = fl_watch_hits = 0
    buy_total = buy_matches = 0
    buy_strict_total = buy_strict_matches = 0
    buy_candidate_total = buy_candidate_hits = 0
    buy_loose_matches = 0

    for post in posts:
        kind = post.get("kind", "").upper()
        if kind == "FL":
            fl_date = parse_date(post["datetime_et"])
            for ticker in post.get("tickers", "").replace(",", " ").split():
                rows = prices(ticker)
                if not rows:
                    report.append({"kind": "FL", "date": fl_date, "ticker": ticker, "state": "MISSING_PRICE"})
                    continue
                idx = trading_date_on_or_before(rows, fl_date)
                if idx is None:
                    continue
                st = state_for(rows, spy, idx)
                state = st["state"]
                fl_total += 1
                fl_watch_hits += state in ("SETUP", "WATCH_ONLY")
                report.append({"kind": "FL", "date": fl_date, "ticker": ticker, "state": state, "rp": round(st.get("weighted_rp", math.nan), 2)})
        elif kind == "BUY":
            ticker = post.get("buy_ticker") or post.get("tickers", "").split()[0]
            rows = prices(ticker)
            if not rows:
                report.append({"kind": "BUY", "date": parse_date(post["datetime_et"]), "ticker": ticker, "state": "MISSING_PRICE"})
                continue
            buy_date = parse_date(post["datetime_et"])
            buy_idx = trading_date_on_or_before(rows, buy_date)
            if buy_idx is None or buy_idx == 0:
                continue
            eval_idx = buy_idx - 1
            st = state_for(rows, spy, eval_idx)
            try:
                buy_price = float(post["buy_price"])
            except ValueError:
                continue
            level_name, dist = closest_level(st.get("levels", {}), buy_price)
            buy_total += 1
            matched = dist <= BUY_MATCH_TOLERANCE_PCT
            buy_matches += matched
            if st["state"] not in ("MISSING_PRICE", "INSUFFICIENT_HISTORY"):
                buy_strict_total += 1
                buy_strict_matches += matched
                buy_loose_matches += dist <= BUY_LOOSE_MATCH_TOLERANCE_PCT
                buy_candidate_total += 1
                buy_candidate_hits += st["state"] in ("SETUP", "WATCH_ONLY")
            report.append(
                {
                    "kind": "BUY",
                    "date": buy_date,
                    "ticker": ticker,
                    "state": st["state"],
                    "buy_price": buy_price,
                    "closest_level": level_name,
                    "level_dist_pct": round(dist, 2),
                    "matched": matched,
                    "rp": round(st.get("weighted_rp", math.nan), 2),
                    "rs_near_high": st.get("rs_near_high", ""),
                    "above_20ma": st.get("above_20ma", ""),
                    "above_50ma": st.get("above_50ma", ""),
                    "near_20ma": st.get("near_20ma", ""),
                    "near_50ma": st.get("near_50ma", ""),
                    "near_63d_high": st.get("near_63d_high", ""),
                    "too_extended": st.get("too_extended", ""),
                }
            )

    out_path = Path(args.out)
    fields = sorted({k for row in report for k in row.keys()})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(report)

    fl_recall = fl_watch_hits / fl_total if fl_total else math.nan
    buy_match_rate = buy_matches / buy_total if buy_total else math.nan
    print(f"FL recall: {fl_watch_hits}/{fl_total} = {fl_recall:.1%}" if fl_total else "FL recall: no FL cases")
    print(f"Buy match: {buy_matches}/{buy_total} = {buy_match_rate:.1%}" if buy_total else "Buy match: no BUY cases")
    if buy_strict_total:
        print(f"Buy candidate recall: {buy_candidate_hits}/{buy_candidate_total} = {buy_candidate_hits / buy_candidate_total:.1%}")
        print(f"Buy level strict <= {BUY_MATCH_TOLERANCE_PCT}%: {buy_strict_matches}/{buy_strict_total} = {buy_strict_matches / buy_strict_total:.1%}")
        print(f"Buy level loose <= {BUY_LOOSE_MATCH_TOLERANCE_PCT}%: {buy_loose_matches}/{buy_strict_total} = {buy_loose_matches / buy_strict_total:.1%}")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
