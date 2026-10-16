"""Bounded public daily OHLCV download for three explicitly allowed products."""
import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PRODUCTS = ("BTC-USD", "ETH-USD", "LTC-USD")


def download(product, start, end, output, *, opener=urlopen):
    if product not in PRODUCTS:
        raise ValueError("Unregistered product")
    if start >= end or end > datetime.now(timezone.utc).date() or (end-start).days > 4000:
        raise ValueError("Invalid/incomplete/bounded daily range")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    observations, requests = {}, []
    cursor = start
    while cursor < end:
        stop = min(cursor+timedelta(days=250),end)
        endpoint = f"https://api.exchange.coinbase.com/products/{product}/candles?"+urlencode({
            "granularity":86400,"start":cursor.isoformat()+"T00:00:00Z","end":stop.isoformat()+"T00:00:00Z"})
        requested = datetime.now(timezone.utc).isoformat()
        with opener(Request(endpoint,headers={"User-Agent":"TradingAgents-public-research/2"}),timeout=40) as response:
            if response.status != 200 or response.geturl() != endpoint:
                raise ValueError("Unexpected response or redirect")
            raw = response.read(1_000_001)
        if len(raw)>1_000_000:
            raise ValueError("Response exceeds byte bound")
        raw_name=f"raw_{len(requests)+1:02}.json"
        (output/raw_name).write_bytes(raw)
        rows=json.loads(raw,parse_constant=lambda x:(_ for _ in ()).throw(ValueError("Nonfinite JSON")))
        if not isinstance(rows,list) or not rows or len(rows)>300:
            raise ValueError("Invalid candle array")
        for row in rows:
            if not isinstance(row,list) or len(row)!=6 or any(type(x) not in (int,float) or not math.isfinite(x) for x in row):
                raise ValueError("Invalid candle shape/numbers")
            stamp=datetime.fromtimestamp(row[0],timezone.utc)
            if stamp.time().isoformat()!="00:00:00":
                raise ValueError("Nonmidnight candle")
            day=stamp.date()
            low,high,opened,closed,volume=row[1:]
            if min(low,high,opened,closed)<=0 or volume<0 or not low<=min(opened,closed)<=max(opened,closed)<=high:
                raise ValueError("Invalid OHLCV")
            if not start<=day<end:continue
            if day in observations and observations[day]!=row:
                raise ValueError("Conflicting duplicate candle")
            observations[day]=row
        requests.append({"url":endpoint,"requested_at_utc":requested,"received_at_utc":datetime.now(timezone.utc).isoformat(),
            "raw_file":raw_name,"sha256":hashlib.sha256(raw).hexdigest(),"returned_rows":len(rows)})
        (output/"requests.json").write_text(json.dumps(requests,indent=2))
        print(f"Downloaded {product} batch{len(requests)} {cursor}..{stop}",flush=True)
        cursor=stop
    expected={start+timedelta(days=i) for i in range((end-start).days)}
    if set(observations)!=expected:
        raise ValueError(f"Incomplete dataset; missing{len(expected-set(observations))} days")
    target=output/"candles.csv"
    with target.open("w",newline="",encoding="utf-8") as stream:
        writer=csv.writer(stream,lineterminator="\n")
        writer.writerow(["Date","Open","High","Low","Close","Volume"])
        for day,row in sorted(observations.items()):writer.writerow([day.isoformat(),row[3],row[2],row[1],row[4],row[5]])
    manifest={"product":product,"source":"Coinbase Exchange public GET","start":start.isoformat(),"end_exclusive":end.isoformat(),
        "rows":len(observations),"csv_sha256":hashlib.sha256(target.read_bytes()).hexdigest(),"request_count":len(requests),
        "synthetic":False,"cross_venue_verified":False,"automatic_retry":False}
    (output/"manifest.json").write_text(json.dumps(manifest,indent=2))
    return manifest


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product",required=True,choices=PRODUCTS)
    parser.add_argument("--start",required=True)
    parser.add_argument("--end-exclusive",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    print(json.dumps(download(args.product,date.fromisoformat(args.start),date.fromisoformat(args.end_exclusive),args.output)))
