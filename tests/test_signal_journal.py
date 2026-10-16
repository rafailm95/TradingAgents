"""Prospective observations cannot silently become historical or duplicate logs."""

import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from tradingagents import signal_journal as journal


@pytest.fixture
def data(tmp_path):
    frame = pd.DataFrame({"Date": pd.date_range("2026-01-01", "2026-10-17"),
                          "Open": 100., "High": 101., "Low": 99., "Close": 100., "Volume": 10.})
    path = tmp_path / "data.csv"
    frame.to_csv(path, index=False)
    return path


def set_clock(monkeypatch, day):
    monkeypatch.setattr(journal, "utc_now", lambda: datetime.fromisoformat(day).replace(tzinfo=timezone.utc))


def test_cannot_create_forward_evidence_before_observation_day(tmp_path, monkeypatch):
    set_clock(monkeypatch, "2026-10-16T12:00:00")
    out = tmp_path / "journal"
    result = journal.observe(tmp_path / "unused.csv", out)
    assert result["status"] == "WAITING_FOR_NEW_CANDLES"
    assert not out.exists()


def test_new_day_records_once_and_never_adds_fake_fills(data, tmp_path, monkeypatch):
    set_clock(monkeypatch, "2026-10-18T01:00:00")
    out = tmp_path / "journal"
    assert journal.observe(data, out)["status"] == "RECORDED"
    record = json.loads((out / "2026-10-17/observation.json").read_text())
    assert record["as_of_utc_day"] == "2026-10-17"
    assert record["orders"] == 0
    assert "pnl" not in record and "fills" not in record
    assert journal.observe(data, out)["status"] == "ALREADY_RECORDED"
    assert len(list(out.glob("*/observation.json"))) == 1


def test_stale_data_is_not_backfilled(data, tmp_path, monkeypatch):
    set_clock(monkeypatch, "2026-10-19T01:00:00")
    assert journal.observe(data, tmp_path / "journal")["status"] == "WAITING_FOR_NEW_CANDLES"


def test_revised_past_data_cannot_overwrite_existing_record(data, tmp_path, monkeypatch):
    set_clock(monkeypatch, "2026-10-18T01:00:00")
    out = tmp_path / "journal"
    journal.observe(data, out)
    before = (out / "2026-10-17/observation.json").read_bytes()
    frame = pd.read_csv(data)
    frame.loc[0, "Volume"] = 11
    frame.to_csv(data, index=False)
    with pytest.raises(ValueError, match="conflicts"):
        journal.observe(data, out)
    assert (out / "2026-10-17/observation.json").read_bytes() == before


def test_partial_day_directory_is_not_claimed_as_success(data, tmp_path, monkeypatch):
    set_clock(monkeypatch, "2026-10-18T01:00:00")
    out = tmp_path / "journal"
    (out / "2026-10-17").mkdir(parents=True)
    with pytest.raises(ValueError, match="Incomplete"):
        journal.observe(data, out)


def test_changed_stored_signal_is_not_accepted_as_duplicate(data, tmp_path, monkeypatch):
    set_clock(monkeypatch, "2026-10-18T01:00:00")
    out = tmp_path / "journal"
    journal.observe(data, out)
    target = out / "2026-10-17/observation.json"
    record = json.loads(target.read_text())
    record["entry_condition"] = not record["entry_condition"]
    target.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="conflicts"):
        journal.observe(data, out)
