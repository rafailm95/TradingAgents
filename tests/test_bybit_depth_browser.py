"""Synthetic depth-first, continuity, import and refusal tests. No real network."""
import json
from pathlib import Path
import sys
import zipfile

import pytest
from tests.test_bybit_packet_026 import setup, raw, b, audit_module

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import collect_bybit_depth_browser as depth
import collect_bybit_history_browser as history


def args(j,server,clock):
    return dict(clock=clock,transport=server,plan_raw=raw(j.plan),core_raw=raw(j.core),source_hashes={'test':'fixture'})


def test_depth_precedes_history_and_full_goal_remains_partial(tmp_path):
    j,server,clock=setup(tmp_path)
    r=depth.collect(j.out,depth_rounds=2,**args(j,server,clock))
    assert server.calls[0][:2]==('instrument','BTCUSDT')
    first_candle=next(i for i,c in enumerate(server.calls) if c[0]=='trade')
    assert sum(c[0]=='book' for c in server.calls[:first_candle])==20
    assert r['summary']['core_history_status']=='COMPLETE'
    assert r['summary']['live']['rounds_requested']==3
    assert r['summary']['live']['valid_books']==20
    assert r['summary']['live']['status']=='PARTIAL'
    assert r['summary']['status']=='COLLECTED_WITH_GAPS_REVIEW_REQUIRED'
    n=len(server.calls)
    depth.collect(j.out,depth_rounds=2,**args(j,server,clock))
    assert len(server.calls)==n


def test_interrupted_pair_keeps_raw_and_never_backfills_old_round(tmp_path):
    j,server,clock=setup(tmp_path); count=0
    def interrupt(url,*other):
        nonlocal count
        count+=1
        if count==4:raise KeyboardInterrupt('after first book')
        return server(url,*other)
    r=depth.collect(j.out,depth_rounds=2,**args(j,interrupt,clock))
    assert r['summary']['live']['valid_books']==0
    state=json.loads((j.out/'state.json').read_bytes())
    assert state['rounds'][0]['assets']['BTCUSDT']['status']=='INTERRUPTED'
    original=(j.out/'response_000002.bin.gz').read_bytes()
    clock.sleep(900)
    r2=depth.collect(j.out,depth_rounds=2,**args(j,server,clock))
    state=json.loads((j.out/'state.json').read_bytes())
    assert state['rounds'][0]['assets']['BTCUSDT']['status']=='INTERRUPTED'
    assert r2['summary']['live']['valid_books']==10
    assert r2['summary']['live']['largest_round_gap_seconds']>=900
    assert original==(j.out/'response_000002.bin.gz').read_bytes()
    assert all(r['scope']!='live-0000-BTCUSDT-after' or not r.get('accepted')
               for r in [json.loads(p.read_bytes()) for p in j.out.glob('request_*.json')])


@pytest.mark.parametrize('code,body',[(403,b'denied'),(200,b'<html>Site Unavailable</html>')])
def test_block_preserved_once_no_history_or_rerun_retry(tmp_path,code,body):
    j,server,clock=setup(tmp_path);server.failures=[(code,body)]
    r=depth.collect(j.out,depth_rounds=2,**args(j,server,clock))
    assert len(server.calls)==1 and r['summary']['successful_responses']==0
    assert r['receipt']['offline_integrity']=='PASS'
    depth.collect(j.out,depth_rounds=2,**args(j,server,clock))
    assert len(server.calls)==1


def test_wait_budget_stop_saves_completed_round_and_reuses_it(tmp_path):
    j,server,clock=setup(tmp_path)
    r=depth.collect(j.out,depth_rounds=2,budget_seconds=15,**args(j,server,clock))
    assert r['summary']['live']['valid_books']==10
    assert 'session budget' in r['summary']['error']
    saved=[p.read_bytes() for p in sorted(j.out.glob('response_*.bin.gz'))]
    r2=depth.collect(j.out,depth_rounds=2,**args(j,server,clock))
    assert r2['summary']['live']['valid_books']==20
    assert saved==[p.read_bytes() for p in sorted(j.out.glob('response_*.bin.gz'))[:len(saved)]]


def test_import_history_audited_preserves_raw_does_not_redownload(tmp_path):
    source=tmp_path/'old';source.mkdir()
    j,server,clock=setup(source)
    old=history.collect(j.out,**args(j,server,clock))
    originals={p.name:p.read_bytes() for p in j.out.glob('response_*.bin.gz')}
    target=tmp_path/'new'/'data'
    imported=depth.import_packet(old['zip'],old['receipt']['sha256'],target,
        plan_raw=raw(j.plan),core_raw=raw(j.core),source_hashes={'test':'fixture'})
    n=len(server.calls)
    r=depth.collect(target,depth_rounds=2,**args(j,server,clock))
    assert set(c[0] for c in server.calls[n:])=={'instrument','ticker','book','trades'}
    assert all((target/name).read_bytes()==value for name,value in originals.items())
    assert r['summary']['core_history_status']=='COMPLETE'
    assert json.loads((target/'state.json').read_bytes())['browser_import']['archive_sha256']==old['receipt']['sha256']
    assert imported['raw_responses_verified']>0


def test_bad_import_hash_and_existing_directory_refused(tmp_path):
    j,server,clock=setup(tmp_path);server.failures=[(403,b'denied')]
    old=history.collect(j.out,**args(j,server,clock))
    kw=dict(plan_raw=raw(j.plan),core_raw=raw(j.core),source_hashes={'test':'fixture'})
    dest=tmp_path/'import'
    with pytest.raises(ValueError,match='hash'):
        depth.import_packet(old['zip'],'0'*64,dest,**kw)
    assert not dest.exists()
    with pytest.raises(b.StopCollection,match='empty destination'):
        depth.import_packet(old['zip'],old['receipt']['sha256'],j.out,**kw)


def test_existing_history_profile_not_overwritten_without_import(tmp_path):
    j,server,clock=setup(tmp_path)
    state={'schema':'bybit_packet_026_state_v1','rounds':[],'collection_profile':'browser_history_only_v1'}
    b.write(j.out/'state.json',state)
    with pytest.raises(b.StopCollection,match='import option'):
        depth.collect(j.out,depth_rounds=2,**args(j,server,clock))
    assert json.loads((j.out/'state.json').read_bytes())==state and not server.calls


def test_checkpoint_zip_exists_before_next_round_network(tmp_path):
    j,server,clock=setup(tmp_path);last_scope=[]
    def observe(url,*other):
        if len(server.calls)==25:
            with zipfile.ZipFile(j.out.parent/'BYBIT_SEND_THIS.zip') as z:
                state=json.loads(z.read('state.json'))
                assert len(state['rounds'])==1
                last_scope.append(True)
        return server(url,*other)
    depth.collect(j.out,depth_rounds=2,**args(j,observe,clock))
    assert last_scope==[True]


def test_pinned_target_cannot_silently_expand(tmp_path):
    j,server,clock=setup(tmp_path)
    depth.collect(j.out,depth_rounds=2,**args(j,server,clock))
    state=json.loads((j.out/'state.json').read_bytes())
    state['browser_depth_target']=3;b.write(j.out/'state.json',state)
    n=len(server.calls)
    with pytest.raises(b.StopCollection,match='pinned browser depth target'):
        depth.collect(j.out,depth_rounds=2,**args(j,server,clock))
    assert len(server.calls)==n


def test_notebook_is_self_contained_and_first_failure_packages_under_stdlib(tmp_path):
    import subprocess
    root=Path(__file__).resolve().parents[1]
    nb=json.loads((root/'notebooks/Bybit_Depth_and_History_One_Click.ipynb').read_bytes())
    cells=[''.join(c['source']) for c in nb['cells'] if c['cell_type']=='code']
    for cell in cells:compile(cell,'cell','exec')
    setup_code=cells[0].replace('/content/Bybit_Browser_Depth_20261018',str(tmp_path/'bundle'))
    setup_code+='''
import collect_bybit_depth_browser as d
calls=[]
def denied(*args):
    calls.append(args[0]);return 403,b'fixture denied'
r=d.collect(ROOT/'browser_depth_data',transport=denied)
assert len(calls)==1 and r['receipt']['offline_integrity']=='PASS'
assert r['summary']['live']['valid_books']==0
'''
    r=subprocess.run([sys.executable,'-S','-c',setup_code],text=True,capture_output=True)
    assert r.returncode==0,r.stdout+r.stderr
