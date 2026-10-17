"""Additive023 new-date archive audit; no modification of old sources or inputs."""
import hashlib,json,re
from pathlib import Path
import pandas as pd
from tradingagents.binance_assets_021 import (SYMBOLS,RULES_NOTE,sha,csv_rows,
    parse_bars,recover_bars,parse_funding)
from tradingagents.bybit_history import utc_ms,HOUR,DAY
START=utc_ms('2026-01-01T00:00:00Z')
END=utc_ms('2026-10-01T00:00:00Z')
def month_bounds(period):
    if not re.fullmatch(r'2026-0[1-9]',period):raise ValueError('Unregistered archive month')
    start=pd.Timestamp(period+'-01',tz='UTC');end=start+pd.offsets.MonthBegin(1)
    return int(start.timestamp()*1000),int(end.timestamp()*1000)

def audit_raw(root,expected_manifest_sha):
    root=Path(root)
    if sha(root/'manifest.json')!=expected_manifest_sha:raise ValueError('Raw manifest pin mismatch')
    manifest=json.loads((root/'manifest.json').read_bytes())
    symbols=manifest['symbols']
    if not symbols or len(set(symbols))!=len(symbols) or not set(symbols)<=set(SYMBOLS):raise ValueError('Invalid manifest symbols')
    expected={(p,k,f'{y}-{m:02d}') for p in symbols for k in ('klines','markPriceKlines','fundingRate') for y in (2026,) for m in range(1,10)}
    files=manifest['files'];keys=[(r['symbol'],r['kind'],r['period']) for r in files]
    if set(keys)!=expected or len(keys)!=len(expected):raise ValueError('Incomplete/duplicate archive inventory for the declared assets')
    data={p:{'trade':[],'mark':[],'funding':[]} for p in symbols};max_offset=0
    repairs={}; repair_records=[]; added_hours=overlap_hours=0
    for item in manifest.get('supplemental_daily',[]):
        if item['symbol'] not in symbols or item['kind'] not in ('klines','markPriceKlines') or not re.fullmatch(r'2026-0[1-9]-[0-9]{2}',item['day']):raise ValueError('Unregistered daily recovery')
        name=f"{item['symbol']}-1h-{item['day']}.zip";rel='daily-repairs/'+item['kind']+'/'+name
        url=f"https://data.binance.vision/data/futures/um/daily/{item['kind']}/{item['symbol']}/1h/{name}"
        if item['relative']!=rel or item['url']!=url or item['status']!='VERIFIED':raise ValueError('Invalid recovery provenance')
        path=root/rel;check=Path(str(path)+'.CHECKSUM')
        if sha(path)!=item['sha256'] or sha(check)!=item['checksum_sha256'] or check.read_text().split()!=[item['sha256'],name]:raise ValueError('Daily recovery hash mismatch')
        day=utc_ms(item['day']+'T00:00:00Z');key=(item['symbol'],item['kind'],item['day'][:7])
        if any(d==day for d,_ in repairs.get(key,[])):raise ValueError('Duplicate recovery day')
        repairs.setdefault(key,[]).append((day,csv_rows(path.read_bytes(),name[:-4]+'.csv')))
        repair_records.append(item)
    for item in sorted(files,key=lambda r:r['relative']):
        p,k,period=item['symbol'],item['kind'],item['period']
        name=f'{p}-fundingRate-{period}.zip' if k=='fundingRate' else f'{p}-1h-{period}.zip'
        rel=f'{k}/{p}/'+('' if k=='fundingRate' else '1h/')+name
        if item['relative']!=rel or item['url']!='https://data.binance.vision/data/futures/um/monthly/'+rel:raise ValueError('Unexpected source/path')
        raw=(root/rel).read_bytes();check=Path(str(root/rel)+'.CHECKSUM').read_bytes()
        if len(raw)>5_000_000 or hashlib.sha256(raw).hexdigest()!=item['sha256'] or hashlib.sha256(check).hexdigest()!=item['checksum_sha256']:raise ValueError('Archive/checksum hash mismatch')
        parts=check.decode().split()
        if parts!=[item['sha256'],name]:raise ValueError('Published checksum content mismatch')
        rows=csv_rows(raw,name[:-4]+'.csv');a,b=month_bounds(period)
        if k=='fundingRate':
            parsed=parse_funding(rows,start=a,end=b);data[p]['funding'].extend(parsed)
            max_offset=max(max_offset,max(x['source_timestamp_ms']-x['timestamp_ms'] for x in parsed))
        else:
            if (p,k,period) in repairs:
                bars,diagnostic=recover_bars(rows,repairs[(p,k,period)],kind=k,start=a,end=b)
                added_hours+=diagnostic['added_hours'];overlap_hours+=diagnostic['matched_overlap_hours']
            else:bars=parse_bars(rows,kind=k,start=a,end=b)
            data[p]['trade' if k=='klines' else 'mark'].extend(bars)
    for p,d in data.items():
        for k in ('trade','mark'):d[k].sort(key=lambda x:int(x[0]));assert [int(x[0]) for x in d[k]]==list(range(START,END,HOUR))
        d['funding'].sort(key=lambda x:x['timestamp_ms']);assert [x['timestamp_ms'] for x in d['funding']]==list(range(START,END,8*HOUR))
    audit={'status':'COMPLETE','venue':'Binance USD-M perpetual','manifest_sha256':expected_manifest_sha,'archives':len(files),'daily_recovery_archives':len(repair_records),'recovered_real_hours':added_hours,'matched_overlap_hours':overlap_hours,'start_ms':START,'end_exclusive_ms':END,'max_funding_clock_offset_ms':max_offset,'per_symbol':{p:{'trade_hours':len(d['trade']),'mark_hours':len(d['mark']),'funding_events':len(d['funding'])} for p,d in data.items()},'execution_rules':RULES_NOTE,'no_price_imputation':True,'strategy_pnl_computed':False}
    return data,audit

