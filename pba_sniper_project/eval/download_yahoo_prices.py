#!/usr/bin/env python3
import argparse
import csv
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def unix(date: str) -> int:
    return int(datetime.fromisoformat(date).replace(tzinfo=timezone.utc).timestamp())


def download(ticker: str, start: str, end: str) -> list[dict]:
    symbol = ticker.upper().replace(".", "-")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={unix(start)}&period2={unix(end)}&interval=1d&events=history&includeAdjustedClose=true"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read())
    result = payload["chart"]["result"][0]
    stamps = result.get("timestamp") or []
    quote = result["indicators"]["quote"][0]
    rows = []
    for i, stamp in enumerate(stamps):
        vals = {k: quote.get(k, [None] * len(stamps))[i] for k in ("open", "high", "low", "close", "volume")}
        if any(vals[k] is None for k in ("open", "high", "low", "close")):
            continue
        rows.append(
            {
                "Date": datetime.fromtimestamp(stamp, tz=timezone.utc).date().isoformat(),
                "Open": vals["open"],
                "High": vals["high"],
                "Low": vals["low"],
                "Close": vals["close"],
                "Volume": vals["volume"] or 0,
            }
        )
    return rows


def tickers_from_posts(posts_path: Path) -> list[str]:
    tickers = {"SPY"}
    with posts_path.open(newline="") as f:
        for row in csv.DictReader(f):
            for field in ("tickers", "buy_ticker"):
                for ticker in row.get(field, "").replace(",", " ").split():
                    if ticker:
                        tickers.add(ticker.upper().replace("$", ""))
    return sorted(tickers)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--posts", default="pba_sniper_project/eval/posts.csv")
    ap.add_argument("--outdir", default="pba_sniper_project/eval/prices")
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--end", default="2026-08-18")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    for ticker in tickers_from_posts(Path(args.posts)):
        out = outdir / f"{ticker}.csv"
        try:
            rows = download(ticker, args.start, args.end)
        except Exception as exc:
            print(f"FAIL {ticker}: {exc}")
            continue
        if not rows:
            print(f"EMPTY {ticker}")
            continue
        with out.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["Date", "Open", "High", "Low", "Close", "Volume"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"OK {ticker}: {len(rows)} rows")
        time.sleep(0.2)


if __name__ == "__main__":
    main()
