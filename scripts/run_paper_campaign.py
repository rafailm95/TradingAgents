"""One scheduled paper iteration with durable checkpoint verification."""
import argparse
import json
import os
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))
# This research runner has no account use. Disable the package's general
# dotenv discovery before importing it, including parent-directory .env files.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
import observe_paper_portfolios
from tradingagents import paper_campaign


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-dir", required=True)
    parser.add_argument("--runtime-sha", required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    try:
        result = paper_campaign.run(args.campaign_dir, args.runtime_sha,
                                    observe_paper_portfolios.run, verify_only=args.verify_only)
    except Exception as exc:
        print(json.dumps({"status": "CAMPAIGN_BLOCKED", "error": f"{type(exc).__name__}: {exc}",
                          "persistence": "UNVERIFIED", "orders": 0}))
        return 1
    print(json.dumps(result, indent=2, allow_nan=False))
    return 1 if result.get("error") or result.get("integrity_status") == "INSPECTION_REQUIRED" or result["status"] in {
        "DOWNLOAD_FAILED", "RUN_FAILED_REQUIRES_INSPECTION"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
