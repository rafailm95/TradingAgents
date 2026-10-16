"""Record prospective daily indicators without orders, positions or invented P&L.

Only yesterday's completed UTC candle can be observed; historical backfilling
is refused. This is an on-demand journal, not a scheduler or paper-fill engine.
"""

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from tradingagents.strategy_backtest import features, load_daily

FIRST_OBSERVATION_DAY = "2026-10-17"
RULE_VERSION = "btc_trend_200_20_10_entry50_v1"


def utc_now():
    return datetime.now(timezone.utc)


def observe(csv_path, journal_dir):
    now = utc_now()
    cutoff = (now.date() - timedelta(days=1)).isoformat()
    if cutoff < FIRST_OBSERVATION_DAY:
        return {"status": "WAITING_FOR_NEW_CANDLES", "observed_at_utc": now.isoformat(),
                "first_observation_day": FIRST_OBSERVATION_DAY,
                "earliest_recording_utc": "2026-10-18T00:00:00+00:00", "record_created": False}
    frame = load_daily(csv_path)
    past = frame.loc[frame.Date <= pd.Timestamp(cutoff, tz="UTC")].copy()
    if past.empty or past.Date.iloc[-1].strftime("%Y-%m-%d") != cutoff:
        return {"status": "WAITING_FOR_NEW_CANDLES", "required_day": cutoff, "record_created": False}
    if len(past) < 200:
        raise ValueError("Need 200 completed candles")
    row = features(past).iloc[-1]
    record = {
        "schema_version": 1, "rule_version": RULE_VERSION, "symbol": "BTC-USD",
        "as_of_utc_day": cutoff, "observed_at_utc": now.isoformat(),
        "csv_sha256": hashlib.sha256(Path(csv_path).read_bytes()).hexdigest(),
        "used_rows_sha256": hashlib.sha256(past.to_json(orient="records", date_format="iso").encode()).hexdigest(),
        "used_rows": len(past), "last_close": float(row.Close),
        "sma200": float(row.sma200), "prior_high20": float(row.prior_high20),
        "prior_low10": float(row.prior_low10), "entry_condition": bool(row.entry),
        "exit_condition": bool(row.exit), "hypothetical_entry_allocation": .5,
        "meaning": "Conditions only. No portfolio state, trade, fill or P&L is inferred.",
        "historical_backfill": False, "orders": 0,
    }
    journal = Path(journal_dir)
    journal.mkdir(parents=True, exist_ok=True)
    day_dir = journal / cutoff
    # Exclusive directory creation prevents overwrites and duplicate recording.
    # An interrupted incomplete directory fails closed on the next invocation.
    try:
        day_dir.mkdir()
    except FileExistsError:
        path = day_dir / "observation.json"
        if not path.exists():
            raise ValueError("Incomplete prior recording; inspect before proceeding") from None
        previous = json.loads(path.read_text())
        ignored = {"observed_at_utc", "csv_sha256"}
        if (not isinstance(previous, dict) or set(previous) != set(record)
                or any(previous[key] != value for key, value in record.items() if key not in ignored)):
            raise ValueError("Existing observation conflicts with current data or rules") from None
        return {"status": "ALREADY_RECORDED", "as_of_utc_day": cutoff, "record_created": False}
    (day_dir / "observation.json").write_text(json.dumps(record, indent=2, allow_nan=False))
    return {"status": "RECORDED", "as_of_utc_day": cutoff, "record_created": True,
            "path": str(day_dir / "observation.json"), "orders": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--journal", required=True)
    args = parser.parse_args()
    print(json.dumps(observe(args.csv, args.journal), indent=2))
