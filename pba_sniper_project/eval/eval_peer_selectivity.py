#!/usr/bin/env python3
import argparse
import csv
import math
from datetime import datetime, timedelta
from pathlib import Path

from eval_pba_rules import parse_date, read_prices, state_for, trading_date_on_or_before


THEMES: dict[str, list[str]] = {
    "ai_infra": ["VST", "CEG", "GEV", "ETN", "NRG", "VRT", "STRL", "PWR", "SMR", "OKLO"],
    "semis_storage": [
        "STX",
        "WDC",
        "NTAP",
        "PSTG",
        "SNDK",
        "MU",
        "AMD",
        "NVDA",
        "AVGO",
        "ARM",
        "ASML",
        "MRVL",
        "INTC",
        "QCOM",
        "TER",
        "AMAT",
        "LRCX",
        "KLAC",
        "ALAB",
        "MPWR",
        "MCHP",
        "CRDO",
        "COHR",
        "LITE",
    ],
    "software_ai": [
        "PLTR",
        "TEAM",
        "NOW",
        "MSFT",
        "AMZN",
        "NET",
        "DDOG",
        "CRWD",
        "MDB",
        "SNOW",
        "CRM",
        "ORCL",
        "ADBE",
        "PANW",
        "OKTA",
        "DOCN",
        "RBRK",
        "TOST",
        "APP",
        "IOT",
    ],
    "crypto": ["MSTR", "COIN", "HOOD", "CRCL", "IBIT", "MARA", "RIOT", "CLSK", "HUT", "CORZ"],
    "retail_consumer": ["AEO", "BROS", "CAVA", "FIGS", "LULU", "RH", "RVLV", "TGTX", "UBER"],
}


def load_posts(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def mentioned_near(posts: list[dict], ticker: str, date: str, lookahead_days: int) -> tuple[bool, str]:
    start = datetime.fromisoformat(date).date()
    end = start + timedelta(days=lookahead_days)
    hits = []
    for post in posts:
        try:
            post_date = datetime.fromisoformat(parse_date(post["datetime_et"])).date()
        except Exception:
            continue
        if not (start <= post_date <= end):
            continue
        tickers = set(post.get("tickers", "").replace(",", " ").upper().split())
        buy_ticker = post.get("buy_ticker", "").upper()
        if ticker.upper() in tickers or ticker.upper() == buy_ticker:
            hits.append(post.get("kind", "?").upper())
    return bool(hits), "/".join(sorted(set(hits)))


def read_price_cache(prices_dir: Path) -> dict[str, list]:
    out = {}
    for path in prices_dir.glob("*.csv"):
        out[path.stem.upper()] = read_prices(path)
    return out


def default_dates(posts: list[dict], limit: int) -> list[str]:
    dates = sorted({parse_date(row["datetime_et"]) for row in posts if row.get("datetime_et")})
    return dates[-limit:]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--posts", default="pba_sniper_project/eval/posts.csv")
    ap.add_argument("--prices", default="pba_sniper_project/eval/prices")
    ap.add_argument("--lookahead-days", type=int, default=1)
    ap.add_argument("--dates", default="", help="Comma-separated YYYY-MM-DD dates. Defaults to recent post dates.")
    ap.add_argument("--recent-date-limit", type=int, default=12)
    args = ap.parse_args()

    posts = load_posts(Path(args.posts))
    prices = read_price_cache(Path(args.prices))
    spy = prices.get("SPY")
    if not spy:
        raise SystemExit("Missing SPY price data")

    dates = [x.strip() for x in args.dates.split(",") if x.strip()] or default_dates(posts, args.recent_date_limit)
    rows = []
    totals = {"tested": 0, "setup": 0, "watch": 0, "mentioned_setup": 0}

    for date in dates:
        print(f"\nDATE {date}")
        for theme, tickers in THEMES.items():
            tested = setup = watch = mentioned_setup = mentioned_watch = 0
            setup_names = []
            watch_names = []
            for ticker in tickers:
                ticker_rows = prices.get(ticker)
                if not ticker_rows:
                    continue
                idx = trading_date_on_or_before(ticker_rows, date)
                if idx is None:
                    continue
                st = state_for(ticker_rows, spy, idx)
                state = st.get("state")
                if state in ("MISSING_SPY", "INSUFFICIENT_HISTORY"):
                    continue
                tested += 1
                is_mentioned, mention_kind = mentioned_near(posts, ticker, date, args.lookahead_days)
                if state == "SETUP":
                    setup += 1
                    mentioned_setup += int(is_mentioned)
                    setup_names.append(f"{ticker}{'*' if is_mentioned else ''}")
                elif state == "WATCH_ONLY":
                    watch += 1
                    mentioned_watch += int(is_mentioned)
                    watch_names.append(f"{ticker}{'*' if is_mentioned else ''}")
                rows.append(
                    {
                        "date": date,
                        "theme": theme,
                        "ticker": ticker,
                        "state": state,
                        "mentioned_near": is_mentioned,
                        "mention_kind": mention_kind,
                        "weighted_rp": round(st.get("weighted_rp", math.nan), 2),
                        "recent_rp": round(st.get("recent_rp", math.nan), 2),
                        "structure_ok": st.get("structure_ok", ""),
                        "gap_not_filled": st.get("gap_not_filled", ""),
                        "near_20ma": st.get("near_20ma", ""),
                        "near_50ma": st.get("near_50ma", ""),
                        "near_pd_low": st.get("near_pd_low", ""),
                        "too_extended": st.get("too_extended", ""),
                    }
                )
            if tested:
                setup_pct = setup / tested
                watch_pct = watch / tested
                hit_pct = mentioned_setup / setup if setup else math.nan
                hit_text = f"{hit_pct:5.1%}" if setup else " n/a "
                mention_text = f"{mentioned_setup:2d}/{setup:<2d}" if setup else " n/a "
                print(
                    f"  {theme:15s} setup {setup:2d}/{tested:<2d} ({setup_pct:5.1%}) "
                    f"watch {watch:2d}/{tested:<2d} ({watch_pct:5.1%}) "
                    f"mentioned_setup {mention_text} ({hit_text})"
                )
                if setup_names:
                    print(f"    setup: {', '.join(setup_names)}")
                if watch_names:
                    print(f"    watch: {', '.join(watch_names[:18])}{'...' if len(watch_names) > 18 else ''}")
                totals["tested"] += tested
                totals["setup"] += setup
                totals["watch"] += watch
                totals["mentioned_setup"] += mentioned_setup

    print("\nTOTAL")
    tested = totals["tested"]
    setup = totals["setup"]
    watch = totals["watch"]
    print(f"  setup {setup}/{tested} = {setup / tested:.1%}" if tested else "  no tests")
    print(f"  watch  {watch}/{tested} = {watch / tested:.1%}" if tested else "  no tests")
    print(f"  mentioned inside setup {totals['mentioned_setup']}/{setup} = {totals['mentioned_setup'] / setup:.1%}" if setup else "  no setups")

    out = Path("pba_sniper_project/eval/eval_peer_selectivity_report.csv")
    if rows:
        with out.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"Wrote {out}")


if __name__ == "__main__":
    main()
