"""Run frozen descriptive diagnostics on authenticated experiment017 outputs.

No market requests, new trading rules, replay, optimizer or order endpoints.
"""
import argparse
import gzip
import hashlib
import html
import importlib.metadata
import io
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tradingagents.futures_concentration import (
    audit_trade_components, calendar_diagnostics, contribution_diagnostics,
    number, require, sampled_drawdown,
)
from tradingagents.bybit_replay import audit_wealth


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')


def read_result(z, name, expected):
    info = z.getinfo(name)
    require(info.file_size < 100_000_000, 'Oversized compressed result')
    raw = z.read(name)
    require(hashlib.sha256(raw).hexdigest() == expected, 'Archived result hash mismatch: ' + name)
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as f:
        expanded = f.read(300_000_001)
    require(len(expanded) <= 300_000_000, 'Oversized expanded result')
    return json.loads(expanded)


def verify_freeze(expected):
    path = ROOT / 'research/experiments/018/freeze.json'
    require(sha(path) == expected, 'External018freeze mismatch')
    freeze = json.loads(path.read_text())
    for group in ['source_hashes', 'preserved_files']:
        for name, digest in freeze[group].items():
            require(sha(ROOT / name) == digest, 'Changed source: ' + name)
    require(sys.version_info[:2] == (3, 12), 'Requires Python3.12')
    for package, version in freeze['runtime'].items():
        require(importlib.metadata.version(package) == version, 'Runtime mismatch: ' + package)
    return freeze


def diagnostics(result, record):
    require(result['schema'] == 'binance_perpetual_017_v1', 'Wrong venue schema')
    require(result['status'] == 'COMPLETE' and result['metrics'] == record['metrics'], 'Outcome identity mismatch')
    require(result['real_orders'] == 0 and result['symbol'] == 'ETHUSDT', 'Wrong account identity')
    audit = audit_wealth(result)
    trades = audit_trade_components(result)
    metrics = result['metrics']
    attribution = contribution_diagnostics([t['net_before_operating_usdt'] for t in trades],
                                          metrics['operating_expense_usdt'], metrics['initial_usdt'])
    require(number(attribution['net']['usdt']) == number(metrics['net_profit_usdt']), 'Attribution mismatch')
    calendar = calendar_diagnostics(result['curve'], metrics['initial_usdt'], result['start_ms'], result['end_exclusive_ms'])
    dd = sampled_drawdown([r['equity_usdt'] for r in result['curve']])
    require(number(dd['pct']) == number(metrics['max_drawdown_pct']) and
            number(dd['cash_at_max_pct_usdt']) == number(metrics['cash_at_max_pct_drawdown_usdt']), 'Drawdown mismatch')
    flags = []
    if number(metrics['net_profit_usdt']) <= 0: flags.append('NONPOSITIVE_ORIGINAL_NET')
    if number(attribution['without_best_positive_trade']['usdt']) <= 0: flags.append('NONPOSITIVE_WITHOUT_BEST_TRADE_CONTRIBUTION')
    if calendar['positive_years'] != 2: flags.append('NOT_BOTH_CALENDAR_YEARS_POSITIVE')
    return {'file': record['file'], 'sha256': record['sha256'], 'candidate': result['candidate'],
            'benchmark': result['benchmark'], 'cost': result['cost'], 'lag': result['lag_days'],
            'adverse_funding': result['adverse_funding_5bps'], 'original_metrics': metrics,
            'trade_attribution': attribution, 'reconstructed_trades': trades,
            'calendar_attribution': calendar, 'sampled_drawdown': dd,
            'diagnostic_flags': flags, 'descriptive_diagnostic_pass': not flags,
            'independent_wealth_audit': audit}


def summarize(cases, original):
    summaries = []
    for candidate in sorted(original['gates']['ETHUSDT']):
        group = [r for r in cases if r['candidate'] == candidate]
        require(len(group) == 12, 'Missing candidate scenario')
        baseline = next(r for r in group if r['cost'] == 'venue_assumption' and r['lag'] == 0 and not r['adverse_funding'])
        stress = next(r for r in group if r['cost'] == 'stress_assumption' and r['lag'] == 0 and not r['adverse_funding'])
        def worst(key):
            return min(group, key=lambda r: number(r['trade_attribution'][key]['usdt']))
        summaries.append({'candidate': candidate, 'baseline': baseline, 'stress': stress,
                          'worst_original': min(group, key=lambda r: number(r['original_metrics']['net_profit_usdt'])),
                          'worst_without_best_trade': worst('without_best_positive_trade'),
                          'worst_without_two_best_trades': worst('without_two_best_positive_trades'),
                          'scenarios_passing_descriptive_diagnostics': sum(r['descriptive_diagnostic_pass'] for r in group),
                          'all12_descriptive_pass': all(r['descriptive_diagnostic_pass'] for r in group),
                          'both_years_positive_scenarios': sum(r['calendar_attribution']['positive_years'] == 2 for r in group),
                          'original_gate': original['gates']['ETHUSDT'][candidate],
                          'failed_diagnostics': [{'file': r['file'], 'flags': r['diagnostic_flags']} for r in group if r['diagnostic_flags']]})
    return summaries


def fmt(value):
    return f'{number(value):+,.2f}'


def pair(value):
    return fmt(value['pct_initial']) + '% / ' + fmt(value['usdt']) + ' USDT'


def table(headers, rows):
    return '<div class="scroll"><table><tr>' + ''.join('<th>' + html.escape(h) + '</th>' for h in headers) + '</tr>' + ''.join('<tr>' + ''.join('<td>' + html.escape(str(c)) + '</td>' for c in r) + '</tr>' for r in rows) + '</table></div>'


def reports(out, summaries, cases, freeze_sha, freeze_commit):
    labels = {'aroon_trend__fixed50': 'Aroon', 'cci_reversion__fixed50': 'CCI',
              'keltner_breakout__fixed50': 'Keltner', 'obv_breakout__fixed50': 'OBV',
              'regression_trend__fixed50': 'Regression', 'sma200_band__vol15_cap50': 'SMA200 / vol15'}
    rows, years = [], []
    for s in summaries:
        b = s['baseline']; attr = b['trade_attribution']
        worst = s['worst_without_best_trade']['trade_attribution']['without_best_positive_trade']
        rows.append([labels[s['candidate']], pair(attr['net']), pair(attr['without_best_positive_trade']),
                     pair(worst), pair(s['worst_without_two_best_trades']['trade_attribution']['without_two_best_positive_trades']),
                     b['original_metrics']['signal_exits'], str(s['scenarios_passing_descriptive_diagnostics']) + '/12'])
        for year in b['calendar_attribution']['years']:
            years.append([labels[s['candidate']], year['year'], fmt(year['return_pct_start_equity']) + '% / ' + fmt(year['pnl_usdt']) + ' USDT',
                          f"{number(year['sampled_drawdown']['pct']):.2f}% / {number(year['sampled_drawdown']['cash_at_max_pct_usdt']):,.2f} USDT"])
    passed = sum(s['all12_descriptive_pass'] for s in summaries)
    body = '<h1>018 — Πόσο εξαρτάται το κέρδος από λίγες συναλλαγές;</h1>'
    body += f'<p>Ελέγχθηκαν και οι έξι υπάρχουσες στρατηγικές Binance ETHUSDT σε 72 διαδρομές και πέντε σημεία αναφοράς. <b>{passed}/6</b> πέρασαν το νέο περιγραφικό φίλτρο σε όλα τα σενάρια. Αυτό δεν αλλάζει τα αρχικά κριτήρια: <b>0/6 παραμένουν πλήρως αποδεκτές</b>, λόγω μικρού αριθμού συναλλαγών.</p>'
    body += '<p>Περίοδος 1/1/2024–31/12/2025, ανεξάρτητο αρχικό κεφάλαιο 10.000 USDT ανά διαδρομή. Δεν δημιουργήθηκαν νέοι κανόνες και δεν επαναλήφθηκαν backtests. Πρόκειται για 77 νέες αναλύσεις υφιστάμενων αποτελεσμάτων, όχι 77 νέες προσομοιώσεις.</p>'
    body += '<h2>Συγκέντρωση αποτελέσματος</h2><p>Αφαιρείται η καθαρή συμβολή της καλύτερης θετικής συναλλαγής, μαζί με τις δικές της προμήθειες και funding. Οι άλλες καταγεγραμμένες ποσότητες και ολόκληρο το λειτουργικό κόστος μένουν σταθερά. Αυτό είναι διαγνωστική αριθμητική, <b>όχι</b> νέα απόδοση στρατηγικής ή προσομοίωση χαμένης εντολής. Σε πραγματική απουσία συναλλαγής θα άλλαζαν τα μετέπειτα διαθέσιμα και πιθανώς οι θέσεις.</p>'
    body += table(['Στρατηγική', 'Αρχικό βασικό καθαρό', 'Χωρίς καλύτερη — βάση', 'Χωρίς καλύτερη — χειρότερο 12', 'Χωρίς δύο καλύτερες — χειρότερο 12', 'Έξοδοι βάσης', 'Περιγραφικό φίλτρο'], rows)
    body += '<p>Το νέο φίλτρο απαιτεί: αρχικό καθαρό κέρδος &gt;0, υπόλοιπο χωρίς την καλύτερη συμβολή &gt;0, και θετικό αποτέλεσμα τόσο στο 2024 όσο και στο 2025, σε κάθε ένα από τα 12 σενάρια. Είναι διαγνωστικό, όχι στατιστική απόδειξη. Η αφαίρεση δύο συναλλαγών και του καλύτερου μήνα αναφέρεται χωριστά χωρίς αλλαγή του φίλτρου.</p>'
    body += '<h2>Κάθε έτος ξεχωριστά — βασικό σενάριο</h2>' + table(['Στρατηγική', 'Έτος', 'Μεταβολή από κεφάλαιο αρχής έτους', 'Πτώση εντός έτους'], years)
    body += '<p>Οι θέσεις συνεχίζονται στα όρια του έτους και η μεταβολή περιλαμβάνει μη πραγματοποιημένο κέρδος/ζημιά. Χρησιμοποιείται το κλείσιμο της τελευταίας ώρας πριν από το funding του επόμενου έτους. Η ετήσια πτώση μετριέται από την προηγούμενη κορυφή μέσα στο έτος. Τα ετήσια ποσοστά δεν προστίθενται. Αυτή είναι ημερολογιακή ανάλυση της ίδιας διαδρομής, <b>όχι expanding walk-forward</b>. Δεν υπολογίστηκε νέο walk-forward στο 018· παραμένει συγκεκριμένη εκκρεμότητα για επόμενο ξεχωριστό πείραμα.</p>'
    body += '<h2>Επιλογή, κόστη και περιορισμοί</h2><p>Η ήδη παγωμένη επιλογή βάσει του 2023 παρέμεινε σε μετρητά: όλες οι στρατηγικές είχαν λιγότερες από τις 10 απαιτούμενες εξόδους. Το σημείο αναφοράς μετρητών του 017 έχει μηδενικό λειτουργικό κόστος και 0% απόδοση. Δεν αντικαθίσταται εκ των υστέρων από τον καλύτερο υποψήφιο.</p>'
    body += '<p>Κάθε πλευρά συναλλαγής: βασική υπόθεση 0,055% προμήθεια + 0,020% ολίσθηση· δυσμενής 0,100% + 0,100%. Λειτουργικά 120 USDT/έτος, ιστορικά επιτόκια funding με ωριαίο mark-price proxy και χωριστή δυσμενή αποτίμηση 5 bps. Διατηρούνται όλες οι καθυστερήσεις 0/1/2 ημερών. Δεν πρόκειται για προσωπικές προμήθειες, πραγματικά fills, αποδεδειγμένη ιστορική ρευστότητα ή μοχλευμένη liquidation προσομοίωση.</p>'
    body += '<p>Όλες οι έξι συμβατές διαδρομές στρατηγικών εξετάζονται, όχι μόνο οι παλιότεροι νικητές. Οι υπόλοιπες 40 από τις συνολικές 46 παραλλαγές δεν διαθέτουν αντίστοιχες native Binance διαδρομές και δεν αναμειγνύονται με USD spot. Τα 12 σενάρια και οι έξι συγγενείς στρατηγικές είναι συσχετισμένα. Δεν υπολογίζεται διορθωμένη πιθανότητα κερδοφορίας ή p-value. Η προεγγραφή αυτού του διαγνωστικού ελέγχου έγινε αφού ήταν ήδη γνωστά τα συγκεντρωτικά αποτελέσματα του 017.</p>'
    body += '<p>Σύνολο: 46 μοναδικές παραλλαγές / 23 οικογένειες, μηδενικές νέες. Οι καταγεγραμμένες ερευνητικές προσομοιώσεις παραμένουν 7.427, συν δύο παλιότερες επαναλήψεις αποκατάστασης αρχείων (7.429 εκτελέσεις). Μηδενικές πραγματικές εντολές. Η Bybit παραμένει χωριστή, σε αναμονή του ενός ενιαίου πακέτου.</p>'
    body += f'<h2>Αναπαραγωγή</h2><p>Δημοσιευμένο πάγωμα πριν από τους νέους υπολογισμούς: <a href="https://github.com/rafailm95/TradingAgents/commit/{freeze_commit}">{freeze_commit}</a>. SHA256: <code>{freeze_sha}</code>. Όλα τα αναλυτικά αποτελέσματα, μηνιαίες τιμές και αποτυχίες βρίσκονται στο συνοδευτικό JSON/ZIP και στο repository.</p>'
    body += '<p>Μεθοδολογικό υπόβαθρο: <a href="https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf">Bailey et al., The Probability of Backtest Overfitting (2015)</a>. Η εργασία τεκμηριώνει το πρόβλημα πολλαπλών δοκιμών· δεν πιστοποιεί το δικό μας διαγνωστικό φίλτρο. Δεδομένα <a href="https://github.com/binance/binance-public-data">Binance Vision</a>, παράγωγη ανάλυση CC BY-NC-SA 4.0· προσωπική μη παραγωγική έρευνα, χωρίς έγκριση Binance.</p>'
    page = '<!doctype html><html lang="el"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Futures 018 — Συγκέντρωση κερδών</title><style>body{font:16px/1.65 system-ui,sans-serif;margin:auto;padding:24px;max-width:1150px;color:#173047;background:#f7f9fb}h1{line-height:1.2}h2{margin-top:30px}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px;background:white}th,td{padding:11px;border:1px solid #d9e1e7;text-align:left;min-width:90px}th{background:#183b52;color:white}code{overflow-wrap:anywhere}a{color:#135c86}</style></head><body>' + body + '</body></html>'
    (out / 'Futures_018_Concentration_EL.html').write_text(page)
    md = '# Futures018 contribution-concentration diagnostics\n\n'
    md += 'Descriptive analysis of existing Binance ETHUSDT outputs for 2024–2025, not new simulations or strategy rules. Initial capital: 10,000 USDT per original path. Fixed-size contribution removals are not causal missing-fill counterfactuals. All original gates and the 2023 cash selection remain unchanged. No new walk-forward run was performed; calendar attribution is not walk-forward validation.\n\n'
    md += '| Candidate | Original baseline | Baseline without best trade | Worst12 without best trade | Worst12 without top two | Base signal exits | Descriptive passes |\n|---|---|---|---|---|---|---|\n'
    md += ''.join('| ' + ' | '.join(str(x) for x in row) + ' |\n' for row in rows)
    md += f'\nAll12 descriptive passes: {passed}/6. Original historical gates: 0/6. All 72 candidate paths and five benchmarks retained. The descriptive filter requires original positive net, positive static remainder after the best profitable trade, and both calendar years positive. Top-two removals are a separate diagnostic, not an adjusted gate.\n\n'
    md += 'Costs: 5.5 fee + 2 slippage bps/side baseline; 10 + 10 stress; 120 USDT/year operating expense. Preserve 0/1/2-day feed lags and both funding valuations. Funding rates are observed; settlement marks and execution rules are modeled. No order book, historical fill, personal-fee or liquidation validation. All six compatible native-futures variants are retained; 40 other variants lack comparable native Binance outputs. No p-values or independence claim. Zero new strategies; 46 variants, 23 families; 7,427 design runs plus two prior recovery replays, unchanged.\n\n'
    md += f'Pre-analysis freeze commit: {freeze_commit}; freeze SHA256: {freeze_sha}. Primary methodological context: https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf . This is not an implementation of PBO. Data/derived analysis CC BY-NC-SA 4.0.\n'
    (out / 'RESULTS.md').write_text(md)


def main(args):
    freeze = verify_freeze(args.freeze_sha256)
    require(not args.output.exists(), 'Output exists; preserve original attempts')
    require(sha(args.archive) == freeze['input_archive_sha256'], 'Evidence archive identity mismatch')
    args.output.mkdir(parents=True)
    write_new(args.output / 'intent.json', {'experiment': '018', 'freeze_sha256': args.freeze_sha256,
                                           'freeze_commit': args.freeze_commit, 'new_strategy_simulations': 0, 'real_orders': 0})
    try:
        protocol = json.loads((ROOT / 'docs/FUTURES_CONCENTRATION_018.json').read_text())
        with zipfile.ZipFile(args.archive) as z:
            require(len(z.namelist()) == len(set(z.namelist())), 'Duplicate archive members')
            require(z.testzip() is None, 'Archive CRC failure')
            raw = z.read('binance-017-evaluation/evaluation.json')
            require(hashlib.sha256(raw).hexdigest() == protocol['evaluation_manifest_sha256'], 'Evaluation manifest mismatch')
            original = json.loads(raw)
            require(original['evaluation_bounds'] == protocol['evaluation_bounds'], 'Wrong period')
            require(set(original['results']) == {'ETHUSDT'}, 'Wrong symbol set')
            require(sorted(original['results']['ETHUSDT']) == sorted(protocol['candidates']), 'Candidate set mismatch')
            records = [r for values in original['results']['ETHUSDT'].values() for r in values]
            records += list(original['benchmarks']['ETHUSDT'].values())
            require(len(records) == 77 and len({r['file'] for r in records}) == 77, 'Wrong scenario count')
            cases = []
            for i, record in enumerate(records):
                require('/' not in record['file'] and '\\' not in record['file'], 'Invalid result filename')
                result = read_result(z, 'binance-017-evaluation/' + record['file'], record['sha256'])
                cases.append(diagnostics(result, record))
                if (i + 1) % 12 == 0: print(f'Verified and analyzed {i + 1}/77 existing paths', flush=True)
        summaries = summarize(cases, original)
        write_new(args.output / 'cases.json', cases)
        summary = {'experiment': '018', 'status': 'COMPLETE', 'freeze_sha256': args.freeze_sha256,
                   'freeze_commit': args.freeze_commit, 'input_archive_sha256': freeze['input_archive_sha256'],
                   'candidate_paths': 72, 'benchmark_paths': 5, 'new_strategy_simulations': 0,
                   'new_unique_variants': 0, 'total_variants': 46, 'total_families': 23,
                   'cumulative_design_runs': 7427, 'cumulative_executions_with_recovery': 7429,
                   'all12_descriptive_passes': [s['candidate'] for s in summaries if s['all12_descriptive_pass']],
                   'original_full_gate_passes': [], 'training_selection': original['frozen_train_selection'],
                   'new_walk_forward_runs': 0, 'calendar_attribution_is_not_walk_forward': True,
                   'candidates': summaries, 'real_orders': 0}
        write_new(args.output / 'summary.json', summary)
        reports(args.output, summaries, cases, args.freeze_sha256, args.freeze_commit)
        verify_freeze(args.freeze_sha256)
        write_new(args.output / 'verification.json', {'status': 'PASS', 'input_sha256': sha(args.archive),
            'result_hashes_verified': len(cases), 'independent_wealth_events': sum(r['independent_wealth_audit']['events_checked'] for r in cases),
            'maximum_wealth_error_usdt': str(max(number(r['independent_wealth_audit']['max_error_usdt']) for r in cases)),
            'reconstructed_trade_records': sum(len(r['reconstructed_trades']) for r in cases),
            'sources_unchanged': True, 'output_hashes': {p.name: sha(p) for p in sorted(args.output.iterdir()) if p.is_file()}})
        print(json.dumps({'status': 'COMPLETE', 'summary_sha256': sha(args.output / 'summary.json'), 'paths': 77}), flush=True)
    except Exception as exc:
        write_new(args.output / 'stopped.json', {'status': 'STOPPED_REVIEW_REQUIRED', 'error': type(exc).__name__ + ': ' + str(exc)})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--freeze-sha256', required=True)
    parser.add_argument('--freeze-commit', required=True)
    main(parser.parse_args())
