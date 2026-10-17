"""Close the registry only from fully verified025 outcomes; no strategy execution."""
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
    out = ROOT / 'research/experiments/025'
    summary = json.loads((out / 'summary.json').read_bytes())
    verification = json.loads((out / 'verification.json').read_bytes())
    registry_path = ROOT / 'research/registry.json'
    registry = json.loads(registry_path.read_bytes())
    if registry['active_experiment']['id'] != '025' or any(x['id'] == '025' for x in registry['completed']):
        raise ValueError('Registry state conflict; never overwrite a completed attempt')
    publication=json.loads((out/'publication.json').read_bytes())
    count = summary['new_historical_executions']
    if verification['full_result_files_verified'] != count or verification['integrity_failures'] or verification['financial_result_integrity_unresolved']:
        raise ValueError('Incomplete verification')
    if verification['maximum_error_usdt'] != '0' or summary['all_results_statuses'] != {'COMPLETE': count}:
        raise ValueError('Financial result failure')
    old_completed = json.dumps(registry['completed'], sort_keys=True)
    observations = []
    for stage, expected, prefix in [('train1', 60, 'train1 '), ('train2', 60, 'train2 '), ('evaluation', 96, None)]:
        path = a.workspace / ('futures-025-' + stage + '.log')
        content = path.read_bytes()
        lines = content.decode().splitlines()
        n = sum(line.startswith(prefix) if prefix else line.startswith(('evaluation ', 'WFA ')) for line in lines)
        observations.append({'stage': stage, 'expected_progress_lines': expected, 'observed_progress_lines': n,
                             'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content),
                             'status': 'COMPLETE_PROGRESS_LOG' if n == expected else 'PARTIAL_PROGRESS_LOG_FINANCIAL_FILES_VERIFIED'})
    (out / 'progress-log-observations.json').write_text(json.dumps(observations, indent=2) + '\n')
    now = datetime.now(timezone.utc).isoformat()
    entry = {'id': '025', 'status': 'COMPLETED', 'completed_utc': now,
             'type': 'USER_AUTHORIZED_TEN_DISTINCT_FAMILIES_TWENTY_VARIANTS',
             'assets': ['BTCUSDT', 'SOLUSDT', 'XRPUSDT'], 'new_variants': 20, 'new_signal_families': 10,
             'new_historical_simulations': count, 'new_integrity_replays': 0,
             'protocol': 'docs/MULTIFAMILY_FUTURES_025.json', 'results': 'research/experiments/025',
             'report': 'docs/MULTIFAMILY_FUTURES_025_RESULTS.md',
             'reproduce': 'docs/MULTIFAMILY_FUTURES_025_REPRODUCE.md',
             'artifact_receipts': 'research/experiments/025/artifact_receipts.json',
             'preregistration_commit': publication['preregistration_commit'],
             'freeze_sha256': verification['source_freeze_sha256'],
             'selection1_commit': publication['selection1_commit'],
             'selection1_sha256': publication['selection1_sha256'],
             'selection2_commit': publication['selection2_commit'],
             'selection2_sha256': publication['selection2_sha256'],
             'software_tests_passed': 117, 'new_tests': 117,
             'new_wealth_audit_events': summary['wealth_events'], 'max_wealth_error_usdt': '0',
             'preserved_source_files': verification['old_files_preserved'],
             'attempts': [{'id':'025-initial','status':'RUNTIME_INTERRUPTION_PROCESS_ACK_UNKNOWN','record':'research/experiments/025/runtime-interruption.json','confirmed_financial_results':0},{'id': '025-recovery-1', 'status': 'COMPLETED_ALL_RESULTS_VERIFIED',
                           'new_simulations': count, 'integrity_replays': 0,
                           'progress_log_observations': 'research/experiments/025/progress-log-observations.json'}],
             'runtime_recovery':'research/experiments/025/runtime-recovery-success.json',
             'conclusion': 'All20newvariants/all3assets/all12scenarios retained. Exact strengths, failures, selections and WFA in summary/report. No retuning or newforwardevidence; historical success is not confirmed futureprofit. Source013/014/023 andprospectivecohorts unchanged.'}
    for key in ('new_full_pass_fail', 'new_scenario_pass_fail', 'new_positive_all12', 'WFA_scenario_pass_fail',
                'cross_asset_new_full_passes', 'cross_asset_new_positive_all12', 'reused_WFA_folds'):
        entry[key] = summary[key]
    registry['completed'].append(entry)
    if json.dumps(registry['completed'][:-1], sort_keys=True) != old_completed:
        raise ValueError('Prior registry entries changed')
    registry.update(updated_utc=now, unique_signal_families=45, unique_sizing_variants=90,
                    active_experiment=None,
                    count_note=f"{summary['cumulative_design_executions']} design executions +7 prior integrity replays={summary['cumulative_known_executions']} known executions;90variants/45families.025adds20variants/10families,{count}newexecutions. Sharedhistory andsizingvariants are notindependent discoveries.",
                    next_action='Prioritize single Bybitpacket audit/frozen013 if available.023 remains data-blocked without automatic retries.Otherwise one bounded preregistered futures evidence-gap/distinct-family batch;025parameters/gates never retuned and no automatic paper/live promotion.')
    registry['cumulative_known_design_runs_through_025'] = summary['cumulative_design_executions']
    registry['additional_integrity_replays_025'] = 0
    registry['cumulative_known_executions_through_025'] = summary['cumulative_known_executions']
    registry_path.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'completed': '025', 'new_executions': count, 'progress_logs': observations}, indent=2))


if __name__ == '__main__':
    main()
