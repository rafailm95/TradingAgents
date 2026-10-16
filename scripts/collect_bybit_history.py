"""Portable public Bybit history collector. GET only; no keys or orders.
Run again to resume hash-verified successful pages. No automatic network retries.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tradingagents'))
from bybit_depth import response
from bybit_history import assemble, sha, request_url, validate_protocol

SOURCE_FILES = ('scripts/collect_bybit_history.py', 'tradingagents/bybit_history.py', 'tradingagents/bybit_depth.py')
PROTOCOL = ROOT / 'docs/BYBIT_HISTORY_013.json'


def write(path, data):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temp.replace(path)


def sources():
    return {name: sha((ROOT / name).read_bytes()) for name in SOURCE_FILES}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Unexpected redirect; no alternate host permitted')


class Session:
    def __init__(self, out, protocol_raw, source_hashes, *, offline=False):
        self.out = out
        self.protocol = json.loads(protocol_raw)
        validate_protocol(self.protocol)
        self.offline = offline
        self.last_request = None
        identity = {'schema': 'bybit_history_013_session_v1', 'protocol_sha256': sha(protocol_raw),
                    'source_hashes': source_hashes}
        path = out / 'session.json'
        if path.exists():
            self.state = json.loads(path.read_bytes())
            if any(self.state.get(k) != v for k, v in identity.items()):
                raise ValueError('Resume protocol/source mismatch; preserve this folder and upload its ZIP')
            if (out / 'protocol.json').read_bytes() != protocol_raw:
                raise ValueError('Stored protocol changed')
        else:
            if offline or any(out.iterdir()):
                raise ValueError('Missing session manifest or non-empty new folder')
            self.state = {**identity, 'created_utc': datetime.now(timezone.utc).isoformat(), 'requests': []}
            (out / 'protocol.json').write_bytes(protocol_raw)
            write(path, self.state)
        self.cache = {}
        for index, rec in enumerate(self.state['requests']):
            if rec['index'] != index or rec['method'] != 'GET' or rec['url'] != request_url(rec['kind'], rec['symbol'], rec['params']):
                raise ValueError('Invalid recorded request identity')
            if 'raw_file' in rec:
                name = f'{index:04d}_{rec["symbol"]}_{rec["kind"]}.response'
                if rec['raw_file'] != name or sha((out / name).read_bytes()) != rec['sha256']:
                    raise ValueError('Cached response hash/name mismatch')
            if rec.get('accepted_api_response'):
                if rec.get('http_status') != 200 or 'raw_file' not in rec or rec['url'] in self.cache:
                    raise ValueError('Invalid/duplicate accepted request')
                self.cache[rec['url']] = rec
        self.used = set()

    def get(self, kind, symbol, **params):
        url = request_url(kind, symbol, params)
        self.used.add(url)
        if url in self.cache:
            rec = self.cache[url]
            payload = json.loads((self.out / rec['raw_file']).read_bytes())
            response(payload, rec['received_ms'])
            return payload, rec['received_ms']
        if self.offline:
            raise ValueError('Missing successful page: ' + url)
        if len(self.state['requests']) >= self.protocol['max_requests_per_session']:
            raise ValueError('Session request limit reached; no silent restart')
        if self.last_request is not None:
            time.sleep(max(0, self.protocol['request_spacing_seconds'] - (time.monotonic() - self.last_request)))
        index = len(self.state['requests'])
        rec = {'index': index, 'method': 'GET', 'kind': kind, 'symbol': symbol, 'params': params,
               'url': url, 'request_ms': int(time.time() * 1000)}
        self.state['requests'].append(rec)
        started = time.monotonic()
        try:
            req = urllib.request.Request(url, headers={'Accept': 'application/json',
                                                       'User-Agent': 'TradingAgents-Public-History/013'}, method='GET')
            try:
                stream = urllib.request.build_opener(NoRedirect()).open(req, timeout=self.protocol['timeout_seconds'])
            except urllib.error.HTTPError as error:
                stream = error
            with stream:
                raw = stream.read(self.protocol['max_response_bytes'] + 1)
                rec['http_status'] = stream.status
            rec['received_ms'] = int(time.time() * 1000)
            if len(raw) > self.protocol['max_response_bytes']:
                raise ValueError('Response size bound exceeded')
            name = f'{index:04d}_{symbol}_{kind}.response'
            (self.out / name).write_bytes(raw)
            rec.update(raw_file=name, sha256=sha(raw))
            if rec['http_status'] != 200:
                raise ValueError('HTTP ' + str(rec['http_status']) + '; stopped without retry')
            try:
                payload = json.loads(raw)
            except (ValueError, UnicodeError):
                raise ValueError('Non-JSON response; no market data accepted') from None
            response(payload, rec['received_ms'])
            rec['accepted_api_response'] = True
            self.cache[url] = rec
            print(f'Saved request {index + 1}: {symbol} {kind}', flush=True)
            return payload, rec['received_ms']
        except (Exception, KeyboardInterrupt) as error:
            rec['error'] = type(error).__name__ + ': ' + str(error)
            raise
        finally:
            self.last_request = time.monotonic()
            rec['elapsed_seconds'] = self.last_request - started
            write(self.out / 'session.json', self.state)


def package(out):
    target = out.with_suffix('.zip')
    temp = target.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(out.iterdir()):
            if path.name in ('session.json', 'protocol.json', 'summary.json') or path.suffix == '.response':
                z.write(path, path.name)
    temp.replace(target)
    return target


def collect(out, protocol_raw=None, source_hashes=None):
    protocol_raw = PROTOCOL.read_bytes() if protocol_raw is None else protocol_raw
    source_hashes = sources() if source_hashes is None else source_hashes
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    lock = out.parent / (out.name + '.lock')
    with lock.open('x', encoding='ascii') as f:
        f.write('Collector active. Remove only if no collector process is running.\n')
    result = {'schema': 'bybit_history_013_collection_v1', 'status': 'INTERRUPTED_OR_INVALID',
              'protocol_sha256': sha(protocol_raw), 'orders': 0, 'private_api_calls': 0}
    try:
        protocol = json.loads(protocol_raw)
        _, end = validate_protocol(protocol)
        if end > int(time.time() * 1000):
            raise ValueError('Requested history extends into the future')
        s = Session(out, protocol_raw, source_hashes)
        validation, _ = assemble(protocol, s.get)
        if s.used != set(s.cache):
            raise ValueError('Extra successful requests outside deterministic plan')
        result.update(status=validation['status'], validation=validation,
                      total_request_attempts=len(s.state['requests']), successful_pages=len(s.cache))
    except (Exception, KeyboardInterrupt) as error:
        result['error'] = type(error).__name__ + ': ' + str(error)
        print(result['error'], flush=True)
    finally:
        # A protocol/source mismatch never rewrites existing collection metadata.
        existing = json.loads((out / 'session.json').read_bytes()) if (out / 'session.json').exists() else None
        if existing is None or (existing.get('protocol_sha256') == sha(protocol_raw) and existing.get('source_hashes') == source_hashes):
            result['completed_utc'] = datetime.now(timezone.utc).isoformat()
            write(out / 'summary.json', result)
        archive = package(out)
        lock.unlink()
        print('Status: ' + result['status'], flush=True)
        print('Upload this evidence ZIP: ' + str(archive.resolve()), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'bybit_history_013')
    args = parser.parse_args()
    try:
        result = collect(args.output)
    except FileExistsError:
        parser.exit(2, 'Collector lock exists. Close the other collector first.\n')
    sys.exit(0 if result['status'] == 'COMPLETE' else 2)
