"""Synthetic end-to-end old-result reuse, two train freezes and annual cash carry."""
import copy,sys,shutil
from pathlib import Path
from decimal import Decimal as D
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent));sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from test_funding_futures_019 import market
from test_bybit_replay import signals,FIRST
from tradingagents.bybit_history import DAY
import run_multifamily_futures_024 as old
from test_multifamily_runner_024 import prior_fixture as base_fixture
import run_multifamily_futures_025 as new

def prior_fixture(tmp_path,monkeypatch):
    base=tmp_path/'base';base.mkdir();m,_=base_fixture(base,monkeypatch)
    shutil.copytree(base/'futures-021-evaluation',tmp_path/'futures-021-evaluation')
    for name,t in [('T0',FIRST),('T1',FIRST+2*DAY),('T2',FIRST+4*DAY),('T3',FIRST+6*DAY)]:monkeypatch.setattr(new,name,t)
    monkeypatch.setattr(new,'load_market',lambda *a:m)
    monkeypatch.setattr(new.ledger,'make_signals',old.ledger.make_signals)
    folders={s:tmp_path/('futures-024-'+s) for s in ('train1','train2','evaluation')}
    for p in folders.values():p.mkdir()
    a=old.train_asset((str(tmp_path),str(folders['train1']),'BTCUSDT',{},'train1'))
    b=old.train_asset((str(tmp_path),str(folders['train2']),'BTCUSDT',{},'train2'))
    e=old.evaluate_asset((str(tmp_path),str(base),str(folders['evaluation']),'BTCUSDT',{},a,b))
    values={'train1':a,'train2':b,'evaluation':e}
    monkeypatch.setattr(new,'prior_summary',lambda symbol,stage:(copy.deepcopy(values[stage]),{'batch':'024','synthetic_fixture':True}))
    return m,values

def test_full20variant_matrix_reuses_old312_paths_and24_wfa_folds(tmp_path,monkeypatch):
    m,prior=prior_fixture(tmp_path,monkeypatch)
    folders={s:tmp_path/('new-'+s) for s in ('train1','train2','evaluation')}
    for p in folders.values():p.mkdir()
    a=new.train_asset((str(tmp_path),str(folders['train1']),'BTCUSDT',{},'train1'))
    b=new.train_asset((str(tmp_path),str(folders['train2']),'BTCUSDT',{},'train2'))
    assert a['new_simulations']==b['new_simulations']==40 and len(a['training'])==46
    e=new.evaluate_asset((str(tmp_path),str(tmp_path),str(folders['evaluation']),'BTCUSDT',{},a,b))
    assert e['new_simulations']==241 and len(e['comparisons'])==46 and len(e['reused_wfa_folds'])==24
    assert len(e['new_results'])==241 and all(x['status']=='PASS' for x in e['audits'])
    assert e['main_selection']['selected']=='cash' and D(e['main_selected_fixed']['venue_assumption']['metrics']['net_profit_usdt'])<0
    for cost in new.COSTS:assert e['main_selected_fixed'][cost]['metrics']['operating_expense_usdt']!='0'
    assert all(e['comparisons'][c]==prior['evaluation']['comparisons'][c] for c in old.CANDIDATES)
    for key,row in e['walk_forward'].items():
        assert row['metrics']==prior['evaluation']['walk_forward'][key]['metrics']
        assert all(f['reused'] for f in row['folds'])

def test_changed_choice_reuses_identical_prefix_and_carries_exact_cash(tmp_path,monkeypatch):
    m,prior=prior_fixture(tmp_path,monkeypatch);folder=tmp_path/'changed';folder.mkdir()
    c=new.NEW_CANDIDATES[0];monkeypatch.setattr(new,'NEW_CANDIDATES',(c,))
    a=prior['train1'];b=copy.deepcopy(prior['train2']);b['selection']['selected']=c
    e=new.evaluate_asset((str(tmp_path),str(tmp_path),str(folder),'BTCUSDT',{},a,b))
    assert e['new_simulations']==25 #12candidatecases+1managedcash+12changed2025folds
    assert len(e['reused_wfa_folds'])==12
    for r in e['walk_forward'].values():
        first,last=r['folds'];assert [first['year'],last['year']]==[2024,2025]
        assert first['reused'] and last['chosen']==c
        assert first['metrics']['final_cash_usdt']==last['metrics']['initial_usdt']
        assert last['metrics']['initial_usdt']!='10000'

def test_selection_hash_refused_before_any_reference_read(tmp_path):
    (tmp_path/'selection.json').write_text('{}')
    with pytest.raises(ValueError,match='pin mismatch'):new.read_selection(tmp_path,'0'*64,{},'0'*64,'train1')
