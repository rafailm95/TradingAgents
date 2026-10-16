"""Strict, stdlib-only Bybit hourly history validation and deterministic request plan.
No network or order capabilities. Amounts remain decimal strings in source rows.
"""
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from urllib.parse import urlencode

try:
    from .bybit_depth import instrument, response
except ImportError:  # portable stdlib-only entry point
    from bybit_depth import instrument, response

HOUR = 3_600_000
DAY = 24 * HOUR
HOST = 'https://api.bybit.com'
ENDPOINTS = {'instrument': '/v5/market/instruments-info', 'trade': '/v5/market/kline',
             'mark': '/v5/market/mark-price-kline', 'funding': '/v5/market/funding/history'}
SYMBOLS = ('BTCUSDT', 'ETHUSDT', 'LTCUSDT')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def utc_ms(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None or dt.utcoffset().total_seconds() != 0:
        raise ValueError('UTC timestamp required')
    return int(dt.timestamp() * 1000)


def integer(value):
    if isinstance(value, bool) or not str(value).isdigit():
        raise ValueError('Non-negative integer required')
    return int(value)


def number(value, *, positive=False):
    if isinstance(value, bool):
        raise ValueError('Boolean amount')
    try:
        x = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError('Invalid decimal amount') from None
    if not x.is_finite() or (positive and x <= 0):
        raise ValueError('Non-finite or non-positive amount')
    return x


def validate_protocol(p):
    if (p['schema'] != 'bybit_history_013_v1' or p['host'] != HOST or
            p['category'] != 'linear' or tuple(p['symbols']) != SYMBOLS or p['interval'] != '60'):
        raise ValueError('Unsupported venue, symbols, or interval')
    start, end = utc_ms(p['start_utc']), utc_ms(p['end_exclusive_utc'])
    if start % DAY or end % DAY or not 0 < end - start <= 10 * 366 * DAY:
        raise ValueError('Invalid UTC daily coverage bounds')
    if not 1 <= p['candle_page_limit'] <= 1000 or not 1 <= p['funding_page_limit'] <= 200:
        raise ValueError('Invalid page limit')
    if p['expected_funding_interval_hours'] != 8:
        raise ValueError('Funding schedule amendment requires a new protocol')
    return start, end


def request_url(kind, symbol, params):
    if kind not in ENDPOINTS or symbol not in SYMBOLS:
        raise ValueError('Only registered public market endpoints/symbols allowed')
    expected = {'instrument': set(), 'trade': {'interval', 'start', 'end', 'limit'},
                'mark': {'interval', 'start', 'end', 'limit'}, 'funding': {'endTime', 'limit'}}[kind]
    if set(params) != expected:
        raise ValueError('Unexpected request parameters')
    return HOST + ENDPOINTS[kind] + '?' + urlencode({'category': 'linear', 'symbol': symbol, **params})


def candle_windows(start, end, limit):
    """Fixed non-overlapping windows; a truncated/empty response cannot move the boundary."""
    stop = end
    while stop > start:
        first = max(start, stop - limit * HOUR)
        yield first, stop
        stop = first


def candle_page(payload, received, symbol, kind, start, end, limit):
    r = response(payload, received)
    if r.get('category') != 'linear' or r.get('symbol') != symbol:
        raise ValueError('Wrong candle identity')
    rows = r['list']
    if not isinstance(rows, list) or len(rows) > limit:
        raise ValueError('Invalid candle page length')
    times = []
    for row in rows:
        if not isinstance(row, list) or len(row) != (7 if kind == 'trade' else 5):
            raise ValueError('Malformed candle row')
        ts = integer(row[0]); times.append(ts)
        if ts % HOUR or not start <= ts < end:
            raise ValueError('Off-grid or out-of-request candle')
        if ts + HOUR > min(integer(payload['time']), received):
            raise ValueError('Unclosed candle')
        o, h, l, c = [number(x, positive=True) for x in row[1:5]]
        if not l <= min(o, c) <= max(o, c) <= h:
            raise ValueError('Inconsistent OHLC')
        if kind == 'trade' and any(number(x) < 0 for x in row[5:]):
            raise ValueError('Negative volume/turnover')
    if times != sorted(set(times), reverse=True):
        raise ValueError('Duplicate or unsorted candles')
    expected = set(range(start, end, HOUR))
    return rows, sorted(expected - set(times))


def funding_page(payload, received, symbol, end_inclusive, limit):
    r = response(payload, received)
    if r.get('category') != 'linear' or not isinstance(r['list'], list) or len(r['list']) > limit:
        raise ValueError('Wrong funding category/page')
    rows = r['list']; times = []
    for row in rows:
        if row.get('symbol') != symbol:
            raise ValueError('Wrong funding symbol')
        ts = integer(row['fundingRateTimestamp']); times.append(ts)
        if ts > min(end_inclusive, integer(payload['time']), received):
            raise ValueError('Out-of-request or future funding')
        number(row['fundingRate'])
    if times != sorted(set(times), reverse=True):
        raise ValueError('Duplicate or unsorted funding')
    return rows


def assemble(protocol, get):
    """get(kind,symbol,**params) -> (payload, original_received_ms).
    Reused by local capture and offline audit; exact page coverage is never inferred
    from an HTTP success or from a count alone. No data interpolation.
    """
    start, end = validate_protocol(protocol)
    summary = {'schema': 'bybit_history_013_audit_v1', 'status': 'COMPLETE',
               'start_ms': start, 'end_exclusive_ms': end,
               'expected_hours_per_series': (end - start) // HOUR,
               'symbols': {}, 'orders': 0, 'private_api_calls': 0,
               'limitation': 'Hourly candles do not establish historical order-book fills, tick order, or an exchange liquidation model.'}
    datasets = {}
    for symbol in protocol['symbols']:
        payload, received = get('instrument', symbol)
        product = instrument(payload, symbol, received)
        info = {'launch_ms': integer(product['launchTime']), 'issues': [], 'series': {}}
        if info['launch_ms'] > start:
            info['issues'].append('Instrument launched after the requested start')
        if integer(product['fundingInterval']) != 480:
            info['issues'].append('Current funding interval differs from the assumed eight-hour validation schedule')
        data = {'instrument': product}
        for kind in ('trade', 'mark'):
            merged = []; gaps = []
            for lo, hi in candle_windows(start, end, protocol['candle_page_limit']):
                payload, received = get(kind, symbol, interval='60', start=lo,
                                        end=hi - 1, limit=protocol['candle_page_limit'])
                rows, missing = candle_page(payload, received, symbol, kind, lo, hi, protocol['candle_page_limit'])
                merged.extend(rows); gaps.extend(missing)
            merged.sort(key=lambda x: integer(x[0]))
            data[kind] = merged
            info['series'][kind] = {'rows': len(merged), 'missing_hours': len(gaps),
                                    'first_missing_ms': sorted(gaps)[:20],
                                    'first_ms': integer(merged[0][0]) if merged else None,
                                    'last_ms': integer(merged[-1][0]) if merged else None}
            if gaps:
                info['issues'].append(f'{kind}: {len(gaps)} missing hourly candles')
        all_funding = []; boundary = end - 1; anchor = None
        for _ in range(protocol['max_funding_pages_per_symbol']):
            payload, received = get('funding', symbol, endTime=boundary, limit=protocol['funding_page_limit'])
            rows = funding_page(payload, received, symbol, boundary, protocol['funding_page_limit'])
            if not rows:
                break
            all_funding.extend(rows)
            if integer(rows[-1]['fundingRateTimestamp']) < start:
                anchor = max((x for x in rows if integer(x['fundingRateTimestamp']) < start),
                             key=lambda x: integer(x['fundingRateTimestamp']))
                break
            boundary = integer(rows[-1]['fundingRateTimestamp']) - 1
        else:
            raise ValueError('Funding page bound exhausted')
        funding = sorted((x for x in all_funding if start <= integer(x['fundingRateTimestamp']) < end),
                         key=lambda x: integer(x['fundingRateTimestamp']))
        times = [integer(x['fundingRateTimestamp']) for x in funding]
        if len(times) != len(set(times)):
            raise ValueError('Funding pagination overlap')
        joined = ([integer(anchor['fundingRateTimestamp'])] if anchor else []) + times
        cadence = Counter(b - a for a, b in zip(joined, joined[1:]))
        off_grid = [t for t in joined if t % (8 * HOUR)]
        expected = set(range(start, end, 8 * HOUR)); missing = sorted(expected - set(times))
        if anchor is None or not times or (joined and joined[0] != start - 8 * HOUR):
            info['issues'].append('Missing exact pre-start funding anchor or funding history')
        if off_grid or missing or any(delta != 8 * HOUR for delta in cadence):
            info['issues'].append('Funding coverage/schedule differs from assumed uninterrupted eight-hour grid; review required')
        data['funding'] = funding; data['funding_anchor'] = anchor
        info['funding'] = {'events': len(times), 'first_ms': times[0] if times else None,
                           'last_ms': times[-1] if times else None,
                           'anchor_ms': integer(anchor['fundingRateTimestamp']) if anchor else None,
                           'missing_expected_events': len(missing), 'first_missing_ms': missing[:20],
                           'off_grid_events': len(off_grid),
                           'interval_counts_ms': {str(k): v for k, v in sorted(cadence.items())}}
        if info['issues']:
            summary['status'] = 'DATA_GAPS_OR_SCHEDULE_REVIEW'
        summary['symbols'][symbol] = info; datasets[symbol] = data
    return summary, datasets


def daily_trade(rows):
    """Aggregate only complete UTC days, preserving quote turnover and base volume."""
    if not rows:
        raise ValueError('Empty hourly series')
    times = [integer(r[0]) for r in rows]
    if times[0] % DAY or len(rows) % 24 or times != list(range(times[0], times[0] + len(rows) * HOUR, HOUR)):
        raise ValueError('Complete consecutive UTC days required')
    result = []
    for index in range(0, len(rows), 24):
        day = rows[index:index + 24]
        result.append([day[0][0], day[0][1], str(max(number(r[2]) for r in day)),
                       str(min(number(r[3]) for r in day)), day[-1][4],
                       str(sum((number(r[5]) for r in day), Decimal(0))),
                       str(sum((number(r[6]) for r in day), Decimal(0)))])
    return result
