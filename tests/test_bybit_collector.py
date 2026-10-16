"""Network-free end-to-end checks of the portable public collector."""
import importlib.util,json,subprocess,sys,urllib.parse,zipfile
from pathlib import Path
_fs=importlib.util.spec_from_file_location('depth_test_fixtures',Path(__file__).with_name('test_bybit_discovery.py'))
_fm=importlib.util.module_from_spec(_fs);_fs.loader.exec_module(_fm)
fixture,NOW=_fm.fixture,_fm.NOW

PATH=Path(__file__).resolve().parents[1]/'scripts/collect_bybit_public_v2.py'
spec=importlib.util.spec_from_file_location('bybit_portable',PATH)
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)


def test_portable_has_no_site_package_dependency():
    r=subprocess.run([sys.executable,'-S',str(PATH),'--help'],capture_output=True,text=True)
    assert r.returncode==0


class Reply:
    status=200
    def __init__(self,raw):self.raw=raw
    def read(self,n):return self.raw[:n]
    def __enter__(self):return self
    def __exit__(self,*a):pass


def test_html_failure_retained_and_stops(monkeypatch,tmp_path):
    calls=[]
    class Opener:
        def open(self,req,timeout):
            calls.append(req);return Reply(b'<html>Site Unavailable</html>')
    monkeypatch.setattr(c.urllib.request,'build_opener',lambda *a:Opener())
    out=tmp_path/'blocked';r=c.collect(out,1)
    assert r['status']=='BLOCKED_OR_INVALID_DATA' and r['valid_snapshot_count']==0
    assert len(calls)==1 and calls[0].get_method()=='GET'
    records=json.loads((out/'requests.json').read_text())
    assert records[0]['http_status']==200 and 'Non-JSON' in records[0]['error']
    assert (out/records[0]['raw_file']).read_bytes()==b'<html>Site Unavailable</html>'
    with zipfile.ZipFile(out.with_suffix('.zip')) as z:assert z.testzip() is None


def test_synthetic_full_collection_never_private_or_orders(monkeypatch,tmp_path):
    calls=[]
    class Opener:
        def open(self,req,timeout):
            url=urllib.parse.urlparse(req.full_url);q=urllib.parse.parse_qs(url.query);symbol=q['symbol'][0]
            calls.append(req)
            p,b=fixture();p['symbol']=symbol;b['result']['s']=symbol
            if url.path.endswith('instruments-info'):r={'category':'linear','list':[p]}
            elif url.path.endswith('funding/history'):
                r={'category':'linear','list':[{'symbol':symbol,'fundingRate':'.0001','fundingRateTimestamp':str(NOW-1000)}]}
            elif url.path.endswith('tickers'):
                r={'category':'linear','list':[{'symbol':symbol,'markPrice':'100','indexPrice':'100','fundingRate':'.0001','nextFundingTime':str(NOW+1000)}]}
            elif url.path.endswith('orderbook'):r=b['result']
            else:raise AssertionError('Unexpected endpoint')
            return Reply(json.dumps({'retCode':0,'time':NOW,'result':r}).encode())
    monkeypatch.setattr(c.urllib.request,'build_opener',lambda *a:Opener())
    monkeypatch.setattr(c.time,'time',lambda:NOW/1000)
    r=c.collect(tmp_path/'synthetic',1)
    assert r['status']=='COLLECTED_PUBLIC_SNAPSHOTS'
    assert r['valid_snapshot_count']==3 and r['unique_book_timestamps']==3
    assert len(calls)==12
    assert all(x.get_method()=='GET' and '/v5/market/' in x.full_url for x in calls)
    assert all(not any('BAPI' in k.upper() for k in x.headers) for x in calls)
    assert r['actual_order_fills']==0 and r['private_api_calls']==0
