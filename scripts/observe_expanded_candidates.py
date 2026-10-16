"""Append new prices to an immutable2019 seed; observe only yesterday's candle."""
from datetime import date,timedelta
from pathlib import Path
import subprocess
import sys
import uuid

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from tradingagents import expanded_journal as journal


def run(state_dir):
    _,spec,_=journal.contract()
    now=journal._utc(journal.utc_now());cutoff=now.date()-timedelta(days=1)
    state=Path(state_dir);target=state/"journal"
    if cutoff<date.fromisoformat(spec["first_observation_day"]):
        return journal.observe(state/"not_read_before_eligibility.csv",target)
    checked=journal.verify(target)
    if checked["status"]=="VERIFIED" and checked["last_day"]==cutoff.isoformat():
        return {"status":"ALREADY_RECORDED","as_of_utc_day":cutoff.isoformat(),"record_created":False,"public_downloads":0,"orders":0}
    if checked.get("last_day"):
        last_day=date.fromisoformat(checked["last_day"])
        historical=journal._bounded_read(target/checked["last_day"]/"candles.csv")
    else:
        last_day=date.fromisoformat(spec["seed_last_day"])
        historical=journal._seed_bytes(spec)
    if not historical.endswith(b"\n") or last_day>=cutoff:
        raise ValueError("Invalid anchored history extension")
    download_dir=state/"downloads"/f"{now.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex}"
    command=[sys.executable,str(REPO/"scripts/fetch_research_candles.py"),"--product","BTC-USD",
        "--start",(last_day+timedelta(days=1)).isoformat(),"--end-exclusive",now.date().isoformat(),"--output",str(download_dir)]
    result=subprocess.run(command,check=False,timeout=120,capture_output=True,text=True)
    if result.returncode!=0:
        return {"status":"DOWNLOAD_FAILED","record_created":False,"orders":0,"detail":result.stderr[-2000:],"download_dir":str(download_dir),"automatic_retry":False}
    extension=journal._bounded_read(download_dir/"candles.csv")
    header,body=extension.split(b"\n",1)
    if header!=historical.split(b"\n",1)[0] or not body:
        raise ValueError("Downloaded candle schema changed")
    raw=historical+body
    frame=journal._validate_snapshot_bytes(raw,spec)
    if frame.Date.iloc[-1].date()!=cutoff:
        raise ValueError("Incomplete extension")
    merged=download_dir/"anchored.csv"
    journal._write_new(merged,raw)
    return {**journal.observe(merged,target),"download_dir":str(download_dir),"download_attempts":1,"automatic_retry":False}
