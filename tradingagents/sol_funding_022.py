"""Additive022 SOL archive schedule contract. Frozen021 remains unchanged.

Exact observed schedule, not an inference that interval labels describe elapsed
settlement intervals. No rates aggregated or invented. See SOL_FUNDING_022.json.
"""
import csv,gzip,hashlib,io,json,re,zipfile
from decimal import Decimal as D,localcontext
from pathlib import Path
import pandas as pd
from tradingagents.bybit_history import DAY,HOUR,utc_ms,daily_trade
from tradingagents import bybit_replay as inherited

SYMBOLS=('SOLUSDT',)
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

def parse_bars(rows,*,kind,start,end,allow_gaps=False):
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
    actual=[int(r[0]) for r in out]; expected=list(range(start,end,HOUR))
    if actual!=sorted(set(actual)) or not set(actual)<=set(expected) or (not allow_gaps and actual!=expected):raise ValueError('Missing/duplicate/out-of-window hourly candles')
    return out

def recover_bars(monthly, supplements, *, kind, start, end):
    """Fill only absent timestamps using authenticated official daily rows.
    Exact decimal equality required at every overlap. Never interpolate or
    overwrite a conflicting observed bar. Final grid must still be complete.
    """
    base=parse_bars(monthly,kind=kind,start=start,end=end,allow_gaps=True)
    merged={int(r[0]):r for r in base};added=overlap=0
    for day,rows in supplements:
        parsed=parse_bars(rows,kind=kind,start=day,end=day+DAY)
        if not start<=day<end:raise ValueError('Supplement outside month')
        for row in parsed:
            ts=int(row[0])
            if ts in merged:
                if [D(x) for x in row[1:]]!=[D(x) for x in merged[ts][1:]]:raise ValueError('Conflicting official daily/monthly observation')
                overlap+=1
            else:merged[ts]=row;added+=1
    if sorted(merged)!=list(range(start,end,HOUR)):raise ValueError('Still missing hours after official daily recovery')
    return [merged[t] for t in sorted(merged)],{'added_hours':added,'matched_overlap_hours':overlap}

# The first2h-labelled event follows4h, and the return-to8h event follows8h.
# Boundaries are from preserved raw timestamps, frozen before strategy PnL.
TRANSITION4=utc_ms('2022-11-09T20:00:00Z')
TRANSITION2=utc_ms('2022-11-10T04:00:00Z')
RETURN8=utc_ms('2022-11-18T16:00:00Z')
LAST2=utc_ms('2022-11-18T08:00:00Z')

def expected_schedule(start,end):
    if type(start) is not int or type(end) is not int or start>=end or start%HOUR or end%HOUR:
        raise ValueError('Invalid schedule window')
    out=[]
    for t in range(start,end,HOUR):
        if t<TRANSITION4 or t>=RETURN8:
            if t%(8*HOUR)==0:out.append((t,8))
        elif t<TRANSITION2:
            if (t-TRANSITION4)%(4*HOUR)==0:out.append((t,4))
        elif t<=LAST2 and (t-TRANSITION2)%(2*HOUR)==0:out.append((t,2))
    return out

def parse_funding(rows,*,start,end):
    """Exact archive-conditional schedule. Source timestamp/rate/label preserved.
    Events are within60seconds after an even-hour boundary; positions change
    only at01UTC or terminal end-1ms. Hour-open mark is an explicit proxy.
    """
    out=[]
    for row in rows:
        if len(row)!=3:raise ValueError('Malformed funding row')
        actual=integer(row[0]);slot=actual//HOUR*HOUR;interval=integer(row[1])
        if not 0<=actual-slot<60_000:raise ValueError('Funding clock offset exceeds frozen60second bound')
        rate=inherited.decimal(row[2])
        out.append({'timestamp_ms':slot,'source_timestamp_ms':actual,'rate':str(rate),'interval_hours':interval})
    if [(r['timestamp_ms'],r['interval_hours']) for r in out]!=expected_schedule(start,end):
        raise ValueError('Missing/duplicate/out-of-window funding or unexplained schedule transition')
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
    repairs={}; repair_records=[]; added_hours=overlap_hours=0
    for item in manifest.get('supplemental_daily',[]):
        if item['symbol'] not in symbols or item['kind'] not in ('klines','markPriceKlines') or not re.fullmatch(r'202[2-5]-[0-9]{2}-[0-9]{2}',item['day']):raise ValueError('Unregistered daily recovery')
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
        d['funding'].sort(key=lambda x:x['timestamp_ms']);assert [(x['timestamp_ms'],x['interval_hours']) for x in d['funding']]==expected_schedule(START,END)
    audit={'status':'COMPLETE','venue':'Binance USD-M perpetual','manifest_sha256':expected_manifest_sha,'archives':len(files),'daily_recovery_archives':len(repair_records),'recovered_real_hours':added_hours,'matched_overlap_hours':overlap_hours,'start_ms':START,'end_exclusive_ms':END,'max_funding_clock_offset_ms':max_offset,'per_symbol':{p:{'trade_hours':len(d['trade']),'mark_hours':len(d['mark']),'funding_events':len(d['funding'])} for p,d in data.items()},'execution_rules':RULES_NOTE,'no_price_imputation':True,'strategy_pnl_computed':False,'funding_completeness':'Exact observed piecewise archive schedule; not independent API confirmation','funding_interval_labels':{str(h):sum(x['interval_hours']==h for d in data.values() for x in d['funding']) for h in (2,4,8)}}
    return data,audit

def prepare(data,symbol):
    if symbol not in SYMBOLS:raise ValueError('Unsupported symbol')
    times=[int(x[0]) for x in data['trade']];other=[int(x[0]) for x in data['mark']]
    if not times or times!=other or times!=list(range(times[0],times[-1]+HOUR,HOUR)) or times[0]%DAY or len(times)%24:raise ValueError('Normalized hourly grid mismatch')
    start,end=times[0],times[-1]+HOUR
    expected=expected_schedule(start,end);fund=data['funding']
    if [(f['timestamp_ms'],f['interval_hours']) for f in fund]!=expected:raise ValueError('Normalized funding grid mismatch')
    for f in fund:
        if not 0<=f['source_timestamp_ms']-f['timestamp_ms']<60_000:raise ValueError('Funding alignment changed')
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
    result['funding_timestamp_note']='Raw source timestamps retained in pinned normalized inputs; events within60seconds after boundary mapped to frozen observed even-hour slots with unchanged held quantity. Hour-open mark valuation is a proxy.'
    result['cost_note']='5.5bpsfee+2bpsslippage per side baseline;10+10stress. Explicit comparable scenarios,not verified personal/historical Binance fees.'
    return result

make_signals=inherited.make_signals
select_training=inherited.select_training
evaluation_gate=inherited.evaluation_gate
audit_wealth=inherited.audit_wealth

