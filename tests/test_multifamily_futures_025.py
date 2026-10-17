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
from tradingagents import multifamily_futures_025 as b
from tradingagents import strategy_lab,strategy_families
from tradingagents.bybit_history import DAY,HOUR
import run_multifamily_futures_025 as runner

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
    assert len(b.FAMILIES)==10 and len(b.NEW_CANDIDATES)==20 and len(b.CANDIDATES)==46
    assert not set(b.FAMILIES)&set(b.prior.FAMILIES)
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
    changed=replace(changed,trade=changed.trade[:240*24]+tuple((D('1e9'),)*4 for _ in changed.trade[240*24:]),mark=changed.mark[:240*24]+tuple((D('2e9'),)*4 for _ in changed.mark[240*24:]))
    for t in changed.funding:
        if t>=cut:changed.funding[t]=D(100)
    pd.testing.assert_frame_equal(prefix,b.make_signals(changed,c,cut))
    assert not (full.entry&full.exit).any() and full.max_hold.isin([10,20]).all()

@pytest.mark.parametrize('family',b.FAMILIES)
def test_flat_zero_volume_is_finite_neutral_and_no_entry(family):
    f=frame();f[['Open','High','Low','Close']]=100.;f.Volume=0.
    hf=pd.DataFrame({'basis':0.,'rv':0.,'down_rv':0.},index=f.index)
    z=b.features(f,hf);assert not np.isinf(z.to_numpy()).any()
    s=b.daily_signals(f,family,z);assert not s.entry.any()

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

def test_selector_requires_all46_and_old_candidate_remains_eligible():
    m=market(202);r=b.replay(m,FIRST,m.end,benchmark='cash')
    training={c:{k:copy.deepcopy(r) for k in b.COSTS} for c in b.CANDIDATES}
    c=b.OLD_CANDIDATES[0]
    for k in b.COSTS:training[c][k]['metrics'].update(net_profit_usdt='100',max_drawdown_pct='10',signal_exits=10,annualized_net_return_pct=2.)
    assert b.select_training(training)['selected']==c
    training[c]['stress_assumption']['metrics']['signal_exits']=9
    assert b.select_training(training)['selected']=='cash'
    training.pop(b.CANDIDATES[-1])
    with pytest.raises(ValueError):b.select_training(training)

def test_bootstrap_includes_138_matched_old_new_pairs(monkeypatch):
    calls=[]
    def boot(panel,base,**kwargs):calls.append(panel.shape);assert kwargs==dict(block=30,repeats=2000,seed=20261017);return {}
    monkeypatch.setattr(runner,'bootstrap_max_mean',boot)
    curves={c+'|'+cost:[.001]*731 for c in b.CANDIDATES for cost in b.COSTS}
    curves.update({'buy_hold50|'+cost:[.0005]*731 for cost in b.COSTS})
    result=runner.multiplicity({s:{'daily_returns_for_diagnostics':curves} for s in ('BTCUSDT','SOLUSDT','XRPUSDT')})
    assert len(result)==16 and calls.count((731,138))==4 and calls.count((731,46))==12

def test_invalid_candidate_and_unclosed_day_refused():
    m=market(204)
    with pytest.raises(ValueError):b.make_signals(m,b.NEW_CANDIDATES[0],m.end-1)
    with pytest.raises(ValueError):b.replay(m,FIRST,m.end,candidate='unknown__fixed50')


def test_independent_daily_indicator_oracles():
    f=frame();f['Open']=f.Close-.5*np.cos(np.arange(len(f))*.4)
    f['High']=f.Close+1+np.arange(len(f))%11/3
    f['Low']=f.Close-1-np.arange(len(f))%7/4
    z=b.features(f);c=f.Close.to_list();h=f.High.to_list();l=f.Low.to_list();v=f.Volume.to_list();o=f.Open.to_list();n=len(c)
    dm=[h[i]-l[i] for i in range(n)]
    e=ema(dm,9);ee=ema(e,9);triple=ema(ema(ema(c,18),18),18)
    trix=[math.nan]+[100*(triple[i]/triple[i-1]-1) for i in range(1,n)]
    dirs=[-1]+[1 if h[i]+l[i]+c[i]>h[i-1]+l[i-1]+c[i-1] else -1 for i in range(1,n)]
    cm=dm[0];vf=[0.];nvi=[1000.]
    for i in range(1,n):
        cm=cm+dm[i] if dirs[i]==dirs[i-1] else dm[i-1]+dm[i]
        vf.append(v[i]*2*(dm[i]/cm-1)*dirs[i]*100)
        nvi.append(nvi[-1]+(100*(c[i]/c[i-1]-1) if v[i]<v[i-1] else 0))
    ko=[x-y for x,y in zip(ema(vf,34),ema(vf,55))]
    def weighted(values,i):return sum(w*values[i-j] for j,w in enumerate((1,2,2,1)))/6
    body=[c[i]-o[i] for i in range(n)]
    rvi=[math.nan]*n
    for i in range(12,n):rvi[i]=sum(weighted(body,j) for j in range(i-9,i+1))/sum(weighted(dm,j) for j in range(i-9,i+1))
    for i in range(200,n):
        up=sum(max(h[j]-h[j-1],0) for j in range(i-13,i+1));dn=sum(max(l[j-1]-l[j],0) for j in range(i-13,i+1))
        ulcer=math.sqrt(sum((100*(c[j]/max(c[j-13:j+1])-1))**2 for j in range(i-13,i+1))/14)
        expected={'rvi':rvi[i],'rvi_signal':weighted(rvi,i),'demarker':up/(up+dn),'mass':sum(e[j]/ee[j] for j in range(i-24,i+1)),
          'ulcer':ulcer,'trix':trix[i],'trix_signal':ema(trix,9)[i],'klinger':ko[i],'klinger_signal':ema(ko,13)[i],'nvi':nvi[i],'nvi_signal':ema(nvi,255)[i]}
        for key,value in expected.items():assert z[key].iloc[i]==pytest.approx(value,rel=1e-10,abs=1e-9),key


def test_hourly_features_independent_sum_and_prior_window_oracle():
    m=market(70);bars=[];marks=[]
    for i in range(70*24):
        c=D(str(100+math.sin(i*.9)+i*.01));o=c-D('.1')
        bars.append((o,c+D(1),c-D(1),c));marks.append((c,c,c,c+D(str(.01*(1+i%13)))))
    m=replace(m,trade=tuple(bars),mark=tuple(marks))
    hf=b.hourly_features(m,70);f=frame(70);z=b.features(f,hf)
    returns=[]
    for i,bar in enumerate(bars):returns.append(math.log(float(bar[3])/float(bars[i-1][3] if i else bars[0][0])))
    for d in range(70):
        rr=returns[d*24:(d+1)*24]
        assert hf.rv.iloc[d]==pytest.approx(sum(x*x for x in rr))
        assert hf.down_rv.iloc[d]==pytest.approx(sum(x*x for x in rr if x<0))
        assert hf.basis.iloc[d]==pytest.approx(10000*(float(bars[24*d+23][3])/float(marks[24*d+23][3])-1))
    values=hf.basis.iloc[9:69].tolist();mu=sum(values)/60;sd=math.sqrt(sum((x-mu)**2 for x in values)/59)
    assert z.basis_z.iloc[69]==pytest.approx((hf.basis.iloc[69]-mu)/sd)
    assert z.down_share.iloc[69]==pytest.approx(sum(x*x for x in returns[-14*24:] if x<0)/sum(x*x for x in returns[-14*24:]))
    with pytest.raises(ValueError):b.hourly_features(m,71)


def test_calendar_utc_exact_friday_entry_and_sunday_exit():
    f=frame();f.Close=np.arange(len(f))+100.;z=b.features(f)
    s=b.daily_signals(f,'utc_weekend_trend',z)
    for i in range(200,len(f)):
        assert bool(s.entry.iloc[i])==(f.Date.iloc[i].weekday()==4)
        assert bool(s.exit.iloc[i])==(f.Date.iloc[i].weekday()==6)


def test_hourly_signals_refuse_missing_features_and_zero_denominator_is_neutral():
    f=frame()
    for family in ('mark_discount60','semivariance14_recovery'):
        with pytest.raises(ValueError):b.daily_signals(f,family)
    hf=pd.DataFrame({'basis':1.,'rv':0.,'down_rv':0.},index=f.index);z=b.features(f,hf)
    assert z.basis_z.isna().all() and (z.down_share.iloc[13:]==.5).all()
    for family in ('mark_discount60','semivariance14_recovery'):assert not b.daily_signals(f,family,z).entry.any()


@pytest.mark.parametrize('candidate',b.OLD_CANDIDATES)
def test_all26_old_dispatch_unchanged(candidate):
    m=market(203);sig=signals(m,(199,),(201,),vol=.6)
    assert b.replay(m,FIRST,m.end,candidate=candidate,prepared_signals=sig)==b.prior.replay(m,FIRST,m.end,candidate=candidate,prepared_signals=sig)
