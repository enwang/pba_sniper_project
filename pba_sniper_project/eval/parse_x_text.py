#!/usr/bin/env python3
import argparse
import csv
import re
from pathlib import Path


TICKER_RE = re.compile(r"\$([A-Z][A-Z0-9]{0,5})")
BUY_RE = re.compile(r"\bBought\s+\$?([A-Z][A-Z0-9]{0,5})\b", re.I)
PRICE_RE = re.compile(r"(?<![A-Za-z])(\d+(?:\.\d+)?)")
STOP_RE = re.compile(r"\bstop(?:ped)?\s*(?:at|under|below)?\s*(\d+(?:\.\d+)?)", re.I)


def infer_kind(text: str) -> str:
    low = text.lower()
    if "bought" in low:
        return "BUY"
    if re.search(r"\bfl\b", low) or "focus list" in low or "watchlist" in low:
        return "FL"
    return "OTHER"


def parse_buy(text: str) -> tuple[str, str, str]:
    match = BUY_RE.search(text)
    ticker = match.group(1).upper() if match else ""
    tail = text[match.end() :] if match else text
    nums = PRICE_RE.findall(tail)
    buy_price = nums[0] if nums else ""
    stop_match = STOP_RE.search(text)
    stop_price = stop_match.group(1) if stop_match else (nums[1] if len(nums) > 1 else "")
    return ticker, buy_price, stop_price


def split_posts(raw: str) -> list[str]:
    parts = re.split(r"\n\s*\n+", raw.strip())
    return [p.replace("\n", " ").strip() for p in parts if p.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--infile", default="pba_eval/raw_x_posts.txt")
    ap.add_argument("--out", default="pba_eval/posts.csv")
    ap.add_argument("--date", default="", help="Fallback ET datetime, e.g. 2026-08-14 09:35:58")
    args = ap.parse_args()

    raw_path = Path(args.infile)
    if not raw_path.exists():
        raise SystemExit(f"Missing {raw_path}. Paste copied X posts into this file, separated by blank lines.")

    rows = []
    for i, text in enumerate(split_posts(raw_path.read_text())):
        kind = infer_kind(text)
        tickers = " ".join(TICKER_RE.findall(text))
        buy_ticker = buy_price = stop_price = ""
        if kind == "BUY":
            buy_ticker, buy_price, stop_price = parse_buy(text)
            if not tickers and buy_ticker:
                tickers = buy_ticker
        rows.append(
            {
                "post_id": f"raw-{i + 1}",
                "datetime_et": args.date,
                "kind": kind,
                "tickers": tickers,
                "buy_ticker": buy_ticker,
                "buy_price": buy_price,
                "stop_price": stop_price,
                "text": text,
            }
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["post_id", "datetime_et", "kind", "tickers", "buy_ticker", "buy_price", "stop_price", "text"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
