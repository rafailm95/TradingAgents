"""Ten frozen causal daily signal hypotheses, two unchanged sizing contracts.

Indicators are features, never executable prices. No fitting/network/orders.
The frozen019 Decimal accounting engine is reused without global mutation.
"""
import math
import numpy as np
import pandas as pd
from tradingagents import futures_replay_019 as ledger
from tradingagents import bybit_replay as original
from tradingagents.bybit_history import DAY
FAMILIES=('vortex14_cross','tsi25_13_cross','ao_saucer','fisher10_turn','heikin2_trend',
          'vwma20_reclaim','ultimate_rebound','chop14_release','force2_pullback','eom14_confirm')
SIZINGS=('fixed50','vol15_cap50')
NEW_CANDIDATES=tuple(f+'__'+s for f in FAMILIES for s in SIZINGS)
OLD_CANDIDATES=original.CANDIDATES
CANDIDATES=OLD_CANDIDATES+NEW_CANDIDATES
COSTS=original.COSTS
audit_wealth=ledger.audit_wealth
evaluation_gate=original.evaluation_gate

def cross(a,b):return (a>b)&(a.shift(1)<=b.shift(1) if isinstance(b,pd.Series) else a.shift(1)<=b)
def ratio(a,b,neutral=0.):return (a/b.replace(0,np.nan)).where(b!=0,neutral)

def features(frame):
    c,h,l,o,v=(frame[k] for k in ('Close','High','Low','Open','Volume'));mid=(h+l)/2
    sma200=c.rolling(200).mean();sma50=c.rolling(50).mean();sma20=c.rolling(20).mean()
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    vp=ratio((h-l.shift()).abs().rolling(14).sum(),tr.rolling(14).sum())
    vm=ratio((l-h.shift()).abs().rolling(14).sum(),tr.rolling(14).sum())
    change=c.diff();sm=change.ewm(span=25,adjust=False).mean().ewm(span=13,adjust=False).mean()
    ab=change.abs().ewm(span=25,adjust=False).mean().ewm(span=13,adjust=False).mean()
    tsi=100*ratio(sm,ab);tsi_signal=tsi.ewm(span=7,adjust=False).mean()
    ao=mid.rolling(5).mean()-mid.rolling(34).mean()
    low10=mid.rolling(10).min();high10=mid.rolling(10).max()
    norm=2*ratio(mid-low10,high10-low10,.5)-1
    fisher=np.full(len(c),np.nan);previous_x=previous_f=0.
    for i,value in enumerate(norm.to_numpy()):
        if not math.isfinite(value):continue
        x=float(np.clip(.33*value+.67*previous_x,-.999,.999))
        f=.5*math.log((1+x)/(1-x))+.5*previous_f
        fisher[i]=f;previous_x,previous_f=x,f
    ha_close=(o+h+l+c)/4;ha_open=np.full(len(c),np.nan)
    if len(c):ha_open[0]=(o.iloc[0]+c.iloc[0])/2
    for i in range(1,len(c)):ha_open[i]=(ha_open[i-1]+ha_close.iloc[i-1])/2
    vwma=(c*v).rolling(20).sum()/v.rolling(20).sum().replace(0,np.nan)
    bp=c-pd.concat([l,c.shift()],axis=1).min(axis=1)
    uo=100*(4*ratio(bp.rolling(7).sum(),tr.rolling(7).sum(),.5)+2*ratio(bp.rolling(14).sum(),tr.rolling(14).sum(),.5)+ratio(bp.rolling(28).sum(),tr.rolling(28).sum(),.5))/7
    spread=h.rolling(14).max()-l.rolling(14).min()
    chop=100*np.log10(ratio(tr.rolling(14).sum(),spread,14))/math.log10(14)
    force=(change*v).ewm(span=2,adjust=False).mean();ema13=c.ewm(span=13,adjust=False).mean()
    # Positive scale factor of1e8 is omitted; zero-crossing is invariant.
    raw_eom=(mid.diff()*(h-l)/v.replace(0,np.nan)).where(v>0,np.nan)
    eom=raw_eom.rolling(14).mean()
    return pd.DataFrame({'sma200':sma200,'sma50':sma50,'sma20':sma20,'vp':vp,'vm':vm,
      'tsi':tsi,'tsi_signal':tsi_signal,'ao':ao,'fisher':fisher,'ha_close':ha_close,'ha_open':ha_open,
      'vwma':vwma,'uo':uo,'chop':chop,'prior_high20':h.rolling(20).max().shift(),
      'force':force,'ema13':ema13,'eom':eom,
      'vol60':c.pct_change(fill_method=None).rolling(60).std(ddof=1)*math.sqrt(365.25)})

def daily_signals(frame,family,prepared=None):
    if family not in FAMILIES:raise ValueError('Unregistered024family')
    z=features(frame) if prepared is None else prepared
    if not z.index.equals(frame.index):raise ValueError('Feature alignment')
    c=frame.Close;up=c>z.sma200;down=c<z.sma200;hold=20
    if family=='vortex14_cross':
        entry=cross(z.vp,z.vm)&up;leave=(z.vp<z.vm)|down
    elif family=='tsi25_13_cross':
        entry=cross(z.tsi,z.tsi_signal)&(z.tsi>0)&up;leave=(z.tsi<z.tsi_signal)|down
    elif family=='ao_saucer':
        entry=(z.ao>0)&(z.ao>z.ao.shift())&(z.ao.shift()<z.ao.shift(2))&(z.ao.shift(2)<z.ao.shift(3))&up
        leave=((z.ao<z.ao.shift())&(z.ao.shift()<z.ao.shift(2)))|down;hold=10
    elif family=='fisher10_turn':
        entry=(z.fisher>z.fisher.shift())&(z.fisher.shift()<=z.fisher.shift(2))&(z.fisher.shift()<-1)&up
        leave=(z.fisher<z.fisher.shift())|down;hold=10
    elif family=='heikin2_trend':
        green=z.ha_close>z.ha_open
        entry=green&green.shift(fill_value=False)&~green.shift(2,fill_value=False)&up
        leave=(z.ha_close<z.ha_open)|down
    elif family=='vwma20_reclaim':
        entry=cross(c,z.vwma)&(z.vwma>z.sma20)&up;leave=(c<z.vwma)|down
    elif family=='ultimate_rebound':
        entry=cross(z.uo,30)&up;leave=(z.uo>50)|down;hold=10
    elif family=='chop14_release':
        entry=(z.chop.shift().rolling(10).max()>=61.8)&(z.chop<38.2)&(c>z.prior_high20)&up
        leave=(c<z.sma20)|(z.chop>61.8)|down
    elif family=='force2_pullback':
        entry=(z.force<0)&(z.ema13>z.ema13.shift())&up;leave=(z.force>0)|down;hold=10
    else:
        entry=cross(z.eom,0)&(c>z.sma50)&up;leave=(z.eom<0)|(c<z.sma50)|down
    leave=leave.fillna(False)
    return pd.DataFrame({'entry':entry.fillna(False)&~leave,'exit':leave,'vol60':z.vol60,'max_hold':hold})

def make_signals(market,candidate,end):
    if candidate not in CANDIDATES:raise ValueError('Unregistered024candidate')
    if candidate in OLD_CANDIDATES:return ledger.make_signals(market,candidate,end)
    if end%DAY or not market.start<end<=market.end:raise ValueError('Closed day boundary required')
    frame=market.frame.iloc[:(end-market.start)//DAY].copy().reset_index(drop=True)
    index=list(range(market.start,end,DAY))
    if list(frame.Date.astype('int64')//1000000)!=index:raise ValueError('Daily grid mismatch')
    sig=daily_signals(frame,candidate.split('__')[0]);sig.index=pd.Index(index);return sig

def replay(market,start,end,*,candidate=None,prepared_signals=None,**kwargs):
    if candidate not in NEW_CANDIDATES:
        if candidate is not None and candidate not in OLD_CANDIDATES:raise ValueError('Unregistered024candidate')
        return ledger.replay(market,start,end,candidate=candidate,prepared_signals=prepared_signals,**kwargs)
    sig=make_signals(market,candidate,end) if prepared_signals is None else prepared_signals
    dispatch='funding_carry7_momentum28__'+candidate.split('__')[1]
    result=ledger.replay(market,start,end,candidate=dispatch,prepared_signals=sig,**kwargs)
    result['candidate']=candidate;result['ledger_sizing_dispatch_id']=dispatch
    result['signal_family_source']='tradingagents/multifamily_futures_024.py'
    result['classification']='Exploratory Binance USD-M historical research; no Bybit/live execution or prospective validation.'
    result['independent_wealth_audit']=audit_wealth(result);return result

def select_training(training):
    if set(training)!=set(CANDIDATES) or any(set(v)!=set(COSTS) for v in training.values()):raise ValueError('Incomplete26candidate training matrix')
    ranked=[]
    for c in CANDIDATES:
        pair=training[c];stress=pair['stress_assumption']['metrics']
        if all(ledger.passes(r,10) for r in pair.values()) and stress['annualized_net_return_pct'] is not None:
            ranked.append({'id':c,'score':stress['annualized_net_return_pct']/max(float(stress['max_drawdown_pct']),1.)})
    ranked.sort(key=lambda x:(-x['score'],x['id']))
    return {'selected':ranked[0]['id'] if ranked else 'cash','eligible':ranked,'basis':'All26 compatible candidates; train-only bothcosts/lag0/nominal funding,>=10exits,DD<=35%,positive net. Frozen before evaluation.'}
