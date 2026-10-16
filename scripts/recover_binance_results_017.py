"""Reconstruct two lost result files without changing frozen data or rules.
Only byte-identical matches to pre-existing manifest hashes may be restored.
Original zero-byte files are preserved; this is evidence recovery, not tuning.
"""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from run_binance_replay_017 import (ROOT, DESIGN, verify_engine, load_archive,
                                  bounds, engine, save_result, file_sha, write_new)
BASE = ROOT.parent
FROZEN = '59291edfbb05990fd32ebd0be369ac22be1c4c75842a2d6e0a85fd5b5797c807'
INPUT = 'cccf3ff868465439ede973dd505c95d906c9e6eb9a9c31263c040fd053ccd00e'
MANIFEST = '71e492e15aca6cd9086466a31761807636b6a6938acfe705263ee941059fd4dc'
EMPTY = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
TARGETS = [
 ('keltner_breakout__fixed50', 0, False),
 ('obv_breakout__fixed50', 2, True),
]

def main():
    verify_engine(FROZEN)
    source = BASE / 'binance-017-evaluation'
    assert file_sha(source / 'evaluation.json') == MANIFEST
    manifest = json.loads((source / 'evaluation.json').read_text())
    dest = BASE / 'binance-017-result-recovery'
    dest.mkdir()
    (dest / 'original-zero-byte').mkdir()
    write_new(dest / 'intent.json', {
        'purpose': 'Recover exactly two zero-byte result files by deterministic replay',
        'observed_utc': datetime.now(timezone.utc).isoformat(),
        'cause': 'Unknown; no cause inferred',
        'manifest_sha256': MANIFEST, 'input_sha256': INPUT, 'freeze_sha256': FROZEN,
        'targets': TARGETS, 'new_strategy_variants': 0, 'additional_recovery_replays': 2,
        'require_byte_identical_original_hash': True, 'real_orders': 0,
    })
    _, datasets = load_archive(BASE / 'binance-017-normalized.json.gz', INPUT)
    market = engine.prepare(datasets['ETHUSDT'], 'ETHUSDT')
    design = json.loads(DESIGN.read_text())
    start, end = bounds(design, 'evaluation')
    recovered = []
    for candidate, lag, adverse in TARGETS:
        name = f'eval_ETHUSDT_{candidate}_venue_assumption_lag{lag}_adverse{int(adverse)}'
        record = next(r for r in manifest['results']['ETHUSDT'][candidate]
                      if r['file'] == name + '.json.gz')
        original = source / record['file']
        assert original.stat().st_size == 0 and file_sha(original) == EMPTY
        result = engine.replay(market, start, end, candidate=candidate,
                               cost='venue_assumption', lag=lag, adverse_funding=adverse,
                               prepared_signals=engine.make_signals(market, candidate, end))
        new = save_result(dest, name, result)
        assert new == record, 'Recovery differs from original manifest; refuse restoration'
        recovered.append(new)
        print('Byte-identical reconstruction: ' + name, flush=True)
    # Restore only after both full results match their original hashes.
    for record in recovered:
        original = source / record['file']
        original.rename(dest / 'original-zero-byte' / record['file'])
        shutil.copyfile(dest / record['file'], original)
        assert file_sha(original) == record['sha256']
    receipt = {'status': 'RECOVERED_BYTE_IDENTICAL', 'completed_utc': datetime.now(timezone.utc).isoformat(),
               'manifest_sha256_unchanged': file_sha(source / 'evaluation.json'),
               'results': recovered, 'original_zero_byte_files_preserved': True,
               'frozen_sources_unchanged': True, 'additional_integrity_replays': 2,
               'new_scenario_configurations': 0, 'new_strategy_variants': 0, 'real_orders': 0}
    write_new(dest / 'receipt.json', receipt)
    write_new(ROOT / 'research/experiments/017/result-recovery.json', receipt)
    print(json.dumps({'status': receipt['status'], 'additional_integrity_replays': 2}), flush=True)

if __name__ == '__main__':
    main()
