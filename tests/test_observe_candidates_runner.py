"""Exercise download orchestration using synthetic inputs; no network calls."""
from datetime import datetime
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from tradingagents import candidate_journal as journal

SCRIPT=Path(__file__).parents[1]/'scripts/observe_candidates.py'
spec=importlib.util.spec_from_file_location('observe_candidates_runner',SCRIPT)
runner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def clock(monkeypatch,value):
    monkeypatch.setattr(journal,'utc_now',lambda:datetime.fromisoformat(value))


def test_early_wrapper_has_no_download_or_state_directory(monkeypatch,tmp_path):
    clock(monkeypatch,'2026-10-16T12:00:00+00:00')
    def forbidden(*a,**k):raise AssertionError('Network/download should not run')
    monkeypatch.setattr(runner.subprocess,'run',forbidden)
    state=tmp_path/'state'
    assert runner.run(state)['status']=='WAITING_FOR_NEW_CANDLES'
    assert not state.exists()


def test_download_and_record_then_duplicate_without_download(monkeypatch,tmp_path):
    clock(monkeypatch,'2026-10-18T00:10:00+00:00')
    calls=[]
    def download(command,**kwargs):
        calls.append(command)
        start=command[command.index('--start')+1]
        end=command[command.index('--end-exclusive')+1]
        output=Path(command[command.index('--output')+1]);output.mkdir(parents=True)
        dates=pd.date_range(start,end,inclusive='left');assert len(dates)==200
        assert end=='2026-10-18'
        assert kwargs['timeout']==90 and not kwargs['check']
        pd.DataFrame({'Date':dates,'Open':100.,'High':101.,'Low':99.,'Close':100.,'Volume':10.}).to_csv(output/'btc_coinbase_daily.csv',index=False)
        return SimpleNamespace(returncode=0,stderr='',stdout='Synthetic download fixture')
    monkeypatch.setattr(runner.subprocess,'run',download)
    state=tmp_path/'state'
    assert runner.run(state)['status']=='RECORDED'
    assert runner.run(state)['status']=='ALREADY_RECORDED'
    assert len(calls)==1
    assert journal.verify(state/'journal')['records']==1


def test_download_failure_not_retried_or_recorded(monkeypatch,tmp_path):
    clock(monkeypatch,'2026-10-18T00:10:00+00:00');calls=[]
    def fail(*a,**k):calls.append(1);return SimpleNamespace(returncode=1,stderr='failed')
    monkeypatch.setattr(runner.subprocess,'run',fail)
    state=tmp_path/'state';outcome=runner.run(state)
    assert outcome['status']=='DOWNLOAD_FAILED' and outcome['record_created'] is False
    assert len(calls)==1 and not (state/'journal').exists()


def test_existing_lock_refuses_before_download(monkeypatch,tmp_path):
    clock(monkeypatch,'2026-10-18T00:10:00+00:00')
    def forbidden(*a,**k):raise AssertionError('Should inspect the locked journal first')
    monkeypatch.setattr(runner.subprocess,'run',forbidden)
    state=tmp_path/'state';(state/'journal/.record.lock').mkdir(parents=True)
    with pytest.raises(ValueError,match='locked'):runner.run(state)


def test_timeout_never_retries(monkeypatch,tmp_path):
    clock(monkeypatch,'2026-10-18T00:10:00+00:00');calls=[]
    def timeout(command,**k):
        calls.append(1)
        raise runner.subprocess.TimeoutExpired(command,k['timeout'])
    monkeypatch.setattr(runner.subprocess,'run',timeout)
    with pytest.raises(runner.subprocess.TimeoutExpired):runner.run(tmp_path/'state')
    assert len(calls)==1 and not (tmp_path/'state/journal').exists()
