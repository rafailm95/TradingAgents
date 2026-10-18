"""Optional browser history profile over unchanged packet026 sources.

No multiday live sampling, no credentials, no orders. A partial packet stays
partial. Run in a user-controlled Python/Colab session with permitted access.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tradingagents'))
sys.path.insert(0, str(ROOT / 'scripts'))
import bybit_packet_026 as b
import audit_bybit_packet_026 as auditor


def collect(out, *, clock=None, transport=None, budget_seconds=14400,
            plan_raw=None, core_raw=None, source_hashes=None):
    if not 0 < budget_seconds <= 14400:
        raise ValueError('Browser session budget must be at most four hours')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    plan_raw = plan_raw or (ROOT / 'docs/BYBIT_PACKET_026.json').read_bytes()
    core_raw = core_raw or (ROOT / 'docs/BYBIT_HISTORY_013.json').read_bytes()
    source_hashes = b.sources() if source_hashes is None else source_hashes
    if shutil.disk_usage(out).free < json.loads(plan_raw)['minimum_free_bytes']:
        raise b.StopCollection('At least 3 GB free disk required')
    clock = clock or b.Clock()
    original_transport = transport or b.network_get
    deadline = clock.mono() + budget_seconds

    def bounded_transport(url, timeout, limit):
        if clock.mono() >= deadline:
            raise b.StopCollection('Browser four-hour session budget reached')
        return original_transport(url, timeout, limit)

    with b.file_lock(out.parent / 'bybit_history_browser.lock'):
        j = b.Journal(out, plan_raw, core_raw, source_hashes,
                      clock=clock, transport=bounded_transport)
        path = out / 'state.json'
        state = json.loads(path.read_bytes()) if path.exists() else {
            'schema': 'bybit_packet_026_state_v1', 'rounds': [],
            'collection_profile': 'browser_history_only_v1',
            'live_sampling': 'NOT_REQUESTED_IN_THIS_OPTIONAL_PROFILE'}
        if state.get('collection_profile') != 'browser_history_only_v1' or state.get('rounds'):
            raise b.StopCollection('Use a separate folder for the browser profile')
        error = None
        try:
            # Never automatically retry an access/integrity block on cell rerun.
            blocked = [r for r in j.records if r.get('status') == 'STOPPED'
                       and 'Browser four-hour' not in r.get('error', '')]
            if blocked:
                raise b.StopCollection('Previous access/integrity stop retained; no new request')
            b.write(path, state)
            state['history'] = b.historical(j)
            b.write(path, state)
        except (Exception, KeyboardInterrupt) as exc:
            error = type(exc).__name__ + ': ' + str(exc)
            print(error, flush=True)
        summary = b.status_summary(j, error)
        b.write(out / 'summary.json', summary)
        (out / 'STATUS_EL.txt').write_text(
            'ΠΡΟΑΙΡΕΤΙΚΗ ΣΥΛΛΟΓΗ ΙΣΤΟΡΙΚΟΥ ΑΠΟ BROWSER\n'
            'BTC, ETH, LTC, SOL, XRP — δημόσια δεδομένα, χωρίς εντολές.\n'
            'Δεν ζητήθηκε η ζωντανή συλλογή 72 ωρών ούτε τελική επέκταση.\n'
            'Κατάσταση πλήρους πακέτου: ' + summary['status'] + '\n'
            'Ιστορικό πυρήνα013: ' + summary['core_history_status'] + '\n'
            'Στείλε το BYBIT_SEND_THIS.zip ακόμη και με κενά/σφάλματα.\n'
            'Δεν είναι αποτέλεσμα στρατηγικής ή απόδειξη κερδοφορίας.\n', encoding='utf-8')
        target = out.parent / 'BYBIT_SEND_THIS.zip'
        receipt = b.package(out, target)
        checked = auditor.audit(target, receipt['sha256'], plan_raw=plan_raw,
                                core_raw=core_raw, source_hashes=source_hashes)
        receipt.update(offline_integrity='PASS',
                       raw_responses_verified=checked['raw_responses_verified'],
                       collection_profile='browser_history_only_v1',
                       wrapper_sha256=b.file_sha(Path(__file__)))
        b.write(out.parent / 'BYBIT_SEND_THIS_RECEIPT.json', receipt)
        print('ZIP έτοιμο: ' + str(target), flush=True)
        print('Πυρήνας ιστορικού: ' + summary['core_history_status'], flush=True)
        print('Πλήρης συλλογή 72 ωρών: ΔΕΝ ΕΚΤΕΛΕΣΤΗΚΕ', flush=True)
        return {'summary': summary, 'receipt': receipt, 'zip': str(target)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'browser_history_data')
    args = parser.parse_args()
    collect(args.output)
