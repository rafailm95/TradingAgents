"""Synthetic causality, mathematical oracles and unchanged financial accounting."""
import copy,math,sys
from pathlib import Path
from decimal import Decimal as D
from dataclasses import replace
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent));sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from test_funding_futures_019 import market
from test_bybit_replay import signals,FIRST,START
from tradingagents import multifamily_futures_024 as b
from tradingagents import strategy_lab,strategy_families
from tradingagents.bybit_history import DAY,HOUR
import run_multifamily_futures_024 as runner

def frame(n=280):
    i=np.arange(n,dtype=float);c=100+i*.08+4*np.sin(i*.7)+np.cos(i*.19)
    return pd.DataFrame({'Date':pd.to_datetime(START+i*DAY,unit='ms',utc=True),'Open':c-.3,'High':c+1.2,'Low':c-1.4,'Close':c,'Volume':100+(i%17)*9,'Turnover':c*(100+(i%17)*9)})

def ema(values,n):
    out=[];x=None
    for v in values:
        if not math.isfinite(v):out.append(math.nan);continue
        x=v if x is None else x+(v-x)*2/(n+1);out.append(x)
    return out

def test_ten_distinct_families_and_twenty_sizings_without_old_mutation():
    old=b.ledger.CANDIDATES
    assert len(b.FAMILIES)==10 and len(b.NEW_CANDIDATES)==20 and len(b.CANDIDATES)==26
    assert not set(b.FAMILIES)&(set(strategy_lab.FAMILIES)|set(strategy_families.FAMILIES)|{'weekly_confirm','relative_leader28','peer_reversion60','funding_carry7_momentum28','nr7_close10'})
    assert all(c.split('__')[1] in strategy_lab.SIZINGS for c in b.NEW_CANDIDATES)
    assert b.ledger.CANDIDATES==old

@pytest.mark.parametrize('family',b.FAMILIES)
def test_prefix_and_future_mutation_causality(family):
    f=frame();m=replace(market(280),frame=f)
    c=family+'__fixed50';cut=START+240*DAY
    full=b.make_signals(m,c,m.end);prefix=b.make_signals(m,c,cut)
    pd.testing.assert_frame_equal(prefix,full.iloc[:240])
    changed=copy.deepcopy(m);changed.frame.loc[240:,['Open','High','Low','Close','Volume']]=1e9
    for t in changed.funding:
        if t>=cut:changed.funding[t]=D(100)
    pd.testing.assert_frame_equal(prefix,b.make_signals(changed,c,cut))
    assert not (full.entry&full.exit).any() and full.max_hold.isin([10,20]).all()

@pytest.mark.parametrize('family',b.FAMILIES)
def test_flat_zero_volume_is_finite_neutral_and_no_entry(family):
    f=frame();f[['Open','High','Low','Close']]=100.;f.Volume=0.
    z=b.features(f);assert not np.isinf(z.to_numpy()).any()
    s=b.daily_signals(f,family);assert not s.entry.any()

def test_independent_indicator_numeric_oracles():
    f=frame();z=b.features(f);c=f.Close.to_list();h=f.High.to_list();l=f.Low.to_list();v=f.Volume.to_list();mid=[(a+d)/2 for a,d in zip(h,l)]
    tr=[h[0]-l[0]]+[max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1])) for i in range(1,len(c))]
    bp=[c[0]-l[0]]+[c[i]-min(l[i],c[i-1]) for i in range(1,len(c))]
    delta=[math.nan]+[c[i]-c[i-1] for i in range(1,len(c))]
    sm=ema(ema(delta,25),13);ab=ema(ema([abs(x) for x in delta],25),13)
    tsi=[100*a/d if d else 0 for a,d in zip(sm,ab)];tsis=ema(tsi,7)
    force=ema([a*d for a,d in zip(delta,v)],2)
    haopen=(f.Open.iloc[0]+c[0])/2;last_close=None;fisher=None;xprev=fprev=0.
    for i in range(len(c)):
        if i:haopen=(haopen+last_close)/2
        last_close=(f.Open.iloc[i]+h[i]+l[i]+c[i])/4
        assert z.ha_open.iloc[i]==pytest.approx(haopen)
        if i>=9:
            lo=min(mid[i-9:i+1]);hi=max(mid[i-9:i+1]);x=.33*(2*(mid[i]-lo)/(hi-lo)-1)+.67*xprev
            x=max(-.999,min(.999,x));fisher=.5*math.log((1+x)/(1-x))+.5*fprev;xprev,fprev=x,fisher
            assert z.fisher.iloc[i]==pytest.approx(fisher)
        if i<200:continue
        vp=sum(abs(h[j]-l[j-1]) for j in range(i-13,i+1))/sum(tr[i-13:i+1])
        vm=sum(abs(l[j]-h[j-1]) for j in range(i-13,i+1))/sum(tr[i-13:i+1])
        uo=100*sum(w*sum(bp[i-n+1:i+1])/sum(tr[i-n+1:i+1]) for n,w in [(7,4),(14,2),(28,1)])/7
        eom=sum((mid[j]-mid[j-1])*(h[j]-l[j])/v[j] for j in range(i-13,i+1))/14
        chop=100*math.log10(sum(tr[i-13:i+1])/(max(h[i-13:i+1])-min(l[i-13:i+1])))/math.log10(14)
        expected={'vp':vp,'vm':vm,'tsi':tsi[i],'tsi_signal':tsis[i],'ao':sum(mid[i-4:i+1])/5-sum(mid[i-33:i+1])/34,'vwma':sum(c[j]*v[j] for j in range(i-19,i+1))/sum(v[i-19:i+1]),'uo':uo,'chop':chop,'force':force[i],'eom':eom}
        for key,value in expected.items():assert z[key].iloc[i]==pytest.approx(value,rel=1e-10,abs=1e-10),key

@pytest.mark.parametrize('candidate',b.NEW_CANDIDATES)
@pytest.mark.parametrize('lag',[0,1,2])
def test_twenty_candidates_keep_cashflow_sizing_delay_and_real_price_execution(candidate,lag):
    m=market(206);sig=signals(m,(199,),(202,),vol=.7)
    result=b.replay(m,FIRST,m.end,candidate=candidate,prepared_signals=sig,lag=lag,adverse_funding=True)
    carrier='funding_carry7_momentum28__'+candidate.split('__')[1]
    oracle=b.ledger.replay(m,FIRST,m.end,candidate=carrier,prepared_signals=sig,lag=lag,adverse_funding=True)
    for key in ('metrics','events','fills','trades','curve','funding_events','independent_wealth_audit'):assert result[key]==oracle[key]
    assert result['fills'][0]['timestamp_ms']==FIRST+lag*DAY+HOUR
    assert result['candidate']==candidate and result['independent_wealth_audit']['max_error_usdt']=='0'

def test_selector_requires_all26_and_old_candidate_remains_eligible():
    m=market(202);r=b.replay(m,FIRST,m.end,benchmark='cash')
    training={c:{k:copy.deepcopy(r) for k in b.COSTS} for c in b.CANDIDATES}
    c=b.OLD_CANDIDATES[0]
    for k in b.COSTS:training[c][k]['metrics'].update(net_profit_usdt='100',max_drawdown_pct='10',signal_exits=10,annualized_net_return_pct=2.)
    assert b.select_training(training)['selected']==c
    training[c]['stress_assumption']['metrics']['signal_exits']=9
    assert b.select_training(training)['selected']=='cash'
    training.pop(b.CANDIDATES[-1])
    with pytest.raises(ValueError):b.select_training(training)

def test_bootstrap_includes_78_matched_old_new_pairs(monkeypatch):
    calls=[]
    def boot(panel,base,**kwargs):calls.append(panel.shape);assert kwargs==dict(block=30,repeats=2000,seed=20261017);return {}
    monkeypatch.setattr(runner,'bootstrap_max_mean',boot)
    curves={c+'|'+cost:[.001]*731 for c in b.CANDIDATES for cost in b.COSTS}
    curves.update({'buy_hold50|'+cost:[.0005]*731 for cost in b.COSTS})
    result=runner.multiplicity({s:{'daily_returns_for_diagnostics':curves} for s in ('BTCUSDT','SOLUSDT','XRPUSDT')})
    assert len(result)==16 and calls.count((731,78))==4 and calls.count((731,26))==12

def test_invalid_candidate_and_unclosed_day_refused():
    m=market(204)
    with pytest.raises(ValueError):b.make_signals(m,b.NEW_CANDIDATES[0],m.end-1)
    with pytest.raises(ValueError):b.replay(m,FIRST,m.end,candidate='unknown__fixed50')
