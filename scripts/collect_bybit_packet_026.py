"""One public, five-symbol research packet. No credentials or order capability."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tradingagents'))
import bybit_packet_026 as b


def settings(path):
    keys = {'maker_fee_bps', 'taker_fee_bps', 'leverage', 'margin_mode'}
    result = dict.fromkeys(sorted(keys))
    if path.exists():
        if path.stat().st_size > 4096: raise ValueError('Optional settings too large; not included')
        result = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(result, dict) or set(result) != keys:
            raise ValueError('Optional settings contain unsupported fields; not included')
        for key in ('maker_fee_bps', 'taker_fee_bps', 'leverage'):
            if result[key] is not None:
                value = b.number(result[key])
                if not ((1 if key == 'leverage' else 0) <= value <= (125 if key == 'leverage' else 100)):
                    raise ValueError('Optional numeric setting outside bounds; not included')
                result[key] = str(value)
        if result['margin_mode'] not in (None, 'isolated', 'cross', 'portfolio'):
            raise ValueError('Unsupported margin mode; not included')
    return {'source': 'optional manually entered, not independently verified', 'values': result}


def main(out, *, clock=None, transport=None, audit_after=True):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    plan = (ROOT / 'docs/BYBIT_PACKET_026.json').read_bytes()
    core = (ROOT / 'docs/BYBIT_HISTORY_013.json').read_bytes()
    if shutil.disk_usage(out).free < json.loads(plan)['minimum_free_bytes']:
        raise b.StopCollection('At least3GB free disk required. Existing evidence unchanged.')
    with b.file_lock(out.parent / 'bybit_packet_026.lock'), b.keep_awake():
        j = b.Journal(out, plan, core, b.sources(), clock=clock, transport=transport)
        error = None
        try:
            if b.utc_ms(j.core['end_exclusive_utc']) > j.session['history_end_ms']:
                raise b.StopCollection('Frozen core cutoff is in the future')
            b.write(out / 'operator_settings.json', settings(ROOT / 'OPTIONAL_SETTINGS.json'))
            candidates = []
            for parent in (ROOT.parent, ROOT.parent.parent):
                candidates += [parent / 'Bybit_History_Collector' / 'bybit_history_013',
                               parent / 'Bybit_History_Collector' / 'Bybit_History_Collector' / 'bybit_history_013']
            b.import_old_history(j, candidates)
            b.run(j)
        except (Exception, KeyboardInterrupt) as e:
            error = type(e).__name__ + ': ' + str(e)
            print(error, flush=True)
        summary = b.status_summary(j, error)
        b.write(out / 'summary.json', summary)
        (out / 'STATUS_EL.txt').write_text(
            'ΣΥΛΛΟΓΗ BYBIT — BTC, ETH, LTC, SOL, XRP\n'
            + 'Κατάσταση: ' + summary['status'] + '\n'
            + 'Αρχικό ιστορικό013: ' + summary['core_history_status'] + '\n'
            + 'Έγκυρα βιβλία: ' + str(summary['live']['valid_books']) + '\n'
            + 'Τα κενά/σφάλματα παραμένουν. Δεν είναι αποτέλεσμα στρατηγικής ή πραγματικής εκτέλεσης.\n'
            + 'Ανέβασε μόνο το BYBIT_SEND_THIS.zip, ακόμη και αν είναι ελλιπές.\n', encoding='utf-8')
        target = out.parent / 'BYBIT_SEND_THIS.zip'
        receipt = b.package(out, target)
        if audit_after:
            import audit_bybit_packet_026
            checked = audit_bybit_packet_026.audit(target, receipt['sha256'])
            receipt['offline_integrity_check'] = 'PASS'
            receipt['verified_raw_responses'] = checked['raw_responses_verified']
        b.write(out.parent / 'BYBIT_SEND_THIS_RECEIPT.json', receipt)
        print('\nUPLOAD ONLY: ' + str(target.resolve()), flush=True)
        print('Status: ' + summary['status'] + '\nSHA256: ' + receipt['sha256'], flush=True)
        return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=ROOT / 'bybit_packet_026_data')
    a = p.parse_args()
    if sys.version_info < (3, 10): p.exit(2, 'Python3.10 or later required; Python3.12 recommended.\n')
    try:
        result = main(a.output)
        sys.exit(0 if result['status'] == 'CAPTURED_FOR_REVIEW' else 2)
    except (Exception, KeyboardInterrupt) as e:
        print(type(e).__name__ + ': ' + str(e))
        p.exit(2, 'Keep all files. If BYBIT_SEND_THIS.zip exists, send that one ZIP for review.\n')
