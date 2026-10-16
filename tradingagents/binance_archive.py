"""Strict native Binance archive adapter. Never represents data as Bybit inputs."""
import csv,gzip,hashlib,io,json,re,zipfile
from decimal import Decimal as D,localcontext
from pathlib import Path
import pandas as pd
from tradingagents.bybit_history import DAY,HOUR,utc_ms,daily_trade
from tradingagents import bybit_replay as inherited

SYMBOLS=('BTCUSDT','ETHUSDT','LTCUSDT')
START=utc_ms('2022-01-01T00:00:00Z'); END=utc_ms('2026-01-01T00:00:00Z')
RULES_NOTE='Hypothetical fine-lot execution assumptions, NOT current or historical Binance order filters. Public exchangeInfo returned451; no bypass or inferred filters.'
# Explicit research assumptions, not inferred from prices or a different venue.
RULES=inherited.Rules(D('0.00000001'),D('0.00000001'),D('1000000000'),D('0.01'),D('0.00000001'))
CANDIDATES=inherited.CANDIDATES
COSTS=inherited.COSTS

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def csv_rows(raw,filename):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos=z.infolist()
        if len(infos)!=1 or infos[0].filename!=filename or infos[0].file_size>15_000_000 or z.testzip():raise ValueError('Invalid archive structure/CRC')
        text=z.read(infos[0]).decode('utf-8-sig')
    rows=list(csv.reader(io.StringIO(text)))
    if not rows or any(not r for r in rows):raise ValueError('Empty CSV row')
    if rows[0][0] in ('open_time','calc_time'):rows=rows[1:]
    return rows

def integer(value):
    if not re.fullmatch(r'[0-9]+',str(value)):raise ValueError('Invalid unsigned integer')
    return int(value)

def parse_bars(rows,*,kind,start,end):
    out=[]
    if kind not in ('klines','markPriceKlines'):raise ValueError('Unknown candle type')
    for row in rows:
        if len(row)!=12:raise ValueError('Expected12Binance kline columns')
        ts=integer(row[0]);closed=integer(row[6])
        if ts%HOUR or closed!=ts+HOUR-1:raise ValueError('Wrong timestamp unit/close or incomplete bar')
        o,h,l,c=[inherited.decimal(v,positive=True) for v in row[1:5]]
        if not l<=min(o,c)<=max(o,c)<=h:raise ValueError('Invalid OHLC')
        if any(inherited.decimal(row[i])<0 for i in (5,7,9,10)) or integer(row[8])<0:raise ValueError('Invalid volume/count')
        out.append([str(ts),*row[1:5],row[5],row[7]])
    if [int(r[0]) for r in out]!=list(range(start,end,HOUR)):raise ValueError('Missing/duplicate/out-of-window hourly candles')
    return out

def parse_funding(rows,*,start,end):
    """Normalize only documented bounded clock jitter, preserving exact raw time.

    Positions can change only at01UTC and terminal end-1ms; all actual events
    must occur within60seconds AFTER00/08/16UTC. Thus no position crosses the
    normalization interval. Mark at the hour open remains an explicit proxy.
    """
    out=[]
    for row in rows:
        if len(row)!=3 or integer(row[1])!=8:raise ValueError('Changed funding cadence or malformed row')
        actual=integer(row[0]);slot=actual//(8*HOUR)*(8*HOUR)
        if not 0<=actual-slot<60_000:raise ValueError('Funding clock offset exceeds frozen60second bound')
        rate=inherited.decimal(row[2])
        out.append({'timestamp_ms':slot,'source_timestamp_ms':actual,'rate':str(rate),'interval_hours':8})
    if [r['timestamp_ms'] for r in out]!=list(range(start,end,8*HOUR)):raise ValueError('Missing/duplicate/out-of-window funding events')
    return out

def month_bounds(period):
    if not re.fullmatch(r'202[2-5]-(0[1-9]|1[0-2])',period):raise ValueError('Unregistered archive month')
    start=pd.Timestamp(period+'-01',tz='UTC');end=start+pd.offsets.MonthBegin(1)
    return int(start.timestamp()*1000),int(end.timestamp()*1000)

def audit_raw(root,expected_manifest_sha):
    root=Path(root)
    if sha(root/'manifest.json')!=expected_manifest_sha:raise ValueError('Raw manifest pin mismatch')
    manifest=json.loads((root/'manifest.json').read_bytes())
    symbols=manifest['symbols']
    if not symbols or len(set(symbols))!=len(symbols) or not set(symbols)<=set(SYMBOLS):raise ValueError('Invalid manifest symbols')
    expected={(p,k,f'{y}-{m:02d}') for p in symbols for k in ('klines','markPriceKlines','fundingRate') for y in range(2022,2026) for m in range(1,13)}
    files=manifest['files'];keys=[(r['symbol'],r['kind'],r['period']) for r in files]
    if set(keys)!=expected or len(keys)!=len(expected):raise ValueError('Incomplete/duplicate archive inventory for the declared assets')
    data={p:{'trade':[],'mark':[],'funding':[]} for p in symbols};max_offset=0
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
        else:data[p]['trade' if k=='klines' else 'mark'].extend(parse_bars(rows,kind=k,start=a,end=b))
    for p,d in data.items():
        for k in ('trade','mark'):d[k].sort(key=lambda x:int(x[0]));assert [int(x[0]) for x in d[k]]==list(range(START,END,HOUR))
        d['funding'].sort(key=lambda x:x['timestamp_ms']);assert [x['timestamp_ms'] for x in d['funding']]==list(range(START,END,8*HOUR))
    audit={'status':'COMPLETE','venue':'Binance USD-M perpetual','manifest_sha256':expected_manifest_sha,'archives':len(files),'start_ms':START,'end_exclusive_ms':END,'max_funding_clock_offset_ms':max_offset,'per_symbol':{p:{'trade_hours':len(d['trade']),'mark_hours':len(d['mark']),'funding_events':len(d['funding'])} for p,d in data.items()},'execution_rules':RULES_NOTE,'no_price_imputation':True,'strategy_pnl_computed':False}
    return data,audit

def prepare(data,symbol):
    if symbol not in SYMBOLS:raise ValueError('Unsupported symbol')
    times=[int(x[0]) for x in data['trade']];other=[int(x[0]) for x in data['mark']]
    if not times or times!=other or times!=list(range(times[0],times[-1]+HOUR,HOUR)) or times[0]%DAY or len(times)%24:raise ValueError('Normalized hourly grid mismatch')
    start,end=times[0],times[-1]+HOUR
    expected=list(range(start,end,8*HOUR));fund=data['funding']
    if [f['timestamp_ms'] for f in fund]!=expected:raise ValueError('Normalized funding grid mismatch')
    for f in fund:
        if f['interval_hours']!=8 or not 0<=f['source_timestamp_ms']-f['timestamp_ms']<60_000:raise ValueError('Funding alignment changed')
    parsed={}
    for kind in ('trade','mark'):
        bars=[]
        for r in data[kind]:
            if len(r)!=7:raise ValueError('Normalized candle shape mismatch')
            o,h,l,c=[inherited.decimal(v,positive=True) for v in r[1:5]]
            if not l<=min(o,c)<=max(o,c)<=h or any(inherited.decimal(v)<0 for v in r[5:]):raise ValueError('Normalized OHLCV invalid')
            bars.append((o,h,l,c))
        parsed[kind]=tuple(bars)
    with localcontext() as ctx:
        ctx.prec=128;daily=daily_trade(data['trade'])
    frame=pd.DataFrame(daily,columns=['Date','Open','High','Low','Close','Volume','Turnover'])
    frame['Date']=pd.to_datetime(frame.Date.astype('int64'),unit='ms',utc=True)
    for k in frame.columns[1:]:frame[k]=frame[k].astype(float)
    return inherited.Market(symbol,start,end,parsed['trade'],parsed['mark'],{f['timestamp_ms']:inherited.decimal(f['rate']) for f in fund},RULES,frame)

def replay(market,start,end,**kwargs):
    result=inherited.replay(market,start,end,**kwargs)
    result['schema']='binance_perpetual_017_v1';result['venue']='Binance USD-M perpetual'
    result['classification']='Exploratory Binance historical simulation with funding and mark proxies; NOT Bybit data, current-filter validation or actual execution.'
    result['execution_rules_note']=RULES_NOTE
    result['current_rule_proxies_field_meaning']='Inherited field name; values are frozen hypothetical fine-lot assumptions, not observed exchange filters.'
    result['funding_timestamp_note']='Raw source timestamps retained in pinned normalized inputs; events within60seconds after boundary mapped to nominal00/08/16UTC with unchanged held quantity. Hour-open mark valuation is a proxy.'
    result['cost_note']='5.5bpsfee+2bpsslippage per side baseline;10+10stress. Explicit comparable scenarios,not verified personal/historical Binance fees.'
    return result

make_signals=inherited.make_signals
select_training=inherited.select_training
evaluation_gate=inherited.evaluation_gate
audit_wealth=inherited.audit_wealth
