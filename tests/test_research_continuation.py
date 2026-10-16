"""New-cohort isolation, anchored history, replay, data ingest and asset labels."""
from datetime import date,datetime,timedelta,timezone
import hashlib
import io
import json
from pathlib import Path
import shutil

import numpy as np
import pytest

from tradingagents import expanded_journal as journal
from tradingagents import expanded_paper as paper
from tradingagents import expanded_campaign as campaign
from tradingagents import strategy_families as new
from tradingagents import strategy_lab as old
from scripts import observe_expanded_candidates as observer
from scripts.fetch_research_candles import download
from scripts.run_cross_asset_lab import simulate,select,CANDIDATES
from tests.test_strategy_backtest import frame_for,bounds


def clock(monkeypatch,day="2026-10-18",seconds=0):
    now=datetime.fromisoformat(day+"T06:00:00+00:00")+timedelta(seconds=seconds)
    monkeypatch.setattr(journal,"utc_now",lambda:now)
    return now


def data(tmp_path,day="2026-10-17"):
    # Public historical seed plus explicitly synthetic future extension.
    spec=journal.contract()[1];raw=journal._seed_bytes(spec)
    start=date.fromisoformat(spec["seed_last_day"])+timedelta(days=1)
    for i in range((date.fromisoformat(day)-start).days+1):
        stamp=start+timedelta(days=i);c=120000+100*i
        raw+=f"{stamp},{c},{c+1000},{c-1000},{c},5000\n".encode()
    target=tmp_path/f"input-{day}.csv";target.write_bytes(raw)
    return target


def quote():
    now=journal.utc_now()
    return {"endpoint":paper.contract()[1]["quote_endpoint"],"request_started_at_utc":now.isoformat(),
        "response_received_at_utc":(now+timedelta(seconds=2)).isoformat(),
        "response_body_utf8":json.dumps({"bid":"119900","ask":"120100","time":(now+timedelta(seconds=1)).isoformat()})}


def initialized(monkeypatch,tmp_path,day="2026-10-17"):
    now=(date.fromisoformat(day)+timedelta(days=1)).isoformat();clock(monkeypatch,now)
    journal.observe(data(tmp_path,day),tmp_path/"journal")
    q=quote();clock(monkeypatch,now,3)
    return paper.record(tmp_path/"journal",tmp_path/"ledger",q)


def test_five_candidates_preserve_failed_selection_provenance_and_old_sources():
    _,spec,_=journal.contract()
    assert len(spec["candidates"])==5
    assert all(d["selection_class"]=="POST_HOC_EXPLORATORY_DELAY_FAILED" for d in spec["candidates"])
    frozen=json.loads((journal.REPO/"docs/PAPER_AUTOMATION_RUNTIME.json").read_text())
    for name,expected in frozen["source_files"].items():
        assert hashlib.sha256((journal.REPO/name).read_bytes()).hexdigest()==expected


def test_no_early_network_or_state(monkeypatch,tmp_path):
    clock(monkeypatch,"2026-10-16")
    monkeypatch.setattr(observer.subprocess,"run",lambda *a,**k:pytest.fail("Unexpected network"))
    assert observer.run(tmp_path/"state")["status"]=="WAITING_FOR_NEW_CANDLES"
    assert not (tmp_path/"state").exists()


def test_full_anchored_signals_equal_original_research(monkeypatch,tmp_path):
    clock(monkeypatch);csv=data(tmp_path);root=tmp_path/"journal"
    journal.observe(csv,root)
    record=json.loads((root/"2026-10-17/observation.json").read_text())["payload"]
    f=journal.load_daily(csv)
    assert record["snapshot_rows"]==2847
    for definition in record["candidates"]:
        row=new.signals(f,definition["family"]).iloc[-1]
        assert definition["entry_condition"]==bool(row.entry)
        assert definition["exit_condition"]==bool(row.exit)
        assert definition["hypothetical_entry_fraction"]==old.allocation(definition["sizing"],float(row.vol60))
    assert (root/"2026-10-17/candles.csv").read_bytes()==csv.read_bytes()


def test_replay_cached_indicators_are_prefix_identical(monkeypatch,tmp_path):
    for day in ("2026-10-17","2026-10-18","2026-10-20"):
        clock(monkeypatch,(date.fromisoformat(day)+timedelta(days=1)).isoformat())
        journal.observe(data(tmp_path,day),tmp_path/"journal")
    assert journal.verify(tmp_path/"journal")["records"]==3
    last=json.loads((tmp_path/"journal/2026-10-20/observation.json").read_text())["payload"]
    assert last["unrecorded_days_since_previous"]==1


def test_revised_seed_refused_before_mutation(monkeypatch,tmp_path):
    clock(monkeypatch);csv=data(tmp_path);raw=csv.read_bytes();csv.write_bytes(raw.replace(b"2019-01-01",b"2018-01-01",1))
    with pytest.raises(ValueError,match="seed prefix"):journal.observe(csv,tmp_path/"journal")
    assert not (tmp_path/"journal").exists()


def test_revised_accepted_extension_refused(monkeypatch,tmp_path):
    clock(monkeypatch);journal.observe(data(tmp_path),tmp_path/"journal")
    clock(monkeypatch,"2026-10-19");csv=data(tmp_path,"2026-10-18")
    csv.write_bytes(csv.read_bytes().replace(b"2026-10-16,120000,121000,119000,120000,5000",b"2026-10-16,120000,121000,119000,120000,5001"))
    with pytest.raises(ValueError,match="revised"):journal.observe(csv,tmp_path/"journal")
    assert not (tmp_path/"journal/2026-10-18").exists()


def test_fourteen_independent_books_and_duplicate_noop(monkeypatch,tmp_path):
    result=initialized(monkeypatch,tmp_path)
    assert result["events"]==1 and len(result["books"]["base"])==7
    for scenario,books in result["books"].items():
        for book in books.values():
            assert book["cash_usd"]>=0 and book["quantity_btc"]>=0
            assert book["net_pnl_usd"]==pytest.approx(book["realized_pnl_usd"]+book["unrealized_liquidation_pnl_usd"]-book["operating_cost_sensitivity_usd"])
    path=tmp_path/"ledger/2026-10-17.json";before=path.read_bytes()
    assert paper.record(tmp_path/"journal",tmp_path/"ledger",{})["status"]=="ALREADY_RECORDED"
    assert path.read_bytes()==before
    assert paper.verify(tmp_path/"journal",tmp_path/"ledger")["events"]==1


def test_tampered_quote_is_not_repriced_or_accepted(monkeypatch,tmp_path):
    initialized(monkeypatch,tmp_path);path=tmp_path/"ledger/2026-10-17.json"
    event=json.loads(path.read_text());event["payload"]["quote"]["response_body_utf8"]=event["payload"]["quote"]["response_body_utf8"].replace('119900','119800')
    path.write_text(json.dumps(event))
    with pytest.raises(ValueError,match="replay mismatch"):paper.verify(tmp_path/"journal",tmp_path/"ledger")


def test_stale_pending_signal_blocks_new_execution(monkeypatch,tmp_path):
    clock(monkeypatch);journal.observe(data(tmp_path),tmp_path/"journal")
    clock(monkeypatch,"2026-10-19")
    with pytest.raises(ValueError,match="stale"):paper.prepare(tmp_path/"journal",tmp_path/"ledger")


def setup_campaign(monkeypatch,tmp_path):
    clock(monkeypatch,"2026-10-16")
    raw=journal.canonical({"schema_version":1,"campaign_id":campaign.CAMPAIGN_ID,"source_files":{
        "tradingagents/expanded_campaign.py":journal.digest(Path(campaign.__file__).read_bytes())}})
    path=tmp_path/"runtime.json";path.write_bytes(raw);monkeypatch.setattr(campaign,"RUNTIME_MANIFEST",str(path))
    root=tmp_path/"campaign";root.mkdir();sha=journal.digest(raw)
    (root/"checkpoint.json").write_bytes(journal.canonical(campaign.initial_checkpoint(sha)))
    return root,sha


def test_campaign_restore_and_missing_state_refusal(monkeypatch,tmp_path):
    root,sha=setup_campaign(monkeypatch,tmp_path)
    def execute(state):
        state.mkdir();clock(monkeypatch)
        journal.observe(data(tmp_path),state/"journal")
        q=quote();clock(monkeypatch,seconds=3)
        return paper.record(state/"journal",state/"paper_ledger",q)
    result=campaign.run(root,sha,execute)
    assert result["status"]=="LOCAL_PROPOSAL_READY" and result["verification"]["events"]==1
    fresh=tmp_path/"restored";shutil.copytree(root,fresh)
    assert campaign.run(fresh,sha,lambda _:pytest.fail("execute"),verify_only=True)["verification"]["events"]==1
    (fresh/"state/paper_ledger/2026-10-17.json").unlink()
    with pytest.raises(ValueError,match="missing"):campaign.run(fresh,sha,lambda _:pytest.fail("execute"))


def test_partial_new_observation_is_quarantined(monkeypatch,tmp_path):
    root,sha=setup_campaign(monkeypatch,tmp_path)
    original=journal._write_new
    def broken(path,raw):
        if path.name=="observation.json":raise OSError("Synthetic write interruption")
        original(path,raw)
    monkeypatch.setattr(journal,"_write_new",broken)
    def execute(state):
        state.mkdir();clock(monkeypatch);return journal.observe(data(tmp_path),state/"journal")
    result=campaign.run(root,sha,execute)
    assert result["status"]=="LOCAL_QUARANTINE_READY" and result["integrity_status"]=="INSPECTION_REQUIRED"
    with pytest.raises(ValueError,match="inspection"):campaign.run(root,sha,lambda _:pytest.fail("execute"))


@pytest.mark.parametrize("item",[old.Candidate('breakout20','fixed50'),new.Candidate('adx_directional','fixed50'),new.Candidate('aroon_trend','vol15_cap50')])
def test_cross_asset_adapter_matches_existing_ledgers(item):
    c=100*np.exp(np.cumsum(np.random.default_rng(11).normal(.002,.035,600)))
    f=frame_for(c);mod=new if isinstance(item,new.Candidate) else old
    features={item.family:mod.signals(f,item.family)};cost={"fee":60,"slippage":10}
    result,check=simulate(f,*bounds(f),item,features,cost)
    direct=mod.simulate(f,*bounds(f),item,prepared=features[item.family])
    assert result["metrics"]==direct["metrics"]
    assert all('asset_quantity' in r and 'btc' not in r for r in result["curve"])
    np.testing.assert_array_equal([x['equity'] for x in result['curve']],[x['equity'] for x in direct['curve']])
    assert check['status']=='PASS'


def test_cross_asset_selector_needs_all40_and_falls_back_to_cash():
    with pytest.raises(ValueError):select({})
    t={c.id:{k:{"profit_after_operating_usd":-1,"max_close_drawdown_pct":10,"closed_trades":20,"annualized_after_operating_pct":5} for k in ('base','stress')} for c in CANDIDATES}
    assert select(t)['selected']=='cash'


class Response:
    status=200
    def __init__(self,url,body):self.url=url;self.body=body
    def geturl(self):return self.url
    def read(self,n):return self.body[:n]
    def __enter__(self):return self
    def __exit__(self,*args):pass


def test_download_retains_exact_response_and_validates_provenance(tmp_path):
    stamp=int(datetime(2026,10,14,tzinfo=timezone.utc).timestamp());raw=json.dumps([[stamp,99,102,100,101,50]]).encode()
    calls=[]
    def opener(req,timeout):calls.append(req.full_url);return Response(req.full_url,raw)
    result=download('ETH-USD',date(2026,10,14),date(2026,10,15),tmp_path/'data',opener=opener)
    assert len(calls)==1 and '/ETH-USD/candles?' in calls[0]
    assert (tmp_path/'data/raw_01.json').read_bytes()==raw
    assert result['product']=='ETH-USD' and result['rows']==1


@pytest.mark.parametrize('row',[[0,1,2,3,1,5],[0,1,2,1,1,-5],[0,1,2,True,1,5]])
def test_bad_market_data_cannot_become_a_dataset(tmp_path,row):
    row[0]=int(datetime(2026,10,14,tzinfo=timezone.utc).timestamp())
    with pytest.raises(ValueError):
        download('LTC-USD',date(2026,10,14),date(2026,10,15),tmp_path/'data',opener=lambda r,timeout:Response(r.full_url,json.dumps([row]).encode()))
    assert not (tmp_path/'data/manifest.json').exists()


def milestone_events(days=181,sells=20,stress_pnl=100):
    events=[];start=date(2026,10,17)
    for i in range(days):
        day=start+timedelta(days=i)
        books={cost:{'candidate':{'action':'SELL' if i<sells else 'FLAT',
            'net_pnl_usd':100 if cost=='base' else stress_pnl,'sampled_max_drawdown_fraction':.1}}
            for cost in ('base','stress')}
        events.append({'payload':{'as_of_utc_day':day.isoformat(),
            'valuation_at_utc':(day+timedelta(days=1)).isoformat()+'T06:00:00+00:00','books':books}})
    return events


@pytest.mark.parametrize('case',['short','few_trades','stress_loss','missing_days','pending'])
def test_forward_milestone_requires_all_evidence_dimensions(case):
    from scripts.expanded_forward_status import assess
    events=milestone_events(days=180 if case=='short' else 181,sells=19 if case=='few_trades' else 20,
        stress_pnl=-1 if case=='stress_loss' else 100)
    if case=='missing_days':events=events[:30]+events[45:]
    result=assess({'pending_observations':1 if case=='pending' else 0},events,'2026-10-17')
    assert result['milestone_candidates']==[]


def test_forward_milestone_positive_fixture_is_only_a_monitoring_flag():
    from scripts.expanded_forward_status import assess
    result=assess({'pending_observations':0},milestone_events(),'2026-10-17')
    assert result['milestone_candidates']==['candidate'] and result['orders']==0
    assert 'No statistical proof' in result['meaning']
    assert assess({'pending_observations':0},[],'2026-10-17')['milestone_candidates']==[]
