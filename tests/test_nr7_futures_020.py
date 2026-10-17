"""Only synthetic fixtures; no new historical outcomes before remote freeze."""
import copy
import json
from pathlib import Path
import sys
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_funding_futures_019 import market
from test_bybit_replay import signals, START, FIRST
from tradingagents import nr7_futures_020 as new
from tradingagents import futures_replay_019 as old
from tradingagents.bybit_history import DAY,HOUR
from run_nr7_futures_020 import save_result,read_result,reusable_fold


def signal_market():
    m=market(224)
    m.frame['High']=110.;m.frame['Low']=90.;m.frame['Close']=100.
    m.frame.loc[198,['High','Low','Close']]=[102.,98.,100.]
    m.frame.loc[199,'Close']=103.
    return m


def test_exact_strict_range_then_next_close_breakout():
    m=signal_market();s=new.nr7_signals(m,m.end)
    assert not s.iloc[198].entry and s.iloc[199].entry
    assert not s.iloc[:7].entry.any() and not (s.entry&s.exit).any()
    assert (s.max_hold==10).all()


@pytest.mark.parametrize('mode',['tie','equal_close','zero_width','intraday_only'])
def test_nonqualifying_setups_are_excluded(mode):
    m=signal_market()
    if mode=='tie':m.frame.loc[195,['High','Low']]=[102.,98.]
    if mode=='equal_close':m.frame.loc[199,'Close']=102.
    if mode=='zero_width':m.frame.loc[198,['High','Low']]=[100.,100.]
    if mode=='intraday_only':m.frame.loc[199,['High','Close']]=[130.,101.]
    assert not new.nr7_signals(m,m.end).iloc[199].entry


def test_six_prior_ranges_only_and_strict_exit():
    m=signal_market();m.frame.loc[191,['High','Low']]=[100.5,99.5]
    m.frame.loc[200,'Close']=90.;m.frame.loc[201,'Close']=89.
    s=new.nr7_signals(m,m.end)
    assert s.iloc[199].entry and not s.iloc[200].exit and s.iloc[201].exit


def test_prefix_and_future_price_mutation_causality():
    m=signal_market();end=START+210*DAY
    a=new.nr7_signals(m,end);b=new.nr7_signals(m,m.end)
    pd.testing.assert_frame_equal(a,b.loc[b.index<end])
    m.frame.loc[210:,['High','Low','Close']]=[1e7,1.,1e6]
    pd.testing.assert_frame_equal(a,new.nr7_signals(m,end))


@pytest.mark.parametrize('candidate',new.NEW_CANDIDATES)
@pytest.mark.parametrize('lag',[0,1,2])
def test_dispatch_uses_new_signals_with_correct_delay_and_sizing(candidate,lag,monkeypatch):
    m=market(204);sig=signals(m,(199,),(201,),max_hold=10,vol=.6)
    monkeypatch.setattr(old,'make_signals',lambda *a:pytest.fail('old family signals must not run'))
    r=new.replay(m,FIRST,m.end,candidate=candidate,prepared_signals=sig,lag=lag)
    assert r['candidate']==candidate and r['fills'][0]['timestamp_ms']==FIRST+lag*DAY+HOUR
    assert r['fills'][0]['fraction']==('0.5' if candidate.endswith('fixed50') else '0.25')
    assert r['independent_wealth_audit']['status']=='PASS'


def test_actual_ten_day_holding_limit_and_frozen_ledger_equivalence():
    m=market(220);sig=signals(m,(199,),(),max_hold=10,vol=.6)
    a=new.replay(m,FIRST,m.end,candidate=new.NEW_CANDIDATES[0],prepared_signals=sig,lag=2)
    b=old.replay(m,FIRST,m.end,candidate=old.CANDIDATES[-2],prepared_signals=sig,lag=2)
    assert a['trades'][0]['reason']=='time_exit'
    assert a['fills'][1]['timestamp_ms']-a['fills'][0]['timestamp_ms']==10*DAY
    for key in ('metrics','events','curve','fills','trades','funding_events'):assert a[key]==b[key]


def test_native_new_signal_path_uses_nr7(monkeypatch):
    m=signal_market()
    monkeypatch.setattr(old,'make_signals',lambda *a:pytest.fail('wrong signal family'))
    r=new.replay(m,FIRST,m.end,candidate=new.NEW_CANDIDATES[0])
    assert r['fills'][0]['timestamp_ms']==FIRST+HOUR


def test_envelope_fsync_roundtrip_and_corruption_detection(tmp_path):
    m=market(202);r=new.replay(m,FIRST,m.end,benchmark='cash')
    rec=save_result(tmp_path,'synthetic',r);path=tmp_path/rec['file']
    assert read_result(path,rec['sha256'],rec['container_sha256'])==r
    with pytest.raises(FileExistsError):save_result(tmp_path,'synthetic',r)
    e=json.loads(path.read_bytes());e['decoded_sha256']='0'*64;path.write_text(json.dumps(e))
    with pytest.raises(ValueError):read_result(path,rec['sha256'])


def test_wfa_reuse_requires_exact_capital_candidate_dates_and_scenario():
    m=market(204);r=new.replay(m,FIRST,m.end,candidate=new.NEW_CANDIDATES[0],prepared_signals=signals(m,(199,),(201,)))
    kw=dict(chosen=new.NEW_CANDIDATES[0],capital='10000',start=FIRST,end=m.end,cost='venue_assumption',lag=0,adverse=False)
    assert reusable_fold(r,**kw)
    for key,value in [('chosen',old.CANDIDATES[0]),('capital','9999.999999999999999999999'),('start',FIRST+DAY),('end',m.end-DAY),('cost','stress_assumption'),('lag',1),('adverse',True)]:
        assert not reusable_fold(r,**(kw|{key:value}))


def test_all_ten_candidates_required_and_training_gates_preserved():
    m=market(202);r=new.replay(m,FIRST,m.end,benchmark='cash')
    matrix={c:{cost:copy.deepcopy(r) for cost in new.COSTS} for c in new.CANDIDATES}
    assert new.select_training(matrix)['selected']=='cash'
    c=new.NEW_CANDIDATES[0]
    for v in matrix[c].values():v['metrics'].update(net_profit_usdt='100',max_drawdown_pct='5',signal_exits=9,annualized_net_return_pct=1.)
    assert new.select_training(matrix)['selected']=='cash'
    for v in matrix[c].values():v['metrics']['signal_exits']=10
    assert new.select_training(matrix)['selected']==c
    matrix.pop(new.NEW_CANDIDATES[1])
    with pytest.raises(ValueError):new.select_training(matrix)
