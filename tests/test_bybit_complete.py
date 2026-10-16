"""Independent synthetic endpoint fixtures, retry/resume and returned-ZIP audit."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import urllib.parse
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tradingagents'))
sys.path.insert(0, str(ROOT / 'scripts'))
import bybit_complete as b
import audit_bybit_complete as audit_module


class Clock:
    def __init__(self): self.t = b.utc_ms('2026-10-16T18:30:00Z'); self.slept = []
    def now(self): return self.t
    def mono(self): return self.t / 1000
    def sleep(self, seconds): self.slept.append(seconds); self.t += int(round(seconds * 1000))


def config():
    p = json.loads((ROOT / 'docs/BYBIT_COMPLETE_014.json').read_bytes())
    core = json.loads((ROOT / 'docs/BYBIT_HISTORY_013.json').read_bytes())
    p.update(fine_history_days=1, open_interest_days=1, live_rounds=3, live_interval_seconds=30,
             request_spacing_seconds=0, paired_book_delay_seconds=2)
    core.update(start_utc='2026-10-14T00:00:00Z', end_exclusive_utc='2026-10-16T00:00:00Z')
    return p, core


def raw(p): return json.dumps(p).encode()


class Server:
    def __init__(self, clock): self.clock = clock; self.calls = []; self.failures = []; self.mutate = None
    def __call__(self, url, timeout, limit):
        u = urllib.parse.urlparse(url)
        assert u.scheme == 'https' and u.netloc == 'api.bybit.com' and u.path.startswith('/v5/market/')
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        assert q.pop('category') == 'linear'
        symbol = q.pop('symbol'); kind = next(k for k, v in b.PATHS.items() if v == u.path)
        self.calls.append((kind, symbol, q)); self.clock.sleep(.1); now = self.clock.now()
        if self.failures:
            error = self.failures.pop(0)
            if isinstance(error, Exception): raise error
            return error
        if kind == 'instrument':
            result = {'category': 'linear', 'list': [{'symbol': symbol, 'status': 'Trading', 'contractType': 'LinearPerpetual',
              'settleCoin': 'USDT', 'quoteCoin': 'USDT', 'launchTime': '1577836800000', 'fundingInterval': 480,
              'priceFilter': {'tickSize': '.5'},
              'lotSizeFilter': {'qtyStep': '.1', 'minOrderQty': '.1', 'maxMktOrderQty': '1000', 'minNotionalValue': '5'}}]}
        elif kind in ('trade', 'mark', 'index', 'premium'):
            step = int(q['interval']) * 60000
            stamps = list(range(int(q['start']), int(q['end']) + 1, step))[::-1]
            prices = ['-.0001', '.0002', '-.0002', '0'] if kind == 'premium' else ['100', '110', '90', '101']
            result = {'category': 'linear', 'symbol': symbol, 'list': [[str(t), *prices, *(['10', '1000'] if kind == 'trade' else [])] for t in stamps]}
        elif kind == 'funding':
            latest = int(q['endTime']) // (8 * b.HOUR) * 8 * b.HOUR
            result = {'category': 'linear', 'list': [{'symbol': symbol, 'fundingRate': '.0001',
              'fundingRateTimestamp': str(latest - i * 8 * b.HOUR)} for i in range(int(q['limit']))]}
        elif kind in ('oi', 'ratio'):
            step = b.HOUR if kind == 'oi' else b.DAY
            stamps = list(range(int(q['startTime']), int(q['endTime']) + 1, step))[::-1]
            result = {'category': 'linear', 'symbol': symbol, 'list': [
                {'timestamp': str(t), **({'openInterest': '100', 'singleOpenInterest': '50'} if kind == 'oi' else {'symbol': symbol, 'buyRatio': '.4', 'sellRatio': '.6'})} for t in stamps]}
        elif kind == 'risk':
            result = {'category': 'linear', 'list': [{'id': 1, 'symbol': symbol, 'riskLimitValue': '2000000',
               'maintenanceMargin': '.005', 'initialMargin': '.01', 'maxLeverage': '100', 'mmDeduction': '0'}], 'nextPageCursor': ''}
        elif kind == 'ticker':
            result = {'category': 'linear', 'list': [{'symbol': symbol, 'markPrice': '100', 'indexPrice': '100', 'lastPrice': '100',
                'fundingRate': '.0001', 'openInterest': '1000', 'nextFundingTime': str(now + b.HOUR)}]}
        elif kind == 'book':
            result = {'s': symbol, 'ts': now, 'cts': now - 10, 'u': now, 'seq': now,
                      'a': [['100', '100'], ['101', '100']], 'b': [['99.5', '100'], ['99', '100']]}
        elif kind == 'trades':
            result = {'category': 'linear', 'list': [{'execId': str(now), 'symbol': symbol, 'price': '100', 'size': '1', 'side': 'Buy', 'time': str(now - 10)}]}
        else: raise AssertionError(kind)
        payload = {'retCode': 0, 'result': result, 'time': now}
        if self.mutate: self.mutate(payload, kind, symbol)
        return 200, json.dumps(payload).encode()


def setup(tmp_path, p=None, core=None):
    pp, cc = config(); p = p or pp; core = core or cc
    clock = Clock(); server = Server(clock); out = tmp_path / 'data'; out.mkdir()
    j = b.Journal(out, raw(p), raw(core), {'test': 'fixture'}, clock=clock, transport=server)
    return j, server, clock


def finalize(j, target, error=None):
    b.write(j.out / 'summary.json', b.status_summary(j, error))
    return b.package(j.out, target)


def test_complete_end_to_end_raw_audit_and_no_repeat(tmp_path):
    j, server, clock = setup(tmp_path)
    state = b.run(j)
    assert state['live_coverage']['valid_books'] == 18
    assert state['live_coverage']['fully_valid_rounds'] == 3
    assert state['history']['supplements']['BTCUSDT_premium']['status'] == 'COMPLETE'
    n = len(server.calls)
    j2 = b.Journal(j.out, raw(j.plan), raw(j.core), {'test': 'fixture'}, clock=clock, transport=server)
    again = b.run(j2)
    assert len(server.calls) == n and again == state
    archive = tmp_path / 'result.zip'; rec = finalize(j2, archive)
    audited = audit_module.audit(archive, rec['sha256'], plan_raw=raw(j.plan), core_raw=raw(j.core), source_hashes={'test': 'fixture'})
    assert audited['live_assets_recomputed'] == 9
    assert audited['summary']['status'] == 'ALL_REQUESTED_COMPONENTS_COLLECTED'
    assert audited['summary']['orders'] == 0 and audited['summary']['private_api_calls'] == 0


def test_transient_retry_bounded_and_errors_kept(tmp_path):
    j, server, clock = setup(tmp_path)
    server.failures = [TimeoutError('test'), (503, b'unavailable')]
    payload, _ = j.get('instrument', 'BTCUSDT')
    assert payload['retCode'] == 0 and len(server.calls) == 3
    assert [r['status'] for r in j.records] == ['TRANSIENT_FAILURE', 'TRANSIENT_FAILURE', 'ACCEPTED']
    assert 5 in clock.slept and 15 in clock.slept
    j.get('instrument', 'BTCUSDT'); assert len(server.calls) == 3


def test_rate_limit_retries_and_stops_at_three(tmp_path):
    j, server, clock = setup(tmp_path)
    server.failures = [(429, b'rate limit')] * 4
    with pytest.raises(b.DataUnavailable): j.get('instrument', 'BTCUSDT')
    assert len(server.calls) == 3 and len(server.failures) == 1


@pytest.mark.parametrize('reply', [(403, b'blocked'), (401, b'unauthorized'), (200, b'<html>Unavailable</html>')])
def test_access_errors_never_retried(tmp_path, reply):
    j, server, _ = setup(tmp_path); server.failures = [reply]
    with pytest.raises(b.StopCollection): j.get('instrument', 'BTCUSDT')
    assert len(server.calls) == 1 and j.records[0]['status'] == 'STOPPED'


def test_redirect_refused():
    with pytest.raises(b.StopCollection): b.NoRedirect().redirect_request(None, None, None, None, None, None)


def test_missing_optional_series_does_not_block_core_or_live(tmp_path):
    j, server, _ = setup(tmp_path)
    def mutate(payload, kind, symbol):
        if kind == 'index' and symbol == 'LTCUSDT': payload['result']['list'] = []
    server.mutate = mutate
    state = b.run(j)
    assert state['history']['core']['status'] == 'COMPLETE'
    assert state['history']['supplements']['LTCUSDT_index']['status'] == 'GAPS'
    assert state['live_coverage']['valid_books'] == 18
    assert b.status_summary(j)['status'] == 'COLLECTED_WITH_GAPS_REVIEW_REQUIRED'


def test_interrupted_round_is_not_reused_as_fresh(tmp_path):
    j, server, clock = setup(tmp_path)
    def mutate(payload, kind, symbol):
        if kind == 'ticker' and symbol == 'ETHUSDT': raise KeyboardInterrupt()
    server.mutate = mutate
    with pytest.raises(KeyboardInterrupt): b.run(j)
    partial = json.loads((j.out / 'state.json').read_bytes())
    old_stamp = partial['pending_round']['assets']['BTCUSDT']['received_ms'][0]
    clock.sleep(3600); server.mutate = None
    resumed = b.Journal(j.out, raw(j.plan), raw(j.core), {'test': 'fixture'}, clock=clock, transport=server)
    state = b.run(resumed)
    assert state['rounds'][0]['assets']['ETHUSDT']['status'] == 'INTERRUPTED'
    assert state['rounds'][1]['assets']['BTCUSDT']['received_ms'][0] > old_stamp + 3600000
    assert state['live_coverage']['fully_valid_rounds'] == 2
    rec = finalize(resumed, tmp_path / 'partial.zip')
    result = audit_module.audit(tmp_path / 'partial.zip', rec['sha256'], plan_raw=raw(j.plan), core_raw=raw(j.core), source_hashes={'test': 'fixture'})
    assert result['summary']['status'] == 'COLLECTED_WITH_GAPS_REVIEW_REQUIRED'


def test_cached_response_and_source_tampering_block_resume(tmp_path):
    j, server, clock = setup(tmp_path); j.get('instrument', 'BTCUSDT')
    with pytest.raises(b.StopCollection, match='identity changed'):
        b.Journal(j.out, raw(j.plan), raw(j.core), {'test': 'changed'}, clock=clock, transport=server)
    (j.out / j.records[0]['raw_file']).write_bytes(b'{}')
    with pytest.raises(b.StopCollection, match='hash mismatch'):
        b.Journal(j.out, raw(j.plan), raw(j.core), {'test': 'fixture'}, clock=clock, transport=server)
    assert len(server.calls) == 1


def test_old_scope_cannot_be_changed_to_fresh_scope(tmp_path):
    j, server, clock = setup(tmp_path); j.get('instrument', 'BTCUSDT')
    rec = dict(j.records[0]); rec['key'] = 'live-0001-BTCUSDT|' + rec['url']
    b.write(j.out / 'request_000000.json', rec)
    with pytest.raises(b.StopCollection, match='cache identity'):
        b.Journal(j.out, raw(j.plan), raw(j.core), {'test': 'fixture'}, clock=clock, transport=server)


def test_request_and_storage_bounds(tmp_path):
    j, server, _ = setup(tmp_path)
    j.plan['max_requests'] = 1; j.get('instrument', 'BTCUSDT')
    with pytest.raises(b.StopCollection, match='bound'): j.get('instrument', 'ETHUSDT')
    assert len(server.calls) == 1


@pytest.mark.parametrize('kind', ['oi', 'ratio'])
def test_supplement_gaps_are_measured(tmp_path, kind):
    j, server, _ = setup(tmp_path)
    def mutate(p, k, s):
        if k == kind: p['result']['list'].pop()
    server.mutate = mutate
    end = b.utc_ms(j.core['end_exclusive_utc'])
    result = b.sampled_series(j, kind, 'BTCUSDT', end - b.DAY, end)
    assert result['status'] == 'GAPS' and result['missing'] == 1


def test_risk_cursor_loop_refused(tmp_path):
    j, server, _ = setup(tmp_path)
    def mutate(p, k, s):
        if k == 'risk': p['result']['nextPageCursor'] = 'repeat'
    server.mutate = mutate
    with pytest.raises(ValueError): b.risk_snapshot(j, 'BTCUSDT', 'test')
    assert len(server.calls) == 2


def test_round_summary_tampering_caught_even_with_new_manifest(tmp_path):
    j, _, _ = setup(tmp_path); b.run(j)
    state = json.loads((j.out / 'state.json').read_bytes())
    state['rounds'][0]['assets']['BTCUSDT']['pair_elapsed_ms'] += 1
    b.write(j.out / 'state.json', state)
    archive = tmp_path / 'tampered.zip'; rec = finalize(j, archive)
    with pytest.raises(ValueError, match='observation summary'):
        audit_module.audit(archive, rec['sha256'], plan_raw=raw(j.plan), core_raw=raw(j.core), source_hashes={'test': 'fixture'})


def test_path_traversal_archive_rejected(tmp_path):
    archive = tmp_path / 'evil.zip'
    with zipfile.ZipFile(archive, 'w') as z: z.writestr('../evil', 'data')
    with pytest.raises(ValueError, match='Unsafe'): audit_module.audit(archive, b.file_sha(archive))


def test_os_lock_released_after_exception(tmp_path):
    path = tmp_path / 'lock'
    with pytest.raises(RuntimeError):
        with b.file_lock(path): raise RuntimeError('interrupted')
    with b.file_lock(path): pass


def test_unregistered_private_path_or_query_refused():
    with pytest.raises(b.StopCollection): b.url_for('create-order', 'BTCUSDT', {})
    with pytest.raises(b.StopCollection): b.url_for('instrument', 'BTCUSDT', {'api_key': 'forbidden'})


def test_stdlib_only_entrypoints():
    for script in ('collect_bybit_complete.py', 'audit_bybit_complete.py'):
        r = subprocess.run([sys.executable, '-S', str(ROOT / 'scripts' / script), '--help'], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


def test_core_endpoint_failure_does_not_suppress_other_assets(tmp_path):
    j, server, _ = setup(tmp_path)
    def mutate(payload, kind, symbol):
        if kind == 'mark' and symbol == 'BTCUSDT':
            payload['retCode'] = 10001
    server.mutate = mutate
    state = b.run(j)
    assert state['history']['core']['status'] == 'UNAVAILABLE_OR_INVALID'
    available = state['history']['core_component_availability']
    assert available['ETHUSDT']['mark']['status'] == 'COMPLETE'
    assert available['LTCUSDT']['trade']['status'] == 'COMPLETE'
    assert state['live_coverage']['valid_books'] == 18
    # Revalidation does not cause another retry cycle for the same failed query.
    for kind, symbol, q in server.calls:
        if kind == 'mark' and symbol == 'BTCUSDT':
            assert server.calls.count((kind, symbol, q)) == 1
    rec = finalize(j, tmp_path / 'core-gap.zip')
    checked = audit_module.audit(tmp_path / 'core-gap.zip', rec['sha256'], plan_raw=raw(j.plan), core_raw=raw(j.core), source_hashes={'test': 'fixture'})
    assert checked['summary']['status'] == 'COLLECTED_WITH_GAPS_REVIEW_REQUIRED'


def test_same_logical_query_not_retried_again_after_exhaustion(tmp_path):
    j, server, _ = setup(tmp_path)
    server.failures = [TimeoutError('offline')] * 6
    for _ in range(2):
        with pytest.raises(b.DataUnavailable): j.get('instrument', 'BTCUSDT')
    assert len(server.calls) == 3


def test_extension_collected_after_new_utc_day(tmp_path):
    j, _, clock = setup(tmp_path)
    clock.sleep(2 * 86400)
    state = b.run(j)
    assert state['extension']['status'] == 'COMPLETE'
    assert state['extension']['expected_hours_per_series'] == 48
    assert state['extension']['end_exclusive_ms'] == b.utc_ms('2026-10-18T00:00:00Z')


def test_import_previous_history_checks_old_source_and_reuses_bytes(tmp_path):
    import collect_bybit_history as old
    p, core = config()
    # Old collector validation uses its actual fixed protocol, but importing does not
    # require all historical pages to have been completed.
    clock = Clock(); server = Server(clock); folder = tmp_path / 'previous'; folder.mkdir()
    original = old.Session(folder, (ROOT / 'docs/BYBIT_HISTORY_013.json').read_bytes(), old.sources(), offline=False)
    url = b.url_for('instrument', 'BTCUSDT', {})
    status, blob = server(url, 20, 15000000)
    name = '0000_BTCUSDT_instrument.response'; (folder / name).write_bytes(blob)
    record = {'index': 0, 'method': 'GET', 'kind': 'instrument', 'symbol': 'BTCUSDT', 'params': {},
              'url': url, 'request_ms': clock.now() - 100, 'received_ms': clock.now(), 'http_status': status,
              'raw_file': name, 'sha256': b.sha(blob), 'accepted_api_response': True, 'elapsed_seconds': .1}
    original.state['requests'].append(record); old.write(folder / 'session.json', original.state)
    out = tmp_path / 'imported'; out.mkdir()
    j = b.Journal(out, raw(p), (ROOT / 'docs/BYBIT_HISTORY_013.json').read_bytes(), {'test': 'fixture'}, clock=clock, transport=server)
    assert b.import_old_history(j, [folder]) == 1
    calls = len(server.calls)
    assert j.get('instrument', 'BTCUSDT')[0] == json.loads(blob)
    assert len(server.calls) == calls
    assert (j.out / j.records[0]['raw_file']).read_bytes() == blob
