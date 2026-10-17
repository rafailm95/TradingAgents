"""018: descriptive contribution diagnostics, never a strategy or trade selector.

Removal diagnostics retain other recorded trade sizes and the full operating
expense. They are static attribution arithmetic, not counterfactual replays.
"""
from datetime import datetime, timezone
from decimal import Decimal, localcontext

ZERO = Decimal(0)


def number(value):
    if isinstance(value, (bool, float)):
        raise ValueError('Use finite decimal strings or integers')
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError('Nonfinite value')
    return result


def require(condition, message):
    if not condition:
        raise ValueError(message)


def amount(value, initial):
    return {'usdt': str(value), 'pct_initial': str(value / initial * 100)}


def contribution_diagnostics(values, expense, initial):
    """Exact fixed-size attribution. A losing trade is never removed as a winner."""
    with localcontext() as ctx:
        ctx.prec = 128
        values = [number(v) for v in values]
        expense, initial = number(expense), number(initial)
        require(expense >= 0 and initial > 0, 'Invalid expense/capital')
        winners = sorted((v for v in values if v > 0), reverse=True)
        gross_profit = sum(winners, ZERO)
        gross_loss = -sum((v for v in values if v < 0), ZERO)
        total = sum(values, ZERO) - expense
        concentration = sum((v * v for v in winners), ZERO)
        return {
            'net': amount(total, initial), 'trade_count': len(values),
            'winning_trades': len(winners), 'losing_trades': sum(v < 0 for v in values),
            'gross_positive_contributions_usdt': str(gross_profit),
            'gross_negative_contributions_usdt': str(gross_loss),
            'largest_positive_contribution_usdt': str(winners[0] if winners else ZERO),
            'top_two_positive_contributions_usdt': str(sum(winners[:2], ZERO)),
            'largest_share_of_gross_positive_pct': str(winners[0] / gross_profit * 100) if winners else None,
            'inverse_winner_concentration': str(gross_profit * gross_profit / concentration) if concentration else None,
            'profit_factor_before_operating': str(gross_profit / gross_loss) if gross_loss else None,
            'without_best_positive_trade': amount(total - sum(winners[:1], ZERO), initial),
            'without_two_best_positive_trades': amount(total - sum(winners[:2], ZERO), initial),
            'single_trade_removals': [amount(total - v, initial) for v in values],
            'interpretation': 'Static recorded-size contributions only; unchanged other trades and full operating expense. Not a replay, causal missing-fill model, independent sample count or significance test.',
        }


def audit_trade_components(result):
    """Reconstruct every completed trade from fill pairs and funding intervals."""
    with localcontext() as ctx:
        ctx.prec = 128
        fills, funds, trades = result['fills'], result['funding_events'], result['trades']
        require(result['status'] == 'COMPLETE', 'Incomplete result')
        require(number(result['metrics']['open_quantity']) == 0, 'Open position')
        require(len(fills) == 2 * len(trades), 'Fill/trade count mismatch')
        fund_times = [f['timestamp_ms'] for f in funds]
        require(fund_times == sorted(set(fund_times)), 'Duplicate/unordered funding')
        rows, used = [], set()
        previous_exit = result['start_ms'] - 1
        for index, trade in enumerate(trades):
            entry, exit = fills[index * 2:index * 2 + 2]
            require(entry['side'] == 'buy' and exit['side'] == 'sell', 'Wrong fill sides')
            a, b = entry['timestamp_ms'], exit['timestamp_ms']
            require(previous_exit < a < b < result['end_exclusive_ms'], 'Overlapping/out-of-window trades')
            require(a >= result['start_ms'], 'Entry before evaluation')
            require((a, b) == (trade['entry_ms'], trade['exit_ms']), 'Trade timestamps mismatch')
            q = number(entry['quantity'])
            require(q > 0 and q == number(exit['quantity']), 'Quantity mismatch')
            require(all(f['timestamp_ms'] not in (a, b) for f in funds), 'Ambiguous same-time funding/fill')
            owned = [(i, f) for i, f in enumerate(funds) if a < f['timestamp_ms'] < b]
            require(all(number(f['quantity_before']) == q for _, f in owned), 'Funding position mismatch')
            price_pnl = q * (number(exit['price']) - number(entry['price']))
            fees = number(entry['fee_usdt']) + number(exit['fee_usdt'])
            require(fees >= 0, 'Negative fees')
            funding = sum((number(f['cashflow_usdt']) for _, f in owned), ZERO)
            net = price_pnl - fees + funding
            for key, value in [('price_pnl_usdt', price_pnl), ('fees_usdt', fees),
                               ('funding_usdt', funding), ('net_before_operating_usdt', net)]:
                require(value == number(trade[key]), 'Trade component mismatch: ' + key)
            require(trade['reason'] == exit['reason'], 'Exit reason mismatch')
            used.update(i for i, _ in owned)
            rows.append({'index': index, 'entry_ms': a, 'exit_ms': b,
                         'reason': trade['reason'], 'net_before_operating_usdt': str(net),
                         'price_pnl_usdt': str(price_pnl), 'fees_usdt': str(fees),
                         'funding_usdt': str(funding), 'funding_events': len(owned)})
            previous_exit = b
        require(all(number(f['quantity_before']) == 0 and number(f['cashflow_usdt']) == 0
                    for i, f in enumerate(funds) if i not in used), 'Unassigned nonzero funding')
        metrics = result['metrics']
        for key, field in [('price_pnl_usdt', 'realized_price_pnl_usdt'),
                           ('fees_usdt', 'fees_usdt'), ('funding_usdt', 'funding_usdt')]:
            require(sum((number(t[key]) for t in rows), ZERO) == number(metrics[field]), 'Aggregate mismatch: ' + field)
        net = sum((number(t['net_before_operating_usdt']) for t in rows), ZERO) - number(metrics['operating_expense_usdt'])
        require(net == number(metrics['net_profit_usdt']), 'Net reconciliation failed')
        require(len(rows) == metrics['closed_trades'], 'Trade count mismatch')
        require(sum(t['reason'] in ('signal_exit', 'time_exit') for t in rows) == metrics['signal_exits'], 'Signal exit count mismatch')
        return rows


def sampled_drawdown(values):
    with localcontext() as ctx:
        ctx.prec = 128
        values = [number(v) for v in values]
        require(bool(values) and all(v > 0 for v in values), 'Invalid equity curve')
        peak = values[0]
        max_pct = cash_at_pct = max_cash = ZERO
        for value in values:
            peak = max(peak, value)
            cash = peak - value
            pct = cash / peak * 100
            max_cash = max(max_cash, cash)
            if pct > max_pct:
                max_pct, cash_at_pct = pct, cash
        return {'pct': str(max_pct), 'cash_at_max_pct_usdt': str(cash_at_pct),
                'max_cash_drawdown_usdt': str(max_cash)}


def month_boundary(year, month):
    return int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp() * 1000)


def calendar_diagnostics(curve, initial, start_ms, end_ms):
    """Use completed-hour samples at boundaries, before next-hour funding.

    Calendar attribution carries existing positions across boundaries. It does
    not reselect strategies, reset accounts or perform walk-forward training.
    """
    with localcontext() as ctx:
        ctx.prec = 128
        initial = number(initial)
        require(bool(curve), 'Missing curve')
        times = [r['timestamp_ms'] for r in curve]
        require(times == sorted(times), 'Nonchronological curve')
        require(times[0] == start_ms and times[-1] == end_ms, 'Wrong curve bounds')
        closes = {}
        for i, row in enumerate(curve):
            if row['phase'] == 'hour_close':
                require(row['timestamp_ms'] not in closes, 'Duplicate hour close')
                closes[row['timestamp_ms']] = (i, number(row['equity_usdt']))
        start = datetime.fromtimestamp(start_ms / 1000, timezone.utc)
        require(start.day == 1 and start.hour == start.minute == start.second == start.microsecond == 0, 'Start must be a month boundary')
        require(number(curve[0]['equity_usdt']) == initial, 'Initial equity mismatch')
        y, m, previous, previous_index = start.year, start.month, initial, 0
        months, year_start, year_index, years = [], initial, 0, []
        while True:
            ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
            boundary = month_boundary(ny, nm)
            require(boundary <= end_ms and boundary in closes, 'Missing calendar boundary')
            index, equity = closes[boundary]
            delta = equity - previous
            months.append({'month': f'{y}-{m:02d}', 'start_equity_usdt': str(previous),
                           'end_equity_usdt': str(equity), 'pnl_usdt': str(delta),
                           'return_pct_start_equity': str(delta / previous * 100)})
            if m == 12 or boundary == end_ms:
                change = equity - year_start
                years.append({'year': y, 'start_equity_usdt': str(year_start),
                              'end_equity_usdt': str(equity), 'pnl_usdt': str(change),
                              'return_pct_start_equity': str(change / year_start * 100),
                              'sampled_drawdown': sampled_drawdown([r['equity_usdt'] for r in curve[year_index:index + 1]])})
                year_start, year_index = equity, index
            previous, previous_index = equity, index
            if boundary == end_ms:
                break
            y, m = ny, nm
        total = previous - initial
        require(sum((number(r['pnl_usdt']) for r in months), ZERO) == total, 'Monthly reconciliation')
        require(sum((number(r['pnl_usdt']) for r in years), ZERO) == total, 'Yearly reconciliation')
        best_month = max(ZERO, max(number(r['pnl_usdt']) for r in months))
        return {'months': months, 'years': years,
                'positive_months': sum(number(r['pnl_usdt']) > 0 for r in months),
                'positive_years': sum(number(r['pnl_usdt']) > 0 for r in years),
                'without_best_positive_month': amount(total - best_month, initial),
                'interpretation': 'Mark-to-market attribution of one existing path, not walk-forward validation or a counterfactual replay.'}
