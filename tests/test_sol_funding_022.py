"""Synthetic boundary, event-cashflow and causality tests, no market PnL."""
import copy
from decimal import Decimal as D,localcontext
from pathlib import Path
import sys
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_binance_archive import native
from tradingagents import sol_funding_022 as b,binance_assets_021 as strict,futures_replay_019 as ledger

def rows(start,end):
    return [[str(t+7),str(h),'.0001'] for t,h in b.expected_schedule(start,end)]

def synthetic(start,end):
    raw=[[str(t),'100','101','99','100','2','200'] for t in range(start,end,b.HOUR)]
    return {'trade':raw,'mark':copy.deepcopy(raw),'funding':b.parse_funding(rows(start,end),start=start,end=end)}

def test_independent_exact_transition_schedule_and_labels():
    a=b.utc_ms('2022-11-09T00:00:00Z');z=b.utc_ms('2022-11-19T00:00:00Z')
    # Explicit independent boundary oracle, not derived from parser output.
    want=[(a+8*i*b.HOUR,8) for i in range(3)]
    want += [(a+20*b.HOUR,4),(a+24*b.HOUR,4)]
    want += [(a+(28+2*i)*b.HOUR,2) for i in range(99)]
    want += [(a+232*b.HOUR,8)]
    assert b.expected_schedule(a,z)==want
    assert want[5][0]-want[4][0]==4*b.HOUR and want[5][1]==2
    assert want[-1][0]-want[-2][0]==8*b.HOUR
    full=b.expected_schedule(b.START,b.END)
    assert len(full)==4458
    assert {h:sum(x[1]==h for x in full) for h in (2,4,8)}=={2:99,4:2,8:4357}

def test_every_missing_november_event_rejected():
    a=b.utc_ms('2022-11-01T00:00:00Z');z=b.utc_ms('2022-12-01T00:00:00Z');rr=rows(a,z)
    for i in range(len(rr)):
        with pytest.raises(ValueError,match='schedule'):b.parse_funding(rr[:i]+rr[i+1:],start=a,end=z)

@pytest.mark.parametrize('problem',['duplicate','order','late','early','label','nan','extra','wrongunit'])
def test_funding_mutations_rejected(problem):
    a=b.utc_ms('2022-11-10T00:00:00Z');z=a+b.DAY;rr=rows(a,z)
    if problem=='duplicate':rr.insert(1,rr[0])
    elif problem=='order':rr.reverse()
    elif problem=='late':rr[0][0]=str(a+60000)
    elif problem=='early':rr[0][0]=str(a-1)
    elif problem=='label':rr[1][1]='4'
    elif problem=='nan':rr[1][2]='NaN'
    elif problem=='extra':rr.insert(1,[str(a+2*b.HOUR),'2','.0001'])
    else:rr[0][0]=str(a*1000)
    with pytest.raises(ValueError):b.parse_funding(rr,start=a,end=z)

def test_normalized_input_also_checks_schedule_and_jitter():
    a=b.utc_ms('2022-11-10T00:00:00Z');d=synthetic(a,a+b.DAY)
    for key,value in [('interval_hours',8),('source_timestamp_ms',a+60000)]:
        bad=copy.deepcopy(d);bad['funding'][0][key]=value
        with pytest.raises(ValueError):b.prepare(bad,'SOLUSDT')
    d['funding'].pop()
    with pytest.raises(ValueError):b.prepare(d,'SOLUSDT')

def test_strict021_contract_still_rejects_changed_cadence():
    a=b.utc_ms('2022-11-10T00:00:00Z');z=a+b.DAY
    with pytest.raises(ValueError,match='cadence'):strict.parse_funding(rows(a,z),start=a,end=z)

def test_unchanged8hour_synthetic_accounting_parity():
    d=native();new=b.prepare(d,'SOLUSDT');old=strict.prepare(d,'BTCUSDT')
    for a,z in zip(new.trade,old.trade):assert a==z
    assert new.funding==old.funding and new.rules==old.rules

@pytest.mark.parametrize('first',['2022-11-09','2022-11-10','2022-11-18'])
@pytest.mark.parametrize('adverse',[False,True])
def test_actual_held_timestamp_funding_independent_oracle(first,adverse):
    a=b.utc_ms(first+'T00:00:00Z');start=a-201*b.DAY;end=a+2*b.DAY
    d=synthetic(start,end);m=b.prepare(d,'SOLUSDT')
    sig=pd.DataFrame({'entry':False,'exit':False,'vol60':.5,'max_hold':0},index=pd.Index(range(start,end,b.DAY)))
    sig.loc[a-b.DAY,'entry']=True;sig.loc[a,'exit']=True
    result=ledger.replay(m,a,end,candidate='regression_trend__fixed50',prepared_signals=sig,adverse_funding=adverse)
    assert result['status']=='COMPLETE' and result['independent_wealth_audit']['max_error_usdt']=='0'
    opened,closed=result['fills'];assert opened['timestamp_ms']==a+b.HOUR and closed['timestamp_ms']==a+b.DAY+b.HOUR
    with localcontext() as ctx:
        ctx.prec=128;q=D(opened['quantity']);mark=D(100)*(D('1.0005') if adverse else D(1))
        expected=0
        for f in result['funding_events']:
            held=opened['timestamp_ms']<f['timestamp_ms']<closed['timestamp_ms']
            cash=-q*mark*D('.0001') if held else D(0)
            assert D(f['cashflow_usdt'])==cash
            assert D(f['quantity_before'])==(q if held else D(0));expected+=cash
        assert D(result['metrics']['funding_usdt'])==expected

@pytest.mark.parametrize('candidate',b.CANDIDATES)
def test_signal_prefix_ignores_future_prices_and_funding(candidate):
    a=b.utc_ms('2022-11-01T00:00:00Z');m=b.prepare(synthetic(a-210*b.DAY,a+25*b.DAY),'SOLUSDT')
    baseline=ledger.make_signals(m,candidate,a)
    changed=copy.deepcopy(m);changed.frame.loc[210:,'Close']=1e6
    for t in changed.funding:
        if t>=a:changed.funding[t]=D('100')
    pd.testing.assert_frame_equal(baseline,ledger.make_signals(changed,candidate,a))
