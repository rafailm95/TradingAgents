"""Orchestration and HTTP adapter tests with synthetic responses; no network."""
from datetime import timedelta
import importlib.util
from pathlib import Path

import pytest

from tradingagents import candidate_journal as journal
from tradingagents import paper_portfolio as paper
from tests.test_paper_portfolio import clock, observation, quote

SCRIPT=Path(__file__).parents[1]/"scripts/observe_paper_portfolios.py"
spec=importlib.util.spec_from_file_location("paper_runner",SCRIPT)
runner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_before_eligibility_no_network_or_state(monkeypatch,tmp_path):
    clock(monkeypatch,"2026-10-16T13:00:00+00:00")
    def forbidden(*a,**k):raise AssertionError("No network before eligibility")
    monkeypatch.setattr(paper,"urlopen",forbidden)
    monkeypatch.setattr(runner.observe_candidates.subprocess,"run",forbidden)
    state=tmp_path/"state"
    result=runner.run(state)
    assert result["status"]=="WAITING_FOR_NEW_CANDLES" and result["quote_requests"]==0
    assert not state.exists()


def test_observe_then_quote_then_record_and_skip_duplicate(monkeypatch,tmp_path):
    clock(monkeypatch,"2026-10-18T00:10:00+00:00")
    calls=[]
    def observe(state):
        calls.append("observe")
        if not (state/"journal").exists():observation(monkeypatch,state)
        return {"status":"ALREADY_RECORDED","orders":0}
    def fetch():
        calls.append("quote")
        assert journal.verify(tmp_path/"journal")["records"]==1
        evidence=quote()
        clock(monkeypatch,(journal.utc_now()+timedelta(seconds=3)).isoformat())
        return evidence
    monkeypatch.setattr(runner.observe_candidates,"run",observe)
    monkeypatch.setattr(paper,"fetch_quote",fetch)
    assert runner.run(tmp_path)["status"]=="RECORDED"
    duplicate=runner.run(tmp_path)
    assert duplicate["status"]=="ALREADY_RECORDED" and duplicate["quote_requests"]==0
    assert calls==["observe","quote","observe"]


def test_failed_quote_preserves_signal_then_manual_retry_can_record(monkeypatch,tmp_path):
    observation(monkeypatch,tmp_path);calls=[]
    monkeypatch.setattr(runner.observe_candidates,"run",lambda state:{"status":"ALREADY_RECORDED"})
    def fail():calls.append(1);raise TimeoutError("Synthetic HTTP timeout")
    monkeypatch.setattr(paper,"fetch_quote",fail)
    with pytest.raises(TimeoutError):runner.run(tmp_path)
    assert calls==[1] and not (tmp_path/"paper_ledger").exists()
    assert journal.verify(tmp_path/"journal")["records"]==1
    def good():
        evidence=quote();clock(monkeypatch,(journal.utc_now()+timedelta(seconds=3)).isoformat());return evidence
    monkeypatch.setattr(paper,"fetch_quote",good)
    assert runner.run(tmp_path)["status"]=="RECORDED"
    assert paper.verify(tmp_path/"journal",tmp_path/"paper_ledger")["events"]==1


def test_stale_signal_blocks_before_any_download(monkeypatch,tmp_path):
    observation(monkeypatch,tmp_path)
    clock(monkeypatch,"2026-10-19T00:10:00+00:00")
    def forbidden(*a,**k):raise AssertionError("Should refuse before download")
    monkeypatch.setattr(runner.observe_candidates,"run",forbidden)
    with pytest.raises(ValueError,match="stale"):runner.run(tmp_path)


def test_candle_download_failure_does_not_request_quote(monkeypatch,tmp_path):
    monkeypatch.setattr(runner.observe_candidates,"run",lambda state:{"status":"DOWNLOAD_FAILED","orders":0})
    def forbidden():raise AssertionError("No quote after failed candles")
    monkeypatch.setattr(paper,"fetch_quote",forbidden)
    result=runner.run(tmp_path)
    assert result["status"]=="DOWNLOAD_FAILED" and result["quote_requests"]==0
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("mode",["ok","large","status","redirect","timeout"])
def test_bounded_single_public_get(monkeypatch,tmp_path,mode):
    clock(monkeypatch,"2026-10-18T00:10:00+00:00")
    calls=[];limits=[];endpoint=paper.contract()[1]["quote_endpoint"]
    body=b'{"bid":"119","ask":"121","time":"2026-10-18T00:10:01Z"}'
    class Response:
        status=500 if mode=="status" else 200
        def geturl(self):return "https://invalid.example" if mode=="redirect" else endpoint
        def read(self,limit):
            limits.append(limit)
            clock(monkeypatch,"2026-10-18T00:10:02+00:00")
            return b"x"*limit if mode=="large" else body
        def __enter__(self):return self
        def __exit__(self,*args):return False
    def request(req,timeout):
        calls.append(req)
        assert timeout==10 and req.get_method()=="GET" and req.full_url==endpoint
        assert "Authorization" not in req.headers
        if mode=="timeout":raise TimeoutError("synthetic timeout")
        return Response()
    monkeypatch.setattr(paper,"urlopen",request)
    if mode=="ok":
        result=paper.fetch_quote()
        assert result["response_body_utf8"]==body.decode()
        assert result["request_started_at_utc"]=="2026-10-18T00:10:00+00:00"
        assert result["response_received_at_utc"]=="2026-10-18T00:10:02+00:00"
    else:
        with pytest.raises((ValueError,TimeoutError)):paper.fetch_quote()
    assert len(calls)==1
    if mode in {"ok","large"}:assert limits==[65537]


def test_cli_reports_ambiguous_persistence_as_unverified(monkeypatch,capsys,tmp_path):
    monkeypatch.setattr(runner.sys,"argv",[str(SCRIPT),"--state-dir",str(tmp_path)])
    def fail(state):raise OSError("Simulated write failure")
    monkeypatch.setattr(runner,"run",fail)
    assert runner.main()==1
    output=capsys.readouterr().out
    assert '"paper_record_created": "UNVERIFIED"' in output and '"orders": 0' in output


def test_verify_only_never_downloads(monkeypatch,capsys,tmp_path):
    monkeypatch.setattr(runner.sys,"argv",[str(SCRIPT),"--state-dir",str(tmp_path),"--verify-only"])
    def forbidden(state):raise AssertionError("Should not call observation runner")
    monkeypatch.setattr(runner,"run",forbidden)
    assert runner.main()==0 and '"status": "NOT_STARTED"' in capsys.readouterr().out
    assert not list(tmp_path.iterdir())
