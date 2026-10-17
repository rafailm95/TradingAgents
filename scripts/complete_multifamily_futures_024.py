"""Close the registry only from fully verified024 outcomes; no strategy execution."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--workspace', type=Path, required=True)
    a = p.parse_args()
    out = ROOT / 'research/experiments/024'
    summary = json.loads((out / 'summary.json').read_bytes())
    verification = json.loads((out / 'verification.json').read_bytes())
    registry_path = ROOT / 'research/registry.json'
    registry = json.loads(registry_path.read_bytes())
    if registry['active_experiment']['id'] != '024' or any(x['id'] == '024' for x in registry['completed']):
        raise ValueError('Registry state conflict; never overwrite a completed attempt')
    count = summary['new_historical_executions']
    if verification['full_result_files_verified'] != count or verification['integrity_failures'] or verification['financial_result_integrity_unresolved']:
        raise ValueError('Incomplete verification')
    if verification['maximum_error_usdt'] != '0' or summary['all_results_statuses'] != {'COMPLETE': count}:
        raise ValueError('Financial result failure')
    old_completed = json.dumps(registry['completed'], sort_keys=True)
    observations = []
    for stage, expected, prefix in [('train1', 60, 'train1 '), ('train2', 60, 'train2 '), ('evaluation', 96, None)]:
        path = a.workspace / ('futures-024-' + stage + '.log')
        content = path.read_bytes()
        lines = content.decode().splitlines()
        n = sum(line.startswith(prefix) if prefix else line.startswith(('evaluation ', 'WFA ')) for line in lines)
        observations.append({'stage': stage, 'expected_progress_lines': expected, 'observed_progress_lines': n,
                             'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content),
                             'status': 'COMPLETE_PROGRESS_LOG' if n == expected else 'PARTIAL_PROGRESS_LOG_FINANCIAL_FILES_VERIFIED'})
    (out / 'progress-log-observations.json').write_text(json.dumps(observations, indent=2) + '\n')
    now = datetime.now(timezone.utc).isoformat()
    entry = {'id': '024', 'status': 'COMPLETED', 'completed_utc': now,
             'type': 'USER_AUTHORIZED_TEN_DISTINCT_FAMILIES_TWENTY_VARIANTS',
             'assets': ['BTCUSDT', 'SOLUSDT', 'XRPUSDT'], 'new_variants': 20, 'new_signal_families': 10,
             'new_historical_simulations': count, 'new_integrity_replays': 0,
             'protocol': 'docs/MULTIFAMILY_FUTURES_024.json', 'results': 'research/experiments/024',
             'report': 'docs/MULTIFAMILY_FUTURES_024_RESULTS.md',
             'reproduce': 'docs/MULTIFAMILY_FUTURES_024_REPRODUCE.md',
             'artifact_receipts': 'research/experiments/024/artifact_receipts.json',
             'preregistration_commit': 'ce5344ba556ffd3312faa68f68aadcf6f40dbda0',
             'freeze_sha256': verification['source_freeze_sha256'],
             'selection1_commit': '115ef568b725e72590a19df558602a570c0704a6',
             'selection1_sha256': '354db42cacfa74c2a9d349b4f7717265e5565703ea05d0735b75ee92b377834b',
             'selection2_commit': '6ccbcdfc11d81618c76480dca307871e8aec9b1d',
             'selection2_sha256': '7cec2b484e2e6a8e004f90e8c04ffd089cea413a5417355e79085a5ef31ca451',
             'software_tests_passed': 88, 'new_tests': 88,
             'new_wealth_audit_events': summary['wealth_events'], 'max_wealth_error_usdt': '0',
             'preserved_source_files': verification['old_files_preserved'],
             'attempts': [{'id': '024-initial', 'status': 'COMPLETED_ALL_RESULTS_VERIFIED',
                           'new_simulations': count, 'integrity_replays': 0,
                           'progress_log_observations': 'research/experiments/024/progress-log-observations.json'}],
             'conclusion': 'All20newvariants/all3assets/all12scenarios retained. Exact strengths, failures, selections and WFA in summary/report. No retuning or newforwardevidence; historical success is not confirmed futureprofit. Source013/014/023 andprospectivecohorts unchanged.'}
    for key in ('new_full_pass_fail', 'new_scenario_pass_fail', 'new_positive_all12', 'WFA_scenario_pass_fail',
                'cross_asset_new_full_passes', 'cross_asset_new_positive_all12', 'reused_WFA_folds'):
        entry[key] = summary[key]
    registry['completed'].append(entry)
    if json.dumps(registry['completed'][:-1], sort_keys=True) != old_completed:
        raise ValueError('Prior registry entries changed')
    registry.update(updated_utc=now, unique_signal_families=35, unique_sizing_variants=70,
                    active_experiment=None,
                    count_note=f"{summary['cumulative_design_executions']} design executions +7 prior integrity replays={summary['cumulative_known_executions']} known executions;70variants/35families.024adds20variants/10families,{count}newexecutions. Sharedhistory andsizingvariants are notindependent discoveries.",
                    next_action='Prioritize single Bybitpacket audit/frozen013 if available.023 remains data-blocked without automatic retries.Otherwise one bounded preregistered futures evidence-gap/distinct-family batch;024parameters/gates never retuned and no automatic paper/live promotion.')
    registry['cumulative_known_design_runs_through_024'] = summary['cumulative_design_executions']
    registry['additional_integrity_replays_024'] = 0
    registry['cumulative_known_executions_through_024'] = summary['cumulative_known_executions']
    registry_path.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'completed': '024', 'new_executions': count, 'progress_logs': observations}, indent=2))


if __name__ == '__main__':
    main()
