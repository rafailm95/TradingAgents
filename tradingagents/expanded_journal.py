"""Five frozen exploratory prospective signal observers. No positions, orders or scheduler.

Use yesterday's completed UTC candle only. All stored observations retain the
complete anchored candles needed to replay all five rules, including recursive ADX. Local integrity
checks are not authentication of market data or protection against a privileged
attacker rewriting the entire journal and application together.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re

from tradingagents.strategy_backtest import load_daily
from tradingagents.strategy_lab import allocation
from tradingagents.strategy_families import signals, indicators

REPO = Path(__file__).resolve().parents[1]
WATCHLIST = REPO / "docs/EXPANDED_CANDIDATE_WATCHLIST.json"
WATCHLIST_SHA256 = "3bc96eb858a44456a8728229291a54011dcd4e8c0a0787a0f3f4af6f442ef495"
MAX_INPUT_BYTES = 5_000_000
MAX_INPUT_ROWS = 10000
ZERO_HASH = "0" * 64


def utc_now():
    return datetime.now(timezone.utc)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def source_bytes(raw):
    # Git on Windows may check text out with CRLF. Only that representation
    # difference is normalized; all other source bytes stay hash-bound.
    return raw.replace(b"\r\n", b"\n")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"Invalid JSON constant: {value}")


def strict_json(raw):
    return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_reject_constant)


def _utc(value):
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timezone-aware clock required")
    return value.astimezone(timezone.utc)


def contract():
    raw = source_bytes(WATCHLIST.read_bytes())
    if digest(raw) != WATCHLIST_SHA256:
        raise ValueError("Frozen watchlist mismatch; do not silently change rules")
    spec = strict_json(raw)
    for name, expected in spec["implementation_sha256"].items():
        if digest(source_bytes((REPO / name).read_bytes())) != expected:
            raise ValueError(f"Frozen implementation mismatch: {name}")
    parent = REPO / spec["research_protocol_path"]
    if digest(source_bytes(parent.read_bytes())) != spec["research_protocol_sha256"]:
        raise ValueError("Parent research protocol mismatch")
    return raw, spec, digest(source_bytes(Path(__file__).read_bytes()))


def _bounded_read(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Expected a regular, non-symlink file")
    with path.open("rb") as stream:
        raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("Input exceeds bounded file size")
    return raw


def _seed_bytes(spec):
    raw = _bounded_read(REPO / spec["seed_file"])
    if digest(raw) != spec["seed_sha256"] or not raw.endswith(b"\n"):
        raise ValueError("Anchored seed changed")
    return raw


def _validate_snapshot_bytes(raw, spec):
    seed = _seed_bytes(spec)
    if not raw.startswith(seed):
        raise ValueError("Snapshot must preserve exact anchored seed prefix")
    frame = load_daily(io.BytesIO(raw))
    if frame.Date.iloc[0].date().isoformat() != spec["history_start"]:
        raise ValueError("Indicator history start changed")
    if len(frame) > MAX_INPUT_ROWS:
        raise ValueError("Anchored history exceeds row limit")
    return frame


def _conditions(frame, spec, prepared=None):
    if len(frame) < 200 or frame.Date.iloc[0].date().isoformat() != spec["history_start"]:
        raise ValueError("Expected complete anchored indicator history")
    z, cached = prepared if prepared is not None else (indicators(frame), None)
    index = len(frame)-1
    common = {key:float(z.iloc[index][key]) for key in ("sma200","adx","plus_di","minus_di","aroon_up","aroon_down","cmo")}
    common["close"] = float(frame.Close.iloc[-1])
    computed = []
    for definition in spec["candidates"]:
        row = (cached[definition["family"]].iloc[index] if cached is not None else
               signals(frame, definition["family"], prepared_indicators=z).iloc[-1])
        vol = float(row.vol60)
        if not all(math.isfinite(value) for value in (*common.values(),vol)):
            raise ValueError("Non-finite calculated indicator")
        computed.append({**definition,"entry_condition":bool(row.entry),"exit_condition":bool(row.exit),
                         "annualized_vol60":vol,"hypothetical_entry_fraction":allocation(definition["sizing"],vol)})
    return {"indicators":common,"candidates":computed}


def _snapshot_bytes(frame):
    saved = frame.copy()
    saved["Date"] = saved.Date.dt.strftime("%Y-%m-%d")
    return saved.to_csv(index=False, lineterminator="\n").encode("utf-8")


def _payload(frame, snapshot, spec, build_hash, observed_at, source, previous, prepared=None):
    day = frame.Date.iloc[-1].date()
    completed = datetime.combine(day + timedelta(days=1), datetime.min.time(), timezone.utc)
    prior_day = date.fromisoformat(previous["as_of_utc_day"]) if previous else date.fromisoformat(spec["first_observation_day"]) - timedelta(days=1)
    return {
        "schema_version": 1, "watchlist_id": spec["watchlist_id"],
        "watchlist_sha256": WATCHLIST_SHA256, "observer_build_sha256": build_hash,
        "symbol": spec["symbol"], "as_of_utc_day": day.isoformat(),
        "observed_at_utc": observed_at.isoformat(),
        "seconds_after_candle_completion": (observed_at - completed).total_seconds(),
        "previous_record_sha256": previous["record_sha256"] if previous else ZERO_HASH,
        "unrecorded_days_since_previous": (day - prior_day).days - 1,
        "source": source, "snapshot_sha256": digest(snapshot), "snapshot_rows": len(frame),
        **_conditions(frame, spec, prepared), "historical_backfill": False, "orders": 0,
        "meaning": spec["meaning"], "data_authentication": spec["data_authentication"],
    }


def _write_new(path, raw):
    # Exclusive creation: no original observation or snapshot is overwritten.
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def _lock(journal):
    lock = journal / ".record.lock"
    try:
        lock.mkdir()
    except FileExistsError:
        raise ValueError("Journal locked or interrupted; inspect before retrying") from None
    try:
        yield
    finally:
        lock.rmdir()


def _scan(journal, raw_spec, spec, build_hash, now):
    """Replay every recorded day and validate the local append chain."""
    profile = journal / "watchlist.json"
    if not profile.is_file() or _bounded_read(profile) != raw_spec:
        raise ValueError("Missing or mismatched journal watchlist")
    days = []
    for path in journal.iterdir():
        if path.name in {"watchlist.json", ".record.lock"}:
            continue
        if path.is_symlink() or not path.is_dir() or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.name):
            raise ValueError("Unexpected journal entry; use a dedicated journal directory")
        day = date.fromisoformat(path.name)
        if day < date.fromisoformat(spec["first_observation_day"]) or day >= now.date():
            raise ValueError("Historical or future journal day is invalid")
        days.append(path)
    records, previous = {}, None
    prepared = None
    if days:
        # Prefix-invariant indicators are calculated once per full replay.
        # Every older snapshot must be an exact byte prefix of the newest.
        latest_snapshot = _bounded_read(max(days) / "candles.csv")
        latest_frame = _validate_snapshot_bytes(latest_snapshot, spec)
        z = indicators(latest_frame)
        prepared = (z, {d["family"]:signals(latest_frame,d["family"],prepared_indicators=z) for d in spec["candidates"]})
    for path in sorted(days):
        if {p.name for p in path.iterdir()} != {"candles.csv", "observation.json"}:
            raise ValueError("Incomplete or unexpected day files; inspect before proceeding")
        snapshot = _bounded_read(path / "candles.csv")
        if not latest_snapshot.startswith(snapshot):
            raise ValueError("Snapshots must preserve anchored history prefixes")
        record = strict_json(_bounded_read(path / "observation.json"))
        if not isinstance(record, dict) or set(record) != {"payload", "record_sha256"}:
            raise ValueError("Invalid record envelope")
        payload = record["payload"]
        if not isinstance(payload, dict) or digest(canonical(payload)) != record["record_sha256"]:
            raise ValueError("Record integrity mismatch")
        try:
            observed_at = _utc(datetime.fromisoformat(payload["observed_at_utc"]))
            if observed_at.date() != date.fromisoformat(path.name) + timedelta(days=1) or observed_at > now:
                raise ValueError("Stored observation time is inconsistent")
            frame = _validate_snapshot_bytes(snapshot, spec)
            if frame.Date.iloc[-1].date().isoformat() != path.name:
                raise ValueError("Snapshot day mismatch")
            source = payload["source"]
            if not isinstance(source, dict) or set(source) != {"csv_sha256", "received_rows", "first_day", "last_day"}:
                raise ValueError("Invalid source metadata")
            count = source["received_rows"]
            if type(count) is not int or not 200 <= count <= MAX_INPUT_ROWS:
                raise ValueError("Invalid source count")
            if not isinstance(source["csv_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", source["csv_sha256"]):
                raise ValueError("Invalid source digest")
            if (source["last_day"] != path.name or
                    date.fromisoformat(source["first_day"]) != date.fromisoformat(path.name) - timedelta(days=count - 1)):
                raise ValueError("Invalid source date range")
            expected = _payload(frame, snapshot, spec, build_hash, observed_at, source, previous, prepared)
            if canonical(expected) != canonical(payload):
                raise ValueError("Stored rules, signals, data or record chain conflict")
        except (KeyError, TypeError, OverflowError) as error:
            raise ValueError("Malformed stored observation") from error
        if records:
            previous_day = max(records)
            prior_raw = _bounded_read(journal / previous_day / "candles.csv")
            if not snapshot.startswith(prior_raw):
                raise ValueError("Accepted anchored candle history was revised")
        records[path.name] = record
        previous = {"as_of_utc_day": path.name, "record_sha256": record["record_sha256"]}
    return records


def verify(journal_dir):
    raw_spec, spec, build_hash = contract()
    now = _utc(utc_now())
    journal = Path(journal_dir)
    if not journal.exists():
        return {"status": "NOT_INITIALIZED", "records": 0, "orders": 0}
    if journal.is_symlink() or not journal.is_dir():
        raise ValueError("Invalid journal directory")
    with _lock(journal):
        records = _scan(journal, raw_spec, spec, build_hash, now)
    return {"status": "VERIFIED", "records": len(records),
            "last_day": max(records) if records else None,
            "integrity_scope": "Local consistency and numerical replay; not authenticated origin or external timestamp",
            "orders": 0}


def observe(csv_path, journal_dir):
    raw_spec, spec, build_hash = contract()
    now = _utc(utc_now())
    cutoff = now.date() - timedelta(days=1)
    if cutoff < date.fromisoformat(spec["first_observation_day"]):
        return {"status": "WAITING_FOR_NEW_CANDLES", "observed_at_utc": now.isoformat(),
                "first_observation_day": spec["first_observation_day"],
                "earliest_recording_utc": spec["earliest_recording_utc"],
                "record_created": False, "candidate_count": len(spec["candidates"]), "orders": 0}
    raw_input = _bounded_read(csv_path)
    frame = _validate_snapshot_bytes(raw_input, spec)
    if not 200 <= len(frame) <= MAX_INPUT_ROWS:
        raise ValueError("Expected bounded anchored consecutive daily history")
    final_day = frame.Date.iloc[-1].date()
    if final_day > cutoff:
        raise ValueError("CSV contains a future or incomplete candle")
    if final_day < cutoff:
        return {"status": "WAITING_FOR_NEW_CANDLES", "required_day": cutoff.isoformat(),
                "received_last_day": final_day.isoformat(), "record_created": False, "orders": 0}
    source = {"csv_sha256": digest(raw_input), "received_rows": len(frame),
              "first_day": frame.Date.iloc[0].date().isoformat(), "last_day": final_day.isoformat()}
    # Preserve exact anchored bytes; never reserialize the immutable seed.
    snapshot = raw_input
    used = _validate_snapshot_bytes(snapshot, spec)
    _conditions(used, spec)  # Verify calculations before mutating the journal.
    record_time = _utc(utc_now())
    if record_time.date() != now.date():
        raise ValueError("UTC date changed during input processing; start a fresh observation")
    now = record_time
    journal = Path(journal_dir)
    if journal.is_symlink():
        raise ValueError("Journal cannot be a symlink")
    journal.mkdir(parents=True, exist_ok=True)
    with _lock(journal):
        profile = journal / "watchlist.json"
        if not profile.exists():
            if {p.name for p in journal.iterdir()} != {".record.lock"}:
                raise ValueError("Uninitialized nonempty journal; refuse to adopt existing files")
            _write_new(profile, raw_spec)
        records = _scan(journal, raw_spec, spec, build_hash, now)
        day = cutoff.isoformat()
        if day in records:
            stored = records[day]["payload"]
            if (stored["snapshot_sha256"] != digest(snapshot) or
                    canonical(stored["candidates"]) != canonical(_conditions(used, spec)["candidates"])):
                raise ValueError("Existing observation conflicts with revised input")
            return {"status": "ALREADY_RECORDED", "as_of_utc_day": day,
                    "record_created": False, "candidate_count": len(spec["candidates"]), "orders": 0}
        last_day = max(records) if records else None
        if last_day and not snapshot.startswith(_bounded_read(journal / last_day / "candles.csv")):
            raise ValueError("Accepted anchored candle history was revised")
        previous = {"as_of_utc_day": last_day, "record_sha256": records[last_day]["record_sha256"]} if last_day else None
        payload = _payload(used, snapshot, spec, build_hash, now, source, previous)
        record = {"payload": payload, "record_sha256": digest(canonical(payload))}
        day_dir = journal / day
        day_dir.mkdir()  # Interrupted partial writes remain visibly incomplete.
        _write_new(day_dir / "candles.csv", snapshot)
        _write_new(day_dir / "observation.json", canonical(record) + b"\n")
        # Read back the exact persisted bytes and replay before claiming success.
        confirmed = _scan(journal, raw_spec, spec, build_hash, now)
        if confirmed[day]["record_sha256"] != record["record_sha256"]:
            raise ValueError("Unexpected post-write record identity")
    return {"status": "RECORDED", "as_of_utc_day": day, "record_created": True,
            "candidate_count": len(spec["candidates"]), "record_sha256": record["record_sha256"],
            "unrecorded_days_since_previous": payload["unrecorded_days_since_previous"],
            "path": str(day_dir / "observation.json"), "orders": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", required=True)
    parser.add_argument("--csv")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.verify_only and args.csv or not args.verify_only and not args.csv:
        parser.error("Use --csv to observe OR --verify-only to inspect")
    try:
        result = verify(args.journal) if args.verify_only else observe(args.csv, args.journal)
    except (ValueError, OSError, ArithmeticError) as error:
        print(json.dumps({"status": "ERROR_REQUIRES_INSPECTION", "error": str(error),
                          "record_created": "UNVERIFIED", "orders": 0}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
