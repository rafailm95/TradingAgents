"""Experiment019 additive capital-carry derivative of the frozen013 replay.

Only registration, initial capital and managed-cash expense are extended.
Frozen013 source is untouched. See engine-diff.patch for the exact delta.

Frozen daily signals; exact decimal cash accounting; current-rule fill proxies.
No exchange transport, private API, orders, or liquidation-price calculation.
"""
from dataclasses import dataclass
from decimal import Decimal as D, ROUND_CEILING, ROUND_FLOOR, localcontext
import math

import pandas as pd

from tradingagents import strategy_lab as legacy, strategy_families as families
from tradingagents.bybit_cashflow import LinearCashflow, drawdown
from tradingagents.bybit_history import DAY, HOUR, SYMBOLS, daily_trade, integer, number

CANDIDATES = ('sma200_band__vol15_cap50', 'regression_trend__fixed50',
              'keltner_breakout__fixed50', 'obv_breakout__fixed50',
              'aroon_trend__fixed50', 'cci_reversion__fixed50')
COSTS = {'venue_assumption': ('5.5', '2'), 'stress_assumption': ('10', '10')}
from tradingagents.funding_signal_019 import NEW_CANDIDATES, funding_signals
CANDIDATES = CANDIDATES + NEW_CANDIDATES
ZERO = D(0)


def decimal(value, *, positive=False):
    v = number(value, positive=positive)
    # Bound arithmetic and reject pathological numerical payloads before replay.
    if len(v.as_tuple().digits) > 30 or not -24 <= v.as_tuple().exponent <= 12 or abs(v) > D('1e15'):
        raise ValueError('Unsupported decimal precision/magnitude')
    return v


@dataclass(frozen=True)
class Rules:
    step: D
    minimum: D
    maximum: D
    minimum_notional: D
    tick: D

    @classmethod
    def from_product(cls, product, symbol):
        if (product.get('symbol') != symbol or product.get('contractType') != 'LinearPerpetual'
                or product.get('quoteCoin') != 'USDT' or product.get('settleCoin') != 'USDT'
                or product.get('status') != 'Trading' or integer(product['fundingInterval']) != 480):
            raise ValueError('Unsupported current instrument or funding schedule')
        lot = product['lotSizeFilter']
        r = cls(*(decimal(x, positive=True) for x in (lot['qtyStep'], lot['minOrderQty'],
                lot['maxMktOrderQty'], lot['minNotionalValue'], product['priceFilter']['tickSize'])))
        if r.maximum < r.minimum or r.minimum % r.step or r.maximum % r.step:
            raise ValueError('Inconsistent current quantity filters')
        return r


@dataclass(frozen=True)
class Market:
    symbol: str
    start: int
    end: int
    trade: tuple
    mark: tuple
    funding: dict
    rules: Rules
    frame: pd.DataFrame


def prepare(dataset, symbol):
    """Revalidate normalized raw rows. Caller separately pins/audits provenance."""
    if symbol not in SYMBOLS:
        raise ValueError('Unsupported symbol')
    rules = Rules.from_product(dataset['instrument'], symbol)
    parsed = {}
    times = None
    for kind in ('trade', 'mark'):
        raw = dataset[kind]
        if not raw or len(raw) > 10 * 366 * 24:
            raise ValueError('Empty or oversized hourly series')
        current = [integer(r[0]) for r in raw]
        if (current[0] % DAY or len(raw) % 24 or
                current != list(range(current[0], current[0] + len(raw) * HOUR, HOUR))):
            raise ValueError('Incomplete/duplicate/nonconsecutive hourly UTC grid')
        if times is not None and current != times:
            raise ValueError('Trade/mark alignment mismatch')
        times = current
        bars = []
        for r in raw:
            if len(r) != (7 if kind == 'trade' else 5):
                raise ValueError('Malformed candle')
            o, h, l, c = [decimal(x, positive=True) for x in r[1:5]]
            if not l <= min(o, c) <= max(o, c) <= h:
                raise ValueError('Invalid OHLC')
            if kind == 'trade' and any(decimal(x) < 0 for x in r[5:]):
                raise ValueError('Negative volume')
            bars.append((o, h, l, c))
        parsed[kind] = tuple(bars)
    start, end = times[0], times[-1] + HOUR
    if integer(dataset['instrument']['launchTime']) > start:
        raise ValueError('Instrument launched after requested start')
    funding = {}
    rows = dataset['funding']
    if [integer(r['fundingRateTimestamp']) for r in rows] != list(range(start, end, 8 * HOUR)):
        raise ValueError('Funding grid incomplete or changed; no zero filling')
    anchor = dataset['funding_anchor']
    if not anchor or integer(anchor['fundingRateTimestamp']) != start - 8 * HOUR:
        raise ValueError('Missing exact funding anchor')
    for row in [anchor] + rows:
        if row['symbol'] != symbol:
            raise ValueError('Funding symbol mismatch')
        rate = decimal(row['fundingRate'])
        if row is not anchor:
            funding[integer(row['fundingRateTimestamp'])] = rate
    with localcontext() as ctx:
        ctx.prec = 128
        daily = daily_trade(dataset['trade'])
    frame = pd.DataFrame(daily, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'Turnover'])
    frame['Date'] = pd.to_datetime(frame.Date.astype('int64'), unit='ms', utc=True)
    for name in ['Open', 'High', 'Low', 'Close', 'Volume', 'Turnover']:
        frame[name] = frame[name].astype(float)
    return Market(symbol, start, end, parsed['trade'], parsed['mark'], funding, rules, frame)


def make_signals(market, candidate, end):
    if candidate not in CANDIDATES:
        raise ValueError('Unregistered013 candidate')
    if candidate in NEW_CANDIDATES:
        return funding_signals(market, end)
    frame = market.frame.iloc[:(end - market.start) // DAY].copy()
    family, _ = candidate.split('__')
    sig = legacy.signals(frame, family) if family in legacy.FAMILIES else families.signals(frame, family)
    # Index by day-open UTC milliseconds. Signal becomes observable after day close.
    sig.index = pd.Index(frame.Date.astype('int64') // 1_000_000)
    return sig


def fill_price(reference, slip_bps, tick, buy):
    raw = reference * (1 + slip_bps / 10000 if buy else 1 - slip_bps / 10000)
    price = (raw / tick).to_integral_value(rounding=ROUND_CEILING if buy else ROUND_FLOOR) * tick
    if price <= 0:
        raise ValueError('Nonpositive rounded fill')
    return price


def replay(market, start, end, *, candidate=None, benchmark=None, cost='venue_assumption',
           lag=0, adverse_funding=False, prepared_signals=None,
           initial_usdt='10000', managed_cash=False):
    """Exclusive UTC end; explicit opening cash; terminal flatten each fold; no network.

    prepared_signals is a test/internal causal cache, never a CLI input.
    Cash precision128; expense rounded to18decimal places cumulatively by hour.
    """
    with localcontext() as ctx:
        ctx.prec = 128
        return _replay(market, start, end, candidate=candidate, benchmark=benchmark,
                       cost=cost, lag=lag, adverse_funding=adverse_funding,
                       prepared_signals=prepared_signals, initial_usdt=initial_usdt,
                       managed_cash=managed_cash)


def _replay(m, start, end, *, candidate, benchmark, cost, lag, adverse_funding, prepared_signals,
            initial_usdt, managed_cash):
    initial = D(initial_usdt)
    if not initial.is_finite() or not 0 < initial <= D('1e15') or len(initial.as_tuple().digits) > 200:
        raise ValueError('Invalid opening cash')
    if type(managed_cash) is not bool:
        raise ValueError('managed_cash must be boolean')
    if (candidate is None) == (benchmark is None) or candidate not in (None, *CANDIDATES):
        raise ValueError('Exactly one registered candidate or benchmark required')
    if benchmark not in (None, 'cash', 'buy_hold50') or cost not in COSTS:
        raise ValueError('Unknown benchmark/cost')
    if type(lag) is not int or lag not in (0, 1, 2) or type(adverse_funding) is not bool:
        raise ValueError('Unregistered sensitivity')
    if (type(start) is not int or type(end) is not int or start % DAY or end % DAY or
            not m.start <= start < end <= m.end or start - m.start < 200 * DAY):
        raise ValueError('Invalid window or insufficient warmup')
    if benchmark and lag:
        raise ValueError('Benchmarks have no signal lag')
    sig = None
    if candidate:
        sig = make_signals(m, candidate, end) if prepared_signals is None else prepared_signals
        expected = list(range(m.start, end, DAY))
        if list(sig.index) != expected or list(sig.columns) != ['entry', 'exit', 'vol60', 'max_hold']:
            raise ValueError('Signal alignment/columns mismatch')
        if any(sig[k].dtype != bool or sig[k].isna().any() for k in ('entry', 'exit')) or (sig.entry & sig.exit).any():
            raise ValueError('Invalid/conflicting signals')
        if not sig.max_hold.isin([0, 10, 20]).all():
            raise ValueError('Invalid holding limit')
    fee, slip = map(D, COSTS[cost])
    ledger = LinearCashflow(initial, fee)
    events, curve, fills, trades, rejections, funding_events = [], [], [], [], [], []
    opened = None
    status, failure = 'COMPLETE', None
    peak = ledger.initial
    excursion = {'max_excursion_pct': '0', 'cash_at_max_excursion_usdt': '0',
                 'mark_low_ms': None, 'prior_sampled_peak_usdt': str(initial),
                 'low_equity_after_exit_fee_usdt': None,
                 'interpretation': 'Adverse hourly low relative to preceding sampled peak; unknown OHLC order, not realized drawdown.'}

    def event(ts, kind, mark, **extra):
        events.append({'timestamp_ms': ts, 'kind': kind, 'mark': str(mark),
                       'cash': str(ledger.balance), 'quantity': str(ledger.quantity),
                       'equity': str(ledger.equity(mark)), **extra})

    def sample(ts, phase, mark):
        nonlocal peak
        equity = ledger.equity(mark, reserve_exit_fee=True)
        curve.append({'timestamp_ms': ts, 'phase': phase, 'equity_usdt': str(equity),
                      'cash_usdt': str(ledger.balance), 'quantity': str(ledger.quantity), 'mark': str(mark)})
        event(ts, 'sample', mark, phase=phase, reserved_equity=str(equity))
        peak = max(peak, equity)

    def guard(ts, phase, mark):
        nonlocal status, failure
        equity = ledger.equity(mark, reserve_exit_fee=True)
        notional = abs(ledger.quantity) * mark
        if equity <= 0 or equity < notional:
            status = 'MARGIN_MODEL_UNSUPPORTED'
            failure = {'timestamp_ms': ts, 'phase': phase, 'mark': str(mark),
                       'equity_after_exit_fee_usdt': str(equity), 'notional_usdt': str(notional),
                       'open_quantity': str(ledger.quantity),
                       'reason': 'Fully cash-backed guard breached; no assumed liquidation/further fills.'}
            return False
        return True

    def enter(ts, reference, mark, fraction, signal_day):
        nonlocal opened
        price = fill_price(reference, slip, m.rules.tick, True)
        q = (ledger.balance * fraction / price / m.rules.step).to_integral_value(rounding=ROUND_FLOOR) * m.rules.step
        notional = q * price
        charge = notional * ledger.fee_rate
        if (not q or q % m.rules.step or not m.rules.minimum <= q <= m.rules.maximum
                or notional < m.rules.minimum_notional or notional > ledger.balance * D('.5')
                or notional + 2 * charge > ledger.balance):
            rejections.append({'timestamp_ms': ts, 'reason': 'CURRENT_FILTER_OR_ENTRY_BUDGET_REJECTION',
                               'quantity': str(q), 'fill_price': str(price)})
            return
        # Accounting failures are fatal, never mislabeled as harmless order rejection.
        ledger.open(q, price, quantity_step=m.rules.step, minimum_quantity=m.rules.minimum,
                    maximum_quantity=m.rules.maximum, minimum_notional=m.rules.minimum_notional)
        opened = {'timestamp_ms': ts, 'price': price, 'quantity': q, 'fee': charge,
                  'funding_start': ledger.funding, 'expense_start': ledger.expense}
        fill = {'timestamp_ms': ts, 'side': 'buy', 'reason': 'entry', 'signal_day_ms': signal_day,
                'reference': str(reference), 'price': str(price), 'quantity': str(q),
                'fee_usdt': str(charge), 'fraction': str(fraction)}
        fills.append(fill); event(ts, 'fill', mark, fill=fill)

    def leave(ts, reference, mark, reason, signal_day):
        nonlocal opened
        price = fill_price(reference, slip, m.rules.tick, False)
        q = ledger.quantity; charge = q * price * ledger.fee_rate
        ledger.close(price)
        fill = {'timestamp_ms': ts, 'side': 'sell', 'reason': reason, 'signal_day_ms': signal_day,
                'reference': str(reference), 'price': str(price), 'quantity': str(q), 'fee_usdt': str(charge)}
        fills.append(fill); event(ts, 'fill', mark, fill=fill)
        price_pnl = q * (price - opened['price'])
        funding = ledger.funding - opened['funding_start']
        trade_fees = opened['fee'] + charge
        trades.append({'entry_ms': opened['timestamp_ms'], 'exit_ms': ts, 'reason': reason,
                       'price_pnl_usdt': str(price_pnl), 'fees_usdt': str(trade_fees),
                       'funding_usdt': str(funding), 'net_before_operating_usdt': str(price_pnl + funding - trade_fees)})
        opened = None

    first, last = (start - m.start) // HOUR, (end - m.start) // HOUR
    for i in range(first, last):
        ts = m.start + i * HOUR
        trade, mark = m.trade[i], m.mark[i]
        event(ts, 'hour_open', mark[0]); sample(ts, 'before_funding', mark[0])
        if not guard(ts, 'hour_open', mark[0]): break
        if ts in m.funding:
            rate = m.funding[ts]
            valuation = mark[0]
            if adverse_funding and ledger.quantity:
                valuation *= D('1.0005') if rate >= 0 else D('.9995')
            quantity_before = ledger.quantity
            cash = ledger.settle_funding(ts, valuation, rate)
            record = {'timestamp_ms': ts, 'rate': str(rate), 'valuation_mark': str(valuation),
                      'quantity_before': str(quantity_before), 'cashflow_usdt': str(cash)}
            funding_events.append(record); event(ts, 'funding', mark[0], funding=record)
            sample(ts, 'after_funding', mark[0])
            if not guard(ts, 'after_funding', mark[0]): break
        if ts % DAY == HOUR:
            if candidate:
                day = ts - HOUR - (lag + 1) * DAY
                row = sig.loc[day]
                timed = bool(opened and row.max_hold > 0 and ts - opened['timestamp_ms'] >= int(row.max_hold) * DAY)
                if ledger.quantity:
                    if bool(row.exit) or timed:
                        leave(ts, trade[0], mark[0], 'time_exit' if timed else 'signal_exit', day)
                elif bool(row.entry):
                    try:
                        fraction = D(str(legacy.allocation(candidate.split('__')[1], float(row.vol60))))
                    except ValueError:
                        rejections.append({'timestamp_ms': ts, 'reason': 'MISSING_SIZING_VOLATILITY'})
                    else:
                        enter(ts, trade[0], mark[0], fraction, day)
            elif benchmark == 'buy_hold50' and ts == start + HOUR:
                enter(ts, trade[0], mark[0], D('.5'), None)
            sample(ts, 'after_decision', mark[0])
            if not guard(ts, 'after_decision', mark[0]): break
        # Allocate expense to each completed hour, rounded cumulatively, not per trade.
        hours = i - first + 1
        desired = (D(120) * hours / (D('365.25') * 24)).quantize(D('1e-18')) if benchmark != 'cash' or managed_cash else ZERO
        expense = desired - ledger.expense
        ledger.operating_cost(expense)
        event(ts + HOUR - 1, 'expense', mark[3], amount_usdt=str(expense))
        # Charge that hour's expense before assessing extremes: conservative cash reserve.
        low_equity = ledger.equity(mark[2], reserve_exit_fee=True)
        drop = max(ZERO, peak - low_equity)
        pct = drop / peak * 100
        if pct > D(excursion['max_excursion_pct']):
            excursion.update(max_excursion_pct=str(pct), cash_at_max_excursion_usdt=str(drop),
                             mark_low_ms=ts, prior_sampled_peak_usdt=str(peak),
                             low_equity_after_exit_fee_usdt=str(low_equity))
        # Low and high are scenarios, never inserted into the chronological equity curve.
        if not guard(ts, 'intrahour_low_unknown_time', mark[2]) or not guard(ts, 'intrahour_high_unknown_time', mark[1]):
            break
        if not guard(ts + HOUR, 'hour_close_before_terminal', mark[3]): break
        if i == last - 1 and ledger.quantity:
            # Close is represented at final millisecond of the last closed candle;
            # the next window's funding event is outside this independent run.
            leave(end - 1, trade[3], mark[3], 'scheduled_terminal_close', None)
            if not guard(end - 1, 'after_terminal', mark[3]): break
        sample(ts + HOUR, 'hour_close', mark[3])
        event(ts + HOUR, 'hour_close', mark[3])
        ledger.reconcile(mark[3])
    # Failed runs retain their partial ledger and open position, never a fake final close.
    last_mark = D(events[-1]['mark'])
    equity = ledger.equity(last_mark, reserve_exit_fee=True)
    if status != 'COMPLETE':
        sample(events[-1]['timestamp_ms'], 'stopped_last_observed_mark', last_mark)
    net = equity - ledger.initial
    duration_days = D(end - start) / DAY
    annualized = None
    if equity > 0 and status == 'COMPLETE':
        exponent = math.log(float(equity / ledger.initial)) * 365.25 / float(duration_days)
        if exponent < 700:
            annualized = 100 * math.expm1(exponent)
    metrics = {'initial_usdt': str(ledger.initial), 'final_cash_usdt': str(ledger.balance),
               'final_equity_after_exit_fee_usdt': str(equity),
               'net_profit_usdt': str(net), 'net_return_pct': str(net / ledger.initial * 100),
               'realized_price_pnl_usdt': str(ledger.price_pnl), 'fees_usdt': str(ledger.fees),
               'funding_usdt': str(ledger.funding), 'operating_expense_usdt': str(ledger.expense),
               'open_quantity': str(ledger.quantity), 'closed_trades': len(trades),
               'signal_exits': sum(t['reason'] in ('signal_exit', 'time_exit') for t in trades),
               'rejected_entries': len(rejections),
               'annualized_net_return_pct': annualized,
               **drawdown([r['equity_usdt'] for r in curve], initial=ledger.initial)}
    result = {'schema': 'futures_replay_019_v1', 'venue': 'Binance USD-M perpetual',
              'managed_cash': managed_cash, 'status': status, 'failure': failure,
              'symbol': m.symbol, 'candidate': candidate, 'benchmark': benchmark,
              'start_ms': start, 'end_exclusive_ms': end, 'cost': cost, 'lag_days': lag,
              'adverse_funding_5bps': adverse_funding, 'metrics': metrics,
              'current_rule_proxies': {k: str(v) for k, v in vars(m.rules).items()},
              'intrahour_excursion': excursion, 'curve': curve, 'events': events,
              'fills': fills, 'trades': trades, 'funding_events': funding_events, 'entry_rejections': rejections,
              'classification': 'Exploratory historical venue transfer, not forward validation or actual execution.',
              'real_orders': 0}
    result['independent_wealth_audit'] = audit_wealth(result)
    return result


def audit_wealth(result):
    """Independent mark-to-mark wealth recurrence; no entry-price/cash-PnL ledger.

    Rebuild exposure and every funding/fee/expense from event inputs and compare
    both total wealth and exit-fee-reserved curve. Checks trade net reconciliation.
    """
    with localcontext() as ctx:
        ctx.prec = 128
        wealth, q, previous = D(result['metrics']['initial_usdt']), ZERO, None
        fee = D(COSTS[result['cost']][0]) / 10000
        funding_seen = set(); maximum = ZERO; sampled = []; previous_ts = -1
        fees = ZERO; funding_total = ZERO; expenses = ZERO; fills = []; settlements = []
        for event in result['events']:
            mark = D(event['mark'])
            if event['timestamp_ms'] < previous_ts:
                raise ValueError('Nonchronological audit events')
            previous_ts = event['timestamp_ms']
            if previous is not None:
                wealth += q * (mark - previous)
            if event['kind'] == 'fill':
                f = event['fill']; qty, price = D(f['quantity']), D(f['price'])
                delta = qty if f['side'] == 'buy' else -qty
                if f['side'] not in ('buy', 'sell'):
                    raise ValueError('Invalid fill side')
                expected_price = fill_price(D(f['reference']), D(COSTS[result['cost']][1]),
                                            D(result['current_rule_proxies']['tick']), delta > 0)
                if price != expected_price:
                    raise ValueError('Adverse price/tick mismatch')
                if f['reason'] == 'entry' and (f['timestamp_ms'] % DAY != HOUR or
                        (f['signal_day_ms'] is not None and f['timestamp_ms'] !=
                         f['signal_day_ms'] + (result['lag_days'] + 1) * DAY + HOUR)):
                    raise ValueError('Noncausal entry time')
                if (delta > 0 and q != 0) or (delta < 0 and qty != q):
                    raise ValueError('Wealth audit: invalid position transition')
                charge = qty * price * fee
                if charge != D(f['fee_usdt']): raise ValueError('Wealth audit: fee mismatch')
                fees += charge; fills.append(f)
                wealth += delta * (mark - price) - charge
                q += delta
            elif event['kind'] == 'funding':
                f = event['funding']; ts = f['timestamp_ms']
                if ts in funding_seen or D(f['quantity_before']) != q:
                    raise ValueError('Wealth audit: duplicate/wrong funding position')
                funding_seen.add(ts)
                valuation = mark
                if result['adverse_funding_5bps'] and q:
                    valuation *= D('1.0005') if D(f['rate']) >= 0 else D('.9995')
                cash = -q * valuation * D(f['rate'])
                if valuation != D(f['valuation_mark']) or cash != D(f['cashflow_usdt']):
                    raise ValueError('Wealth audit: funding mismatch')
                wealth += cash
                funding_total += cash; settlements.append(f)
            elif event['kind'] == 'expense':
                charge = D(event['amount_usdt'])
                hours = (event['timestamp_ms'] + 1 - result['start_ms']) // HOUR
                expected_expense = (D(120) * hours / (D('365.25') * 24)).quantize(D('1e-18')) if result['benchmark'] != 'cash' or result['managed_cash'] else ZERO
                if charge < 0 or expenses + charge != expected_expense:
                    raise ValueError('Operating expense schedule mismatch')
                expenses += charge; wealth -= charge
            elif event['kind'] == 'sample':
                reserved = wealth - q * mark * fee
                if abs(reserved - D(event['reserved_equity'])) > D('1e-40'):
                    raise ValueError('Reserved equity mismatch')
                sampled.append({'timestamp_ms': event['timestamp_ms'], 'phase': event['phase'],
                                'equity_usdt': event['reserved_equity'], 'cash_usdt': event['cash'],
                                'quantity': event['quantity'], 'mark': event['mark']})
            elif event['kind'] not in ('hour_open', 'hour_close'):
                raise ValueError('Unknown audit event')
            error = abs(wealth - D(event['equity'])); maximum = max(maximum, error)
            if error > D('1e-40') or q != D(event['quantity']):
                raise ValueError('Independent wealth recurrence mismatch')
            previous = mark
        metrics = result['metrics']
        if fills != result['fills'] or settlements != result['funding_events']:
            raise ValueError('Fill/funding history mismatch')
        if (fees != D(metrics['fees_usdt']) or funding_total != D(metrics['funding_usdt'])
                or expenses != D(metrics['operating_expense_usdt'])
                or metrics['closed_trades'] != len(result['trades'])
                or metrics['signal_exits'] != sum(t['reason'] in ('signal_exit', 'time_exit') for t in result['trades'])):
            raise ValueError('Accounting summary mismatch')
        if sampled != result['curve']:
            raise ValueError('Sampled curve mismatch')
        dd = drawdown([r['equity_usdt'] for r in sampled], initial=metrics['initial_usdt'])
        if any(result['metrics'][k] != v for k, v in dd.items()):
            raise ValueError('Drawdown summary mismatch')
        final = wealth - q * previous * fee
        if abs(final - D(result['metrics']['final_equity_after_exit_fee_usdt'])) > D('1e-40'):
            raise ValueError('Final wealth mismatch')
        if result['status'] == 'COMPLETE':
            if q or sum((D(t['net_before_operating_usdt']) for t in result['trades']), ZERO) - D(result['metrics']['operating_expense_usdt']) != D(result['metrics']['net_profit_usdt']):
                raise ValueError('Closed trade reconciliation mismatch')
        return {'status': 'PASS', 'events_checked': len(result['events']), 'max_error_usdt': str(maximum)}


def passes(result, exits):
    m = result['metrics']
    return (result['status'] == 'COMPLETE' and D(m['net_profit_usdt']) > 0
            and D(m['max_drawdown_pct']) <= 35 and m['signal_exits'] >= exits
            and result['independent_wealth_audit']['status'] == 'PASS')


def select_training(training):
    if set(training) != set(CANDIDATES) or any(set(v) != set(COSTS) for v in training.values()):
        raise ValueError('Incomplete training matrix')
    ranked = []
    for candidate in CANDIDATES:
        pair = training[candidate]
        if all(passes(r, 10) for r in pair.values()) and pair['stress_assumption']['metrics']['annualized_net_return_pct'] is not None:
            stress = pair['stress_assumption']['metrics']
            score = stress['annualized_net_return_pct'] / max(float(stress['max_drawdown_pct']), 1.)
            ranked.append({'id': candidate, 'score': score})
    ranked.sort(key=lambda r: (-r['score'], r['id']))
    return {'selected': ranked[0]['id'] if ranked else 'cash', 'eligible': ranked,
            'basis': 'Training only, both costs at lag0, nominal funding valuation; frozen before evaluation.'}


def evaluation_gate(results):
    expected = {(c, lag, adverse) for c in COSTS for lag in (0, 1, 2) for adverse in (False, True)}
    keys = [(r['cost'], r['lag_days'], r['adverse_funding_5bps']) for r in results]
    if set(keys) != expected or len(keys) != len(expected):
        raise ValueError('Incomplete/duplicate evaluation scenarios')
    failures = []
    for r in results:
        reasons = []; m = r['metrics']
        if r['status'] != 'COMPLETE': reasons.append(r['status'])
        if D(m['net_profit_usdt']) <= 0: reasons.append('NONPOSITIVE_NET')
        if D(m['max_drawdown_pct']) > 35: reasons.append('DRAWDOWN_OVER_35PCT')
        if m['signal_exits'] < 20: reasons.append('FEWER_THAN_20_SIGNAL_EXITS')
        if r['independent_wealth_audit']['status'] != 'PASS': reasons.append('WEALTH_AUDIT_FAILED')
        if reasons: failures.append({'cost': r['cost'], 'lag': r['lag_days'],
                                     'adverse_funding': r['adverse_funding_5bps'], 'reasons': reasons})
    return {'historical_screen_pass': not failures, 'failed_scenarios': failures,
            'classification': 'Exploratory, reused-history family selection; not proof of future profit.'}

