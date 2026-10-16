"""Download bounded public Coinbase daily candles; retain exact raw responses.

No credentials, automatic retries or paid endpoints. Existing output directories
are refused. Failed downloads remain available for inspection.
"""

import argparse
import csv
import hashlib
import json
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end-exclusive", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end_exclusive)
    if start >= end or end > datetime.now(timezone.utc).date():
        raise ValueError("Invalid date range or incomplete future daily candle")
    if (end - start).days > 4000:
        raise ValueError("This downloader permits at most 4000 days")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    observations, requests = {}, []
    cursor = start
    while cursor < end:
        stop = min(cursor + timedelta(days=250), end)
        query = urllib.parse.urlencode({"granularity": 86400,
            "start": cursor.isoformat() + "T00:00:00Z", "end": stop.isoformat() + "T00:00:00Z"})
        url = "https://api.exchange.coinbase.com/products/BTC-USD/candles?" + query
        request = urllib.request.Request(url, headers={"User-Agent": "TradingAgentsResearch/1.0"})
        with urllib.request.urlopen(request, timeout=40) as response:
            raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError("Unexpected response size")
        name = f"raw_{len(requests) + 1:02}.json"
        (output / name).write_bytes(raw)
        rows = json.loads(raw)
        if not isinstance(rows, list) or not rows:
            raise ValueError("Missing candle array")
        for row in rows:
            if not isinstance(row, list) or len(row) != 6:
                raise ValueError("Invalid Coinbase candle shape")
            stamp = datetime.fromtimestamp(row[0], timezone.utc)
            if stamp.time().isoformat() != "00:00:00":
                raise ValueError("Non-midnight UTC candle")
            day = stamp.date()
            if not start <= day < end:
                continue
            if day in observations and observations[day] != row:
                raise ValueError("Conflicting duplicate candle")
            observations[day] = row
        requests.append({"url": url, "raw_file": name, "sha256": hashlib.sha256(raw).hexdigest(),
                         "returned_rows": len(rows), "retrieved_utc": datetime.now(timezone.utc).isoformat()})
        (output / "requests.json").write_text(json.dumps(requests, indent=2))
        print(f"Downloaded batch {len(requests)}: {cursor} to {stop}", flush=True)
        cursor = stop
    expected = {start + timedelta(days=i) for i in range((end - start).days)}
    if set(observations) != expected:
        missing = sorted(expected - set(observations))
        raise ValueError(f"Incomplete dataset: {len(missing)} missing dates; first {missing[:5]}")
    target = output / "btc_coinbase_daily.csv"
    with target.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["Date", "Open", "High", "Low", "Close", "Volume"])
        for day, row in sorted(observations.items()):
            writer.writerow([day.isoformat(), row[3], row[2], row[1], row[4], row[5]])
    (output / "manifest.json").write_text(json.dumps({"source": "Coinbase Exchange BTC-USD",
        "start": start.isoformat(), "end_exclusive": end.isoformat(), "rows": len(observations),
        "csv_sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "requests": len(requests),
        "synthetic": False, "cross_venue_verified": False}, indent=2))
    print(f"Complete dataset: {len(observations)} daily candles", flush=True)


if __name__ == "__main__":
    main()
