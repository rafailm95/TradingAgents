"""Hash-pinned offline old/new calendar bridge; no model fitting or network."""
import gzip,json
from pathlib import Path
from tradingagents import binance_assets_021 as old
from tradingagents import sol_funding_022 as sol
from tradingagents import futures_extension_023 as extension
from tradingagents.bybit_history import HOUR,DAY,utc_ms
START=old.START
SPLIT=extension.START
END=extension.END
TRAIN_START=utc_ms('2023-01-01T00:00:00Z')
SYMBOLS=old.SYMBOLS

def join_data(prior,new,symbol):
    if symbol not in SYMBOLS:raise ValueError('Unauthorized asset')
    for data,a,b in ((prior,START,SPLIT),(new,SPLIT,END)):
        for kind in ('trade','mark'):
            if [int(r[0]) for r in data[kind]]!=list(range(a,b,HOUR)):
                raise ValueError('Calendar boundary/gap/overlap')
        expected=sol.expected_schedule(a,b) if symbol=='SOLUSDT' and a==START else [(t,8) for t in range(a,b,8*HOUR)]
        if [(r['timestamp_ms'],r['interval_hours']) for r in data['funding']]!=expected:raise ValueError('Funding calendar boundary/schedule')
    merged={k:prior[k]+new[k] for k in ('trade','mark','funding')}
    # Revalidate all OHLC, volumes, rates and source-clock offsets independently.
    market=(sol if symbol=='SOLUSDT' else old).prepare(merged,symbol)
    if (market.start,market.end)!=(START,END):raise ValueError('Combined window mismatch')
    return merged,market

def load_part(root,symbol,record,schema):
    root=Path(root)/symbol
    for filename,key in (('normalized.json.gz','normalized_sha256'),('manifest.json','manifest_sha256')):
        if old.sha(root/filename)!=record[key]:raise ValueError('Input pin mismatch: '+symbol+'/'+filename)
    value=json.loads(gzip.decompress((root/'normalized.json.gz').read_bytes()))
    if value['schema']!=schema or set(value['datasets'])!={symbol} or value['audit']['status']!='COMPLETE':raise ValueError('Input identity mismatch')
    if value['audit']['manifest_sha256']!=record['manifest_sha256']:raise ValueError('Embedded manifest mismatch')
    return value['datasets'][symbol]

def load_market(prior_root,new_root,symbol,pin):
    record=pin['inputs'][symbol]
    schema='binance022_normalized_v1' if symbol=='SOLUSDT' else 'binance021_normalized_v1'
    prior=load_part(prior_root,symbol,record['prior'],schema)
    new=load_part(new_root,symbol,record['extension'],'binance023_extension_v1')
    return join_data(prior,new,symbol)[1]
