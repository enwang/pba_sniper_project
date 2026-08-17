#!/usr/bin/env python3
import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


TICKER_RE = re.compile(r"\$([A-Z][A-Z0-9]{0,5})")
BUY_RE = re.compile(r"\bBought(?:\s+some)?\s+\$([A-Z][A-Z0-9]{0,5})\b", re.I)
STOP_RE = re.compile(r"\bstop(?:ped)?\s*(?:at|under|below)?\s*\$?(\d+(?:\.\d+)?)", re.I)
PRICE_RE = re.compile(r"\$?(\d+(?:\.\d+)?)")


def et_datetime(iso_utc: str) -> str:
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    return dt.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S")


def original_text(text: str) -> str:
    text = text.split("\nQuote\n", 1)[0]
    lines = [x.strip() for x in text.splitlines()]
    drop = {"PBA", "@801010athlete", "Subscribers"}
    body = []
    for line in lines:
        if not line or line in drop or line == "·":
            continue
        if re.fullmatch(r"(?:\d+[smhd]|[A-Z][a-z]{2} \d{1,2}(?:, \d{4})?)", line):
            continue
        if re.fullmatch(r"\d+(?:\.\d+)?[KMB]?", line):
            continue
        if line in {"Show more", "Replying to"}:
            continue
        body.append(line)
    return " ".join(body).strip()


def buy_fields(text: str) -> tuple[str, str, str]:
    low = text.lower()
    if any(x in low for x in ("example from yesterday", "could have bought", "i bought at", "day i bought")):
        return "", "", ""
    match = BUY_RE.search(text)
    if not match:
        return "", "", ""
    ticker = match.group(1).upper()
    tail = text[match.end() :]
    nums = PRICE_RE.findall(tail)
    buy_price = ""
    direct = re.match(r"\s+\$?(\d+(?:\.\d+)?)", tail)
    if direct:
        buy_price = direct.group(1)
    else:
        cost_or_at = re.search(r"\b(?:cost|at|back|here at|pre)\s+\$?(\d+(?:\.\d+)?)", tail, re.I)
        buy_price = cost_or_at.group(1) if cost_or_at else ""
    if not buy_price:
        return "", "", ""
    stop_match = STOP_RE.search(text)
    stop_price = stop_match.group(1) if stop_match else (nums[1] if len(nums) > 1 else "")
    return ticker, buy_price, stop_price


def fl_tickers(text: str) -> list[str]:
    low = text.lower()
    if "fl" not in low and "focus list" not in low:
        return []
    tickers = TICKER_RE.findall(text)
    if not tickers:
        return []
    # If the post has a dedicated FL section, prefer tickers after that marker.
    marker = re.search(r"\b(?:main\s+)?fl\s*:", text, re.I)
    if marker:
        scoped = text[marker.start() :]
        scoped = scoped.split("Longs by", 1)[0]
        scoped = scoped.split("Quote", 1)[0]
        scoped_tickers = TICKER_RE.findall(scoped)
        if scoped_tickers:
            return list(dict.fromkeys(scoped_tickers))
    return list(dict.fromkeys(tickers))


def row_from_post(post: dict) -> dict | None:
    text = original_text(post.get("text", ""))
    if not text:
        return None
    dt = et_datetime(post["datetime"])
    href = post.get("href", "")
    post_id = href.rstrip("/").split("/")[-1] if href else ""
    buy_ticker, buy_price, stop_price = buy_fields(text)
    if buy_ticker and buy_price:
        return {
            "post_id": post_id,
            "datetime_et": dt,
            "kind": "BUY",
            "tickers": buy_ticker,
            "buy_ticker": buy_ticker,
            "buy_price": buy_price,
            "stop_price": stop_price,
            "text": text,
        }
    tickers = fl_tickers(text)
    if tickers:
        return {
            "post_id": post_id,
            "datetime_et": dt,
            "kind": "FL",
            "tickers": " ".join(tickers),
            "buy_ticker": "",
            "buy_price": "",
            "stop_price": "",
            "text": text,
        }
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("json_files", nargs="+")
    ap.add_argument("--out", default="pba_sniper_project/eval/posts.csv")
    args = ap.parse_args()

    by_id: dict[str, dict] = {}
    for filename in args.json_files:
        for post in json.loads(Path(filename).read_text()):
            row = row_from_post(post)
            if row:
                by_id[row["post_id"]] = row

    rows = sorted(by_id.values(), key=lambda r: r["datetime_et"])
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
    print(f"FL: {sum(r['kind'] == 'FL' for r in rows)}")
    print(f"BUY: {sum(r['kind'] == 'BUY' for r in rows)}")


if __name__ == "__main__":
    main()
