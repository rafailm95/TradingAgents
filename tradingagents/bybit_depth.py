"""Public Bybit linear USDT perpetual snapshot diagnostics; never sends orders."""
from decimal import Decimal, ROUND_DOWN


def dec(value, positive=False):
    if isinstance(value, bool): raise ValueError('Boolean is not a number')
    n = Decimal(str(value))
    if not n.is_finite() or (positive and n <= 0): raise ValueError('Invalid finite number')
    return n


def response(payload, received_ms, max_age_ms=30000):
    if type(payload.get('retCode')) is not int or payload['retCode'] != 0: raise ValueError('Bybit API rejected request')
    age = received_ms - int(payload['time'])
    if not -2000 <= age <= max_age_ms: raise ValueError('Stale response or clock mismatch')
    return payload['result']


def instrument(payload, symbol, received_ms):
    r = response(payload, received_ms)
    if r.get('category') != 'linear' or len(r['list']) != 1: raise ValueError('Wrong instrument category/count')
    p = r['list'][0]
    if (p.get('symbol') != symbol or p.get('status') != 'Trading' or
        p.get('contractType') != 'LinearPerpetual' or p.get('settleCoin') != 'USDT' or
        p.get('quoteCoin') != 'USDT' or p.get('isPreListing',False)):
        raise ValueError('Normal USDT linear perpetual required')
    for k in ('qtyStep','minOrderQty','maxMktOrderQty','minNotionalValue'):
        dec(p['lotSizeFilter'][k], True)
    dec(p['priceFilter']['tickSize'],True)
    if int(p['fundingInterval']) <= 0: raise ValueError('Invalid funding interval')
    return p


def parse_book(payload, symbol, received_ms, tick_size):
    r = response(payload, received_ms)
    if r['s'] != symbol: raise ValueError('Wrong book symbol')
    for key in ('ts','cts'):
        if not -2000 <= received_ms-int(r[key]) <= 30000:
            raise ValueError('Stale book or clock mismatch')
    if int(r['u']) < 0 or int(r['seq']) < 0: raise ValueError('Invalid sequence')
    sides = {}
    tick = dec(tick_size,True)
    for side in ('a','b'):
        if not 1 <= len(r[side]) <= 1000: raise ValueError('Invalid depth count')
        levels = [(dec(x[0],True),dec(x[1],True)) for x in r[side] if len(x)==2]
        if len(levels)!=len(r[side]): raise ValueError('Malformed depth row')
        prices = [p for p,q in levels]
        if prices != sorted(set(prices),reverse=side=='b'): raise ValueError('Unsorted or duplicate depth')
        if any(p % tick for p in prices): raise ValueError('Off-tick price')
        sides[side]=levels
    if sides['b'][0][0] >= sides['a'][0][0]: raise ValueError('Crossed or locked book')
    return r,sides


def sweep(levels, qty):
    left,total=qty,Decimal(0)
    for p,q in levels:
        take=min(left,q);total+=take*p;left-=take
        if left==0:return total
    raise ValueError('Insufficient displayed depth; no assumed fill')


def analyze(payload, product, received_ms, target_notional='5000', capital='10000', fee_bps='5.5'):
    r,sides=parse_book(payload,product['symbol'],received_ms,product['priceFilter']['tickSize'])
    target,capital=dec(target_notional,True),dec(capital,True)
    fee=dec(fee_bps)/10000
    if not 0 <= fee < 1 or target > capital: raise ValueError('Invalid fee or research notional cap')
    ask,bid=sides['a'][0][0],sides['b'][0][0];mid=(ask+bid)/2
    lot=product['lotSizeFilter'];step=dec(lot['qtyStep'],True)
    # Same base quantity both directions: sizing reference is current ask.
    qty=(target/ask/step).to_integral_value(rounding=ROUND_DOWN)*step
    if qty < dec(lot['minOrderQty'],True) or qty > dec(lot['maxMktOrderQty'],True):
        raise ValueError('Quantity outside current market limits')
    buy,sell=sweep(sides['a'],qty),sweep(sides['b'],qty)
    if min(buy,sell)<dec(lot['minNotionalValue'],True): raise ValueError('Below min notional')
    fees=(buy+sell)*fee;loss=buy-sell+fees
    bands=[]
    for bps in (5,10,25,50):
        upper,lower=mid*(1+Decimal(bps)/10000),mid*(1-Decimal(bps)/10000)
        asks=sum((p*q for p,q in sides['a'] if p<=upper),Decimal(0))
        bids=sum((p*q for p,q in sides['b'] if p>=lower),Decimal(0))
        bands.append({'distance_from_mid_bps':bps,'ask_notional_usdt':str(asks),'bid_notional_usdt':str(bids),
          'ask_band_fully_observed':sides['a'][-1][0]>=upper,
          'bid_band_fully_observed':sides['b'][-1][0]<=lower})
    return {'symbol':product['symbol'],'market':'linear_USDT_perpetual','source_ts_ms':r['ts'],
      'source_cts_ms':r['cts'],'update_id':r['u'],'sequence':r['seq'],
      'capital_usdt':str(capital),'target_notional_usdt':str(target),'quantity':str(qty),
      'buy_notional_usdt':str(buy),'sell_notional_usdt':str(sell),
      'buy_vwap':str(buy/qty),'sell_vwap':str(sell/qty),
      'spread_bps':str((ask-bid)/mid*10000),
      'buy_impact_bps':str((buy/qty/ask-1)*10000),'sell_impact_bps':str((1-sell/qty/bid)*10000),
      'fee_bps_each_side_assumption':str(fee*10000),'round_trip_fees_usdt':str(fees),
      'same_snapshot_round_trip_loss_usdt':str(loss),'loss_pct_capital':str(loss/capital*100),
      'loss_pct_buy_notional':str(loss/buy*100),'depth_bands':bands,
      'direction_note':'Same quantity long buy/sell or short sell/buy has same static round-trip cost.',
      'excludes':['future book changes','funding during holding period','latency slippage','liquidation','RPI liquidity'],
      'real_execution':False,'representative_of_history':False}


def funding_summary(payload,symbol,received_ms,notional='5000'):
    r=response(payload,received_ms)
    if r.get('category')!='linear' or not r['list']: raise ValueError('Missing linear funding history')
    rows=r['list'];times=[int(x['fundingRateTimestamp']) for x in rows]
    if times!=sorted(set(times),reverse=True) or any(t>received_ms for t in times):
        raise ValueError('Invalid funding history chronology')
    if any(x['symbol']!=symbol for x in rows):raise ValueError('Wrong funding symbol')
    rates=[dec(x['fundingRate']) for x in rows]
    n=dec(notional,True);total=sum(rates,Decimal(0))*n
    return {'observed_events':len(rows),'first_timestamp_ms':min(times),'last_timestamp_ms':max(times),
      'coverage':'latest returned events only; not full backtest coverage',
      'latest_rate_pct':str(rates[0]*100),'constant_notional_assumption_usdt':str(n),
      'sum_long_funding_paid_usdt':str(total),'sum_short_funding_paid_usdt':str(-total),
      'amounts_are_scenarios_not_account_pnl':True}
