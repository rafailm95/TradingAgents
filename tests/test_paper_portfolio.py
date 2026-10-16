"""Synthetic clock/data tests only; none of these results are market evidence."""
from datetime import datetime, timedelta
import json
from pathlib import Path

import pandas as pd
import pytest

from tradingagents import candidate_journal as journal
from tradingagents import paper_portfolio as paper

IDS = ["breakout20__vol15_cap50", "sma200_band__vol15_cap50"]


def clock(monkeypatch, value):
    instant = datetime.fromisoformat(value)
    monkeypatch.setattr(journal, "utc_now", lambda: instant)
    return instant


def observation(monkeypatch, tmp_path, day="2026-10-17", prices=None):
    dates = pd.date_range(end=day, periods=200)
    prices = prices or {"2026-10-17": 120.0, "2026-10-18": 125.0, "2026-10-19": 80.0}
    close = [prices.get(d.strftime("%Y-%m-%d"), 100.0) for d in dates]
    frame = pd.DataFrame({"Date": dates, "Open": close, "High": [p+1 for p in close],
                          "Low": [p-1 for p in close], "Close": close, "Volume": 10.0})
    csv = tmp_path / "input.csv"
    frame.to_csv(csv, index=False)
    now = datetime.fromisoformat(day + "T00:10:00+00:00") + timedelta(days=1)
    clock(monkeypatch, now.isoformat())
    result = journal.observe(csv, tmp_path / "journal")
    assert result["status"] == "RECORDED"
    return json.loads((tmp_path / "journal" / day / "observation.json").read_text())


def quote(bid=119.0, ask=121.0):
    now = journal.utc_now()
    return {"endpoint": paper.contract()[1]["quote_endpoint"],
            "request_started_at_utc": now.isoformat(),
            "response_received_at_utc": (now + timedelta(seconds=2)).isoformat(),
            "response_body_utf8": json.dumps({"bid": str(bid), "ask": str(ask),
                                              "time": (now + timedelta(seconds=1)).isoformat()})}


def append(monkeypatch, tmp_path, bid=119.0, ask=121.0):
    evidence = quote(bid, ask)
    clock(monkeypatch, (journal.utc_now() + timedelta(seconds=3)).isoformat())
    return paper.record(tmp_path / "journal", tmp_path / "ledger", evidence)


def test_empty_readiness_and_record_do_not_create_state(tmp_path):
    a, b = tmp_path / "journal", tmp_path / "ledger"
    result = paper.verify(a, b)
    assert result["events"] == 0 and result["books"] is None
    assert paper.prepare(a, b)["status"] == "WAITING_FOR_OBSERVATIONS"
    assert paper.record(a, b, {})["status"] == "WAITING_FOR_OBSERVATIONS"
    assert not list(tmp_path.iterdir())


def test_first_buy_budget_fees_and_liquidation_math(monkeypatch, tmp_path):
    signal = observation(monkeypatch, tmp_path)["payload"]
    result = append(monkeypatch, tmp_path)
    assert result["status"] == "RECORDED" and result["orders"] == 0
    assert len(result["books"]) == 2
    for scenario, fee, slip in [("base", .006, .001), ("stress", .012, .0025)]:
        for candidate in signal["candidates"]:
            book = result["books"][scenario][candidate["id"]]
            budget = 10000 * candidate["hypothetical_entry_fraction"]
            quantity = budget / (121 * (1+slip) * (1+fee))
            assert book["action"] == "BUY"
            assert book["quantity_btc"] == pytest.approx(quantity)
            assert book["cash_usd"] == pytest.approx(10000-budget)
            assert book["paid_fees_usd"] == pytest.approx(quantity*121*(1+slip)*fee)
            assert book["liquidation_equity_usd"] == pytest.approx(10000-budget+quantity*119*(1-slip)*(1-fee))
            assert book["net_pnl_usd"] < 0  # Costs are visible immediately.
            assert book["realized_pnl_usd"] == 0
            assert book["operating_cost_sensitivity_usd"] == 0
        bh = result["books"][scenario]["buy_hold_50"]
        cash = result["books"][scenario]["cash"]
        assert bh["cash_usd"] == 5000 and bh["action"] == "BUY"
        assert cash["cash_usd"] == 10000 and cash["net_pnl_usd"] == 0 and cash["fill"] is None
    assert paper.verify(tmp_path/"journal", tmp_path/"ledger")["books"] == result["books"]


def test_hold_then_exit_realized_pnl_and_external_expense(monkeypatch, tmp_path):
    observation(monkeypatch, tmp_path)
    first = append(monkeypatch, tmp_path)
    observation(monkeypatch, tmp_path, "2026-10-18")
    second = append(monkeypatch, tmp_path, 124, 126)
    observation(monkeypatch, tmp_path, "2026-10-19")
    third = append(monkeypatch, tmp_path, 79, 81)
    for scenario, fee, slip in [("base", .006, .001), ("stress", .012, .0025)]:
        for name in IDS:
            b1, b2, b3 = [out["books"][scenario][name] for out in [first, second, third]]
            assert b2["action"] == "HOLD" and b2["fill"] is None
            assert b1["quantity_btc"] == b2["quantity_btc"]
            assert b2["operating_cost_sensitivity_usd"] == pytest.approx(120/365.25)
            net_sale = b1["quantity_btc"] * 79 * (1-slip) * (1-fee)
            assert b3["action"] == "SELL" and b3["quantity_btc"] == 0
            assert b3["cost_basis_usd"] == b3["unrealized_liquidation_pnl_usd"] == 0
            assert b3["hypothetical_fill_count"] == 2
            assert b3["realized_pnl_usd"] == pytest.approx(net_sale-b1["cost_basis_usd"])
            assert b3["cash_usd"] == pytest.approx(b1["cash_usd"]+net_sale)
            assert b3["net_pnl_usd"] == pytest.approx(b3["realized_pnl_usd"]-240/365.25)
            peak = max(10000, b1["net_liquidation_equity_usd"], b2["net_liquidation_equity_usd"])
            assert b3["sampled_max_drawdown_fraction"] == pytest.approx(1-b3["net_liquidation_equity_usd"]/peak)
        assert third["books"][scenario]["buy_hold_50"]["action"] == "HOLD"
        assert third["books"][scenario]["cash"]["net_pnl_usd"] == 0
    assert paper.verify(tmp_path/"journal", tmp_path/"ledger")["events"] == 3


def test_duplicate_never_rewrites_or_trades_twice(monkeypatch, tmp_path):
    observation(monkeypatch, tmp_path)
    append(monkeypatch, tmp_path)
    path = tmp_path/"ledger/2026-10-17.json"
    before = path.read_bytes()
    assert paper.record(tmp_path/"journal", tmp_path/"ledger", {"bad": "unused"})["status"] == "ALREADY_RECORDED"
    assert path.read_bytes() == before
    assert paper.verify(tmp_path/"journal", tmp_path/"ledger")["events"] == 1


@pytest.mark.parametrize("change,match", [
    (lambda q: q.update(endpoint="https://invalid.example"), "endpoint"),
    (lambda q: q.update(request_started_at_utc="2026-10-18T00:09:59+00:00"), "follow observation"),
    (lambda q: q.update(response_received_at_utc="2026-10-18T00:10:04+00:00"), "follow observation"),
    (lambda q: q.update(request_started_at_utc="2026-10-18T00:10:03+00:00"), "follow observation"),
    (lambda q: q.update(request_started_at_utc="2026-10-18T00:10:00"), "Timezone-aware"),
    (lambda q: q.update(extra="bad"), "envelope"),
    (lambda q: q.update(response_body_utf8="x"*65537), "bounded"),
])
def test_quote_envelope_refusals_before_creation(monkeypatch, tmp_path, change, match):
    observation(monkeypatch, tmp_path)
    evidence = quote(); change(evidence)
    clock(monkeypatch, "2026-10-18T00:10:03+00:00")
    with pytest.raises(ValueError, match=match):paper.record(tmp_path/"journal", tmp_path/"ledger", evidence)
    assert not (tmp_path/"ledger").exists()


@pytest.mark.parametrize("field,value,match", [
    ("bid", "NaN", "finite"), ("ask", "Infinity", "finite"), ("bid", 0, "positive"),
    ("ask", -1, "positive"), ("bid", True, "Invalid quote"), ("bid", 122, "Crossed"),
    ("time", "2026-10-18T00:09:59+00:00", "precedes"),
    ("time", "2026-10-18T00:10:04+00:00", "future"),
])
def test_ticker_refusals(monkeypatch, tmp_path, field, value, match):
    observation(monkeypatch, tmp_path)
    evidence = quote(); body = json.loads(evidence["response_body_utf8"])
    body[field] = value; evidence["response_body_utf8"] = json.dumps(body)
    clock(monkeypatch, "2026-10-18T00:10:03+00:00")
    with pytest.raises(ValueError, match=match):paper.record(tmp_path/"journal", tmp_path/"ledger", evidence)
    assert not (tmp_path/"ledger").exists()


@pytest.mark.parametrize("case,match", [("delay", "stale before"), ("latency", "too long"), ("trade", "time is stale"), ("midnight", "stale")])
def test_freshness_windows(monkeypatch, tmp_path, case, match):
    observation(monkeypatch, tmp_path)
    if case == "trade":clock(monkeypatch, "2026-10-18T00:10:20+00:00")
    if case == "midnight":clock(monkeypatch, "2026-10-18T23:59:59+00:00")
    evidence = quote()
    if case == "delay":clock(monkeypatch, "2026-10-18T00:10:33+00:00")
    if case == "latency":
        evidence["response_received_at_utc"] = "2026-10-18T00:10:16+00:00"
        clock(monkeypatch, "2026-10-18T00:10:17+00:00")
    if case == "trade":
        body=json.loads(evidence["response_body_utf8"]);body["time"]="2026-10-18T00:10:01+00:00"
        evidence["response_body_utf8"]=json.dumps(body)
        clock(monkeypatch, "2026-10-18T00:10:23+00:00")
    if case == "midnight":clock(monkeypatch, "2026-10-19T00:00:02+00:00")
    with pytest.raises(ValueError, match=match):paper.record(tmp_path/"journal", tmp_path/"ledger", evidence)
    assert not (tmp_path/"ledger").exists()


def test_stale_pending_and_multiple_unconsumed_refused(monkeypatch, tmp_path):
    observation(monkeypatch, tmp_path)
    clock(monkeypatch, "2026-10-19T00:10:00+00:00")
    with pytest.raises(ValueError, match="stale"):paper.prepare(tmp_path/"journal", tmp_path/"ledger")
    observation(monkeypatch, tmp_path, "2026-10-18")
    with pytest.raises(ValueError, match="Multiple unconsumed"):append(monkeypatch, tmp_path)
    assert not (tmp_path/"ledger").exists()


def test_calendar_gaps_preserve_position_and_accrue_expense(monkeypatch, tmp_path):
    observation(monkeypatch, tmp_path)
    first=append(monkeypatch,tmp_path)
    observation(monkeypatch,tmp_path,"2026-10-20",{"2026-10-17":120,"2026-10-20":125})
    last=append(monkeypatch,tmp_path,124,126)
    event=json.loads((tmp_path/"ledger/2026-10-20.json").read_text())["payload"]
    assert event["unrecorded_calendar_days_since_previous_signal"] == 2
    for name in IDS:
        a,b=first["books"]["base"][name],last["books"]["base"][name]
        assert b["quantity_btc"] == a["quantity_btc"] and b["hypothetical_fill_count"] == 1
        assert b["operating_cost_sensitivity_usd"] == pytest.approx(360/365.25)
    assert last["events"] == 2


@pytest.mark.parametrize("change", ["cash", "fill", "source", "quote", "build", "chain"])
def test_rehashed_tampering_detected_by_replay(monkeypatch,tmp_path,change):
    observation(monkeypatch,tmp_path);append(monkeypatch,tmp_path)
    path=tmp_path/"ledger/2026-10-17.json";event=json.loads(path.read_text());payload=event["payload"]
    if change == "cash":payload["books"]["base"][IDS[0]]["cash_usd"] += 100
    if change == "fill":payload["books"]["base"][IDS[0]]["fill"]["price_usd"] = 1
    if change == "source":payload["observation_record_sha256"] = "0"*64
    if change == "quote":
        body=json.loads(payload["quote"]["response_body_utf8"]);body["bid"]="118"
        payload["quote"]["response_body_utf8"]=json.dumps(body)
    if change == "build":payload["ledger_build_sha256"] = "0"*64
    if change == "chain":payload["previous_event_sha256"] = "1"*64
    event["event_sha256"]=journal.digest(journal.canonical(payload));path.write_bytes(journal.canonical(event))
    with pytest.raises(ValueError,match="replay mismatch"):paper.verify(tmp_path/"journal",tmp_path/"ledger")


def test_modified_source_journal_refused(monkeypatch,tmp_path):
    observation(monkeypatch,tmp_path);append(monkeypatch,tmp_path)
    path=tmp_path/"journal/2026-10-17/observation.json";event=json.loads(path.read_text())
    event["payload"]["candidates"][0]["entry_condition"]=False
    event["record_sha256"]=journal.digest(journal.canonical(event["payload"]));path.write_bytes(journal.canonical(event))
    with pytest.raises(ValueError,match="conflict"):paper.verify(tmp_path/"journal",tmp_path/"ledger")


@pytest.mark.parametrize("kind",["lock", "unknown", "partial", "symlink", "protocol"])
def test_invalid_ledger_storage_refused(monkeypatch,tmp_path,kind):
    observation(monkeypatch,tmp_path);append(monkeypatch,tmp_path)
    root=tmp_path/"ledger"
    if kind=="lock":(root/".record.lock").mkdir()
    if kind=="unknown":(root/"unexpected").write_text("bad")
    if kind=="partial":(root/"2026-10-17.json").write_text('{"payload":')
    if kind=="symlink":
        (root/"2026-10-17.json").unlink();(root/"2026-10-17.json").symlink_to(tmp_path/"input.csv")
    if kind=="protocol":(root/"protocol.json").write_text("{}")
    with pytest.raises((ValueError,OSError)):paper.verify(tmp_path/"journal",root)


def test_interrupted_write_is_not_overwritten(monkeypatch,tmp_path):
    observation(monkeypatch,tmp_path)
    original=journal._write_new
    def interrupted(path, raw):
        if path.name=="2026-10-17.json":
            path.write_bytes(raw[:30]);raise OSError("Simulated interrupted write")
        original(path,raw)
    monkeypatch.setattr(journal,"_write_new",interrupted)
    with pytest.raises(OSError,match="interrupted"):append(monkeypatch,tmp_path)
    saved=(tmp_path/"ledger/2026-10-17.json").read_bytes()
    monkeypatch.setattr(journal,"_write_new",original)
    with pytest.raises(ValueError):append(monkeypatch,tmp_path)
    assert (tmp_path/"ledger/2026-10-17.json").read_bytes()==saved


def test_protocol_and_build_identity_and_crlf(monkeypatch,tmp_path):
    raw,spec,build=paper.contract()
    original=Path.read_bytes
    def crlf(path):
        value=original(path)
        return value.replace(b"\n",b"\r\n") if path in {paper.PROTOCOL,Path(paper.__file__)} else value
    monkeypatch.setattr(Path,"read_bytes",crlf)
    assert paper.contract()==(raw,spec,build)
    monkeypatch.setattr(Path,"read_bytes",original)
    modified=tmp_path/"modified.json";modified.write_bytes(raw+b" ")
    monkeypatch.setattr(paper,"PROTOCOL",modified)
    with pytest.raises(ValueError,match="Frozen paper protocol"):paper.contract()


@pytest.mark.parametrize("suffix",["", "nested"])
def test_nested_journal_and_ledger_refused(tmp_path,suffix):
    with pytest.raises(ValueError,match="separate non-nested"):
        paper.verify(tmp_path,tmp_path/suffix)


def test_skipped_record_in_ledger_is_detected(monkeypatch,tmp_path):
    observation(monkeypatch,tmp_path);append(monkeypatch,tmp_path)
    observation(monkeypatch,tmp_path,"2026-10-18");append(monkeypatch,tmp_path)
    (tmp_path/"ledger/2026-10-17.json").unlink()
    with pytest.raises(ValueError,match="every observation"):paper.verify(tmp_path/"journal",tmp_path/"ledger")


def test_malformed_duplicate_json_keys_refused(monkeypatch,tmp_path):
    observation(monkeypatch,tmp_path);evidence=quote()
    evidence["response_body_utf8"]='{"bid":"119","bid":"120","ask":"121","time":"2026-10-18T00:10:01Z"}'
    clock(monkeypatch,"2026-10-18T00:10:03+00:00")
    with pytest.raises(ValueError,match="Duplicate JSON"):paper.record(tmp_path/"journal",tmp_path/"ledger",evidence)


def test_clock_advance_during_replay_refuses_stale_quote(monkeypatch,tmp_path):
    observation(monkeypatch,tmp_path);append(monkeypatch,tmp_path)
    observation(monkeypatch,tmp_path,"2026-10-18");evidence=quote()
    clock(monkeypatch,"2026-10-19T00:10:03+00:00")
    original=paper._replay
    def slow(*a,**k):
        result=original(*a,**k);clock(monkeypatch,"2026-10-19T00:10:40+00:00");return result
    monkeypatch.setattr(paper,"_replay",slow)
    with pytest.raises(ValueError,match="stale before"):paper.record(tmp_path/"journal",tmp_path/"ledger",evidence)
    assert not (tmp_path/"ledger/2026-10-18.json").exists()
