"""New026 invariants: all five assets, causal bounds, compression and privacy."""
import gzip
import json
from pathlib import Path
import sys
import zipfile

import pytest
from tests.test_bybit_packet_026 import setup, finalize, raw, b, audit_module, config

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import collect_bybit_packet_026 as collector


def test_five_symbols_fine_grids_and_original_core_bridge(tmp_path):
    j, server, _ = setup(tmp_path)
    state = b.run(j)
    assert set(state['rounds'][0]['assets']) == set(b.SYMBOLS)
    assert set(state['history']['core']['symbols']) == {'BTCUSDT','ETHUSDT','LTCUSDT'}
    for symbol in b.SYMBOLS:
        for kind in ('trade','mark'):
            assert state['history']['supplements'][symbol+'_'+kind+'_1min']['expected_rows'] == 1440
            assert state['history']['supplements'][symbol+'_'+kind+'_5min']['expected_rows'] == 288
    target=tmp_path/'packet.zip'; receipt=finalize(j,target)
    checked=audit_module.audit(target,receipt['sha256'],plan_raw=raw(j.plan),core_raw=raw(j.core),source_hashes={'test':'fixture'},return_core=True)
    assert checked['replay_core_validation']['status']=='COMPLETE'
    assert set(checked['datasets'])=={'BTCUSDT','ETHUSDT','LTCUSDT'}


def test_funding_variable_cadence_preserved_not_certified(tmp_path):
    j, server, _=setup(tmp_path)
    def mutate(p,k,s):
        if k=='funding' and s=='SOLUSDT':
            # Four-hour fixture includes20:00, which the eight-hour base fixture lacks.
            t=int(p['result']['list'][0]['fundingRateTimestamp'])+4*b.HOUR
            for i,row in enumerate(p['result']['list']): row['fundingRateTimestamp']=str(t-i*4*b.HOUR)
    server.mutate=mutate
    end=b.utc_ms(j.core['end_exclusive_utc'])
    result=b.observed_funding(j,'SOLUSDT',end-b.DAY,end)
    assert result['events']==6 and result['cadence_ms']=={str(4*b.HOUR):6}
    assert result['coverage_certified'] is False and result['zero_filled_events']==0


def test_no_funding_events_remain_failure(tmp_path):
    j,server,_=setup(tmp_path)
    server.mutate=lambda p,k,s:p['result'].update(list=[]) if k=='funding' else None
    end=b.utc_ms(j.core['end_exclusive_utc'])
    assert b.observed_funding(j,'XRPUSDT',end-b.DAY,end)['status']=='NO_EVENTS'


def test_gzip_response_is_exact_and_bounded(tmp_path):
    j,_,_=setup(tmp_path); payload,_=j.get('instrument','SOLUSDT')
    record=j.records[-1]; restored=b.read_raw(j.out/record['raw_file'])
    assert json.loads(restored)==payload and b.sha(restored)==record['sha256']
    assert record['raw_file'].endswith('.bin.gz')
    bomb=tmp_path/'bomb.gz';bomb.write_bytes(gzip.compress(b'x'*15_000_001))
    with pytest.raises(b.StopCollection,match='expands'):b.read_raw(bomb)


def test_compressed_storage_bound_stops_without_claiming_accepted(tmp_path):
    j,_,_=setup(tmp_path);j.plan['max_evidence_bytes']=j.bytes_used+1
    with pytest.raises(b.StopCollection,match='bound'):j.get('instrument','SOLUSDT')
    assert not j.records[-1].get('accepted')


def test_cutoff_cannot_move_on_resume_or_be_tampered(tmp_path):
    j,server,clock=setup(tmp_path); original=j.session['history_end_ms']
    clock.sleep(86400)
    resumed=b.Journal(j.out,raw(j.plan),raw(j.core),{'test':'fixture'},clock=clock,transport=server)
    assert resumed.session['history_end_ms']==original
    changed=dict(j.session);changed['history_end_ms']+=b.DAY;b.write(j.out/'session.json',changed)
    with pytest.raises(b.StopCollection,match='cutoff changed'):
        b.Journal(j.out,raw(j.plan),raw(j.core),{'test':'fixture'},clock=clock,transport=server)


def test_incomplete_one_minute_bar_rejected(tmp_path):
    j,server,clock=setup(tmp_path)
    lo=clock.now()//60000*60000
    with pytest.raises(ValueError,match='unclosed'):
        b.series(j,'trade','XRPUSDT',lo,lo+60000,1)


def test_optional_settings_do_not_accept_secrets_or_unknown_fields(tmp_path):
    p=tmp_path/'settings.json'
    assert set(collector.settings(p)['values'].values())=={None}
    p.write_text(json.dumps({'api_key':'DO_NOT_INCLUDE'}))
    with pytest.raises(ValueError,match='unsupported fields'):collector.settings(p)
    p.write_text(json.dumps({'maker_fee_bps':2,'taker_fee_bps':5.5,'leverage':1,'margin_mode':'isolated'}))
    assert collector.settings(p)['values']['taker_fee_bps']=='5.5'


@pytest.mark.parametrize('value',[0,126,True,'not-a-number'])
def test_invalid_optional_leverage_rejected(tmp_path,value):
    p=tmp_path/'settings.json';p.write_text(json.dumps({'maker_fee_bps':None,'taker_fee_bps':None,'leverage':value,'margin_mode':None}))
    with pytest.raises(ValueError):collector.settings(p)


def test_collector_packages_access_block_with_one_request(tmp_path,monkeypatch):
    j,server,clock=setup(tmp_path)
    root=tmp_path/'portable';(root/'docs').mkdir(parents=True)
    (root/'docs/BYBIT_PACKET_026.json').write_bytes(raw(j.plan))
    (root/'docs/BYBIT_HISTORY_013.json').write_bytes(raw(j.core))
    monkeypatch.setattr(collector,'ROOT',root)
    server.failures=[(403,b'blocked')]
    result=collector.main(root/'out',clock=clock,transport=server,audit_after=False)
    assert result['status']=='STOPPED_WITH_EVIDENCE' and len(server.calls)==1
    archive=root/'BYBIT_SEND_THIS.zip'
    checked=audit_module.audit(archive,b.file_sha(archive),plan_raw=raw(j.plan),core_raw=raw(j.core),source_hashes=b.sources())
    assert checked['summary']['request_attempts']==1


def test_bad_core_never_exports_for_replay(tmp_path):
    j,server,_=setup(tmp_path)
    def mutate(p,k,s):
        if k=='mark' and s=='ETHUSDT':p['result']['list']=[]
    server.mutate=mutate;b.run(j);target=tmp_path/'bad.zip';r=finalize(j,target)
    with pytest.raises(ValueError,match='Incomplete frozen013'):
        audit_module.audit(target,r['sha256'],plan_raw=raw(j.plan),core_raw=raw(j.core),source_hashes={'test':'fixture'},return_core=True)
