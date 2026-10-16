"""One on-demand public-data download plus the two-candidate signal journal.

No background loop, scheduling, credentials, model calls or trading actions.
Before eligibility, and after an already recorded day, no download is attempted.
"""
import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import subprocess
import sys
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from tradingagents import candidate_journal as journal


def run(state_dir):
    _, spec, _ = journal.contract()
    now = journal._utc(journal.utc_now())
    cutoff = now.date() - timedelta(days=1)
    state = Path(state_dir)
    target = state / "journal"
    if cutoff < date.fromisoformat(spec["first_observation_day"]):
        return journal.observe(state / "not_read_before_eligibility.csv", target)
    checked = journal.verify(target)
    if checked["status"] == "VERIFIED" and checked["last_day"] == cutoff.isoformat():
        return {"status": "ALREADY_RECORDED", "as_of_utc_day": cutoff.isoformat(),
                "record_created": False, "public_downloads": 0, "orders": 0}
    start = cutoff - timedelta(days=spec["required_snapshot_rows"] - 1)
    download_dir = state / "downloads" / f"{now.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex}"
    command = [sys.executable, str(REPO / "scripts/fetch_trend_candles.py"),
               "--start", start.isoformat(), "--end-exclusive", now.date().isoformat(),
               "--output", str(download_dir)]
    # The existing downloader uses one bounded public request for these 200
    # rows, no automatic retries, and refuses an existing output directory.
    result = subprocess.run(command, check=False, timeout=90, capture_output=True, text=True)
    if result.returncode != 0:
        return {"status": "DOWNLOAD_FAILED", "record_created": False, "orders": 0,
                "download_dir": str(download_dir), "exit_code": result.returncode,
                "detail": result.stderr[-2000:], "automatic_retry": False}
    outcome = journal.observe(download_dir / "btc_coinbase_daily.csv", target)
    return {**outcome, "download_dir": str(download_dir),
            "download_attempts": 1, "automatic_retry": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", required=True)
    args = parser.parse_args()
    try:
        result = run(args.state_dir)
    except (ValueError, OSError, ArithmeticError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"status": "ERROR_REQUIRES_INSPECTION", "error": str(error),
                          "record_created": "UNVERIFIED", "orders": 0}))
        return 1
    print(json.dumps(result, indent=2))
    return 1 if result["status"] == "DOWNLOAD_FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
