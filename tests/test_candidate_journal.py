"""Only synthetic fixtures/mock clocks create future-date test records."""
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tradingagents import candidate_journal as journal


def clock(monkeypatch, value="2026-10-18T00:10:00+00:00"):
    monkeypatch.setattr(journal, "utc_now", lambda: datetime.fromisoformat(value))


def dataset(tmp_path, last="2026-10-17", count=300):
    # Deterministic synthetic positive prices, unrelated to real future markets.
    c = 100 + .05 * np.arange(count) + 2 * np.sin(np.arange(count) / 7)
    frame = pd.DataFrame({"Date":pd.date_range(end=last, periods=count),
        "Open":c, "High":c+1, "Low":c-1, "Close":c, "Volume":10.})
    path = tmp_path / f"data-{last}-{count}.csv"
    frame.to_csv(path,index=False)
    return path


def stored(root, day="2026-10-17"):
    return journal.strict_json((root/day/"observation.json").read_bytes())


def test_frozen_contract_binds_two_different_selection_classes():
    raw, spec, code_hash = journal.contract()
    assert journal.digest(raw) == journal.WATCHLIST_SHA256
    assert len(code_hash)==64
    assert [c["id"] for c in spec["candidates"]] == ["breakout20__vol15_cap50", "sma200_band__vol15_cap50"]
    assert [c["selection_class"] for c in spec["candidates"]] == ["TRAIN_ONLY_SELECTED_ON_REUSED_HISTORY", "POST_HOC_EXPLORATORY"]


@pytest.mark.parametrize("now", ["2026-10-16T12:00:00+00:00", "2026-10-17T23:59:59+00:00", "2026-10-18T00:30:00+03:00"])
def test_early_clock_does_not_read_csv_or_initialize(tmp_path,monkeypatch,now):
    clock(monkeypatch,now)
    root=tmp_path/'journal'
    assert journal.observe(tmp_path/'absent.csv',root)["status"]=='WAITING_FOR_NEW_CANDLES'
    assert not root.exists()


@pytest.mark.parametrize("now",["2026-10-18T00:00:00+00:00","2026-10-18T03:30:00+03:00"])
def test_first_eligible_day_records_both_and_replays(tmp_path,monkeypatch,now):
    clock(monkeypatch,now)
    root=tmp_path/'journal'; data=dataset(tmp_path)
    assert journal.observe(data,root)["status"]=='RECORDED'
    record=stored(root);p=record['payload']
    assert p['as_of_utc_day']=='2026-10-17' and p['snapshot_rows']==200
    assert p['source']['received_rows']==300
    assert p['unrecorded_days_since_previous']==0 and p['previous_record_sha256']==journal.ZERO_HASH
    assert len(p['candidates'])==2 and p['orders']==0
    assert not ({'positions','fills','pnl'} & set(p))
    assert journal.verify(root)['records']==1
    assert len(pd.read_csv(root/'2026-10-17/candles.csv'))==200


def test_indicators_and_sizing_match_direct_arithmetic(tmp_path,monkeypatch):
    clock(monkeypatch);root=tmp_path/'journal';data=dataset(tmp_path)
    journal.observe(data,root);p=stored(root)['payload']
    frame=pd.read_csv(root/'2026-10-17/candles.csv')
    close=frame.Close.to_numpy();sma=close.mean()
    vol=np.std(np.diff(close[-61:])/close[-61:-1],ddof=1)*np.sqrt(365.25)
    assert p['indicators']['sma200']==pytest.approx(sma)
    for c in p['candidates']:
        assert c['annualized_vol60']==pytest.approx(vol)
        assert c['hypothetical_entry_fraction']==pytest.approx(min(.5,.15/vol))
        if c['family']=='breakout20':
            enter=close[-1]>sma and close[-1]>frame.High.iloc[-21:-1].max()
            leave=close[-1]<sma or close[-1]<frame.Low.iloc[-11:-1].min()
        else:
            enter,leave=close[-1]>1.01*sma,close[-1]<.99*sma
        assert c['entry_condition'] is bool(enter)
        assert c['exit_condition'] is bool(leave)


def test_duplicate_preserves_first_observation_time_and_bytes(tmp_path,monkeypatch):
    clock(monkeypatch);root=tmp_path/'journal';data=dataset(tmp_path)
    journal.observe(data,root)
    path=root/'2026-10-17/observation.json';before=path.read_bytes()
    clock(monkeypatch,'2026-10-18T16:00:00+00:00')
    assert journal.observe(data,root)['status']=='ALREADY_RECORDED'
    assert path.read_bytes()==before


def test_unused_history_revision_does_not_rewrite_first_provenance(tmp_path,monkeypatch):
    clock(monkeypatch);root=tmp_path/'journal';data=dataset(tmp_path)
    journal.observe(data,root);before=stored(root)
    frame=pd.read_csv(data);frame.loc[0,'Volume']=11;frame.to_csv(data,index=False)
    assert journal.observe(data,root)['status']=='ALREADY_RECORDED'
    assert stored(root)==before


def test_used_data_revision_is_conflict_even_if_signals_unchanged(tmp_path,monkeypatch):
    clock(monkeypatch);root=tmp_path/'journal';data=dataset(tmp_path)
    journal.observe(data,root);before=stored(root)
    frame=pd.read_csv(data);frame.loc[299,'Volume']=11;frame.to_csv(data,index=False)
    with pytest.raises(ValueError,match='revised input'):
        journal.observe(data,root)
    assert stored(root)==before


def test_stale_data_never_backfilled(tmp_path,monkeypatch):
    clock(monkeypatch,'2026-10-19T00:10:00+00:00')
    root=tmp_path/'journal'
    assert journal.observe(dataset(tmp_path),root)['status']=='WAITING_FOR_NEW_CANDLES'
    assert not root.exists()


@pytest.mark.parametrize('issue',['future','gap','too_short','too_many','bad_ohlc','nan'])
def test_invalid_input_fails_before_journal_mutation(tmp_path,monkeypatch,issue):
    clock(monkeypatch);root=tmp_path/'journal'
    data=dataset(tmp_path,last='2026-10-18' if issue=='future' else '2026-10-17',count=199 if issue=='too_short' else 4001 if issue=='too_many' else 300)
    frame=pd.read_csv(data)
    if issue=='gap':frame=frame.drop(20)
    elif issue=='bad_ohlc':frame.loc[299,'High']=1
    elif issue=='nan':frame.loc[299,'Close']=np.nan
    frame.to_csv(data,index=False)
    with pytest.raises(ValueError):journal.observe(data,root)
    assert not root.exists()


def test_gap_is_explicit_without_invented_missing_records(tmp_path,monkeypatch):
    clock(monkeypatch);root=tmp_path/'journal';journal.observe(dataset(tmp_path),root)
    first=stored(root)
    clock(monkeypatch,'2026-10-21T01:00:00+00:00')
    journal.observe(dataset(tmp_path,last='2026-10-20'),root)
    second=stored(root,'2026-10-20')['payload']
    assert second['previous_record_sha256']==first['record_sha256']
    assert second['unrecorded_days_since_previous']==2
    assert not (root/'2026-10-18').exists() and not (root/'2026-10-19').exists()
    assert journal.verify(root)['records']==2


def test_late_first_observation_reports_missing_start_days(tmp_path,monkeypatch):
    clock(monkeypatch,'2026-10-21T01:00:00+00:00');root=tmp_path/'journal'
    journal.observe(dataset(tmp_path,last='2026-10-20'),root)
    assert stored(root,'2026-10-20')['payload']['unrecorded_days_since_previous']==3


@pytest.mark.parametrize('damage',['snapshot','payload','payload_rehashed','partial','watchlist','build'])
def test_stored_inconsistency_blocks_new_records(tmp_path,monkeypatch,damage):
    clock(monkeypatch);root=tmp_path/'journal';journal.observe(dataset(tmp_path),root)
    path=root/'2026-10-17/observation.json'
    if damage=='snapshot':
        p=root/'2026-10-17/candles.csv';f=pd.read_csv(p);f.loc[0,'Volume']=123;f.to_csv(p,index=False)
    elif damage in {'payload','payload_rehashed','build'}:
        rec=stored(root)
        if damage=='build':rec['payload']['observer_build_sha256']='a'*64
        else:rec['payload']['candidates'][0]['entry_condition']=not rec['payload']['candidates'][0]['entry_condition']
        if damage!='payload':rec['record_sha256']=journal.digest(journal.canonical(rec['payload']))
        path.write_bytes(journal.canonical(rec))
    elif damage=='partial':path.unlink()
    else:(root/'watchlist.json').write_text('{}')
    clock(monkeypatch,'2026-10-19T00:10:00+00:00')
    with pytest.raises(ValueError):journal.observe(dataset(tmp_path,last='2026-10-18'),root)
    assert not (root/'2026-10-18').exists()


def test_watchlist_change_is_not_silently_accepted(tmp_path,monkeypatch):
    path=tmp_path/'bad.json';path.write_text(journal.WATCHLIST.read_text().replace('POST_HOC_EXPLORATORY','TRAIN_ONLY_SELECTED'))
    monkeypatch.setattr(journal,'WATCHLIST',path)
    with pytest.raises(ValueError,match='watchlist mismatch'):journal.contract()


def test_signal_code_change_is_not_silently_accepted(tmp_path,monkeypatch):
    target=tmp_path/'tradingagents';target.mkdir();(target/'strategy_lab.py').write_text('changed')
    monkeypatch.setattr(journal,'REPO',tmp_path)
    with pytest.raises(ValueError,match='implementation mismatch'):journal.contract()


def test_windows_crlf_sources_preserve_frozen_semantics(tmp_path,monkeypatch):
    original_raw,original_spec,_=journal.contract()
    paths=['docs/TWO_CANDIDATE_WATCHLIST.json','docs/STRATEGY_LAB_PROTOCOL.json',
           'tradingagents/strategy_lab.py','tradingagents/strategy_backtest.py']
    for relative in paths:
        target=tmp_path/relative;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((journal.REPO/relative).read_bytes().replace(b'\n',b'\r\n'))
    monkeypatch.setattr(journal,'REPO',tmp_path)
    monkeypatch.setattr(journal,'WATCHLIST',tmp_path/'docs/TWO_CANDIDATE_WATCHLIST.json')
    raw,spec,_=journal.contract()
    assert raw==original_raw and spec==original_spec


def test_nonempty_uninitialized_directory_is_not_adopted(tmp_path,monkeypatch):
    clock(monkeypatch);root=tmp_path/'journal';root.mkdir();(root/'legacy.json').write_text('{}')
    with pytest.raises(ValueError,match='nonempty'):journal.observe(dataset(tmp_path),root)
    assert (root/'legacy.json').read_text()=='{}' and not (root/'watchlist.json').exists()


def test_existing_lock_refuses_without_automatic_recovery(tmp_path,monkeypatch):
    clock(monkeypatch);root=tmp_path/'journal';(root/'.record.lock').mkdir(parents=True)
    with pytest.raises(ValueError,match='locked'):journal.observe(dataset(tmp_path),root)
    assert (root/'.record.lock').exists() and not (root/'watchlist.json').exists()


def test_partial_write_is_preserved_and_not_accepted(tmp_path,monkeypatch):
    clock(monkeypatch);root=tmp_path/'journal';data=dataset(tmp_path)
    real_write=journal._write_new
    def failing(path,raw):
        if path.name=='observation.json':raise OSError('simulated write interruption')
        return real_write(path,raw)
    monkeypatch.setattr(journal,'_write_new',failing)
    with pytest.raises(OSError):journal.observe(data,root)
    assert (root/'2026-10-17/candles.csv').is_file()
    monkeypatch.setattr(journal,'_write_new',real_write)
    with pytest.raises(ValueError,match='Incomplete'):journal.observe(data,root)


def test_naive_clock_is_rejected(tmp_path,monkeypatch):
    monkeypatch.setattr(journal,'utc_now',lambda:datetime(2026,10,18))
    with pytest.raises(ValueError,match='aware'):journal.observe(tmp_path/'unused',tmp_path/'journal')


def test_midnight_rollover_requires_new_observation(tmp_path,monkeypatch):
    values=iter([datetime(2026,10,18,23,59,59,tzinfo=timezone.utc),datetime(2026,10,19,tzinfo=timezone.utc)])
    monkeypatch.setattr(journal,'utc_now',lambda:next(values))
    root=tmp_path/'journal'
    with pytest.raises(ValueError,match='UTC date changed'):journal.observe(dataset(tmp_path),root)
    assert not root.exists()


def test_missing_journal_verify_does_not_initialize(tmp_path):
    root=tmp_path/'missing';assert journal.verify(root)['status']=='NOT_INITIALIZED'
    assert not root.exists()


@pytest.mark.parametrize('raw',[b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":Infinity}'])
def test_noncanonical_json_rejected(raw):
    with pytest.raises(ValueError):journal.strict_json(raw)
