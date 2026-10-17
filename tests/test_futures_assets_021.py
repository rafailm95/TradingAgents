"""Synthetic symbol/provenance/cashflow tests; no real strategy PnL."""
import copy,hashlib,io,json,zipfile
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_binance_archive import native,row
from test_bybit_replay import signals,FIRST
from tradingagents import binance_assets_021 as b
from tradingagents import binance_archive as original
from tradingagents import futures_replay_019 as engine
from scripts import collect_futures_assets_021 as collect


@pytest.mark.parametrize('symbol',b.SYMBOLS)
def test_exact_bounded_archive_inventory(symbol):
    items=list(collect.specs(symbol));assert len(items)==144
    assert len({x['url'] for x in items})==144
    assert all(x['symbol']==symbol and x['url'].startswith(collect.BASE+'monthly/') for x in items)
    assert items[0]['period']=='2022-01' and items[-1]['period']=='2025-12'


@pytest.mark.parametrize('symbol',['SOLUSDT','XRPUSDT'])
def test_symbol_extension_does_not_change_accounting(symbol):
    d=native();m=b.prepare(d,symbol);old=original.prepare(d,'BTCUSDT')
    s=signals(m);kwargs=dict(candidate=engine.CANDIDATES[0],prepared_signals=s,adverse_funding=True)
    a=engine.replay(m,FIRST,m.end,**kwargs);z=engine.replay(old,FIRST,old.end,**kwargs)
    assert a['symbol']==symbol
    for k in ('metrics','events','fills','trades','curve','funding_events','independent_wealth_audit'):assert a[k]==z[k]


def test_unsupported_symbols_and_incomplete_history_rejected():
    with pytest.raises(ValueError):list(collect.specs('ETHUSDT'))
    with pytest.raises(ValueError):b.prepare(native(),'ETHUSDT')
    d=native();d['mark'].pop()
    with pytest.raises(ValueError):b.prepare(d,'SOLUSDT')


@pytest.mark.parametrize('missing_day',[0,1,2])
def test_daily_repair_plan_is_causal_data_rule_not_price_optimization(missing_day):
    start=b.START;end=start+3*b.DAY
    rows=[row(t) for t in range(start,end,b.HOUR) if (t-start)//b.DAY!=missing_day]
    missing,days=collect.repair_days(rows,start,end)
    target=start+missing_day*b.DAY
    assert missing==[target]
    assert set(days)=={target,target-b.DAY if missing_day else target+b.DAY}


def test_verified_probe_reused_without_redownloading_and_checksum_required(tmp_path,monkeypatch):
    item=next(collect.specs('SOLUSDT'));name=Path(item['relative']).name
    mem=io.BytesIO()
    with zipfile.ZipFile(mem,'w') as z:z.writestr(name[:-4]+'.csv','open_time,open\n1,2\n')
    raw=mem.getvalue();path=tmp_path/'probe';path.write_bytes(raw)
    digest=hashlib.sha256(raw).hexdigest();calls=[]
    def fetch(url,*a):calls.append(url);return (digest+'  '+name+'\n').encode()
    monkeypatch.setattr(collect,'fetch',fetch)
    rec=collect.one(tmp_path,item,{item['url']:{'path':str(path),'sha256':digest}})
    assert rec['probe_reused'] and calls==[item['url']+'.CHECKSUM']
    assert collect.one(tmp_path,item,{})==rec and len(calls)==1
    (tmp_path/item['relative']).write_bytes(b'changed')
    with pytest.raises(ValueError):collect.one(tmp_path,item,{})


def test_failed_checksum_preserves_unaccepted_response(tmp_path,monkeypatch):
    monkeypatch.setattr(collect,'fetch',lambda *a:b'bad')
    with pytest.raises(ValueError,match='checksum'):collect.one(tmp_path,next(collect.specs('XRPUSDT')), {})
    assert list((tmp_path/'unverified').glob('*.response'))
    assert not list(tmp_path.rglob('*.receipt.json'))


def test_existing_failed_capture_cannot_retry(tmp_path,monkeypatch):
    monkeypatch.setattr(collect,'fetch',lambda *a:pytest.fail('Must not retry'))
    with pytest.raises(ValueError,match='New output'):collect.collect_symbol(tmp_path,'BTCUSDT',{})


def test_request_failure_stops_asset_and_retains_status(tmp_path,monkeypatch):
    calls=[]
    def one(*a):calls.append(1);raise ValueError('HTTP451')
    monkeypatch.setattr(collect,'one',one)
    out=tmp_path/'asset';r=collect.collect_symbol(out,'XRPUSDT',{})
    assert r['status']=='BLOCKED_OR_INCOMPLETE' and len(calls)==1
    assert json.loads((out/'stopped.json').read_bytes())['new_strategy_simulations']==0
