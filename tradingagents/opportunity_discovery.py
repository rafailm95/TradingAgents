"""Descriptive discovery ranking; no strategy tuning or promotion authority."""
import math


def drawdown(points, initial):
    peak = float(initial)
    max_pct = amount_at_max_pct = max_amount = 0.0
    for equity in points:
        if not math.isfinite(equity) or equity <= 0:
            raise ValueError('Positive finite equity required')
        peak = max(peak, equity)
        amount = peak - equity
        pct = amount / peak * 100
        max_amount = max(max_amount, amount)
        if pct > max_pct:
            max_pct, amount_at_max_pct = pct, amount
    return {'max_drawdown_pct': max_pct, 'amount_at_max_pct_usd': amount_at_max_pct,
            'max_cash_drawdown_usd': max_amount}


def curve_diagnostics(result):
    m, curve = result['metrics'], result['curve']
    if len(curve) != m['days'] or not curve:
        raise ValueError('Incomplete daily curve')
    dates = [p['Date'] for p in curve]
    if dates != sorted(set(dates)):
        raise ValueError('Unsorted/duplicate daily curve')
    net = [float(p['equity']) - m['operating_cost_usd'] * (i+1)/len(curve)
           for i, p in enumerate(curve)]
    expected = m['initial_usd'] + m['profit_after_operating_usd']
    if not math.isclose(net[-1], expected, abs_tol=1e-7):
        raise ValueError('Terminal accounting mismatch')
    yearly, start = [], float(m['initial_usd'])
    for i, date in enumerate(dates):
        if i == len(dates)-1 or dates[i+1][:4] != date[:4]:
            yearly.append({'year': int(date[:4]), 'pnl_usd': net[i]-start,
                           'return_pct': (net[i]/start-1)*100,
                           'partial_year': date[5:] != '12-31'})
            start = net[i]
    return {**drawdown(net, m['initial_usd']), 'calendar_segments': yearly}


def pareto_tiers(rows):
    """Strict dominance: higher minimum return, lower maximum drawdown."""
    if any(not math.isfinite(r[k]) for r in rows for k in ('worst_return_pct','worst_drawdown_pct')):
        raise ValueError('Finite Pareto dimensions required')
    remaining = list(rows)
    tier = 1
    while remaining:
        front = []
        for a in remaining:
            dominated = any(
                b['worst_return_pct'] >= a['worst_return_pct'] and
                b['worst_drawdown_pct'] <= a['worst_drawdown_pct'] and
                (b['worst_return_pct'] > a['worst_return_pct'] or
                 b['worst_drawdown_pct'] < a['worst_drawdown_pct'])
                for b in remaining)
            if not dominated:
                front.append(a)
        if not front:
            raise ValueError('Invalid Pareto inputs')
        for a in front:
            a['pareto_tier'] = tier
        front_ids = {id(a) for a in front}
        remaining = [a for a in remaining if id(a) not in front_ids]
        tier += 1
    return rows


def rank_asset(product, matrix, delays, assessment):
    rows = []
    train_rank = {x['id']: i+1 for i,x in enumerate(assessment['selection']['eligible'])}
    for check in assessment['assessments']:
        name = check['id']
        scenarios = []
        for lag in (0,1,2):
            for cost in ('base','stress'):
                r = matrix[f'evaluation__{cost}__{name}'] if lag == 0 else delays[f'lag{lag}__{cost}__{name}']
                m = r['metrics']
                scenarios.append({'lag_days':lag, 'cost':cost,
                    'return_pct':m['return_after_operating_pct'],
                    'pnl_usd':m['profit_after_operating_usd'],
                    'signal_exits':m['signal_exits'], 'closed_trades':m['closed_trades'],
                    **curve_diagnostics(r)})
        worst = min(scenarios, key=lambda s:s['return_pct'])
        rows.append({'product':product, 'id':name, 'family':name.split('__')[0],
            'classification':'POST_HOC_SPOT_DISCOVERY_NOT_PERPETUAL_VALIDATION',
            'historical_robust_pass':check['robust_pass'],
            'failed':check['failed']+check['delay_failed'],
            'original_train_rank':train_rank.get(name),
            'original_train_selected':assessment['selection']['selected']==name,
            'worst_return_pct':worst['return_pct'], 'worst_pnl_usd':worst['pnl_usd'],
            'worst_return_scenario':{'lag_days':worst['lag_days'],'cost':worst['cost']},
            'worst_drawdown_pct':max(s['max_drawdown_pct'] for s in scenarios),
            'min_signal_exits':min(s['signal_exits'] for s in scenarios),
            'scenarios':scenarios})
    if len(rows)!=42 or len({r['id'] for r in rows})!=42:
        raise ValueError('All42 distinct candidates required')
    pareto_tiers(rows)
    rows.sort(key=lambda r:(not r['historical_robust_pass'],r['pareto_tier'],
        -r['worst_return_pct']/max(r['worst_drawdown_pct'],1),r['id']))
    for i,r in enumerate(rows):r['review_rank']=i+1
    shortlist, families = [], set()
    for r in rows:
        if r['worst_return_pct']>0 and r['family'] not in families:
            shortlist.append(r['id']);families.add(r['family'])
            if len(shortlist)==3:break
    return {'product':product,'rows':rows,'shortlist_distinct_families':shortlist,
            'shortlist_status':'EXPLORATORY_ONLY','new_simulations':0}
