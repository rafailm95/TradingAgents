"""Bounded depth-first browser session, then historical collection.

Uses unchanged026 transport, measurements, core rules and auditor. No orders.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tradingagents'))
sys.path.insert(0, str(ROOT/'scripts'))
import bybit_packet_026 as b
import audit_bybit_packet_026 as auditor

PROFILE = 'browser_depth_then_history_v1'
BUDGET_STOP = 'Browser six-hour session budget reached'


def inputs(plan_raw=None, core_raw=None, source_hashes=None):
    return (plan_raw or (ROOT/'docs/BYBIT_PACKET_026.json').read_bytes(),
            core_raw or (ROOT/'docs/BYBIT_HISTORY_013.json').read_bytes(),
            b.sources() if source_hashes is None else source_hashes)


def import_packet(archive, expected_sha, out, *, plan_raw=None, core_raw=None, source_hashes=None):
    """Audit a user-selected ZIP before copying bounded flat data; never execute it."""
    archive, out = Path(archive), Path(out)
    plan_raw, core_raw, source_hashes = inputs(plan_raw, core_raw, source_hashes)
    if out.exists() and any(out.iterdir()):
        raise b.StopCollection('Import requires an empty destination; existing evidence unchanged')
    checked = auditor.audit(archive, expected_sha, plan_raw=plan_raw,
                            core_raw=core_raw, source_hashes=source_hashes)
    if b.file_sha(archive) != expected_sha: raise b.StopCollection('Import archive changed')
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        # Exact allowlist, paths, hashes, bounds and CRC were checked by026auditor.
        for name in z.namelist(): (out/name).write_bytes(z.read(name))
    if b.file_sha(archive) != expected_sha: raise b.StopCollection('Import archive changed during copying')
    state_path = out/'state.json'
    state = json.loads(state_path.read_bytes()) if state_path.exists() else {
        'schema': 'bybit_packet_026_state_v1', 'rounds': []}
    if state.get('collection_profile') != PROFILE:
        state['browser_import'] = {
            'archive_sha256': expected_sha,
            'prior_summary': checked['summary'],
            'prior_profile': state.get('collection_profile'),
            'prior_status_text': (out/'STATUS_EL.txt').read_text() if (out/'STATUS_EL.txt').exists() else None}
        state['collection_profile'] = PROFILE
        state.pop('live_sampling', None)
        # Extra browser sampling is bounded separately; original026goal is unchanged.
        state.pop('browser_depth_target', None)
        b.write(state_path, state)
        b.write(out/'summary.json', b.status_summary(
            b.Journal(out,plan_raw,core_raw,source_hashes,offline=True), checked['summary'].get('error')))
    return {'imported_archive_sha256': expected_sha,
            'raw_responses_verified': checked['raw_responses_verified']}


def close_pending(state):
    if 'pending_round' not in state: return
    pending = state.pop('pending_round')
    for symbol in b.SYMBOLS:
        pending['assets'].setdefault(symbol, {'status':'INTERRUPTED',
            'error':'Process stopped before this observation completed; never backfilled'})
    state['rounds'].append(pending)


def checkpoint(j, state, error=None, *, audit=False):
    b.write(j.out/'state.json', state)
    summary = b.status_summary(j,error)
    b.write(j.out/'summary.json',summary)
    (j.out/'STATUS_EL.txt').write_text(
        'BYBIT — ΒΑΘΟΣ ΑΓΟΡΑΣ ΚΑΙ ΙΣΤΟΡΙΚΟ\n'
        'Στόχος browser: έως25γύροι, ανάτουλάχιστον5λεπτά (~2ώρες), έπειτα ιστορικό.\n'
        'Ο στόχος72ωρών του πλήρους026πακέτου παραμένει χωριστός και δεν θεωρείται ολοκληρωμένος.\n'
        'Έγκυρα βιβλία: '+str(summary['live']['valid_books'])+'\n'
        'Πραγματικό διάστημα δείγματος(ώρες): '+str(summary['live']['observed_span_hours'])+'\n'
        'Μεγαλύτερο κενό γύρων(δευτερόλεπτα): '+str(summary['live']['largest_round_gap_seconds'])+'\n'
        'Πυρήνας ιστορικού013: '+summary['core_history_status']+'\n'
        'Τα βιβλία είναι στιγμιότυπα, όχι συνεχής καταγραφή ούτε πραγματικές εκτελέσεις.\n'
        'Στείλε μόνο το BYBIT_SEND_THIS.zip, ακόμη και με κενά.\n', encoding='utf-8')
    target = j.out.parent/'BYBIT_SEND_THIS.zip'
    receipt = b.package(j.out,target)
    if audit:
        checked = auditor.audit(target,receipt['sha256'],plan_raw=(j.out/'plan.json').read_bytes(),
             core_raw=(j.out/'core_protocol.json').read_bytes(),source_hashes=j.session['source_hashes'])
        receipt.update(offline_integrity='PASS',raw_responses_verified=checked['raw_responses_verified'])
    receipt.update(collection_profile=PROFILE, wrapper_sha256=b.file_sha(Path(__file__)))
    b.write(j.out.parent/'BYBIT_SEND_THIS_RECEIPT.json',receipt)
    return {'zip':str(target),'receipt':receipt,'summary':summary}


def collect(out, *, clock=None, transport=None, budget_seconds=21600,
            depth_rounds=25, plan_raw=None, core_raw=None, source_hashes=None):
    if not 0 < budget_seconds <= 21600 or type(depth_rounds) is not int or not 1 <= depth_rounds <= 25:
        raise ValueError('At most six hours and25new rounds per browser profile')
    plan_raw,core_raw,source_hashes=inputs(plan_raw,core_raw,source_hashes)
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(out).free < json.loads(plan_raw)['minimum_free_bytes']:
        raise b.StopCollection('At least3GB free disk required')
    clock=clock or b.Clock(); transport=transport or b.network_get
    deadline=clock.mono()+budget_seconds
    def check_budget():
        if clock.mono()>=deadline: raise b.StopCollection(BUDGET_STOP)
    def bounded_transport(url,timeout,limit):
        check_budget();return transport(url,timeout,limit)
    with b.file_lock(out.parent/'bybit_depth_browser.lock'):
        j=b.Journal(out,plan_raw,core_raw,source_hashes,clock=clock,transport=bounded_transport)
        path=out/'state.json'
        state=json.loads(path.read_bytes()) if path.exists() else {
            'schema':'bybit_packet_026_state_v1','rounds':[],'collection_profile':PROFILE}
        if state.get('collection_profile')!=PROFILE:
            raise b.StopCollection('Use the audited import option for a previous history packet')
        close_pending(state)
        if 'browser_depth_target' not in state:
            state['browser_depth_initial_rounds']=len(state['rounds'])
            state['browser_depth_target']=min(len(state['rounds'])+depth_rounds,j.plan['live_rounds'])
            state['browser_depth_added_limit']=depth_rounds
        target=state['browser_depth_target']
        initial=state.get('browser_depth_initial_rounds')
        added=state.get('browser_depth_added_limit')
        if (any(type(v) is not int for v in (target,initial,added))
                or not 0<=initial<=len(state['rounds'])<=target<=j.plan['live_rounds']
                or not 1<=added<=25 or target!=min(initial+added,j.plan['live_rounds'])):
            raise b.StopCollection('Invalid pinned browser depth target')
        error=None
        try:
            blocked=[r for r in j.records if r.get('status')=='STOPPED'
                     and r.get('error') not in (BUDGET_STOP,'Browser four-hour session budget reached')]
            if blocked: raise b.StopCollection('Previous access/integrity stop retained; no new request')
            checkpoint(j,state)
            while len(state['rounds'])<target:
                check_budget()
                if state['rounds']:
                    due=state['rounds'][-1]['started_ms']+j.plan['live_interval_seconds']*1000
                    while clock.now()<due:
                        check_budget();clock.sleep(min(30,(due-clock.now())/1000))
                check_budget()
                index=len(state['rounds'])
                pending={'id':index,'started_ms':clock.now(),'assets':{}}
                state['pending_round']=pending;b.write(path,state)
                for symbol in b.SYMBOLS:
                    pending['assets'][symbol]=b.component(lambda s=symbol:b.live_asset(j,s,index))
                    b.write(path,state)
                state['rounds'].append(pending);state.pop('pending_round')
                checkpoint(j,state)
                print(f'Βάθος: γύρος{len(state["rounds"])}/{target}. Το ZIP ενημερώθηκε.',flush=True)
            print('Το πρώτο δείγμα βάθους ολοκληρώθηκε. Ελέγχω/συνεχίζω το ιστορικό.',flush=True)
            state['history']=b.historical(j);b.write(path,state)
        except (Exception,KeyboardInterrupt) as exc:
            error=type(exc).__name__+': '+str(exc)
            close_pending(state);b.write(path,state)
            print(error,flush=True)
        result=checkpoint(j,state,error,audit=True)
        print('Έτοιμο για λήψη: '+result['zip'],flush=True)
        return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'browser_depth_data')
    a=p.parse_args();collect(a.output)
