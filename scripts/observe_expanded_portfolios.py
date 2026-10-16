"""On-demand observation and virtual accounting; public data, no real orders."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))
import observe_expanded_candidates as observe_candidates
from tradingagents import expanded_paper as ledger


def run(state_dir):
    state = Path(state_dir)
    source, target = state / "journal", state / "paper_ledger"
    # Refuse damaged ledgers or stale unconsumed signals before any download.
    ledger.prepare(source, target)
    observation = observe_candidates.run(state)
    if observation["status"] not in {"RECORDED", "ALREADY_RECORDED"}:
        return {"status": observation["status"], "observation": observation,
                "paper_record_created": False, "quote_requests": 0, "orders": 0}
    ready = ledger.prepare(source, target)
    if ready["status"] != "READY":
        return {**ready, "record_created": False, "quote_requests": 0, "orders": 0}
    quote = ledger.fetch_quote()
    return {**ledger.record(source, target, quote), "quote_requests": 1,
            "automatic_retry": False, "observation": observation}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    try:
        state = Path(args.state_dir)
        result = ledger.verify(state / "journal", state / "paper_ledger") if args.verify_only else run(state)
    except (ValueError, OSError, ArithmeticError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"status": "ERROR_REQUIRES_INSPECTION", "error": str(error),
                          "paper_record_created": "UNVERIFIED", "automatic_retry": False, "orders": 0}))
        return 1
    print(json.dumps(result, indent=2, allow_nan=False))
    return 1 if result["status"] == "DOWNLOAD_FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
