"""Weekly causality, execution timing and depth-accounting independent oracles."""
from copy import deepcopy
from decimal import Decimal
import numpy as np
import pandas as pd
import pytest
from tradingagents import weekly_confirmation as weekly
from tradingagents.execution_depth import analyze
from scripts.run_weekly_confirmation_lab import CANDIDATES,select,simulate
from tests.test_strategy_backtest import frame_for

def sample():return frame_for(100+np.arange(500)*2.)

def test_completed_sunday_values_match_manual_arithmetic():
    frame=sample();sig=weekly.signals(frame)
    for i in range(len(frame)):
        sundays=frame.iloc[:i+1].loc[frame.Date.iloc[:i+1].dt.dayofweek==6,'Close']
        if len(sundays)>=40:
            assert sig.completed_week_close.iloc[i]==sundays.iloc[-1]
            assert sig.completed_week_sma40.iloc[i]==pytest.approx(sum(sundays.iloc[-40:])/40)
        else:
            assert pd.isna(sig.completed_week_sma40.iloc[i])
            assert not sig.entry.iloc[i] and not sig.exit.iloc[i]

@pytest.mark.parametrize('cut',[4,200,275,276,277,278,279,280,300,499])
def test_every_weekday_prefix_ignores_future_prices_and_incomplete_week(cut):
    frame=sample();expected=weekly.signals(frame.iloc[:cut+1]);changed=frame.copy()
    changed.loc[cut+1:,['Open','High','Low','Close']]*=1000
    pd.testing.assert_frame_equal(expected,weekly.signals(changed).iloc[:cut+1])

def test_weekly_features_do_not_change_during_unfinished_week():
    frame=sample();sig=weekly.signals(frame)
    monday=next(i for i in range(300,400) if frame.Date.iloc[i].dayofweek==0)
    changed=frame.copy();changed.loc[monday:monday+5,'Close']*=50;after=weekly.signals(changed)
    for col in ('completed_week_close','completed_week_sma40'):
        assert (after[col].iloc[monday:monday+6]==sig[col].iloc[monday-1]).all()

def test_prior_channel_excludes_current_candle_and_exit_has_priority():
    frame=sample();frame.loc[350,'High']=1e8;sig=weekly.signals(frame)
    assert bool(sig.entry.iloc[350])
    frame.loc[350,'Close']=1;sig=weekly.signals(frame)
    assert bool(sig.exit.iloc[350]) and not bool(sig.entry.iloc[350])

@pytest.mark.parametrize('sizing',weekly.SIZINGS)
@pytest.mark.parametrize('lag',[0,1,2])
def test_weekly_adapter_conserves_wealth_and_waits_for_next_open(sizing,lag):
    frame=sample();sig=weekly.signals(frame)
    assert sig.entry.iloc[300]
    sig['entry']=False;sig.loc[300,'entry']=True
    result,audit=simulate(frame,str(frame.Date.iloc[295].date()),str(frame.Date.iloc[340].date()),
        weekly.Candidate(weekly.FAMILY,sizing),{weekly.FAMILY:sig},{'fee':120,'slippage':25},lag=lag)
    buy=result['fills'][0]
    assert buy['date']==str(frame.Date.iloc[301+lag].date())
    assert buy['signal_date']==str(frame.Date.iloc[300].date())
    assert buy['price']==pytest.approx(frame.Open.iloc[301+lag]*1.0025)
    assert result['curve'][-1]['asset_quantity']==0
    assert audit['max_usd_error']<1e-8

def test_weekly_missing_daily_candle_refused():
    with pytest.raises(ValueError,match='Contiguous'):weekly.signals(sample().drop(index=300))

def test_selector_requires_all42_and_uses_only_eligible_training():
    good=dict(profit_after_operating_usd=10,max_close_drawdown_pct=10,closed_trades=10,annualized_after_operating_pct=1)
    training={c.id:{k:dict(good) for k in ('base','stress')} for c in CANDIDATES}
    training[weekly.CANDIDATES[0].id]['stress']['annualized_after_operating_pct']=20
    assert select(training)['selected']==weekly.CANDIDATES[0].id
    training.pop(weekly.CANDIDATES[1].id)
    with pytest.raises(ValueError,match='All42'):select(training)

def book():return {'asks':[['100','1',2],['110','10',4]],'bids':[['90','1',3],['80','10',2]],'auction_mode':False}
def product():return {'quote_currency':'USD','status':'online','base_increment':'.01','min_market_funds':'10'}

def test_depth_sweep_hand_oracle_uses_size_once_and_conserves_cash():
    r=analyze(book(),product(),212.10,100)
    assert Decimal(r['quantity'])==2
    assert Decimal(r['buy_notional_usd'])==210
    assert Decimal(r['sell_notional_usd'])==170
    assert Decimal(r['leftover_usd'])==0
    assert r['same_snapshot_round_trip_loss_pct']==pytest.approx(100*(1-168.3/212.1))

def test_depth_rounds_size_down_and_keeps_residual_cash():
    r=analyze(book(),product(),211,100);q=Decimal(r['quantity']);spend=Decimal(r['buy_notional_usd'])*Decimal('1.01')
    assert q%Decimal('.01')==0 and spend<=211
    assert spend+Decimal(r['leftover_usd'])==211

@pytest.mark.parametrize('condition',['auction','halt','crossed','insufficient_ask','insufficient_bid','minimum','duplicate','nan'])
def test_unexecutable_depth_is_not_reported_as_a_fill(condition):
    b,p=deepcopy(book()),product();budget=212.1
    if condition=='auction':b['auction_mode']=True
    elif condition=='halt':p['trading_disabled']=True
    elif condition=='crossed':b['bids'][0][0]='120'
    elif condition=='insufficient_ask':b['asks']=[['100','.01',1]]
    elif condition=='insufficient_bid':b['bids']=[['90','.01',1]]
    elif condition=='minimum':budget=1
    elif condition=='duplicate':b['asks'][1][0]='100'
    elif condition=='nan':b['asks'][1][1]='NaN'
    with pytest.raises(ValueError):analyze(b,p,budget,100)
