"""Durable checkpoint boundary for scheduled, research-only paper runs.

The remote Git branch is authoritative. This module prepares a local proposal;
the scheduler must publish it with an expected-parent, non-forced ref update.
It never uses Git credentials, places orders, or repairs rejected state.
"""
from __future__ import annotations

from datetime import datetime
from importlib import metadata
import os
from pathlib import Path
import re
import sys

from tradingagents import candidate_journal as journal
from tradingagents import paper_portfolio as paper

CAMPAIGN_ID = "btc_paper_scheduled_006_v1"
RUNTIME_MANIFEST = "docs/PAPER_AUTOMATION_RUNTIME.json"
MAX_STATE_FILES = 10000
MAX_STATE_BYTES = 100_000_000
CHECKPOINT_KEYS = {"schema_version", "campaign_id", "generation", "previous_checkpoint_sha256",
                   "runtime_manifest_sha256", "recorded_at_utc", "integrity_status", "state_files",
                   "verification", "last_attempt_status", "orders"}


def verify_runtime(repo, expected_sha):
    if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise ValueError("Explicit runtime manifest SHA-256 required")
    raw = journal.source_bytes(journal._bounded_read(Path(repo) / RUNTIME_MANIFEST))
    if journal.digest(raw) != expected_sha:
        raise ValueError("Pinned runtime manifest mismatch")
    spec = journal.strict_json(raw)
    if set(spec) != {"schema_version", "campaign_id", "source_files"} or spec["schema_version"] != 1 or spec["campaign_id"] != CAMPAIGN_ID:
        raise ValueError("Invalid runtime manifest")
    if not isinstance(spec["source_files"], dict) or not spec["source_files"]:
        raise ValueError("Missing runtime files")
    for name, expected in spec["source_files"].items():
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", name) or name.startswith("/") or ".." in name.split("/"):
            raise ValueError("Invalid runtime path")
        actual = journal.digest(journal.source_bytes(journal._bounded_read(Path(repo) / name)))
        if actual != expected:
            raise ValueError(f"Pinned runtime source mismatch: {name}")
    if sys.version_info[:2] != (3, 12):
        raise ValueError("The frozen scheduled runtime requires Python 3.12")
    for line in (Path(repo) / "requirements-research.txt").read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_-]+)==([A-Za-z0-9_.+-]+)", line)
        if not match or metadata.version(match[1]) != match[2]:
            raise ValueError("Installed research dependency does not match its pinned version")
    return spec


def _inventory(state):
    """Only two bounded core directories persist; downloader scratch is separate."""
    files, total = {}, 0
    if state.is_symlink() or state.exists() and not state.is_dir():
        raise ValueError("Invalid state directory")
    if state.exists() and any(p.name not in {"journal", "paper_ledger", "downloads"} for p in state.iterdir()):
        raise ValueError("Unexpected state entry")
    downloads = state / "downloads"
    if downloads.is_symlink() or downloads.exists() and not downloads.is_dir():
        raise ValueError("Invalid downloader scratch directory")
    for name in ("journal", "paper_ledger"):
        root = state / name
        if root.is_symlink() or root.exists() and not root.is_dir():
            raise ValueError("Invalid core state directory")
        if not root.exists():
            continue
        for directory, dirs, filenames in os.walk(root, followlinks=False):
            for entry in dirs:
                path = Path(directory) / entry
                if path.is_symlink() or entry == ".record.lock":
                    raise ValueError("Core state is linked or locked; inspect it")
            for filename in filenames:
                path = Path(directory) / filename
                relative = path.relative_to(state).as_posix()
                valid = (re.fullmatch(r"journal/(watchlist\.json|\d{4}-\d{2}-\d{2}/(candles\.csv|observation\.json))", relative)
                         or re.fullmatch(r"paper_ledger/(protocol\.json|\d{4}-\d{2}-\d{2}\.json)", relative))
                if not valid:
                    raise ValueError("Unexpected core state file")
                raw = journal._bounded_read(path)
                total += len(raw)
                files[relative] = journal.digest(raw)
                if len(files) > MAX_STATE_FILES or total > MAX_STATE_BYTES:
                    raise ValueError("Campaign state exceeds bounded storage")
    return dict(sorted(files.items()))


def _verification(state):
    result = paper.verify(state / "journal", state / "paper_ledger")
    ledger_days = sorted((state / "paper_ledger").glob("????-??-??.json"))
    tip = journal.ZERO_HASH
    if ledger_days:
        tip = journal.strict_json(journal._bounded_read(ledger_days[-1]))["event_sha256"]
    return {"observations": result["observations"], "events": result["events"],
            "pending_observations": result["pending_observations"],
            "latest_observation_day": result["latest_observation_day"],
            "last_valuation_at_utc": result["last_valuation_at_utc"], "ledger_tip_sha256": tip}


def initial_checkpoint(runtime_sha):
    """Bootstrap-only constructor. Production run refuses a missing checkpoint."""
    return {"schema_version": 1, "campaign_id": CAMPAIGN_ID, "generation": 0,
            "previous_checkpoint_sha256": journal.ZERO_HASH, "runtime_manifest_sha256": runtime_sha,
            "recorded_at_utc": journal._utc(journal.utc_now()).isoformat(), "integrity_status": "VERIFIED",
            "state_files": {}, "verification": {"observations": 0, "events": 0,
            "pending_observations": 0, "latest_observation_day": None, "last_valuation_at_utc": None,
            "ledger_tip_sha256": journal.ZERO_HASH}, "last_attempt_status": "INITIALIZED", "orders": 0}


def _load(campaign, runtime_sha):
    if any(p.name not in {"checkpoint.json", "state", ".gitattributes", ".record.lock"} for p in campaign.iterdir()):
        raise ValueError("Unexpected campaign entry or interrupted proposal; inspect before running")
    raw = journal._bounded_read(campaign / "checkpoint.json")
    check = journal.strict_json(raw)
    if not isinstance(check, dict) or set(check) != CHECKPOINT_KEYS:
        raise ValueError("Invalid checkpoint envelope")
    if (type(check["schema_version"]) is not int or check["schema_version"] != 1
            or check["campaign_id"] != CAMPAIGN_ID or type(check["orders"]) is not int or check["orders"] != 0
            or check["runtime_manifest_sha256"] != runtime_sha):
        raise ValueError("Checkpoint contract mismatch")
    if type(check["generation"]) is not int or check["generation"] < 0:
        raise ValueError("Invalid checkpoint generation")
    if not re.fullmatch(r"[0-9a-f]{64}", check["previous_checkpoint_sha256"]):
        raise ValueError("Invalid previous checkpoint identity")
    if check["generation"] == 0 and check["previous_checkpoint_sha256"] != journal.ZERO_HASH:
        raise ValueError("Invalid initial checkpoint predecessor")
    recorded = journal._utc(datetime.fromisoformat(check["recorded_at_utc"]))
    if recorded > journal._utc(journal.utc_now()):
        raise ValueError("Future checkpoint timestamp")
    if check["state_files"] != _inventory(campaign / "state"):
        raise ValueError("Checkpoint state missing, modified or unlisted; never reset")
    if check["integrity_status"] != "VERIFIED":
        raise ValueError("Checkpoint requires inspection; no automated continuation")
    if check["verification"] != _verification(campaign / "state"):
        raise ValueError("Checkpoint numerical replay mismatch")
    return raw, check


def run(campaign_dir, runtime_sha, execute, *, verify_only=False):
    """Run once after checkpoint verification, then stage an append-only proposal.

    execute is supplied by the production wrapper. Dependency injection keeps
    recovery tests synthetic without exposing a CLI clock override.
    """
    verify_runtime(journal.REPO, runtime_sha)
    campaign = Path(campaign_dir)
    if campaign.is_symlink() or not campaign.is_dir():
        raise ValueError("Existing dedicated campaign required; no automatic bootstrap")
    with journal._lock(campaign):
        raw, previous = _load(campaign, runtime_sha)
        if verify_only:
            return {"status": "CHECKPOINT_VERIFIED", "checkpoint_sha256": journal.digest(raw),
                    "generation": previous["generation"], "verification": previous["verification"],
                    "publish_files": [], "orders": 0}
        state = campaign / "state"
        error = None
        try:
            outcome = execute(state)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            outcome = {"status": "RUN_FAILED_REQUIRES_INSPECTION", "orders": 0}
        files = _inventory(state)
        # Existing accepted files are immutable, including complete trailing
        # records. The remote checkpoint detects deletion before any download.
        for name, digest in previous["state_files"].items():
            if files.get(name) != digest:
                raise ValueError("Accepted state was changed or removed; refuse publication")
        try:
            verification = _verification(state)
            integrity = "VERIFIED"
        except Exception as exc:
            verification = None
            integrity = "INSPECTION_REQUIRED"
            error = f"{error or ''} Replay: {type(exc).__name__}: {exc}".strip()
        if files == previous["state_files"]:
            return {"status": outcome["status"], "outcome": outcome, "error": error,
                    "generation": previous["generation"], "publish_files": [],
                    "remote_commit_required": False, "orders": 0}
        checkpoint = {**previous, "generation": previous["generation"] + 1,
                      "previous_checkpoint_sha256": journal.digest(raw), "state_files": files,
                      "recorded_at_utc": journal._utc(journal.utc_now()).isoformat(),
                      "verification": verification, "integrity_status": integrity,
                      "last_attempt_status": outcome["status"]}
        new_raw = journal.canonical(checkpoint) + b"\n"
        # A leftover proposal is visible and is never overwritten on a retry.
        proposal = campaign / "checkpoint.proposed.json"
        journal._write_new(proposal, new_raw)
        if journal._bounded_read(proposal) != new_raw:
            raise ValueError("Checkpoint proposal readback mismatch")
        os.replace(proposal, campaign / "checkpoint.json")
        if journal._bounded_read(campaign / "checkpoint.json") != new_raw:
            raise ValueError("Checkpoint replacement readback mismatch")
        changed = ["state/" + name for name in files if name not in previous["state_files"]]
        return {"status": "LOCAL_PROPOSAL_READY" if integrity == "VERIFIED" else "LOCAL_QUARANTINE_READY",
                "outcome": outcome, "error": error, "integrity_status": integrity,
                "generation": checkpoint["generation"], "base_checkpoint_sha256": journal.digest(raw),
                "checkpoint_sha256": journal.digest(new_raw), "publish_files": changed + ["checkpoint.json"],
                "remote_commit_required": True, "verification": verification, "orders": 0}
