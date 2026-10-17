"""Bounded future-date collection contract on synthetic bytes; no market PnL."""
import io,zipfile,hashlib,json
from pathlib import Path
import pytest
from tradingagents import futures_extension_023 as b
from scripts import collect_futures_extension_023 as c

@pytest.mark.parametrize('symbol',b.SYMBOLS)
def test_exact_nine_complete_month_inventory(symbol):
    items=list(c.specs(symbol));assert len(items)==27
    assert len({x['url'] for x in items})==27
    assert all(x['period'].startswith('2026-') and x['url'].startswith(c.BASE+'monthly/') for x in items)
    assert (items[0]['period'],items[-1]['period'])==('2026-01','2026-09')
    assert sum((b.month_bounds(f'2026-{m:02d}')[1]-b.month_bounds(f'2026-{m:02d}')[0])//b.HOUR for m in range(1,10))==6552

@pytest.mark.parametrize('month',['2025-12','2026-00','2026-10','2026-13','2027-01'])
def test_unregistered_or_incomplete_month_rejected(month):
    with pytest.raises(ValueError):b.month_bounds(month)

def test_changed2026funding_cadence_is_not_silently_accepted():
    with pytest.raises(ValueError,match='cadence'):b.parse_funding([[str(b.START),'4','.0001']],start=b.START,end=b.START+8*b.HOUR)
    with pytest.raises(ValueError,match='Missing'):b.parse_funding([],start=b.START,end=b.START+8*b.HOUR)

def test_official_checksum_and_cache_identity(tmp_path,monkeypatch):
    item=next(c.specs('SOLUSDT'));name=Path(item['relative']).name;buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w') as z:z.writestr(name[:-4]+'.csv','open_time,open\n1,2\n')
    raw=buf.getvalue();check=(hashlib.sha256(raw).hexdigest()+'  '+name+'\n').encode();calls=[]
    def get(url,*args):calls.append(url);return check if url.endswith('CHECKSUM') else raw
    monkeypatch.setattr(c,'fetch',get);saved=c.one(tmp_path,item,{})
    assert saved['published_checksum_verified'] and len(calls)==2
    assert c.one(tmp_path,item,{})==saved and len(calls)==2
    (tmp_path/item['relative']).write_bytes(b'tampered')
    with pytest.raises(ValueError,match='Cache'):c.one(tmp_path,item,{})

def test_access_block_stops_asset_once_and_preserves_failure(tmp_path,monkeypatch):
    calls=[]
    def fail(*a):calls.append(a);raise ValueError('HTTP451')
    monkeypatch.setattr(c,'one',fail);root=tmp_path/'BTCUSDT';r=c.collect_symbol(root,'BTCUSDT',{})
    assert len(calls)==1 and r['status']=='BLOCKED_OR_INCOMPLETE' and r['new_strategy_simulations']==0
    assert json.loads((root/'stopped.json').read_bytes())==r
    with pytest.raises(ValueError,match='New output'):c.collect_symbol(root,'BTCUSDT',{})
    assert len(calls)==1

def test_wrong_manifest_pin_rejected_before_archive_access(tmp_path):
    (tmp_path/'manifest.json').write_text('{}')
    with pytest.raises(ValueError,match='pin mismatch'):b.audit_raw(tmp_path,'0'*64)
