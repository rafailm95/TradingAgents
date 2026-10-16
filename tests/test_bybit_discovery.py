import copy
from decimal import Decimal as D
import pytest
from tradingagents.bybit_depth import analyze,instrument,parse_book,funding_summary,response
from tradingagents.opportunity_discovery import drawdown,curve_diagnostics,pareto_tiers

NOW=1800000000000

def fixture():
    p={'symbol':'BTCUSDT','status':'Trading','contractType':'LinearPerpetual','settleCoin':'USDT','quoteCoin':'USDT',
       'fundingInterval':480,'priceFilter':{'tickSize':'0.5'},
       'lotSizeFilter':{'qtyStep':'0.1','minOrderQty':'0.1','maxMktOrderQty':'100','minNotionalValue':'5'}}
    b={'retCode':0,'time':NOW,'result':{'s':'BTCUSDT','ts':NOW,'cts':NOW,'u':1,'seq':1,
      'a':[['100','1'],['101','10']],'b':[['99','1'],['98','10']]}}
    return p,b


def test_manual_depth_fee_oracle():
    p,b=fixture();r=analyze(b,p,NOW,250,10000,10)
    assert D(r['quantity'])==D('2.5')
    assert D(r['buy_notional_usdt'])==D('251.5')
    assert D(r['sell_notional_usdt'])==D('246')
    assert D(r['round_trip_fees_usdt'])==D('.4975')
    assert D(r['same_snapshot_round_trip_loss_usdt'])==D('5.9975')
    assert D(r['loss_pct_capital'])==D('.059975')


def test_quantity_rounding_and_zero_fee():
    p,b=fixture();r=analyze(b,p,NOW,259,10000,0)
    assert r['quantity']=='2.5'
    assert D(r['round_trip_fees_usdt'])==0


@pytest.mark.parametrize('mutation',[lambda b:b.update(retCode=10001),lambda b:b.update(time=NOW-30001),
    lambda b:b['result'].update(cts=NOW+3000),lambda b:b['result'].update(s='ETHUSDT'),
    lambda b:b['result'].update(a=[['100','1'],['100','2']]),
    lambda b:b['result'].update(b=[['101','1']]),lambda b:b['result'].update(a=[['NaN','1']]),
    lambda b:b['result'].update(a=[['100.1','1']]),lambda b:b['result'].update(a=[['100','-1']])])
def test_reject_invalid_books(mutation):
    p,b=fixture();mutation(b)
    with pytest.raises(ValueError):analyze(b,p,NOW,250)


def test_insufficient_depth_and_minimum():
    p,b=fixture()
    with pytest.raises(ValueError,match='Insufficient'):analyze(b,p,NOW,5000)
    with pytest.raises(ValueError,match='Quantity'):analyze(b,p,NOW,1)
    p['lotSizeFilter']['maxMktOrderQty']='1'
    with pytest.raises(ValueError,match='Quantity'):analyze(b,p,NOW,250)


def test_depth_bands_not_overclaimed():
    p,b=fixture();r=analyze(b,p,NOW,250)
    band=r['depth_bands'][0]
    assert D(band['bid_notional_usdt'])==0 and D(band['ask_notional_usdt'])==0
    assert band['ask_band_fully_observed'] and band['bid_band_fully_observed']
    b['result']['a']=[['100','100']];b['result']['b']=[['99.5','100']]
    r=analyze(b,p,NOW,250)
    assert not r['depth_bands'][-1]['ask_band_fully_observed']


def test_instrument_contract_identity():
    p,b=fixture();payload={'retCode':0,'time':NOW,'result':{'category':'linear','list':[p]}}
    assert instrument(payload,'BTCUSDT',NOW)==p
    p['settleCoin']='BTC'
    with pytest.raises(ValueError):instrument(payload,'BTCUSDT',NOW)


def test_funding_sign_and_timestamp():
    payload={'retCode':0,'time':NOW,'result':{'category':'linear','list':[
       {'symbol':'BTCUSDT','fundingRate':'.0001','fundingRateTimestamp':str(NOW-100)},
       {'symbol':'BTCUSDT','fundingRate':'-.0002','fundingRateTimestamp':str(NOW-1000)}]}}
    r=funding_summary(payload,'BTCUSDT',NOW)
    assert D(r['sum_long_funding_paid_usdt'])==D('-.5')
    assert D(r['sum_short_funding_paid_usdt'])==D('.5')
    payload['result']['list'].reverse()
    with pytest.raises(ValueError):funding_summary(payload,'BTCUSDT',NOW)


def test_drawdown_cash_is_from_peak_not_initial():
    r=drawdown([12000,9000,13000,10000],10000)
    assert r['max_drawdown_pct']==25
    assert r['amount_at_max_pct_usd']==3000
    assert r['amount_at_max_pct_usd']!=10000*.25


def test_pct_and_cash_maxima_may_differ():
    r=drawdown([10000,5000,20000,14000],10000)
    assert r['max_drawdown_pct']==50
    assert r['amount_at_max_pct_usd']==5000
    assert r['max_cash_drawdown_usd']==6000


def test_accrued_costs_and_calendar_segments():
    r={'metrics':{'initial_usd':10000,'days':2,'operating_cost_usd':100,'profit_after_operating_usd':900},
       'curve':[{'Date':'2025-12-31','equity':12000},{'Date':'2026-01-01','equity':11000}]}
    d=curve_diagnostics(r)
    assert d['amount_at_max_pct_usd']==1050
    assert sum(x['pnl_usd'] for x in d['calendar_segments'])==900
    r['metrics']['profit_after_operating_usd']=901
    with pytest.raises(ValueError):curve_diagnostics(r)


def test_pareto_tradeoffs_and_ties():
    rows=[{'id':'a','worst_return_pct':10,'worst_drawdown_pct':10},
          {'id':'b','worst_return_pct':5,'worst_drawdown_pct':5},
          {'id':'c','worst_return_pct':4,'worst_drawdown_pct':10},
          {'id':'d','worst_return_pct':10,'worst_drawdown_pct':10}]
    ranked=pareto_tiers(rows)
    assert [r['pareto_tier'] for r in ranked]==[1,1,2,1]
    assert [r['id'] for r in pareto_tiers(list(reversed(rows))) if r['pareto_tier']==2]==['c']
