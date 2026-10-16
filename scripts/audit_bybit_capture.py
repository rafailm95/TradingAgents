"""Offline audit of a user-provided public Bybit capture. No network or orders."""
import argparse,hashlib,json,math,statistics,sys,zipfile
from datetime import datetime,timezone
from decimal import Decimal as D
from pathlib import Path
from urllib.parse import urlparse,parse_qs
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tradingagents'))
from bybit_depth import analyze,instrument,response,funding_summary,parse_book

SYMBOLS=('BTCUSDT','ETHUSDT','LTCUSDT')
PATHS={'/v5/market/instruments-info':'instrument','/v5/market/funding/history':'funding',
       '/v5/market/tickers':'ticker','/v5/market/orderbook':'book'}


def require(ok,message):
    if not ok:raise ValueError(message)


def loads(raw):
    return json.loads(raw,parse_constant=lambda v:(_ for _ in ()).throw(ValueError('Non-finite JSON '+v)))


def load_archive(path,expected_sha):
    raw=Path(path).read_bytes();actual=hashlib.sha256(raw).hexdigest()
    require(actual==expected_sha,'Input archive hash mismatch')
    with zipfile.ZipFile(path) as z:
        infos=z.infolist();names=[i.filename for i in infos]
        require(len(names)==len(set(names)),'Duplicate archive entry')
        require(all(n and '/' not in n and '\\' not in n and n not in ('.','..') for n in names),'Non-flat archive')
        require(len(names)<=5000 and sum(i.file_size for i in infos)<=100_000_000,'Oversized archive')
        require(z.testzip() is None,'CRC mismatch')
        files={n:z.read(n) for n in names}
    return actual,files


def stats(values):
    v=sorted(float(x) for x in values)
    require(v and all(math.isfinite(x) for x in v),'Finite nonempty stats required')
    return {'min':v[0],'median':statistics.median(v),'max':v[-1]}


def utc(ms):return datetime.fromtimestamp(ms/1000,timezone.utc).isoformat()


def independent_sweep(levels,quantity):
    # Separate cumulative-depth intersection oracle, not engine's residual loop.
    cumulative=D(0);total=D(0)
    for price,size in levels:
        p,q=D(price),D(size)
        end=cumulative+q
        overlap=max(D(0),min(quantity,end)-cumulative)
        total+=overlap*p;cumulative=end
    require(cumulative>=quantity,'Oracle depth shortfall')
    return total


def audit(path,expected_sha):
    sha,files=load_archive(path,expected_sha)
    summary=loads(files['summary.json']);requests=loads(files['requests.json'])
    require(summary['host']=='https://api.bybit.com' and summary['category']=='linear','Wrong capture venue')
    require(summary['status']=='COLLECTED_PUBLIC_SNAPSHOTS','Capture incomplete')
    rounds=summary['rounds_requested'];require(type(rounds) is int and 1<=rounds<=60,'Invalid round count')
    require(summary['orders']==summary['private_api_calls']==summary['actual_order_fills']==0,'Unexpected execution claim')
    require(summary['capital_assumption_usdt']==10000 and summary['fee_bps_scenarios']==[5.5,10],'Unexpected research scenarios')
    grouped={s:{k:[] for k in PATHS.values()} for s in SYMBOLS};seen=set();latencies=[];api_ages=[]
    for rec in requests:
        url=urlparse(rec['url']);q=parse_qs(url.query)
        require(url.scheme=='https' and url.netloc=='api.bybit.com' and url.path in PATHS and not url.fragment,'Unexpected endpoint')
        require(q.get('category')==['linear'] and len(q.get('symbol',[]))==1,'Wrong category/symbol query')
        symbol=q['symbol'][0];require(symbol in grouped,'Unexpected symbol')
        kind=PATHS[url.path];allowed={'category','symbol'} | ({'limit'} if kind in ('book','funding') else set())
        require(set(q)<=allowed,'Unexpected request argument')
        if kind in ('book','funding'):require(q.get('limit')==[str(1000 if kind=='book' else 200)],'Wrong requested limit')
        require(rec['http_status']==200 and rec.get('accepted_api_response') is True and 'error' not in rec,'Rejected request')
        name=rec['raw_file'];require(name in files and name not in seen and name.endswith('.response'),'Missing/reused raw file')
        seen.add(name);raw=files[name]
        require(hashlib.sha256(raw).hexdigest()==rec['sha256'],'Raw payload hash mismatch')
        payload=loads(raw);received=rec['received_ms'];response(payload,received)
        request_ms=datetime.fromisoformat(rec['request_utc']).timestamp()*1000
        response_ms=datetime.fromisoformat(rec['response_utc']).timestamp()*1000
        require(request_ms<=received<=response_ms and 0<=rec['elapsed_seconds']<=30,'Invalid request timing')
        require(abs((response_ms-request_ms)/1000-rec['elapsed_seconds'])<.05,'Wall/monotonic duration mismatch')
        grouped[symbol][kind].append((payload,received,rec))
        latencies.append(rec['elapsed_seconds']);api_ages.append(received-int(payload['time']))
    require(set(files)==seen|{'summary.json','requests.json'},'Unreferenced archive entry')
    require(len(requests)==6+6*rounds,'Unexpected request count')
    require(len(summary['snapshots'])==3*rounds,'Missing snapshot rows')
    snapshot_map={(s['symbol'],s['round']):s for s in summary['snapshots']}
    require(len(snapshot_map)==3*rounds,'Duplicate snapshot summary')
    result={'input_sha256':sha,'input_provenance':'User-uploaded public API capture; internally reconciled, not independently signed by exchange',
      'status':'VALIDATED_LOCAL_CAPTURE','request_count':len(requests),'book_count':0,'funding_event_count':0,
      'scenario_recalculations':0,'independent_cash_oracles':0,'http_duration_seconds':stats(latencies),
      'response_age_at_capture_ms':stats(api_ages),'assets':{},'orders':0,'strategy_profit_measured':False}
    alltimes=[]
    for symbol,group in grouped.items():
        require(len(group['instrument'])==len(group['funding'])==1,'Metadata/funding count mismatch')
        require(len(group['ticker'])==len(group['book'])==rounds,'Ticker/book count mismatch')
        ip,it,_=group['instrument'][0];meta=instrument(ip,symbol,it)
        fp,ft,_=group['funding'][0];fs=funding_summary(fp,symbol,ft)
        require(fs==summary['funding'][symbol],'Funding summary mismatch')
        events=fp['result']['list'];ts=[int(x['fundingRateTimestamp']) for x in events]
        expected_ms=int(meta['fundingInterval'])*60000
        gaps=[a-b for a,b in zip(ts,ts[1:]) if a-b!=expected_ms]
        rates=[D(x['fundingRate']) for x in events]
        funding={**fs,'first_utc':utc(min(ts)),'last_utc':utc(max(ts)),
          'expected_interval_minutes_current_metadata':int(meta['fundingInterval']),
          'interval_anomalies':len(gaps),'rate_pct_range':stats(x*100 for x in rates),
          'positive_events':sum(x>0 for x in rates),'negative_events':sum(x<0 for x in rates),'zero_events':sum(x==0 for x in rates),
          'long_cost_pct_10000_equity':str(D(fs['sum_long_funding_paid_usdt'])/100),
          'last_event_long_cost_5000_usdt':str(rates[0]*5000)}
        rows=[];previous=None;ages=[];depth={b:{side:[] for side in ('bid','ask')} for b in (5,10,25,50)}
        complete={b:{side:0 for side in ('bid','ask')} for b in depth};scenarios={(n,f):[] for n in (1000,5000) for f in ('5.5','10')}
        for i,((bp,bt,br),(tp,tt,tr)) in enumerate(zip(group['book'],group['ticker']),1):
            record=snapshot_map[(symbol,i)]
            require(record['received_ms']==bt and record['ticker_received_ms']==tt,'Summary capture-time mismatch')
            book,levels=parse_book(bp,symbol,bt,meta['priceFilter']['tickSize'])
            identity=(int(book['ts']),int(book['u']),int(book['seq']))
            if previous:require(all(a>b for a,b in zip(identity,previous)),'Duplicate/regressing book identity')
            previous=identity;alltimes.append(identity[0]);ages.append(bt-int(book['cts']))
            ticker=tp['result'];require(ticker['category']=='linear' and len(ticker['list'])==1,'Ticker category/count')
            ticker=ticker['list'][0];require(ticker['symbol']==symbol,'Ticker symbol mismatch')
            for old,new in [('mark_price','markPrice'),('index_price','indexPrice'),('current_funding_rate','fundingRate'),('next_funding_time','nextFundingTime'),('open_interest','openInterest')]:
                require(record[old]==ticker[new],'Ticker summary mismatch '+old)
            require(D(ticker['markPrice'])>0 and D(ticker['indexPrice'])>0,'Invalid mark/index')
            require(len(record['scenarios'])==4,'Missing scenario')
            for j,(notional,fee) in enumerate(scenarios):
                calculated=analyze(bp,meta,bt,notional,10000,fee)
                require(calculated==record['scenarios'][j],'Recomputed scenario mismatch')
                qty=D(calculated['quantity']);buy=independent_sweep(book['a'],qty);sell=independent_sweep(book['b'],qty)
                loss=buy-sell+(buy+sell)*D(fee)/10000
                require(loss==D(calculated['same_snapshot_round_trip_loss_usdt']),'Independent cost mismatch')
                scenarios[(notional,fee)].append(calculated)
                result['scenario_recalculations']+=1;result['independent_cash_oracles']+=1
            base=record['scenarios'][2]
            for band in base['depth_bands']:
                b=band['distance_from_mid_bps']
                for side in ('bid','ask'):
                    depth[b][side].append(band[side+'_notional_usdt']);complete[b][side]+=int(band[side+'_band_fully_observed'])
            rows.append({'round':i,'source_utc':utc(book['ts']),'age_ms':bt-book['cts'],'spread_bps':base['spread_bps'],
                'notional_usdt':base['buy_notional_usdt'],'round_trip_cost_usdt':base['same_snapshot_round_trip_loss_usdt'],
                'cost_pct_equity':base['loss_pct_capital'],'buy_impact_bps':base['buy_impact_bps'],'sell_impact_bps':base['sell_impact_bps']})
        scenario_stats=[]
        for (n,f),values in scenarios.items():
            scenario_stats.append({'target_notional_usdt':n,'fee_bps_assumption':f,
              **{field:stats(x[field] for x in values) for field in ['buy_notional_usdt','same_snapshot_round_trip_loss_usdt','loss_pct_capital','loss_pct_buy_notional','round_trip_fees_usdt','buy_impact_bps','sell_impact_bps']}})
        result['assets'][symbol]={'snapshots':rounds,'book_age_ms':stats(ages),'spread_bps':stats(x['spread_bps'] for x in rows),
          'qty_step':meta['lotSizeFilter']['qtyStep'],'tick_size':meta['priceFilter']['tickSize'],
          'depth_bands':{b:{side:{**stats(depth[b][side]),'complete_snapshots':complete[b][side]} for side in ('bid','ask')} for b in depth},
          'scenarios':scenario_stats,'funding':funding,'observations':rows}
        result['book_count']+=rounds;result['funding_event_count']+=len(events)
    require(result['book_count']==summary['valid_snapshot_count']==summary['unique_book_timestamps'],'Capture counts mismatch')
    result.update(first_book_utc=utc(min(alltimes)),last_book_utc=utc(max(alltimes)),book_span_seconds=(max(alltimes)-min(alltimes))/1000,
      limits=['Only one brief capture, not representative historical liquidity','Fees are scenarios, account tier unverified','Static book sweep is not an actual fill or latency-slippage estimate','Funding is constant-notional illustration, not strategy PnL','REST book excludes RPI liquidity; deep bands may be incomplete','No matching historical perpetual or mark-price series in this archive'])
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--sha256',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=audit(a.input,a.sha256)
    a.output.write_text(json.dumps(r,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in r.items() if k!='assets'},indent=2))
