"""Adversarial concurrency and seeded cash-flow conservation checks."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import random
import threading

import pytest

from tradingagents import candidate_journal as journal
from tradingagents import paper_portfolio as paper
from tests.test_paper_portfolio import IDS, clock, observation, quote


def test_concurrent_append_commits_exactly_one_event(monkeypatch,tmp_path):
    observation(monkeypatch,tmp_path)
    evidence=quote();clock(monkeypatch,(journal.utc_now()+timedelta(seconds=3)).isoformat())
    barrier=threading.Barrier(8)
    def attempt(_):
        barrier.wait(timeout=5)
        try:return paper.record(tmp_path/"journal",tmp_path/"ledger",evidence)["status"]
        except ValueError as error:
            assert "locked" in str(error)
            return "LOCKED"
    with ThreadPoolExecutor(max_workers=8) as pool:outcomes=list(pool.map(attempt,range(8)))
    assert outcomes.count("RECORDED")==1
    assert set(outcomes)<={"RECORDED","ALREADY_RECORDED","LOCKED"}
    result=paper.verify(tmp_path/"journal",tmp_path/"ledger")
    assert result["events"]==1
    assert all(result["books"][scenario][name]["hypothetical_fill_count"]==1
               for scenario in ["base","stress"] for name in IDS)


@pytest.mark.parametrize("seed",range(8))
def test_seeded_cashflow_and_quantity_conservation(seed):
    rng=random.Random(seed);spec=paper.contract()[1]
    for scenario,cost in spec["cost_scenarios"].items():
        previous=None;cash=10000.;units=fees=0.;peak=10000.;max_dd=0.;buys=sells=0
        for day in range(120):
            bid=rng.uniform(30,500);ask=bid*(1+rng.uniform(0,.03))
            definition={"id":IDS[0],"selection_class":"SYNTHETIC_TEST_ONLY",
                        "entry_condition":rng.random()<.55,"exit_condition":rng.random()<.35,
                        "hypothetical_entry_fraction":rng.uniform(.05,.5)}
            book=paper._book(previous,definition,cost,bid,ask,day*86400,spec)
            fill=book["fill"]
            if fill:
                cash+=fill["net_cash_change_usd"]
                units+=fill["quantity_btc"]*(1 if fill["side"]=="BUY" else -1)
                fees+=fill["fee_usd"]
                buys+=fill["side"]=="BUY";sells+=fill["side"]=="SELL"
            liquidation=cash+units*bid*(1-cost["slippage_bps_per_side"]/10000)*(1-cost["fee_bps_per_side"]/10000)
            net=liquidation-120*day/365.25
            peak=max(peak,net);max_dd=max(max_dd,1-net/peak)
            assert book["cash_usd"]==pytest.approx(cash,abs=1e-8)
            assert book["quantity_btc"]==pytest.approx(units,abs=1e-10)
            assert book["paid_fees_usd"]==pytest.approx(fees,abs=1e-8)
            assert book["net_pnl_usd"]==pytest.approx(net-10000,abs=1e-8)
            assert book["realized_pnl_usd"]+book["unrealized_liquidation_pnl_usd"]==pytest.approx(liquidation-10000,abs=1e-8)
            assert book["sampled_max_drawdown_fraction"]==pytest.approx(max_dd,abs=1e-12)
            assert cash>=0 and units>=-1e-10 and buys-sells in (0,1)
            previous=book
        assert buys>=5 and sells>=5  # Includes repeated exits/re-entries.


def test_flat_candidate_accrues_expense_without_forced_trade():
    spec=paper.contract()[1]
    definition={"id":IDS[0],"entry_condition":False,"exit_condition":False,"hypothetical_entry_fraction":.5}
    book=paper._book(None,definition,spec["cost_scenarios"]["base"],100,101,365.25*86400,spec)
    assert book["cash_usd"]==10000 and book["quantity_btc"]==0
    assert book["net_pnl_usd"]==-120 and book["hypothetical_fill_count"]==0
