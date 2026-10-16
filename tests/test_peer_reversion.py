"""Synthetic financial/chronology tests, before016historical outcomes."""
import copy
import numpy as np
import pandas as pd
import pytest
from tradingagents import peer_reversion as model
from scripts.run_weekly_confirmation_lab import simulate
from tests.test_strategy_backtest import frame_for


def frames(n=500):
    t=np.arange(n)
    return {p:frame_for(100*np.exp(.0005*t+scale*np.sin(t/9+phase)))
            for p,scale,phase in zip(model.PRODUCTS,(.12,.07,.05),(0,1,2))}


def test_independent_prior_window_zscore_and_current_day_exclusion():
    data=frames(); data['BTC-USD'].loc[300,'Close'] *= .6
    output=model.signals(data)
    for p in model.PRODUCTS:
        peers=[k for k in model.PRODUCTS if k != p]
        log=lambda k:np.log(data[k].Close.to_numpy()/data[k].Close.iloc[0])
        spread=log(p)-sum(log(k) for k in peers)/2
        expected=(spread[300]-np.mean(spread[240:300]))/np.std(spread[240:300],ddof=1)
        assert output[p].z60.iloc[300] == pytest.approx(expected)
        assert bool(output[p].entry.iloc[300]) == (expected < -2)
        assert bool(output[p].exit.iloc[300]) == (expected >= 0)
    assert output['BTC-USD'].entry.iloc[300]


@pytest.mark.parametrize('cut',[59,60,200,320,499])
def test_future_peer_mutations_do_not_change_prefix(cut):
    data=frames(); expected=model.signals({p:f.iloc[:cut+1].copy() for p,f in data.items()})
    changed=copy.deepcopy(data)
    changed['LTC-USD'].loc[cut+1:,'Close'] *= 1000
    after=model.signals(changed)
    for p in model.PRODUCTS:pd.testing.assert_frame_equal(expected[p],after[p].iloc[:cut+1])


def test_quote_scale_and_input_order_do_not_change_signals():
    data=frames(); before=model.signals(data)
    changed={p:f.copy() for p,f in reversed(list(data.items()))}
    for (p,f),scale in zip(changed.items(),[1e8,1e-5,17]):f['Close'] *= scale
    after=model.signals(changed)
    for p in model.PRODUCTS:
        np.testing.assert_allclose(before[p].z60,after[p].z60,atol=1e-10,equal_nan=True)
        assert before[p].entry.equals(after[p].entry)
        assert before[p].exit.equals(after[p].exit)


@pytest.mark.parametrize('kind',['flat','identical_growth'])
def test_degenerate_relative_variance_never_trades(kind):
    t=np.arange(500)
    prices=np.full(500,100.) if kind=='flat' else 100*np.exp(t*.001)
    data={p:frame_for(prices*scale) for p,scale in zip(model.PRODUCTS,[1,20,.003])}
    for s in model.signals(data).values():
        assert not s.entry.any() and not s.exit.any()
        assert s.z60.isna().all()


@pytest.mark.parametrize('problem',['missing_peer','missing_day','shifted_day','wrong_index','nan','negative'])
def test_peers_must_be_valid_and_exactly_aligned(problem):
    data=frames()
    if problem=='missing_peer':data.pop('LTC-USD')
    elif problem=='missing_day':data['LTC-USD']=data['LTC-USD'].drop(index=250)
    elif problem=='shifted_day':data['LTC-USD'].Date+=pd.Timedelta(days=1)
    elif problem=='wrong_index':data['LTC-USD'].index+=1
    elif problem=='nan':data['LTC-USD'].loc[250,'Close']=np.nan
    else:data['LTC-USD'].loc[250,'Close']=-1
    with pytest.raises(ValueError):model.signals(data)


@pytest.mark.parametrize('sizing',model.SIZINGS)
@pytest.mark.parametrize('lag',[0,1,2])
def test_next_open_costs_and_time_exit_clock_after_actual_fill(sizing,lag):
    frame=frames()['BTC-USD']; sig=model.signals(frames())['BTC-USD']
    sig['entry']=False;sig.loc[300,'entry']=True;sig['exit']=False
    result,audit=simulate(frame,str(frame.Date.iloc[295].date()),str(frame.Date.iloc[350].date()),
        model.Candidate(model.FAMILY,sizing),{model.FAMILY:sig},{'fee':120,'slippage':25},lag=lag)
    buy,sell=result['fills']
    assert buy['date']==str(frame.Date.iloc[301+lag].date())
    assert buy['signal_date']==str(frame.Date.iloc[300].date())
    assert buy['price']==pytest.approx(frame.Open.iloc[301+lag]*1.0025)
    assert sell['date']==str(frame.Date.iloc[321+lag].date())
    assert sell['reason']=='time_exit' and sell['signal_date'] is None
    assert sell['price']==pytest.approx(frame.Open.iloc[321+lag]*.9975)
    expected=10000-buy['quantity']*buy['price']*(1+.012)+buy['quantity']*sell['price']*(1-.012)
    assert result['metrics']['final_usd']==pytest.approx(expected)
    assert audit['max_usd_error']<1e-8 and result['curve'][-1]['asset_quantity']==0


def test_signal_exit_precedes_time_limit_and_no_same_open_reentry():
    data=frames(); frame=data['BTC-USD'];sig=model.signals(data)['BTC-USD']
    sig['entry']=False;sig.loc[300:330,'entry']=True;sig['exit']=False;sig.loc[309,'exit']=True
    result,_=simulate(frame,str(frame.Date.iloc[295].date()),str(frame.Date.iloc[340].date()),
        model.CANDIDATES[0],{model.FAMILY:sig},{'fee':60,'slippage':10})
    first=result['trades'][0]
    assert first['exit_date']==str(frame.Date.iloc[310].date()) and first['reason']=='signal'
    assert result['fills'][2]['date']==str(frame.Date.iloc[311].date())


def test_training_selection_requires_both_costs():
    good={'profit_after_operating_usd':100,'max_close_drawdown_pct':10,'closed_trades':10,'annualized_after_operating_pct':2}
    train={c.id:{cost:dict(good) for cost in ('base','stress')} for c in model.CANDIDATES}
    assert model.select(train)['selected']==min(train)
    for pair in train.values():pair['stress']['profit_after_operating_usd']=-1
    assert model.select(train)['selected']=='cash'


def test_warmup_and_mutually_exclusive_signals():
    for sig in model.signals(frames()).values():
        assert not sig.entry.iloc[:60].any() and not sig.exit.iloc[:60].any()
        assert not (sig.entry & sig.exit).any()
        assert (sig.max_hold==20).all()


def test_comparison_requires_all46_and_preserves_failed_strong_candidates():
    rows=[{'id':str(i),'historical_robust_pass':False,'worst_return_pct':float(i),
           'worst_drawdown_pct':10.,'failed':['gate']} for i in range(46)]
    result=model.compare(rows[:44],rows[44:])
    assert len(result)==46 and {r['id'] for r in result}=={r['id'] for r in rows}
    assert result[0]['id']=='45' and result[0]['failed']==['gate']
    with pytest.raises(ValueError):model.compare(rows[:43],rows[44:])
