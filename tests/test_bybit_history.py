"""Network-free pagination, gap, resumption, provenance and adversarial checks."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import urllib.parse
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tradingagents'))
import collect_bybit_history as c
import audit_bybit_history as a
import bybit_history as h

spec = importlib.util.spec_from_file_location('history_fixtures', Path(__file__).with_name('test_bybit_discovery.py'))
f = importlib.util.module_from_spec(spec); spec.loader.exec_module(f)
NOW = 1_792_174_000_000


def protocol():
    p = json.loads(c.PROTOCOL.read_bytes())
    p.update(start_utc='2021-01-01T00:00:00Z', end_exclusive_utc='2021-01-04T00:00:00Z',
             candle_page_limit=25, funding_page_limit=4, request_spacing_seconds=0)
    return p


def raw_protocol(p):
    return json.dumps(p).encode()


def payload(kind, symbol, **params):
    if kind == 'instrument':
        product, _ = f.fixture()
        product.update(symbol=symbol, launchTime='1577836800000', fundingInterval=480)
        result = {'category': 'linear', 'list': [product]}
    elif kind in ('trade', 'mark'):
        times = list(range(params['start'], params['end'] + 1, h.HOUR))[::-1]
        rows = [[str(t), '100', '110', '90', '101'] + (['2', '200'] if kind == 'trade' else []) for t in times]
        result = {'category': 'linear', 'symbol': symbol, 'list': rows}
    else:
        latest = params['endTime'] // (8 * h.HOUR) * (8 * h.HOUR)
        result = {'category': 'linear', 'list': [
            {'symbol': symbol, 'fundingRateTimestamp': str(latest - i * 8 * h.HOUR), 'fundingRate': '0.0001'}
            for i in range(params['limit'])]}
    return {'retCode': 0, 'time': NOW, 'result': result}, NOW


class Reply:
    status = 200
    def __init__(self, raw): self.raw = raw
    def read(self, n): return self.raw[:n]
    def __enter__(self): return self
    def __exit__(self, *args): pass


def mock_network(monkeypatch, *, fail_at=None, mutate=None):
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            if fail_at is not None and len(calls) == fail_at:
                raise TimeoutError('synthetic interruption')
            u = urllib.parse.urlparse(request.full_url)
            q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
            kind = next(k for k, path in h.ENDPOINTS.items() if path == u.path)
            assert u.scheme == 'https' and u.netloc == 'api.bybit.com'
            assert request.get_method() == 'GET' and not request.data
            assert not any('BAPI' in k.upper() for k in request.headers)
            assert q.pop('category') == 'linear'
            symbol = q.pop('symbol')
            params = {k: (v if k == 'interval' else int(v)) for k, v in q.items()}
            result, _ = payload(kind, symbol, **params)
            if mutate: mutate(result, kind, symbol, params)
            return Reply(json.dumps(result).encode())
    monkeypatch.setattr(c.urllib.request, 'build_opener', lambda *args: Opener())
    monkeypatch.setattr(c.time, 'time', lambda: NOW / 1000)
    return calls


def test_full_pagination_and_roundtrip_archive_audit(monkeypatch, tmp_path):
    calls = mock_network(monkeypatch)
    p = protocol(); raw = raw_protocol(p); out = tmp_path / 'history'
    result = c.collect(out, raw, {'test': 'synthetic'})
    assert result['status'] == 'COMPLETE' and len(calls) == 30
    assert result['validation']['expected_hours_per_series'] == 72
    archive = out.with_suffix('.zip')
    receipt, data = a.audit(archive, h.sha(archive.read_bytes()), raw, {'test': 'synthetic'})
    assert receipt['raw_responses_verified'] == 30
    for symbol in h.SYMBOLS:
        assert len(data[symbol]['funding']) == 9
        assert len(data[symbol]['daily_trade']) == 3
        assert data[symbol]['daily_trade'][0][5:] == ['48', '4800']
    # Completed sessions reuse every page and remain semantically identical.
    again = c.collect(out, raw, {'test': 'synthetic'})
    assert again['validation'] == result['validation'] and len(calls) == 30


def test_resume_retains_failure_and_does_not_redownload_successes(monkeypatch, tmp_path):
    calls = mock_network(monkeypatch, fail_at=5)
    raw = raw_protocol(protocol()); out = tmp_path / 'resume'
    assert c.collect(out, raw, {})['status'] == 'INTERRUPTED_OR_INVALID'
    assert len(calls) == 5  # no retry in same invocation
    again = c.collect(out, raw, {})
    assert again['status'] == 'COMPLETE' and len(calls) == 31
    state = json.loads((out / 'session.json').read_bytes())
    assert 'TimeoutError' in state['requests'][4]['error']
    archive = out.with_suffix('.zip')
    assert a.audit(archive, h.sha(archive.read_bytes()), raw, {})[0]['validation']['status'] == 'COMPLETE'


def test_corrupt_cached_page_stops_before_network(monkeypatch, tmp_path):
    calls = mock_network(monkeypatch, fail_at=3)
    raw = raw_protocol(protocol()); out = tmp_path / 'corrupt'
    c.collect(out, raw, {})
    next(out.glob('*.response')).write_bytes(b'{}')
    result = c.collect(out, raw, {})
    assert 'hash/name mismatch' in result['error'] and len(calls) == 3


def test_source_mismatch_preserves_summary_and_no_network(monkeypatch, tmp_path):
    calls = mock_network(monkeypatch, fail_at=3)
    raw = raw_protocol(protocol()); out = tmp_path / 'source'
    c.collect(out, raw, {'version': 'one'})
    before = (out / 'summary.json').read_bytes()
    result = c.collect(out, raw, {'version': 'two'})
    assert 'source mismatch' in result['error'] and len(calls) == 3
    assert (out / 'summary.json').read_bytes() == before


def test_missing_candle_is_reported_not_filled(monkeypatch, tmp_path):
    def mutate(result, kind, symbol, params):
        if kind == 'mark' and symbol == 'BTCUSDT': result['result']['list'].pop()
    mock_network(monkeypatch, mutate=mutate)
    raw = raw_protocol(protocol()); out = tmp_path / 'gaps'
    result = c.collect(out, raw, {})
    assert result['status'] == 'DATA_GAPS_OR_SCHEDULE_REVIEW'
    assert result['validation']['symbols']['BTCUSDT']['series']['mark']['missing_hours'] == 3
    archive = out.with_suffix('.zip')
    receipt, data = a.audit(archive, h.sha(archive.read_bytes()), raw, {})
    assert receipt['validation']['status'] == result['status']
    assert 'daily_trade' not in data['BTCUSDT']


@pytest.mark.parametrize('problem', ['symbol', 'nan', 'ohlc', 'duplicate', 'ascending', 'off_grid', 'outside', 'open_bar', 'negative_volume'])
def test_bad_candles_rejected(problem):
    start, end = h.validate_protocol(protocol()); stop = start + 2 * h.HOUR
    p, received = payload('trade', 'BTCUSDT', start=start, end=stop - 1)
    rows = p['result']['list']
    if problem == 'symbol': p['result']['symbol'] = 'ETHUSDT'
    elif problem == 'nan': rows[0][1] = 'NaN'
    elif problem == 'ohlc': rows[0][3] = '120'
    elif problem == 'duplicate': rows[1] = rows[0].copy()
    elif problem == 'ascending': rows.reverse()
    elif problem == 'off_grid': rows[0][0] = str(int(rows[0][0]) + 1)
    elif problem == 'outside': rows[0][0] = str(stop)
    elif problem == 'open_bar': p['time'] = received = stop - 1
    elif problem == 'negative_volume': rows[0][5] = '-1'
    with pytest.raises(ValueError): h.candle_page(p, received, 'BTCUSDT', 'trade', start, stop, 25)


@pytest.mark.parametrize('mode', ['gap', 'shift', 'missing_anchor', 'empty'])
def test_funding_schedule_anomalies_block_completion(mode):
    p = protocol(); start, end = h.validate_protocol(p)
    def get(kind, symbol, **params):
        result, received = payload(kind, symbol, **params)
        if kind == 'funding':
            rows = result['result']['list']
            if mode == 'gap':
                result['result']['list'] = [r for r in rows if int(r['fundingRateTimestamp']) != start + 8 * h.HOUR]
            elif mode == 'shift':
                for r in rows: r['fundingRateTimestamp'] = str(int(r['fundingRateTimestamp']) - h.HOUR)
            elif mode == 'missing_anchor':
                result['result']['list'] = [r for r in rows if int(r['fundingRateTimestamp']) >= start]
            else: result['result']['list'] = []
        return result, received
    result, _ = h.assemble(p, get)
    assert result['status'] == 'DATA_GAPS_OR_SCHEDULE_REVIEW'
    assert all(v['issues'] for v in result['symbols'].values())


def test_duplicate_funding_and_future_event_rejected():
    p, received = payload('funding', 'BTCUSDT', endTime=NOW, limit=4)
    p['result']['list'][1] = p['result']['list'][0].copy()
    with pytest.raises(ValueError): h.funding_page(p, received, 'BTCUSDT', NOW, 4)
    p['result']['list'] = [{'symbol': 'BTCUSDT', 'fundingRate': '0', 'fundingRateTimestamp': str(NOW + 1)}]
    with pytest.raises(ValueError): h.funding_page(p, received, 'BTCUSDT', NOW, 4)


def test_incomplete_daily_aggregation_rejected():
    start, _ = h.validate_protocol(protocol())
    p, _ = payload('trade', 'BTCUSDT', start=start, end=start + 24 * h.HOUR - 1)
    rows = p['result']['list'][::-1]
    assert len(h.daily_trade(rows)) == 1
    with pytest.raises(ValueError): h.daily_trade(rows[:-1])
    rows[5] = rows[4].copy()
    with pytest.raises(ValueError): h.daily_trade(rows)


def test_archive_hash_and_unsafe_names_rejected(tmp_path):
    path = tmp_path / 'unsafe.zip'
    with zipfile.ZipFile(path, 'w') as z: z.writestr('../bad', 'data')
    with pytest.raises(ValueError, match='hash mismatch'): a.audit(path, '0' * 64)
    with pytest.raises(ValueError, match='Unsafe'): a.audit(path, h.sha(path.read_bytes()))


def test_html_stops_without_retry_and_keeps_response(monkeypatch, tmp_path):
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request); return Reply(b'<html>Site Unavailable</html>')
    monkeypatch.setattr(c.urllib.request, 'build_opener', lambda *args: Opener())
    monkeypatch.setattr(c.time, 'time', lambda: NOW / 1000)
    out = tmp_path / 'html'
    result = c.collect(out, raw_protocol(protocol()), {})
    assert 'Non-JSON' in result['error'] and len(calls) == 1
    assert next(out.glob('*.response')).read_bytes().startswith(b'<html>')


def test_stdlib_only_commands():
    for name in ('collect_bybit_history.py', 'audit_bybit_history.py'):
        run = subprocess.run([sys.executable, '-S', str(ROOT / 'scripts' / name), '--help'], capture_output=True, text=True)
        assert run.returncode == 0, run.stderr
