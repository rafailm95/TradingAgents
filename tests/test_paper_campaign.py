"""Durable-state recovery, missing-data, and publication-boundary fixtures."""
from datetime import timedelta
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from tradingagents import candidate_journal as journal
from tradingagents import paper_campaign as campaign
from tradingagents import paper_portfolio as paper
from tests.test_paper_portfolio import clock, observation, quote


def setup_campaign(monkeypatch, tmp_path):
    clock(monkeypatch, "2026-10-16T13:20:00+00:00")
    manifest = tmp_path / "runtime.json"
    spec = {"schema_version": 1, "campaign_id": campaign.CAMPAIGN_ID, "source_files": {
        "tradingagents/paper_campaign.py": journal.digest(journal.source_bytes(Path(campaign.__file__).read_bytes()))}}
    raw = journal.canonical(spec) + b"\n"
    manifest.write_bytes(raw)
    monkeypatch.setattr(campaign, "RUNTIME_MANIFEST", str(manifest))
    sha = journal.digest(raw)
    root = tmp_path / "campaign"; root.mkdir()
    (root / "checkpoint.json").write_bytes(journal.canonical(campaign.initial_checkpoint(sha)) + b"\n")
    return root, sha, manifest


def execute(monkeypatch, day="2026-10-17", fail_quote=False):
    def run(state):
        state.mkdir(exist_ok=True)
        observation(monkeypatch, state, day)
        (state / "input.csv").unlink()  # Synthetic helper input is not campaign state.
        if fail_quote:
            raise TimeoutError("Synthetic quote timeout")
        evidence = quote()
        clock(monkeypatch, (journal.utc_now() + timedelta(seconds=3)).isoformat())
        return paper.record(state / "journal", state / "paper_ledger", evidence)
    return run


def forbidden(state):
    raise AssertionError("No execution should occur before a valid checkpoint")


def test_empty_checkpoint_verifies_without_initializing_market_state(monkeypatch, tmp_path):
    root, sha, _ = setup_campaign(monkeypatch, tmp_path)
    result = campaign.run(root, sha, forbidden, verify_only=True)
    assert result["status"] == "CHECKPOINT_VERIFIED" and result["generation"] == 0
    assert result["verification"]["events"] == 0 and result["publish_files"] == []
    assert not (root/"state").exists()


def test_waiting_does_not_change_checkpoint(monkeypatch, tmp_path):
    root, sha, _ = setup_campaign(monkeypatch, tmp_path)
    before = (root/"checkpoint.json").read_bytes()
    result = campaign.run(root, sha, lambda state:{"status":"WAITING_FOR_NEW_CANDLES"})
    assert result["publish_files"] == [] and result["remote_commit_required"] is False
    assert (root/"checkpoint.json").read_bytes() == before


def test_first_event_proposal_and_fresh_checkout_restore(monkeypatch, tmp_path):
    root, sha, _ = setup_campaign(monkeypatch, tmp_path)
    initial = (root/"checkpoint.json").read_bytes()
    result = campaign.run(root, sha, execute(monkeypatch))
    assert result["status"] == "LOCAL_PROPOSAL_READY" and result["remote_commit_required"]
    assert result["generation"] == 1 and len(result["publish_files"]) == 6
    assert result["base_checkpoint_sha256"] == journal.digest(initial)
    assert result["verification"]["events"] == 1
    fresh = tmp_path/"fresh_checkout";shutil.copytree(root, fresh)
    verified = campaign.run(fresh, sha, forbidden, verify_only=True)
    assert verified["checkpoint_sha256"] == result["checkpoint_sha256"]
    assert verified["verification"] == result["verification"]
    second = campaign.run(fresh, sha, execute(monkeypatch, "2026-10-18"))
    assert second["generation"] == 2 and second["verification"]["events"] == 2
    assert len(second["publish_files"]) == 4
    assert second["base_checkpoint_sha256"] == result["checkpoint_sha256"]


def test_quote_failure_preserves_signal_for_same_day_retry(monkeypatch, tmp_path):
    root, sha, _ = setup_campaign(monkeypatch, tmp_path)
    failed = campaign.run(root, sha, execute(monkeypatch, fail_quote=True))
    assert failed["status"] == "LOCAL_PROPOSAL_READY" and failed["error"]
    assert failed["verification"]["observations"] == failed["verification"]["pending_observations"] == 1
    assert failed["verification"]["events"] == 0
    def retry(state):
        evidence = quote();clock(monkeypatch,(journal.utc_now()+timedelta(seconds=3)).isoformat())
        return paper.record(state/"journal", state/"paper_ledger", evidence)
    good = campaign.run(root, sha, retry)
    assert good["generation"] == 2 and good["verification"]["events"] == 1
    assert good["error"] is None


def test_partial_ledger_is_quarantined_and_future_run_refuses(monkeypatch,tmp_path):
    root,sha,_=setup_campaign(monkeypatch,tmp_path)
    original=journal._write_new
    def partial(path,raw):
        if path.name=="2026-10-17.json":
            path.write_bytes(raw[:20]);raise OSError("Synthetic interrupted ledger write")
        return original(path,raw)
    monkeypatch.setattr(journal,"_write_new",partial)
    result=campaign.run(root,sha,execute(monkeypatch))
    assert result["status"]=="LOCAL_QUARANTINE_READY" and result["integrity_status"]=="INSPECTION_REQUIRED"
    assert "state/paper_ledger/2026-10-17.json" in result["publish_files"]
    with pytest.raises(ValueError,match="requires inspection"):campaign.run(root,sha,forbidden)


@pytest.mark.parametrize("kind",["missing_checkpoint","missing_event","modified_event","unlisted_file","leftover_proposal","locked","linked_downloads"])
def test_invalid_restoration_refuses_before_execution(monkeypatch,tmp_path,kind):
    root,sha,_=setup_campaign(monkeypatch,tmp_path)
    campaign.run(root,sha,execute(monkeypatch))
    if kind=="missing_checkpoint":(root/"checkpoint.json").unlink()
    if kind=="missing_event":(root/"state/paper_ledger/2026-10-17.json").unlink()
    if kind=="modified_event":(root/"state/paper_ledger/2026-10-17.json").write_text("{}")
    if kind=="unlisted_file":(root/"state/paper_ledger/2026-10-18.json").write_text("{}")
    if kind=="leftover_proposal":(root/"checkpoint.proposed.json").write_text("{}")
    if kind=="locked":(root/".record.lock").mkdir()
    if kind=="linked_downloads":(root/"state/downloads").symlink_to(tmp_path,target_is_directory=True)
    with pytest.raises((ValueError,OSError)):campaign.run(root,sha,forbidden)


@pytest.mark.parametrize("field,value",[("generation",True),("generation",-1),("orders",1),("orders",False),
    ("schema_version",True),("campaign_id","wrong"),("previous_checkpoint_sha256","bad"),
    ("recorded_at_utc","2026-10-19T00:00:00+00:00"),("recorded_at_utc","2026-10-16T00:00:00")])
def test_invalid_checkpoint_metadata(monkeypatch,tmp_path,field,value):
    root,sha,_=setup_campaign(monkeypatch,tmp_path)
    path=root/"checkpoint.json";check=json.loads(path.read_text());check[field]=value
    path.write_bytes(journal.canonical(check))
    with pytest.raises(ValueError):campaign.run(root,sha,forbidden)


def test_checkpoint_numerical_summary_cannot_be_forged(monkeypatch,tmp_path):
    root,sha,_=setup_campaign(monkeypatch,tmp_path)
    path=root/"checkpoint.json";check=json.loads(path.read_text());check["verification"]["events"]=99
    path.write_bytes(journal.canonical(check))
    with pytest.raises(ValueError,match="numerical replay"):campaign.run(root,sha,forbidden)


@pytest.mark.parametrize("change",["manifest","source","traversal","symlink"])
def test_runtime_identity_refusal(monkeypatch,tmp_path,change):
    root,sha,manifest=setup_campaign(monkeypatch,tmp_path)
    if change=="manifest":manifest.write_bytes(manifest.read_bytes()+b" ")
    elif change=="source":
        spec=json.loads(manifest.read_text());spec["source_files"]["tradingagents/paper_campaign.py"]="0"*64
        manifest.write_bytes(journal.canonical(spec));sha=journal.digest(manifest.read_bytes())
    elif change=="traversal":
        spec=json.loads(manifest.read_text());spec["source_files"]={"../outside":"0"*64}
        manifest.write_bytes(journal.canonical(spec));sha=journal.digest(manifest.read_bytes())
    else:
        other=tmp_path/"other.json";other.write_bytes(manifest.read_bytes());manifest.unlink();manifest.symlink_to(other)
    with pytest.raises(ValueError):campaign.verify_runtime(journal.REPO,sha)


def test_accepted_bytes_cannot_change_during_execution(monkeypatch,tmp_path):
    root,sha,_=setup_campaign(monkeypatch,tmp_path);campaign.run(root,sha,execute(monkeypatch))
    previous=(root/"checkpoint.json").read_bytes()
    def corrupt(state):
        (state/"paper_ledger/2026-10-17.json").unlink()
        return {"status":"BAD"}
    with pytest.raises(ValueError,match="Accepted state"):campaign.run(root,sha,corrupt)
    assert (root/"checkpoint.json").read_bytes()==previous


def test_checkpoint_replace_failure_keeps_recovery_evidence(monkeypatch,tmp_path):
    root,sha,_=setup_campaign(monkeypatch,tmp_path)
    before=(root/"checkpoint.json").read_bytes()
    def fail(*args):raise OSError("Synthetic rename failure")
    monkeypatch.setattr(campaign.os,"replace",fail)
    with pytest.raises(OSError,match="rename"):campaign.run(root,sha,execute(monkeypatch))
    assert (root/"checkpoint.json").read_bytes()==before
    assert (root/"checkpoint.proposed.json").is_file()
    with pytest.raises(ValueError,match="interrupted proposal"):campaign.run(root,sha,forbidden)


def test_duplicate_campaign_does_not_propose_second_remote_commit(monkeypatch,tmp_path):
    root,sha,_=setup_campaign(monkeypatch,tmp_path);campaign.run(root,sha,execute(monkeypatch))
    before=(root/"checkpoint.json").read_bytes()
    def duplicate(state):return paper.record(state/"journal",state/"paper_ledger",{})
    result=campaign.run(root,sha,duplicate)
    assert result["status"]=="ALREADY_RECORDED" and result["publish_files"]==[]
    assert (root/"checkpoint.json").read_bytes()==before


def test_stale_pending_signal_survives_restore_and_cannot_backfill(monkeypatch,tmp_path):
    root,sha,_=setup_campaign(monkeypatch,tmp_path)
    campaign.run(root,sha,execute(monkeypatch,fail_quote=True))
    clock(monkeypatch,"2026-10-19T00:10:00+00:00")
    def attempt(state):return paper.prepare(state/"journal",state/"paper_ledger")
    result=campaign.run(root,sha,attempt)
    assert result["status"]=="RUN_FAILED_REQUIRES_INSPECTION" and "stale" in result["error"]
    assert result["publish_files"]==[]


def test_campaign_inventory_size_bound(monkeypatch,tmp_path):
    root,sha,_=setup_campaign(monkeypatch,tmp_path);campaign.run(root,sha,execute(monkeypatch))
    monkeypatch.setattr(campaign,"MAX_STATE_FILES",1)
    with pytest.raises(ValueError,match="bounded storage"):campaign.run(root,sha,forbidden)


def test_no_auto_bootstrap_for_nonexistent_campaign(monkeypatch,tmp_path):
    root,sha,_=setup_campaign(monkeypatch,tmp_path)
    absent=tmp_path/"absent"
    with pytest.raises(ValueError,match="no automatic bootstrap"):campaign.run(absent,sha,forbidden)
    assert not absent.exists()


def test_wrong_dependency_version_blocks_before_execution(monkeypatch,tmp_path):
    root,sha,_=setup_campaign(monkeypatch,tmp_path)
    monkeypatch.setattr(campaign.metadata,"version",lambda name:"0.0.0")
    with pytest.raises(ValueError,match="pinned version"):campaign.run(root,sha,forbidden)


def test_scheduled_entrypoint_does_not_load_parent_dotenv(tmp_path):
    (tmp_path/".env").write_text("PAPER_TEST_MUST_NOT_LOAD=yes\n")
    child=tmp_path/"child";child.mkdir()
    script=journal.REPO/"scripts/run_paper_campaign.py"
    code="import os,runpy,sys;runpy.run_path(sys.argv[1],run_name='test_import');print(os.getenv('PAPER_TEST_MUST_NOT_LOAD'));print(os.getenv('PYTHON_DOTENV_DISABLED'))"
    result=subprocess.run([sys.executable,"-c",code,str(script)],cwd=child,capture_output=True,text=True,check=True)
    assert result.stdout.splitlines()==["None","1"]
