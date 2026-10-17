"""Ten preregistered causal hypotheses; unchanged Decimal futures accounting.

Hourly mark data are features/valuation only, never executable fill prices.
"""
import math
import numpy as np
import pandas as pd
from tradingagents import multifamily_futures_024 as prior
from tradingagents.bybit_history import DAY

ledger=prior.ledger
original=prior.original
COSTS=prior.COSTS
audit_wealth=prior.audit_wealth
evaluation_gate=prior.evaluation_gate
cross=prior.cross
ratio=prior.ratio
SIZINGS=prior.SIZINGS
FAMILIES=('rvi10_cross','demarker14_rebound','mass925_reversal','ulcer14_recovery',
          'trix18_rebound','klinger3455_cross','nvi255_confirm','utc_weekend_trend',
          'mark_discount60','semivariance14_recovery')
NEW_CANDIDATES=tuple(f+'__'+s for f in FAMILIES for s in SIZINGS)
OLD_CANDIDATES=prior.CANDIDATES
CANDIDATES=OLD_CANDIDATES+NEW_CANDIDATES

def sym4(s):return (s+2*s.shift()+2*s.shift(2)+s.shift(3))/6

def hourly_features(market,days):
    """Only closed hours within the requested prefix. No daily OHLC-path inference."""
    n=days*24
    if n>len(market.trade) or n>len(market.mark):raise ValueError('Incomplete hourly prefix')
    t=np.array([float(b[3]) for b in market.trade[:n]])
    m=np.array([float(b[3]) for b in market.mark[:n]])
    if not n:return pd.DataFrame(columns=['basis','rv','down_rv'])
    if not np.isfinite(t).all() or not np.isfinite(m).all() or min(t.min(),m.min())<=0:raise ValueError('Invalid hourly closes')
    previous=np.r_[float(market.trade[0][0]),t[:-1]]
    returns=np.log(t/previous)
    return pd.DataFrame({'basis':10000*(t.reshape(days,24)[:,-1]/m.reshape(days,24)[:,-1]-1),
      'rv':(returns**2).reshape(days,24).sum(axis=1),
      'down_rv':np.where(returns<0,returns**2,0).reshape(days,24).sum(axis=1)})

def features(frame,hourly=None):
    c,h,l,o,v=(frame[k] for k in ('Close','High','Low','Open','Volume'))
    span=h-l
    rvi=ratio(sym4(c-o).rolling(10).mean(),sym4(span).rolling(10).mean())
    demax=h.diff().clip(lower=0).rolling(14).mean()
    demin=(-l.diff()).clip(lower=0).rolling(14).mean()
    demarker=ratio(demax,demax+demin,.5)
    emar=span.ewm(span=9,adjust=False).mean()
    mass=ratio(emar,emar.ewm(span=9,adjust=False).mean(),1.).rolling(25).sum()
    dd=100*(c/c.rolling(14).max()-1)
    ulcer=np.sqrt((dd**2).rolling(14).mean())
    triple=c.ewm(span=18,adjust=False).mean().ewm(span=18,adjust=False).mean().ewm(span=18,adjust=False).mean()
    trix=100*triple.pct_change(fill_method=None)
    typical=h+l+c;direction=np.where(typical>typical.shift(),1.,-1.)
    cm=np.zeros(len(c));vf=np.zeros(len(c));dm=span.to_numpy()
    for i in range(len(c)):
        cm[i]=dm[i] if i==0 else (cm[i-1]+dm[i] if direction[i]==direction[i-1] else dm[i-1]+dm[i])
        # Exact signed formulation printed in the cited TradingView documentation.
        vf[i]=float(v.iloc[i])*2*(dm[i]/cm[i]-1)*direction[i]*100 if cm[i] else 0.
    vf=pd.Series(vf,index=frame.index)
    ko=vf.ewm(span=34,adjust=False).mean()-vf.ewm(span=55,adjust=False).mean()
    # Explicit additive-percent NVI convention in the cited software documentation.
    nvi=1000+(100*c.pct_change(fill_method=None)).where(v<v.shift(),0.).fillna(0.).cumsum()
    z=pd.DataFrame({'sma200':c.rolling(200).mean(),'sma20':c.rolling(20).mean(),
      'rvi':rvi,'rvi_signal':sym4(rvi),'demarker':demarker,'mass':mass,'ulcer':ulcer,
      'trix':trix,'trix_signal':trix.ewm(span=9,adjust=False).mean(),
      'klinger':ko,'klinger_signal':ko.ewm(span=13,adjust=False).mean(),
      'nvi':nvi,'nvi_signal':nvi.ewm(span=255,adjust=False).mean(),
      'vol60':c.pct_change(fill_method=None).rolling(60).std(ddof=1)*math.sqrt(365.25)})
    if hourly is not None:
        if not hourly.index.equals(frame.index):raise ValueError('Hourly feature alignment')
        basis=hourly.basis
        z['basis_z']=(basis-basis.rolling(60).mean().shift())/basis.rolling(60).std(ddof=1).shift().replace(0,np.nan)
        z['down_share']=ratio(hourly.down_rv.rolling(14).sum(),hourly.rv.rolling(14).sum(),.5)
    return z

def daily_signals(frame,family,prepared=None):
    if family not in FAMILIES:raise ValueError('Unregistered025family')
    z=features(frame) if prepared is None else prepared
    if not z.index.equals(frame.index):raise ValueError('Feature alignment')
    c=frame.Close;up=c>z.sma200;down=c<z.sma200;hold=20
    if family=='rvi10_cross':
        entry=cross(z.rvi,z.rvi_signal)&up;leave=(z.rvi<z.rvi_signal)|down
    elif family=='demarker14_rebound':
        entry=cross(z.demarker,.3)&up;leave=(z.demarker>.7)|down;hold=10
    elif family=='mass925_reversal':
        entry=(z.mass.shift().rolling(20).max()>27)&(z.mass<26.5)&(z.mass.shift()>=26.5)&(c>c.shift())&up
        leave=(c<z.sma20)|down
    elif family=='ulcer14_recovery':
        entry=(z.ulcer<5)&(z.ulcer.shift()>=5)&up;leave=(z.ulcer>10)|down
    elif family=='trix18_rebound':
        entry=cross(z.trix,z.trix_signal)&(z.trix<0)&up;leave=(z.trix<z.trix_signal)|down
    elif family=='klinger3455_cross':
        entry=cross(z.klinger,z.klinger_signal)&up;leave=(z.klinger<z.klinger_signal)|down
    elif family=='nvi255_confirm':
        entry=cross(z.nvi,z.nvi_signal)&up;leave=(z.nvi<z.nvi_signal)|down
    elif family=='utc_weekend_trend':
        weekday=pd.to_datetime(frame.Date,utc=True).dt.dayofweek
        entry=(weekday==4)&up;leave=(weekday==6)|down;hold=10
    elif family=='mark_discount60':
        if 'basis_z' not in z:raise ValueError('Closed hourly mark/trade features required')
        entry=(z.basis_z<-2)&up;leave=(z.basis_z>=0)|down;hold=10
    else:
        if 'down_share' not in z:raise ValueError('Closed hourly semivariance required')
        entry=(z.down_share<.5)&(z.down_share.shift()>=.5)&(z.down_share.shift().rolling(14).max()>.6)&up
        leave=(z.down_share>.6)|down;hold=10
    leave=leave.fillna(False)
    return pd.DataFrame({'entry':entry.fillna(False)&~leave,'exit':leave,'vol60':z.vol60,'max_hold':hold})

def make_signals(market,candidate,end):
    if candidate not in CANDIDATES:raise ValueError('Unregistered025candidate')
    if candidate in OLD_CANDIDATES:return prior.make_signals(market,candidate,end)
    if end%DAY or not market.start<end<=market.end:raise ValueError('Closed day boundary required')
    days=(end-market.start)//DAY;frame=market.frame.iloc[:days].copy().reset_index(drop=True)
    index=list(range(market.start,end,DAY))
    if list(frame.Date.astype('int64')//1000000)!=index:raise ValueError('Daily grid mismatch')
    z=features(frame,hourly_features(market,days))
    sig=daily_signals(frame,candidate.split('__')[0],z);sig.index=pd.Index(index);return sig

def replay(market,start,end,*,candidate=None,prepared_signals=None,**kwargs):
    if candidate not in NEW_CANDIDATES:
        if candidate is not None and candidate not in OLD_CANDIDATES:raise ValueError('Unregistered025candidate')
        return prior.replay(market,start,end,candidate=candidate,prepared_signals=prepared_signals,**kwargs)
    sig=make_signals(market,candidate,end) if prepared_signals is None else prepared_signals
    dispatch='funding_carry7_momentum28__'+candidate.split('__')[1]
    result=ledger.replay(market,start,end,candidate=dispatch,prepared_signals=sig,**kwargs)
    result['candidate']=candidate;result['ledger_sizing_dispatch_id']=dispatch
    result['signal_family_source']='tradingagents/multifamily_futures_025.py'
    result['classification']='Exploratory Binance USD-M historical research; no Bybit/live execution or prospective validation.'
    result['independent_wealth_audit']=audit_wealth(result);return result

def select_training(training):
    if set(training)!=set(CANDIDATES) or any(set(v)!=set(COSTS) for v in training.values()):raise ValueError('Incomplete46candidate training matrix')
    ranked=[]
    for c in CANDIDATES:
        pair=training[c];stress=pair['stress_assumption']['metrics']
        if all(ledger.passes(r,10) for r in pair.values()) and stress['annualized_net_return_pct'] is not None:
            ranked.append({'id':c,'score':stress['annualized_net_return_pct']/max(float(stress['max_drawdown_pct']),1.)})
    ranked.sort(key=lambda x:(-x['score'],x['id']))
    return {'selected':ranked[0]['id'] if ranked else 'cash','eligible':ranked,'basis':'All46 compatible candidates; train-only bothcosts/lag0/nominal funding,>=10exits,DD<=35%,positive net. Frozen before evaluation.'}
