"""One bounded second recovery: in-memory serialization + fsync + base64 envelope.
The repeated post-write truncation is preserved; no strategy/accounting changes.
"""
import base64,gzip,hashlib,io,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from tradingagents import futures_replay_019 as engine
from tradingagents import binance_archive as old
from run_funding_futures_019 import verify_freeze,load_archive,INPUT_SHA,T1,T2
from run_binance_replay_017 import file_sha,write_new


def main():
    work=ROOT.parent
    intent=json.loads((ROOT/'research/experiments/019/recovery-v2-intent.json').read_bytes())
    if file_sha(__file__)!=intent['source_sha256']:raise ValueError('Recovery source pin failed')
    verify_freeze(intent['original_freeze_sha256'])
    ep=work/'funding019-evaluation/evaluation.json'
    if file_sha(ep)!=intent['original_evaluation_sha256']:raise ValueError('Manifest changed')
    output=work/'funding019-result-recovery-v2';output.mkdir()
    write_new(output/'intent.json',intent)
    _,data=load_archive(work/'binance-017-normalized.json.gz',INPUT_SHA)
    market=old.prepare(data['ETHUSDT'],'ETHUSDT')
    candidate='funding_carry7_momentum28__fixed50'
    result=engine.replay(market,T1,T2,candidate=candidate,cost='venue_assumption',lag=0,
        adverse_funding=True,prepared_signals=engine.make_signals(market,candidate,T2))
    stream=io.BytesIO()
    with gzip.GzipFile(filename='',mode='wb',fileobj=stream,mtime=0) as z:
        z.write(json.dumps(result,separators=(',',':'),allow_nan=False).encode())
    blob=stream.getvalue()
    if hashlib.sha256(blob).hexdigest()!=intent['expected_result_sha256']:
        raise ValueError('Second recovery did not match original bytes')
    envelope={'original_file':intent['file'],'decoded_sha256':intent['expected_result_sha256'],
              'decoded_bytes':len(blob),'encoding':'base64+gzip','data':base64.b64encode(blob).decode()}
    encoded=json.dumps(envelope,separators=(',',':')).encode()
    path=output/'recovered-result-envelope.json'
    with path.open('xb') as f:
        f.write(encoded);f.flush();os.fsync(f.fileno())
    verify=json.loads(path.read_bytes())
    reread=base64.b64decode(verify['data'],validate=True)
    if hashlib.sha256(reread).hexdigest()!=intent['expected_result_sha256']:
        raise ValueError('Envelope failed immediate readback')
    audit=engine.audit_wealth(json.loads(gzip.decompress(reread)))
    write_new(output/'receipt.json',{'status':'PASS','additional_integrity_replays':1,
        'envelope_sha256':file_sha(path),'decoded_sha256':hashlib.sha256(reread).hexdigest(),
        'independent_wealth_audit':audit,'original_and_first_recovery_empty_files_retained':True,
        'cause':'Unknown; second attempt changes persistence only, using in-memory deterministic serialization and fsync of a base64 envelope. No rules/inputs/outcomes change.'})
    print('Original SHA matched; fsynced envelope independently audited',flush=True)


if __name__=='__main__':main()

