"""Native Binance integrity, bounded funding clock mapping and unchanged ledger."""
import copy,hashlib,io,json,zipfile
from decimal import Decimal as D
from pathlib import Path
import pytest
from tradingagents import binance_archive as b
from tradingagents.bybit_history import HOUR,DAY
from tests.test_bybit_replay import dataset,signals,FIRST
from scripts import collect_binance_archive_017 as collector


def native():
    source=dataset()
    return {'trade':source['trade'],'mark':[r+['0','0'] for r in source['mark']],
            'funding':[{'timestamp_ms':int(r['fundingRateTimestamp']),'source_timestamp_ms':int(r['fundingRateTimestamp'])+7,'rate':r['fundingRate'],'interval_hours':8} for r in source['funding']]}


def row(ts):return [str(ts),'100','101','99','100','2',str(ts+HOUR-1),'200','5','1','100','0']


def test_parse_native_prices_and_volume_fields():
    out=b.parse_bars([row(b.START),row(b.START+HOUR)],kind='klines',start=b.START,end=b.START+2*HOUR)
    assert out[0]==[str(b.START),'100','101','99','100','2','200']


@pytest.mark.parametrize('problem',['microseconds','close','missing','duplicate','ohlc','nan','negative_volume'])
def test_bad_candle_data_rejected(problem):
    rows=[row(b.START),row(b.START+HOUR)]
    if problem=='microseconds':rows[0][0]=str(b.START*1000)
    elif problem=='close':rows[0][6]=str(b.START+HOUR)
    elif problem=='missing':rows.pop()
    elif problem=='duplicate':rows[1]=rows[0]
    elif problem=='ohlc':rows[0][2]='98'
    elif problem=='nan':rows[0][4]='NaN'
    else:rows[0][5]='-1'
    with pytest.raises(ValueError):b.parse_bars(rows,kind='klines',start=b.START,end=b.START+2*HOUR)


@pytest.mark.parametrize('offset',[0,2,59999])
def test_funding_clock_mapping_retains_actual_timestamp(offset):
    out=b.parse_funding([[str(b.START+offset),'8','.0001']],start=b.START,end=b.START+8*HOUR)
    assert out==[{'timestamp_ms':b.START,'source_timestamp_ms':b.START+offset,'rate':'0.0001','interval_hours':8}]


@pytest.mark.parametrize('problem',['late','before','cadence','missing','duplicate','nan'])
def test_funding_gaps_or_unbounded_mapping_rejected(problem):
    rows=[[str(b.START),'8','.0001']]
    if problem=='late':rows[0][0]=str(b.START+60000)
    elif problem=='before':rows[0][0]=str(b.START-1)
    elif problem=='cadence':rows[0][1]='4'
    elif problem=='missing':rows=[]
    elif problem=='duplicate':rows*=2
    else:rows[0][2]='NaN'
    with pytest.raises(ValueError):b.parse_funding(rows,start=b.START,end=b.START+8*HOUR)


def test_native_preparation_needs_no_fake_bybit_instrument():
    m=b.prepare(native(),'BTCUSDT')
    assert m.rules==b.RULES and len(m.frame)==204
    assert m.frame.Volume.iloc[0]==48
    assert 'NOT current' in b.RULES_NOTE


def test_replay_label_funding_and_independent_cash_oracle():
    m=b.prepare(native(),'BTCUSDT');s=signals(m)
    r=b.replay(m,FIRST,m.end,candidate=b.CANDIDATES[0],prepared_signals=s)
    assert r['venue']=='Binance USD-M perpetual' and r['schema']=='binance_perpetual_017_v1'
    assert r['independent_wealth_audit']['status']=='PASS'
    held=[f for f in r['funding_events'] if D(f['quantity_before'])]
    q=D(r['fills'][0]['quantity'])
    assert len(held)==11 and all(D(f['cashflow_usdt'])==-q*100*D('.0001') for f in held)
    assert r['fills'][0]['timestamp_ms']==FIRST+HOUR
    assert all(f['timestamp_ms']%DAY in (0,8*HOUR,16*HOUR) for f in held)
    with b.localcontext() as ctx:
        ctx.prec=128
        metric=r['metrics'];expected=D(10000)+D(metric['realized_price_pnl_usdt'])+D(metric['funding_usdt'])-D(metric['fees_usdt'])-D(metric['operating_expense_usdt'])
        assert D(metric['final_cash_usdt'])==expected


def test_normalized_bad_alignment_is_rejected():
    d=native();d['mark'].pop()
    with pytest.raises(ValueError):b.prepare(d,'BTCUSDT')


def test_collector_published_checksum_and_cache_tamper(tmp_path,monkeypatch):
    item=next(collector.specs());name=Path(item['relative']).name
    mem=io.BytesIO()
    with zipfile.ZipFile(mem,'w') as z:z.writestr(name[:-4]+'.csv','open_time,open\n1,2\n')
    raw=mem.getvalue();checksum=(hashlib.sha256(raw).hexdigest()+'  '+name+'\n').encode()
    monkeypatch.setattr(collector,'fetch',lambda url,limit:checksum if url.endswith('.CHECKSUM') else raw)
    result=collector.one(tmp_path,item)
    assert result['published_checksum_verified']
    assert collector.one(tmp_path,item)==result
    (tmp_path/item['relative']).write_bytes(b'changed')
    with pytest.raises(ValueError):collector.one(tmp_path,item)


def test_collector_refuses_wrong_checksum_before_writing(tmp_path,monkeypatch):
    monkeypatch.setattr(collector,'fetch',lambda url,limit:b'bad')
    with pytest.raises(ValueError):collector.one(tmp_path,next(collector.specs()))
    assert not list(tmp_path.rglob('*.zip'))


def test_stopped_capture_never_automatically_retries(tmp_path,monkeypatch):
    (tmp_path/'coverage-stop.json').write_text('{}')
    monkeypatch.setattr(collector,'fetch',lambda *args:pytest.fail('network must not be called'))
    with pytest.raises(ValueError,match='Stopped attempt'):collector.run(tmp_path,('LTCUSDT',))


def test_normalized_archive_identity_hash_and_empty_assets(tmp_path):
    import gzip
    from scripts.run_binance_replay_017 import load_archive
    path=tmp_path/'input.gz'
    payload={'schema':'binance017_normalized_v1','audit':{'status':'COMPLETE','venue':'Binance USD-M perpetual'},'datasets':{}}
    path.write_bytes(gzip.compress(json.dumps(payload).encode()))
    with pytest.raises(ValueError,match='pin mismatch'):load_archive(path,'0'*64)
    with pytest.raises(ValueError,match='Wrong normalized'):load_archive(path,hashlib.sha256(path.read_bytes()).hexdigest())
    payload['datasets']={'ETHUSDT':{}}
    path.write_bytes(gzip.compress(json.dumps(payload).encode()))
    audit,data=load_archive(path,hashlib.sha256(path.read_bytes()).hexdigest())
    assert set(data)=={'ETHUSDT'} and audit['venue']=='Binance USD-M perpetual'
