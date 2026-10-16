"""Read-only snapshot depth diagnostics. No orders or paper-state writes."""
from decimal import Decimal, ROUND_DOWN

def number(value):
    if isinstance(value,bool): raise ValueError('Invalid number')
    value=Decimal(str(value))
    if not value.is_finite() or value<=0: raise ValueError('Positive finite number required')
    return value

def analyze(book,product,budget_usd,fee_bps=120):
    """Hypothetical taker buy then immediate bid liquidation in ONE snapshot.
    Round-trip cost diagnostic, never an actual/forecast fill. Quantity floored
    to base_increment; residual cash conserved. No future-liquidity assertion.
    """
    if product.get('status')!='online' or any(product.get(k,False) for k in
        ('trading_disabled','cancel_only','post_only','limit_only','auction_mode')) or book.get('auction_mode',False):
        raise ValueError('Product not in normal continuous market mode')
    if product.get('quote_currency')!='USD': raise ValueError('USD product required')
    budget,increment,minimum=map(number,(budget_usd,product['base_increment'],product['min_market_funds']))
    fee=number(fee_bps)/10000
    if fee>=1: raise ValueError('Invalid fee')
    sides={}
    for side in ('asks','bids'):
        rows=book[side]
        if not rows or len(rows)>100000: raise ValueError('Invalid depth')
        levels=[(number(row[0]),number(row[1])) for row in rows]
        prices=[p for p,_ in levels]
        if prices!=sorted(set(prices),reverse=side=='bids'): raise ValueError('Unsorted or duplicate prices')
        sides[side]=levels
    ask,bid=sides['asks'][0][0],sides['bids'][0][0]
    if bid>ask: raise ValueError('Crossed book')
    remaining=budget/(1+fee)
    if remaining<minimum: raise ValueError('Below minimum market funds after fees')
    possible_quantity=Decimal(0)
    for price,size in sides['asks']:
        cost=min(remaining,price*size);possible_quantity+=cost/price;remaining-=cost
        if remaining==0:break
    if remaining>0:raise ValueError('Insufficient observed ask depth')
    quantity=(possible_quantity/increment).to_integral_value(rounding=ROUND_DOWN)*increment
    if quantity<=0:raise ValueError('Quantity rounds to zero')
    def sweep(levels):
        left,notional=quantity,Decimal(0)
        for price,size in levels:
            amount=min(left,size);notional+=amount*price;left-=amount
            if left==0:return notional
        raise ValueError('Insufficient observed liquidation depth')
    buy_notional,sell_notional=sweep(sides['asks']),sweep(sides['bids'])
    if min(buy_notional,sell_notional)<minimum:raise ValueError('Rounded order or liquidation below market minimum')
    leftover=budget-buy_notional*(1+fee)
    if leftover<0:raise ArithmeticError('Budget exceeded')
    buy_vwap,sell_vwap=buy_notional/quantity,sell_notional/quantity
    proceeds=leftover+sell_notional*(1-fee);midpoint=(bid+ask)/2
    return {'budget_usd':str(budget),'fee_bps_each_side_assumption':fee_bps,'quantity':str(quantity),
        'leftover_usd':str(leftover),'buy_notional_usd':str(buy_notional),'sell_notional_usd':str(sell_notional),
        'buy_vwap':str(buy_vwap),'sell_vwap':str(sell_vwap),'spread_bps':float((ask-bid)/midpoint*10000),
        'ask_depth_impact_bps':float((buy_vwap/ask-1)*10000),'bid_depth_impact_bps':float((1-sell_vwap/bid)*10000),
        'same_snapshot_round_trip_loss_pct':float((1-proceeds/budget)*100),
        'real_execution':False,'historical_representativeness':False}
