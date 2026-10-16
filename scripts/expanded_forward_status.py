"""Read-only exploratory forward milestone; never an order/adoption decision."""
import argparse
from datetime import date
import json
from pathlib import Path
import sys
REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO))
from tradingagents import expanded_journal as journal
from tradingagents import expanded_paper as paper


def assess(verified,events,first_eligible):
    if not events:
        return {"status":"WAITING_FOR_PROSPECTIVE_EVENTS","events":0,"milestone_candidates":[],"orders":0}
    first,last=events[0]["payload"],events[-1]["payload"]
    elapsed=(paper._time(last["valuation_at_utc"])-paper._time(first["valuation_at_utc"])).total_seconds()/86400
    eligible=(date.fromisoformat(last["as_of_utc_day"])-date.fromisoformat(first_eligible)).days+1
    coverage=len(events)/eligible
    candidates={}
    for cid in last["books"]["base"]:
        if cid in ("cash","buy_hold_50"):continue
        checks={"at_least180elapsed_days":elapsed>=180,"at_least95pct_eligible_days":coverage>=.95,
            "no_pending_observations":verified["pending_observations"]==0}
        trades={}
        for cost in ("base","stress"):
            book=last["books"][cost][cid]
            sells=sum(e["payload"]["books"][cost][cid]["action"]=="SELL" for e in events)
            trades[cost]=sells
            checks[cost+"_20closed_trades"]=sells>=20
            checks[cost+"_positive_net_liquidation_pnl"]=book["net_pnl_usd"]>0
            checks[cost+"_drawdown_at_most35pct"]=book["sampled_max_drawdown_fraction"]<=.35
        candidates[cid]={"milestone_met":all(checks.values()),"checks":checks,"closed_trades":trades}
    return {"status":"FORWARD_MILESTONE_ASSESSED","events":len(events),"elapsed_days":elapsed,
        "eligible_calendar_days":eligible,"coverage_fraction":coverage,"candidates":candidates,
        "milestone_candidates":[cid for cid,c in candidates.items() if c["milestone_met"]],
        "meaning":"Monitoring milestone only. No statistical proof, execution authority or future-profit guarantee.","orders":0}


def run(campaign_dir):
    state=Path(campaign_dir)/"state"
    verified=paper.verify(state/"journal",state/"paper_ledger")
    events=[journal.strict_json(journal._bounded_read(p)) for p in sorted((state/"paper_ledger").glob("????-??-??.json"))]
    return assess(verified,events,journal.contract()[1]["first_observation_day"])


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--campaign-dir",required=True)
    args=parser.parse_args();print(json.dumps(run(args.campaign_dir),indent=2,allow_nan=False))
