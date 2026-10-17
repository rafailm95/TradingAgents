"""Synthetic-only bridge and exact conditional89/90 matrix; never historical profit."""
import copy,gzip,json,sys
from pathlib import Path
from dataclasses import replace
from decimal import Decimal as D
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent));sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from test_funding_futures_019 import market
from test_bybit_replay import signals,FIRST
from test_sol_funding_022 import synthetic
from tradingagents import futures_calendar_023 as b
from tradingagents.bybit_history import DAY,HOUR
import run_futures_calendar_023 as runner

def setup_parts(monkeypatch):
    a=b.SPLIT-2*DAY;c=b.SPLIT;e=c+2*DAY
    monkeypatch.setattr(b,'START',a);monkeypatch.setattr(b,'END',e)
    return synthetic(a,c),synthetic(c,e)

@pytest.mark.parametrize('symbol',b.SYMBOLS)
def test_disjoint_contiguous_join_revalidates_and_preserves_rows(monkeypatch,symbol):
    p,n=setup_parts(monkeypatch);before=copy.deepcopy((p,n))
    data,m=b.join_data(p,n,symbol)
    assert (p,n)==before and len(m.trade)==96 and len(m.funding)==12
    assert data['trade']==p['trade']+n['trade'] and m.symbol==symbol

@pytest.mark.parametrize('kind',['trade','mark','funding'])
@pytest.mark.parametrize('mutation',['missing','overlap','out_of_window'])
def test_join_rejects_boundary_defects(monkeypatch,kind,mutation):
    p,n=setup_parts(monkeypatch)
    if mutation=='missing':n[kind].pop(0)
    elif mutation=='overlap':n[kind].insert(0,p[kind][-1])
    elif kind=='funding':n[kind][-1]['timestamp_ms']+=DAY
    else:n[kind][-1][0]=str(int(n[kind][-1][0])+DAY)
    with pytest.raises(ValueError):b.join_data(p,n,'BTCUSDT')

def test_join_rejects_new_funding_cadence_and_bad_ohlc(monkeypatch):
    p,n=setup_parts(monkeypatch);n['funding'][0]['interval_hours']=4
    with pytest.raises(ValueError):b.join_data(p,n,'SOLUSDT')
    n['funding'][0]['interval_hours']=8;n['trade'][0][2]='0'
    with pytest.raises(ValueError):b.join_data(p,n,'SOLUSDT')

def test_part_checks_external_and_embedded_manifest_pins(tmp_path):
    root=tmp_path/'BTCUSDT';root.mkdir();(root/'manifest.json').write_text('{}')
    digest=b.old.sha(root/'manifest.json')
    p=root/'normalized.json.gz';v={'schema':'expected','audit':{'status':'COMPLETE','manifest_sha256':digest},'datasets':{'BTCUSDT':{'x':1}}}
    p.write_bytes(gzip.compress(json.dumps(v).encode(),mtime=0))
    record={'normalized_sha256':b.old.sha(p),'manifest_sha256':digest}
    assert b.load_part(tmp_path,'BTCUSDT',record,'expected')=={'x':1}
    with pytest.raises(ValueError):b.load_part(tmp_path,'BTCUSDT',record,'other')
    v['audit']['manifest_sha256']='0'*64;p.write_bytes(gzip.compress(json.dumps(v).encode(),mtime=0));record['normalized_sha256']=b.old.sha(p)
    with pytest.raises(ValueError,match='Embedded'):b.load_part(tmp_path,'BTCUSDT',record,'expected')
    p.write_bytes(b'changed')
    with pytest.raises(ValueError,match='Input pin'):b.load_part(tmp_path,'BTCUSDT',record,'expected')

@pytest.mark.parametrize('candidate',runner.CANDIDATES)
def test_training_signals_cannot_view_2026_prices_or_funding(candidate):
    m=market(206);end=FIRST+2*DAY
    baseline=runner.ledger.make_signals(m,candidate,end);future=copy.deepcopy(m)
    future.frame.loc[future.frame.Date>=pd.to_datetime(end,unit='ms',utc=True),'Close']=1e9
    for t in future.funding:
        if t>=end:future.funding[t]=D(100)
    pd.testing.assert_frame_equal(baseline,runner.ledger.make_signals(future,candidate,end))

@pytest.mark.parametrize('cash',[True,False])
def test_full89_or90_matrix_and_selected_fold_reuses_exact_result(tmp_path,monkeypatch,cash):
    m=replace(market(206),symbol='SOLUSDT')
    monkeypatch.setattr(runner,'T0',FIRST);monkeypatch.setattr(runner,'T1',FIRST+2*DAY);monkeypatch.setattr(runner,'T3',FIRST+6*DAY)
    monkeypatch.setattr(runner,'load_market',lambda *a:m)
    monkeypatch.setattr(runner.ledger,'make_signals',lambda market,candidate,end:signals(market,(199,201,203),(200,202,204),vol=.6).loc[lambda x:x.index<end])
    train=tmp_path/'train';evaluate=tmp_path/'evaluate';train.mkdir();evaluate.mkdir()
    t=runner.train_asset(((str(tmp_path),str(tmp_path)),str(train),'SOLUSDT',{},'train'))
    assert t['new_simulations']==12 and t['selection']['selected']=='cash'
    if not cash:t['selection']['selected']=runner.CANDIDATES[0] # Explicit synthetic branch fixture, not a historical selection.
    e=runner.evaluate_asset(((str(tmp_path),str(tmp_path)),str(evaluate),'SOLUSDT',{},t))
    assert t['new_simulations']+e['new_simulations']==(90 if cash else 89)
    assert len(e['benchmarks'])==5 and len(e['selected_2026_fold'])==12
    assert all(len(v)==12 for v in e['comparisons'].values())
    assert all(a['status']=='PASS' and a['max_error_usdt']=='0' for a in e['audits'])
    files=set()
    for key,r in e['selected_2026_fold'].items():
        files.add(r['record']['file']);assert r['metrics']['signal_exits']<20
        assert not r['gate']['passed'] and 'FEWER_THAN_20_SIGNAL_EXITS' in r['gate']['failed_gates']
        if cash:assert D(r['metrics']['operating_expense_usdt'])>0 and not r['reused_without_replay']
        else:assert r['reused_without_replay'] and r['record'] in e['comparisons'][runner.CANDIDATES[0]]
    assert len(files)==(1 if cash else 12)
    assert e['benchmarks']['cash']['metrics']['operating_expense_usdt']=='0'

def test_selection_external_hash_guard(tmp_path):
    (tmp_path/'selection.json').write_text('{}')
    with pytest.raises(ValueError,match='pin mismatch'):runner.read_selection(tmp_path,'0'*64,{},'0'*64,'train')
