"""Offline browser profile checks; no real data requests or PnL."""
import json
import sys
import zipfile
from pathlib import Path

import pytest
from tests.test_bybit_packet_026 import setup, raw, b, audit_module

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import collect_bybit_history_browser as browser


def call(j, server, clock, **kwargs):
    return browser.collect(j.out, transport=server, clock=clock,
                           plan_raw=raw(j.plan), core_raw=raw(j.core),
                           source_hashes={'test': 'fixture'}, **kwargs)


def test_history_only_preserves_core_export_without_claiming_live(tmp_path):
    j, server, clock = setup(tmp_path)
    r = call(j, server, clock)
    assert r['summary']['core_history_status'] == 'COMPLETE'
    assert r['summary']['live']['valid_books'] == 0
    assert r['summary']['status'] == 'COLLECTED_WITH_GAPS_REVIEW_REQUIRED'
    assert not {'book', 'ticker', 'trades'} & {x[0] for x in server.calls}
    checked = audit_module.audit(r['zip'], r['receipt']['sha256'],
        plan_raw=raw(j.plan), core_raw=raw(j.core), source_hashes={'test': 'fixture'}, return_core=True)
    assert checked['replay_core_validation']['status'] == 'COMPLETE'
    assert len(checked['datasets']) == 3
    n = len(server.calls)
    call(j, server, clock)
    assert len(server.calls) == n


@pytest.mark.parametrize('code,body', [(403,b'blocked'), (200,b'<html>Site Unavailable</html>')])
def test_block_packages_and_cell_rerun_does_not_retry(tmp_path,code,body):
    j, server, clock = setup(tmp_path)
    server.failures = [(code,body)]
    r = call(j, server, clock)
    assert r['summary']['status'] == 'STOPPED_WITH_EVIDENCE'
    assert len(server.calls) == 1
    r2 = call(j, server, clock)
    assert len(server.calls) == 1
    with zipfile.ZipFile(r2['zip']) as z:
        assert 'response_000000.bin.gz' in z.namelist()


def test_session_budget_packages_partial_and_resume_uses_saved_pages(tmp_path):
    j, server, clock = setup(tmp_path)
    r = call(j, server, clock, budget_seconds=.05)
    assert len(server.calls) == 1
    assert 'session budget' in r['summary']['error']
    r2 = call(j, server, clock)
    assert r2['summary']['core_history_status'] == 'COMPLETE'
    assert sum(c[0:2] == ('instrument','BTCUSDT') for c in server.calls) == 1


def test_interrupt_keeps_response_journal_and_partial_zip(tmp_path):
    j, server, clock = setup(tmp_path)
    server.failures = [KeyboardInterrupt('synthetic stop')]
    r = call(j, server, clock)
    assert 'KeyboardInterrupt' in r['summary']['error']
    assert r['receipt']['offline_integrity'] == 'PASS'
    assert r['summary']['successful_responses'] == 0


def test_other_profile_folder_is_not_overwritten(tmp_path):
    j, server, clock = setup(tmp_path)
    old = {'schema': 'bybit_packet_026_state_v1', 'rounds': []}
    b.write(j.out / 'state.json', old)
    with pytest.raises(b.StopCollection,match='separate folder'):
        call(j, server, clock)
    assert json.loads((j.out/'state.json').read_bytes()) == old
    assert server.calls == []


def test_incomplete_mark_history_does_not_export_replay_input(tmp_path):
    j, server, clock = setup(tmp_path)
    server.mutate = lambda p,k,s:p['result'].update(list=[]) if k=='mark' and s=='ETHUSDT' else None
    r = call(j, server, clock)
    assert r['summary']['core_history_status'] != 'COMPLETE'
    with pytest.raises(ValueError,match='Incomplete frozen013'):
        audit_module.audit(r['zip'],r['receipt']['sha256'],plan_raw=raw(j.plan),
            core_raw=raw(j.core),source_hashes={'test':'fixture'},return_core=True)
