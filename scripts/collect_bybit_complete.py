"""One portable launcher: historical data, supplements, multiday depth, one ZIP."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tradingagents'))
import bybit_complete as b


def main(out, *, clock=None, transport=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    plan_raw = (ROOT / 'docs/BYBIT_COMPLETE_014.json').read_bytes()
    core_raw = (ROOT / 'docs/BYBIT_HISTORY_013.json').read_bytes()
    p = json.loads(plan_raw)
    if shutil.disk_usage(out).free < p['minimum_free_bytes']:
        raise b.StopCollection('At least 3 GB free space is required before starting')
    with b.file_lock(out.parent / 'bybit_complete.lock'), b.keep_awake():
        # Verify identity before any mutation or packaging of an existing session.
        j = b.Journal(out, plan_raw, core_raw, b.sources(), clock=clock, transport=transport)
        error = None
        try:
            if b.utc_ms(j.core['end_exclusive_utc']) > j.clock.now(): raise b.StopCollection('History cutoff is in the future')
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
        greek = ('ΣΥΛΛΟΓΗ BYBIT\nΚατάσταση: ' + summary['status'] + '\n'
                 'Ιστορικό: ' + summary['core_history_status'] + '\n'
                 'Έγκυρα στιγμιότυπα βιβλίου: ' + str(summary['live']['valid_books']) + '\n'
                 'Αυτό είναι αρχείο δεδομένων, όχι αποτέλεσμα κερδοφορίας.\n'
                 'Προσωπικές προμήθειες, πραγματικό leverage/margin και μελλοντικές επιδόσεις παραμένουν άγνωστα.\n'
                 'Ανέβασε το BYBIT_SEND_THIS.zip στη συνομιλία, ακόμη και αν αναφέρει κενά ή σφάλμα.\n')
        (out / 'STATUS_EL.txt').write_text(greek, encoding='utf-8')
        receipt = b.package(out, out.parent / 'BYBIT_SEND_THIS.zip')
        print('\nStatus: ' + summary['status'], flush=True)
        print('UPLOAD ONLY: ' + str((out.parent / 'BYBIT_SEND_THIS.zip').resolve()), flush=True)
        print('SHA256: ' + receipt['sha256'], flush=True)
        return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'bybit_complete_data')
    args = parser.parse_args()
    try:
        result = main(args.output)
        sys.exit(0 if result['status'] == 'ALL_REQUESTED_COMPONENTS_COLLECTED' else 2)
    except b.StopCollection as e:
        parser.exit(2, str(e) + '\nExisting evidence was not changed.\n')
