"""Full bounded matrix on synthetic prices only, plus comparison/selection guards."""
from pathlib import Path
import sys,copy
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent));sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from test_funding_futures_019 import market
from test_bybit_replay import signals,FIRST
from tradingagents.bybit_history import DAY
from tradingagents import bybit_replay as frozen
from dataclasses import replace
import run_sol_funding_022 as runner


def test_all_six_original_candidates_and_gate_thresholds_unchanged():
    assert runner.CANDIDATES==frozen.CANDIDATES and len(runner.CANDIDATES)==6
    m=market(202);r=runner.ledger.replay(m,FIRST,m.end,benchmark='cash')
    t={c:{k:copy.deepcopy(r) for k in runner.COSTS} for c in runner.CANDIDATES}
    c=runner.CANDIDATES[0]
    for v in t[c].values():v['metrics'].update(net_profit_usdt='100',max_drawdown_pct='10',signal_exits=9,annualized_net_return_pct=2.)
    assert runner.selection_summary(t)['selected']=='cash'
    for v in t[c].values():v['metrics']['signal_exits']=10
    assert runner.selection_summary(t)['selected']==c
    t.pop(runner.CANDIDATES[-1])
    with pytest.raises(ValueError):runner.selection_summary(t)


def test_joint_diagnostic_uses_all_assets_and_matched_hold_costs(monkeypatch):
    calls=[]
    def boot(panel,base,**kwargs):
        assert kwargs=={'block':30,'repeats':2000,'seed':20261017}
        assert np.all(base==0);calls.append(panel.copy());return {}
    monkeypatch.setattr(runner,'bootstrap_max_mean',boot)
    results={}
    for i,symbol in enumerate(('BTCUSDT','SOLUSDT','XRPUSDT'),1):
        curves={c+'|'+cost:[.001*i]*365 for c in runner.CANDIDATES for cost in runner.COSTS}
        curves.update({'buy_hold50|'+cost:[.0005*i]*365 for cost in runner.COSTS})
        results[symbol]={'daily_returns_for_diagnostics':curves}
    out=runner.multiplicity(results)
    assert len(out)==16 and len(calls)==16
    assert all(v['compatible_asset_candidate_pairs']==18 for k,v in out.items() if k.startswith('joint|'))
    assert calls[3].shape==(365,18)
    assert np.allclose(calls[7][:,6:12],.001)


def test_one_asset_complete125_scenario_synthetic_pipeline(tmp_path,monkeypatch):
    m=replace(market(206),symbol='SOLUSDT')
    monkeypatch.setattr(runner,'T0',FIRST);monkeypatch.setattr(runner,'T1',FIRST+2*DAY)
    monkeypatch.setattr(runner,'T2',FIRST+4*DAY);monkeypatch.setattr(runner,'T3',FIRST+6*DAY)
    monkeypatch.setattr(runner,'load_market',lambda *a:m)
    def sig(market,candidate,end):
        return signals(market,(199,201,203),(200,202,204),vol=.6).loc[lambda x:x.index<end]
    monkeypatch.setattr(runner.ledger,'make_signals',sig)
    folders=[tmp_path/x for x in ('train1','train2','evaluate')]
    for p in folders:p.mkdir()
    a=runner.train_asset((str(tmp_path),str(folders[0]),'SOLUSDT',{},'train1'))
    b=runner.train_asset((str(tmp_path),str(folders[1]),'SOLUSDT',{},'train2'))
    assert a['new_simulations']==b['new_simulations']==12
    assert a['selection']['selected']==b['selection']['selected']=='cash'
    e=runner.evaluate_asset((str(tmp_path),str(folders[2]),'SOLUSDT',{},a,b))
    assert e['new_simulations']==101 and len(e['new_results'])==101
    assert len(e['benchmarks'])==5 and len(e['walk_forward'])==12
    assert all(len(v)==12 for v in e['comparisons'].values())
    assert all(x['status']=='PASS' and x['max_error_usdt']=='0' for x in e['audits'])
    assert e['benchmarks']['cash']['metrics']['operating_expense_usdt']=='0'
    for scenario in e['walk_forward'].values():
        f1,f2=scenario['folds'];assert f1['metrics']['final_cash_usdt']==f2['metrics']['initial_usdt']
        assert float(scenario['metrics']['operating_expense_usdt'])>0
        assert 'FEWER_THAN_20_SIGNAL_EXITS' in scenario['failed_gates']


def test_selection_external_hash_refuses_before_file_decode(tmp_path):
    (tmp_path/'selection.json').write_text('{}')
    with pytest.raises(ValueError,match='pin mismatch'):runner.read_selection(tmp_path,'0'*64,{},'0'*64,'train1')
