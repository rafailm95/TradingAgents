"""One-session public Bybit research collection. Standard library, GET only.
Frozen013validation is reused;014adds supplements, bounded transient retries,
paired multiday depth and explicit unknowns. No exchange execution capability.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

try:
    from .bybit_history import HOUR, DAY, number, integer, sha, utc_ms, assemble, funding_page, validate_protocol
    from .bybit_depth import response, instrument, parse_book, analyze
except ImportError:
    from bybit_history import HOUR, DAY, number, integer, sha, utc_ms, assemble, funding_page, validate_protocol
    from bybit_depth import response, instrument, parse_book, analyze

HOST = 'https://api.bybit.com'
SYMBOLS = ('BTCUSDT', 'ETHUSDT', 'LTCUSDT')
PATHS = {'instrument': '/v5/market/instruments-info', 'trade': '/v5/market/kline',
         'mark': '/v5/market/mark-price-kline', 'index': '/v5/market/index-price-kline',
         'premium': '/v5/market/premium-index-price-kline', 'funding': '/v5/market/funding/history',
         'oi': '/v5/market/open-interest', 'ratio': '/v5/market/account-ratio',
         'risk': '/v5/market/risk-limit', 'ticker': '/v5/market/tickers',
         'book': '/v5/market/orderbook', 'trades': '/v5/market/recent-trade'}
ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = ('tradingagents/bybit_complete.py', 'tradingagents/bybit_history.py', 'tradingagents/bybit_depth.py',
                'scripts/collect_bybit_complete.py', 'scripts/collect_bybit_history.py')


class StopCollection(ValueError): pass
class DataUnavailable(ValueError): pass
class Retryable(OSError): pass


def write(path, data):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temp.replace(path)


def file_sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def sources():
    return {name: file_sha(ROOT / name) for name in SOURCE_FILES}


def url_for(kind, symbol, params):
    if kind not in PATHS or symbol not in SYMBOLS:
        raise StopCollection('Unregistered endpoint or symbol')
    fields = {'instrument': set(), 'ticker': set(), 'book': {'limit'}, 'trades': {'limit'},
              'funding': {'endTime', 'limit'}, 'oi': {'intervalTime', 'startTime', 'endTime', 'limit'},
              'ratio': {'period', 'startTime', 'endTime', 'limit'}, 'risk': set()}
    expected = fields.get(kind, {'interval', 'start', 'end', 'limit'})
    required = set(params) - {'cursor'} if kind == 'risk' else set(params)
    if required != expected or ('cursor' in params and kind != 'risk'):
        raise StopCollection('Unexpected public query fields')
    return HOST + PATHS[kind] + '?' + urllib.parse.urlencode({'category': 'linear', 'symbol': symbol, **params})


def verify_plan(p, core):
    if (p['schema'] != 'bybit_complete_014_v1' or p['host'] != HOST or tuple(p['symbols']) != SYMBOLS
            or p['category'] != 'linear'):
        raise StopCollection('Unsupported collection plan')
    validate_protocol(core)
    for key in ('live_rounds', 'live_interval_seconds', 'max_requests', 'max_response_bytes', 'max_evidence_bytes'):
        if type(p[key]) is not int or p[key] <= 0:
            raise StopCollection('Invalid collection bound')
    if p['transient_attempts'] != 3 or len(p['retry_delays_seconds']) != 2:
        raise StopCollection('Retry policy changed')


class Clock:
    def now(self): return int(time.time() * 1000)
    def mono(self): return time.monotonic()
    def sleep(self, seconds):
        until = self.mono() + seconds
        while self.mono() < until:
            time.sleep(min(30, until - self.mono()))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise StopCollection('Redirect refused; no alternate host')


def network_get(url, timeout, limit):
    req = urllib.request.Request(url, headers={'Accept': 'application/json',
        'User-Agent': 'TradingAgents-Complete-Public-Research/014'}, method='GET')
    try:
        stream = urllib.request.build_opener(NoRedirect()).open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        stream = e
    with stream:
        return stream.status, stream.read(limit + 1)


class Journal:
    def __init__(self, out, plan_raw, core_raw, source_hashes, *, clock=None, transport=None, offline=False):
        self.out = Path(out); self.plan = json.loads(plan_raw); self.core = json.loads(core_raw)
        verify_plan(self.plan, self.core)
        self.clock = clock or Clock(); self.transport = transport or network_get; self.offline = offline
        self.records = []; self.cache = {}; self.failed = {}; self.last_request = None; self.used = set()
        expected = {'schema': 'bybit_complete_014_session_v1', 'plan_sha256': sha(plan_raw),
                    'core_protocol_sha256': sha(core_raw), 'source_hashes': source_hashes}
        if (self.out / 'session.json').exists():
            self.session = json.loads((self.out / 'session.json').read_bytes())
            if any(self.session.get(k) != v for k, v in expected.items()):
                raise StopCollection('Source/protocol identity changed; existing evidence left intact')
            if (self.out / 'plan.json').read_bytes() != plan_raw or (self.out / 'core_protocol.json').read_bytes() != core_raw:
                raise StopCollection('Stored protocol bytes changed')
        else:
            if offline or any(self.out.iterdir()): raise StopCollection('Missing session or nonempty new folder')
            self.session = {**expected, 'started_ms': self.clock.now()}
            (self.out / 'plan.json').write_bytes(plan_raw); (self.out / 'core_protocol.json').write_bytes(core_raw)
            write(self.out / 'session.json', self.session)
        for path in sorted(self.out.glob('request_*.json')):
            rec = json.loads(path.read_bytes())
            if path.name != f'request_{len(self.records):06d}.json' or rec['id'] != len(self.records):
                raise StopCollection('Nonconsecutive request journal')
            if rec['method'] != 'GET' or rec['url'] != url_for(rec['kind'], rec['symbol'], rec['params']):
                raise StopCollection('Recorded request identity mismatch')
            if rec['key'] != rec['scope'] + '|' + rec['url']:
                raise StopCollection('Recorded cache identity mismatch')
            if rec.get('raw_file'):
                if rec['raw_file'] != f'response_{rec["id"]:06d}.bin' or file_sha(self.out / rec['raw_file']) != rec['sha256']:
                    raise StopCollection('Response hash mismatch')
            if rec.get('accepted'):
                if rec.get('http_status') != 200 or not rec.get('raw_file'):
                    raise StopCollection('Invalid accepted response')
                if rec['key'] in self.cache: raise StopCollection('Duplicate accepted request key')
                self.cache[rec['key']] = rec
            self.records.append(rec)
        self.bytes_used = sum(p.stat().st_size for p in self.out.iterdir() if p.is_file())

    def read(self, rec):
        payload = json.loads((self.out / rec['raw_file']).read_bytes())
        response(payload, rec['received_ms'])
        return payload, rec['received_ms']

    def get(self, kind, symbol, *, scope='history', **params):
        url = url_for(kind, symbol, params)
        key = scope + '|' + url
        self.used.add(key)
        if key in self.cache: return self.read(self.cache[key])
        if key in self.failed: raise DataUnavailable(self.failed[key])
        if self.offline: raise DataUnavailable('Missing successful page: ' + key)
        for attempt in range(self.plan['transient_attempts']):
            if len(self.records) >= self.plan['max_requests'] or self.bytes_used >= self.plan['max_evidence_bytes']:
                raise StopCollection('Request/storage bound reached')
            if self.clock.now() - self.session['started_ms'] > self.plan['max_wall_days'] * DAY:
                raise StopCollection('Seven-day collection wall-time bound reached')
            if self.last_request is not None:
                self.clock.sleep(max(0, self.plan['request_spacing_seconds'] - (self.clock.mono() - self.last_request)))
            i = len(self.records)
            rec = {'id': i, 'method': 'GET', 'kind': kind, 'symbol': symbol, 'params': params,
                   'scope': scope, 'url': url, 'key': key, 'request_ms': self.clock.now(), 'status': 'PENDING'}
            self.records.append(rec); write(self.out / f'request_{i:06d}.json', rec)
            started = self.clock.mono()
            retry = False
            try:
                code, raw = self.transport(url, self.plan['timeout_seconds'], self.plan['max_response_bytes'])
                rec.update(http_status=code, received_ms=self.clock.now())
                if len(raw) > self.plan['max_response_bytes']: raise StopCollection('Response too large')
                if self.bytes_used + len(raw) > self.plan['max_evidence_bytes']: raise StopCollection('Storage bound reached')
                name = f'response_{i:06d}.bin'; (self.out / name).write_bytes(raw)
                self.bytes_used += len(raw); rec.update(raw_file=name, sha256=sha(raw))
                if code in (401, 403): raise StopCollection(f'HTTP{code}; access block, no retry')
                if code == 429 or 500 <= code <= 599: raise Retryable(f'Transient HTTP{code}')
                if code != 200: raise DataUnavailable(f'HTTP{code}')
                try: payload = json.loads(raw)
                except (ValueError, UnicodeError): raise StopCollection('Non-JSON response; no retry') from None
                if not isinstance(payload, dict): raise StopCollection('Invalid response envelope')
                if payload.get('retCode') == 10006: raise Retryable('API rate limit10006')
                if type(payload.get('retCode')) is not int or payload['retCode'] != 0:
                    raise DataUnavailable('Bybit API rejected query: ' + str(payload.get('retCode')))
                try: response(payload, rec['received_ms'])
                except (KeyError, ValueError, TypeError): raise StopCollection('Response clock/envelope invalid') from None
                rec.update(accepted=True, status='ACCEPTED')
                self.cache[key] = rec
                return payload, rec['received_ms']
            except StopCollection as e:
                rec.update(status='STOPPED', error=str(e)); raise
            except (Retryable, TimeoutError, ConnectionError, urllib.error.URLError, OSError) as e:
                rec.update(status='TRANSIENT_FAILURE', error=type(e).__name__ + ': ' + str(e)); retry = True
                if attempt + 1 == self.plan['transient_attempts']:
                    self.failed[key] = 'Transient retries exhausted'
                    raise DataUnavailable(self.failed[key]) from e
            except (Exception, KeyboardInterrupt) as e:
                rec.update(status='FAILED', error=type(e).__name__ + ': ' + str(e))
                if isinstance(e, DataUnavailable): self.failed[key] = str(e)
                raise
            finally:
                self.last_request = self.clock.mono()
                rec['elapsed_seconds'] = self.last_request - started
                write(self.out / f'request_{i:06d}.json', rec)
            if retry: self.clock.sleep(self.plan['retry_delays_seconds'][attempt])
        raise AssertionError('Unreachable')


def windows(start, end, step, limit):
    stop = end
    while stop > start:
        lo = max(start, stop - step * limit)
        yield lo, stop
        stop = lo


def candle_check(payload, received, symbol, kind, lo, hi, step, limit):
    r = response(payload, received)
    if r.get('category') != 'linear' or r.get('symbol') != symbol: raise ValueError('Candle identity mismatch')
    rows = r['list']; stamps = []
    if not isinstance(rows, list) or len(rows) > limit: raise ValueError('Invalid page length')
    for row in rows:
        if not isinstance(row, list) or len(row) != (7 if kind == 'trade' else 5): raise ValueError('Malformed candle')
        t = integer(row[0]); stamps.append(t)
        if t % step or not lo <= t < hi or t + step > min(received, integer(payload['time'])):
            raise ValueError('Off-grid/out-of-range/unclosed candle')
        o, h, l, c = [number(v, positive=kind != 'premium') for v in row[1:5]]
        if not l <= min(o, c) <= max(o, c) <= h: raise ValueError('Inconsistent OHLC')
        if kind == 'trade' and any(number(v) < 0 for v in row[5:]): raise ValueError('Negative volume')
    if stamps != sorted(set(stamps), reverse=True): raise ValueError('Duplicate/unsorted candle')
    missing = sorted(set(range(lo, hi, step)) - set(stamps))
    return len(rows), missing


def series(journal, kind, symbol, start, end, minutes):
    count = 0; gaps = []; step = minutes * 60_000
    for lo, hi in windows(start, end, step, 1000):
        payload, received = journal.get(kind, symbol, interval=str(minutes), start=lo, end=hi - 1, limit=1000)
        n, missing = candle_check(payload, received, symbol, kind, lo, hi, step, 1000)
        count += n; gaps.extend(missing)
    return {'status': 'COMPLETE' if not gaps else 'GAPS', 'rows': count,
            'expected_rows': (end - start) // step, 'missing': len(gaps), 'first_missing_ms': sorted(gaps)[:20]}


def sampled_series(journal, kind, symbol, start, end):
    step, limit = (HOUR, 200) if kind == 'oi' else (DAY, 500)
    seen = []; missing = []
    for lo, hi in windows(start, end, step, limit):
        params = {'intervalTime': '1h'} if kind == 'oi' else {'period': '1d'}
        payload, received = journal.get(kind, symbol, **params, startTime=lo, endTime=hi - 1, limit=limit)
        r = response(payload, received)
        if kind == 'oi' and (r.get('category') != 'linear' or r.get('symbol') != symbol): raise ValueError('Open-interest identity')
        rows = r['list']; times = []
        if not isinstance(rows, list) or len(rows) > limit: raise ValueError('Sample page length')
        for row in rows:
            if kind == 'ratio' and row.get('symbol') != symbol: raise ValueError('Account-ratio symbol')
            t = integer(row['timestamp']); times.append(t)
            if not lo <= t < hi or t % step or t > min(received, integer(payload['time'])): raise ValueError('Sample timestamp')
            if kind == 'oi':
                if number(row['openInterest']) < 0: raise ValueError('Negative open interest')
                if 'singleOpenInterest' in row and number(row['singleOpenInterest']) < 0: raise ValueError('Negative single-side interest')
            else:
                buy, sell = number(row['buyRatio']), number(row['sellRatio'])
                if not (0 <= buy <= 1 and 0 <= sell <= 1) or abs(buy + sell - 1) > Decimal('.002'):
                    raise ValueError('Invalid account ratios')
        if len(times) != len(set(times)): raise ValueError('Duplicate samples')
        seen.extend(times); missing.extend(sorted(set(range(lo, hi, step)) - set(times)))
        # Windows contain <=limit possible timestamps, so cursors cannot hide another valid point.
    return {'status': 'COMPLETE' if not missing else 'GAPS', 'rows': len(seen),
            'expected_rows': (end - start) // step, 'missing': len(missing), 'first_missing_ms': sorted(missing)[:20]}


def risk_snapshot(journal, symbol, scope):
    cursor = ''; cursors = set(); ids = set(); count = 0
    for _ in range(30):
        params = {'cursor': cursor} if cursor else {}
        payload, received = journal.get('risk', symbol, scope=scope, **params)
        r = response(payload, received)
        if r.get('category') != 'linear' or not isinstance(r['list'], list) or not r['list']: raise ValueError('Empty risk tiers')
        for row in r['list']:
            if row['symbol'] != symbol or integer(row['id']) in ids: raise ValueError('Risk identity/duplicate tier')
            ids.add(integer(row['id']))
            number(row['riskLimitValue'], positive=True); number(row['maxLeverage'], positive=True)
            mm, im = number(row['maintenanceMargin']), number(row['initialMargin'])
            if not 0 <= mm <= im <= 1 or number(row['mmDeduction']) < 0: raise ValueError('Risk margin parameters')
            count += 1
        cursor = r.get('nextPageCursor', '')
        if not cursor: return {'status': 'COMPLETE', 'tiers': count, 'historical_rules': False}
        if cursor in cursors: raise ValueError('Risk cursor loop')
        cursors.add(cursor)
    raise ValueError('Risk cursor bound')


def component(fn):
    try: return fn()
    except StopCollection: raise
    except (ValueError, KeyError, TypeError, DataUnavailable) as e:
        return {'status': 'UNAVAILABLE_OR_INVALID', 'error': type(e).__name__ + ': ' + str(e)}



def preload_core(journal):
    """Fetch independent core components even if one asset/endpoint is unavailable.
    The original013whole-dataset validator still decides complete replay coverage.
    """
    p = journal.core
    start, end = utc_ms(p['start_utc']), utc_ms(p['end_exclusive_utc'])
    result = {}
    def metadata(symbol):
        payload, received = journal.get('instrument', symbol)
        instrument(payload, symbol, received)
        return {'status': 'COMPLETE'}
    def funding(symbol):
        boundary = end - 1; count = 0
        for _ in range(p['max_funding_pages_per_symbol']):
            payload, received = journal.get('funding', symbol, endTime=boundary, limit=p['funding_page_limit'])
            rows = funding_page(payload, received, symbol, boundary, p['funding_page_limit'])
            count += len(rows)
            if not rows: return {'status': 'NO_PRESTART_ANCHOR', 'rows_received': count}
            if integer(rows[-1]['fundingRateTimestamp']) < start:
                return {'status': 'FETCHED_TO_ANCHOR', 'rows_received': count}
            boundary = integer(rows[-1]['fundingRateTimestamp']) - 1
        raise ValueError('Funding page bound exhausted')
    for symbol in SYMBOLS:
        result[symbol] = {'instrument': component(lambda s=symbol: metadata(s)),
                          'trade': component(lambda s=symbol: series(journal, 'trade', s, start, end, 60)),
                          'mark': component(lambda s=symbol: series(journal, 'mark', s, start, end, 60)),
                          'funding': component(lambda s=symbol: funding(s))}
    return result

def historical(journal):
    def core():
        validation, _ = assemble(journal.core, journal.get)
        return validation
    availability = preload_core(journal)
    result = {'core': component(core), 'core_component_availability': availability, 'supplements': {}}
    start, end = utc_ms(journal.core['start_utc']), utc_ms(journal.core['end_exclusive_utc'])
    p = journal.plan
    for symbol in SYMBOLS:
        for kind in p['hourly_supplements']:
            result['supplements'][symbol + '_' + kind] = component(lambda k=kind, s=symbol: series(journal, k, s, start, end, 60))
        for kind in p['fine_series']:
            lo = max(start, end - p['fine_history_days'] * DAY)
            result['supplements'][symbol + '_' + kind + '_5min'] = component(lambda k=kind, s=symbol: series(journal, k, s, lo, end, p['fine_interval_minutes']))
        lo = max(start, end - p['open_interest_days'] * DAY)
        result['supplements'][symbol + '_oi'] = component(lambda s=symbol: sampled_series(journal, 'oi', s, lo, end))
        result['supplements'][symbol + '_ratio'] = component(lambda s=symbol: sampled_series(journal, 'ratio', s, start, end))
        result['supplements'][symbol + '_risk'] = component(lambda s=symbol: risk_snapshot(journal, s, 'initial-risk'))
        print('Historical components checked: ' + symbol, flush=True)
    return result


def live_asset(journal, symbol, round_id):
    scope = f'live-{round_id:04d}-{symbol}'
    payload, received = journal.get('instrument', symbol, scope=scope)
    product = instrument(payload, symbol, received)
    tick, tr = journal.get('ticker', symbol, scope=scope)
    r = response(tick, tr)
    if r.get('category') != 'linear' or len(r['list']) != 1 or r['list'][0]['symbol'] != symbol: raise ValueError('Ticker identity')
    ticker = r['list'][0]
    for key in ('markPrice', 'indexPrice', 'lastPrice'): number(ticker[key], positive=True)
    number(ticker['fundingRate'])
    if number(ticker['openInterest']) < 0 or integer(ticker['nextFundingTime']) <= integer(tick['time']): raise ValueError('Ticker funding/interest')
    before, t0 = journal.get('book', symbol, scope=scope + '-before', limit=journal.plan['orderbook_levels'])
    r0, _ = parse_book(before, symbol, t0, product['priceFilter']['tickSize'])
    if not journal.offline:
        journal.clock.sleep(max(0, journal.plan['paired_book_delay_seconds'] - (journal.clock.now() - t0) / 1000))
    after, t1 = journal.get('book', symbol, scope=scope + '-after', limit=journal.plan['orderbook_levels'])
    r1, _ = parse_book(after, symbol, t1, product['priceFilter']['tickSize'])
    if t1 <= t0 or int(r1['ts']) < int(r0['ts']) or int(r1['seq']) < int(r0['seq']): raise ValueError('Book-pair chronology')
    trades, tt = journal.get('trades', symbol, scope=scope, limit=journal.plan['recent_trades_limit'])
    rt = response(trades, tt)
    if rt.get('category') != 'linear' or len(rt['list']) > journal.plan['recent_trades_limit']: raise ValueError('Trade-tail category/count')
    ids = set()
    for trade in rt['list']:
        if trade['symbol'] != symbol or trade['side'] not in ('Buy', 'Sell') or trade['execId'] in ids: raise ValueError('Trade identity/duplicate')
        ids.add(trade['execId']); number(trade['price'], positive=True); number(trade['size'], positive=True)
        if integer(trade['time']) > min(tt, integer(trades['time'])): raise ValueError('Future trade')
    diagnostics = []
    for book, received in ((before, t0), (after, t1)):
        try:
            d = analyze(book, product, received, '5000', '10000', '5.5')
            diagnostics.append({k: d[k] for k in ('source_ts_ms', 'spread_bps', 'same_snapshot_round_trip_loss_usdt', 'loss_pct_capital', 'depth_bands')})
        except ValueError as e:
            diagnostics.append({'scenario_rejected': str(e)})
    return {'status': 'VALID', 'symbol': symbol, 'book_timestamps': [int(r0['ts']), int(r1['ts'])],
            'received_ms': [t0, t1], 'pair_elapsed_ms': t1 - t0, 'book_sequence_changed': r1['seq'] != r0['seq'],
            'trade_tail_rows': len(ids), 'diagnostics': diagnostics, 'actual_fills': 0}


def live_coverage(rounds, target):
    valid = [r for r in rounds if all(v.get('status') == 'VALID' for v in r['assets'].values()) and len(r['assets']) == 3]
    books = [(a['symbol'], t) for r in rounds for a in r['assets'].values() if a.get('status') == 'VALID' for t in a['book_timestamps']]
    stamps = [t for _, t in books]
    gaps = [b['started_ms'] - a['started_ms'] for a, b in zip(rounds, rounds[1:])]
    return {'rounds_recorded': len(rounds), 'rounds_requested': target, 'fully_valid_rounds': len(valid),
            'valid_books': len(books), 'unique_books': len(set(books)),
            'first_book_ms': min(stamps) if stamps else None, 'last_book_ms': max(stamps) if stamps else None,
            'observed_span_hours': (max(stamps) - min(stamps)) / HOUR if stamps else 0,
            'largest_round_gap_seconds': max(gaps, default=0) / 1000,
            'status': 'COLLECTED' if len(rounds) == target and len(valid) == target else 'PARTIAL',
            'continuous_orderbook': False, 'full_trade_tape': False, 'future_profit_evidence': False}


def extension(journal, end):
    start = utc_ms(journal.core['end_exclusive_utc'])
    if end <= start: return {'status': 'NOT_YET_DUE'}
    p = dict(journal.core)
    p['start_utc'] = datetime.fromtimestamp(start / 1000, timezone.utc).strftime('%Y-%m-%dT00:00:00Z')
    p['end_exclusive_utc'] = datetime.fromtimestamp(end / 1000, timezone.utc).strftime('%Y-%m-%dT00:00:00Z')
    validation, _ = assemble(p, journal.get)
    return validation


def run(journal, *, on_checkpoint=None):
    out, p = journal.out, journal.plan
    state_path = out / 'state.json'
    state = json.loads(state_path.read_bytes()) if state_path.exists() else {'schema': 'bybit_complete_014_state_v1', 'rounds': []}
    if 'pending_round' in state:
        pending = state.pop('pending_round')
        for symbol in SYMBOLS:
            pending['assets'].setdefault(symbol, {'status': 'INTERRUPTED', 'error': 'Process stopped before this observation completed'})
        state['rounds'].append(pending)
        write(state_path, state)
    state['history'] = historical(journal); write(state_path, state)
    print('Historical download checked. Starting/resuming multiday sampling.', flush=True)
    for round_id in range(len(state['rounds']), p['live_rounds']):
        if state['rounds']:
            due = state['rounds'][-1]['started_ms'] + p['live_interval_seconds'] * 1000
            journal.clock.sleep(max(0, (due - journal.clock.now()) / 1000))
        started = journal.clock.now()
        round_record = {'id': round_id, 'started_ms': started, 'assets': {}}
        state['pending_round'] = round_record; write(state_path, state)
        for symbol in SYMBOLS:
            round_record['assets'][symbol] = component(lambda s=symbol: live_asset(journal, s, round_id))
            write(state_path, state)
        state['rounds'].append(round_record); state.pop('pending_round'); write(state_path, state)
        print(f'Observation {round_id + 1}/{p["live_rounds"]} saved; about {(p["live_rounds"] - round_id - 1) * p["live_interval_seconds"] / 3600:.1f} hours remain.', flush=True)
        if on_checkpoint: on_checkpoint(state)
    if 'extension_end_ms' not in state:
        state['extension_end_ms'] = journal.clock.now() // DAY * DAY; write(state_path, state)
    state['extension'] = component(lambda: extension(journal, state['extension_end_ms']))
    state['final_risk'] = {s: component(lambda sym=s: risk_snapshot(journal, sym, 'final-risk')) for s in SYMBOLS}
    state['live_coverage'] = live_coverage(state['rounds'], p['live_rounds'])
    state['status'] = 'COLLECTED_FOR_REVIEW'
    write(state_path, state)
    return state


@contextmanager
def file_lock(path):
    """OS-held lock is released even if Windows terminates the process."""
    f = path.open('a+b')
    try:
        f.seek(0); f.write(b'0'); f.flush(); f.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError):
        f.close(); raise StopCollection('Another collector is already running') from None
    try: yield
    finally:
        f.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        f.close()


@contextmanager
def keep_awake():
    """Temporary Windows idle-sleep request; restored on exit, no power-plan edits."""
    fn = None
    if os.name == 'nt':
        import ctypes
        fn = ctypes.windll.kernel32.SetThreadExecutionState
        fn(0x80000001)
    try: yield
    finally:
        if fn: fn(0x80000000)


def package(out, target):
    files = sorted(p for p in out.iterdir() if p.is_file() and p.suffix != '.tmp')
    manifest = {p.name: {'sha256': file_sha(p), 'bytes': p.stat().st_size} for p in files if p.name != 'FILES.json'}
    write(out / 'FILES.json', manifest)
    temp = target.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(out.iterdir()):
            if p.is_file() and p.suffix != '.tmp': z.write(p, p.name)
    temp.replace(target)
    return {'file': target.name, 'bytes': target.stat().st_size, 'sha256': file_sha(target)}


def import_old_history(journal, candidates):
    """Read-only bounded lookup of the prior collector's known output folders."""
    if journal.records: return 0
    import sys
    sys.path.insert(0, str(ROOT / 'scripts'))
    import collect_bybit_history as old
    for folder in candidates:
        if not (folder / 'session.json').is_file(): continue
        prior = old.Session(folder, (ROOT / 'docs/BYBIT_HISTORY_013.json').read_bytes(), old.sources(), offline=True)
        (journal.out / 'import_013_session.json').write_bytes((folder / 'session.json').read_bytes())
        for original in prior.state['requests']:
            if not original.get('accepted_api_response'): continue
            raw = (folder / original['raw_file']).read_bytes()
            payload = json.loads(raw); response(payload, original['received_ms'])
            i = len(journal.records); name = f'response_{i:06d}.bin'
            if journal.bytes_used + len(raw) > journal.plan['max_evidence_bytes']: raise StopCollection('Import exceeds storage bound')
            url = url_for(original['kind'], original['symbol'], original['params'])
            rec = {'id': i, 'method': 'GET', 'kind': original['kind'], 'symbol': original['symbol'],
                   'params': original['params'], 'scope': 'history', 'url': url, 'key': 'history|' + url,
                   'request_ms': original['request_ms'], 'received_ms': original['received_ms'],
                   'http_status': 200, 'accepted': True, 'status': 'IMPORTED_VERIFIED_013',
                   'raw_file': name, 'sha256': sha(raw), 'elapsed_seconds': original['elapsed_seconds'],
                   'origin_request_id': original['index']}
            (journal.out / name).write_bytes(raw); write(journal.out / f'request_{i:06d}.json', rec)
            journal.bytes_used += len(raw); journal.records.append(rec); journal.cache[rec['key']] = rec
        print(f'Reused {len(journal.records)} verified historical pages from the previous package.', flush=True)
        return len(journal.records)
    return 0


def status_summary(journal, error=None):
    state = json.loads((journal.out / 'state.json').read_bytes()) if (journal.out / 'state.json').exists() else {}
    core = state.get('history', {}).get('core', {})
    live = live_coverage(state.get('rounds', []), journal.plan['live_rounds'])
    supplements = state.get('history', {}).get('supplements', {})
    ext = state.get('extension', {})
    coverage_ok = (core.get('status') == 'COMPLETE' and live['status'] == 'COLLECTED'
                   and all(v.get('status') == 'COMPLETE' for v in supplements.values())
                   and ext.get('status') in ('COMPLETE', 'NOT_YET_DUE')
                   and len(state.get('final_risk', {})) == 3
                   and all(v.get('status') == 'COMPLETE' for v in state.get('final_risk', {}).values()))
    return {'schema': 'bybit_complete_014_summary_v1',
            'status': 'STOPPED_WITH_EVIDENCE' if error else ('ALL_REQUESTED_COMPONENTS_COLLECTED' if coverage_ok else 'COLLECTED_WITH_GAPS_REVIEW_REQUIRED'),
            'error': error, 'request_attempts': len(journal.records),
            'imported_pages': sum(r['status'] == 'IMPORTED_VERIFIED_013' for r in journal.records),
            'successful_responses': sum(bool(r.get('accepted')) for r in journal.records),
            'core_history_status': core.get('status', 'NOT_COMPLETED'), 'live': live,
            'unavailable_or_partial_supplements': {k: v for k, v in supplements.items() if v.get('status') != 'COMPLETE'},
            'extension_status': ext.get('status', 'NOT_COMPLETED'), 'unknowns': journal.plan['unknowns'],
            'orders': 0, 'private_api_calls': 0, 'real_strategy_simulations': 0,
            'meaning': 'Requested collection coverage only. No guarantee of historical execution realism, independent authenticity or future profitability.'}
