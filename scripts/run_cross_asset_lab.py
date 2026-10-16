"""Frozen40-candidate transfer experiment on ETH-USD and LTC-USD; no orders."""
import argparse
from datetime import datetime,timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from tradingagents import strategy_lab as old
from tradingagents import strategy_families as new
from tradingagents.strategy_backtest import load_daily

PROTOCOL_SHA256="a53b6f3aa8305752680d88d55b8fd0475cf476c18e8f7ba002d88fee476501f9"
CANDIDATES=(*old.CANDIDATES,*new.CANDIDATES)


def write(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False))


def select(training):
    if set(training)!={c.id for c in CANDIDATES}:raise ValueError("All40 training candidates required")
    ranked=[]
    for c in CANDIDATES:
        pair=[training[c.id][k] for k in ("base","stress")]
        if all(m["profit_after_operating_usd"]>0 and m["max_close_drawdown_pct"]<=35 and m["closed_trades"]>=10 for m in pair):
            m=pair[1];ranked.append({"id":c.id,"score":m["annualized_after_operating_pct"]/max(m["max_close_drawdown_pct"],1.)})
    ranked.sort(key=lambda x:(-x["score"],x["id"]))
    return {"selected":ranked[0]["id"] if ranked else "cash","eligible":ranked}


def simulate(frame,start,end,item,features,cost,*,lag=0,initial=10000,operating=None):
    if lag not in (0,1,2):raise ValueError("Unregistered lag")
    candidate=not isinstance(item,str)
    name=item.id if candidate else item
    sig=features[item.family if candidate else "breakout20"].copy()
    if lag:
        for key in ("entry","exit"):sig[key]=sig[key].shift(lag,fill_value=False)
        sig["vol60"]=sig.vol60.shift(lag)
    carrier=old.Candidate("breakout20",item.sizing) if candidate else None
    expense=120 if candidate or name=="original_trend100" else 0
    result=old.simulate(frame,start,end,carrier,benchmark=None if candidate else name,prepared=sig,
        fee_bps=cost["fee"],slippage_bps=cost["slippage"],initial=initial,operating_per_year=expense if operating is None else operating)
    check=old.audit_wealth(frame,result,initial,cost["fee"],cost["slippage"])
    for point in result["curve"]:point["asset_quantity"]=point.pop("btc")
    for fill in result["fills"]:
        if fill["signal_date"] and fill["reason"] in ("entry","signal"):
            fill["signal_date"]=(pd.Timestamp(fill["signal_date"])-pd.Timedelta(days=lag)).strftime("%Y-%m-%d")
        elif fill["reason"]=="time_exit":fill["signal_date"]=None
    result.update(candidate_or_benchmark=name,extra_signal_lag=lag)
    return result,check


def returns(result):
    a=np.array([result["metrics"]["initial_usd"]]+[p["equity"] for p in result["curve"]])
    return a[1:]/a[:-1]-1


def run(data_root,output):
    raw=(REPO/"docs/CROSS_ASSET_PROTOCOL.json").read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PROTOCOL_SHA256:raise ValueError("Protocol changed")
    p=json.loads(raw)
    # Verify frozen strategies against the independently pinned paper and family contracts.
    from tradingagents.candidate_journal import contract as old_contract
    from tradingagents.expanded_journal import contract as expanded_contract
    old_contract();expanded_contract()
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    (output/"protocol.json").write_bytes(raw)
    hashes={name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in [
        "scripts/run_cross_asset_lab.py","scripts/fetch_research_candles.py","tradingagents/strategy_lab.py","tradingagents/strategy_families.py","tradingagents/strategy_backtest.py"]}
    inputs={}
    for product in p["products"]:
        csv=Path(data_root)/product/"candles.csv"
        manifest=json.loads((csv.parent/"manifest.json").read_text())
        if manifest["product"]!=product or manifest["synthetic"] is not False or hashlib.sha256(csv.read_bytes()).hexdigest()!=manifest["csv_sha256"]:
            raise ValueError("Input provenance mismatch")
        inputs[product]=manifest
    write(output/"run_manifest.json",{"started_utc":datetime.now(timezone.utc).isoformat(),"protocol_sha256":PROTOCOL_SHA256,"source_hashes":hashes,"inputs":inputs,"orders":0})
    summaries={}
    for product in p["products"]:
        frame=load_daily(Path(data_root)/product/"candles.csv")
        if len(frame)!=2845 or str(frame.Date.iloc[0].date())!=p["data_start"] or str(frame.Date.iloc[-1].date())!=p["data_end"]:
            raise ValueError("Coverage mismatch")
        out=output/product;out.mkdir()
        z=new.indicators(frame)
        features={**{f:old.signals(frame,f) for f in old.FAMILIES},**{f:new.signals(frame,f,prepared_indicators=z) for f in new.FAMILIES}}
        results,metrics,audits,training={},{},[],{}
        for window in p["windows"]:
            for cost in p["costs"]:
                for item in (*CANDIDATES,*p["benchmarks"]):
                    name=item.id if not isinstance(item,str) else item
                    outcome,check=simulate(frame,window["start"],window["end"],item,features,cost)
                    key=f"{window['name']}__{cost['name']}__{name}"
                    outcome["product"]=product;results[key]=outcome
                    metrics[key]={"product":product,"window":window["name"],"cost":cost["name"],"id":name,**outcome["metrics"]}
                    audits.append({"id":key,**check})
                    if window["name"]=="train" and not isinstance(item,str):training.setdefault(name,{})[cost["name"]]=outcome["metrics"]
                print(f"Completed {product} {window['name']} {cost['name']}",flush=True)
            if window["name"]=="train":
                selected=select(training);write(out/"selection_before_evaluation.json",selected)
                print(f"Train-only selection {product}: {selected['selected']}",flush=True)
        delays={};delay_metrics=[]
        for lag in (1,2):
            for cost in p["costs"]:
                for c in CANDIDATES:
                    outcome,check=simulate(frame,"2024-01-01",p["data_end"],c,features,cost,lag=lag)
                    key=f"lag{lag}__{cost['name']}__{c.id}"
                    outcome["product"]=product;delays[key]=outcome;audits.append({"id":key,**check})
                    delay_metrics.append({"id":c.id,"product":product,"lag":lag,"cost":cost["name"],**outcome["metrics"]})
                print(f"Completed {product} lag{lag} {cost['name']}",flush=True)
        assessments=[]
        for c in CANDIDATES:
            checks={};delayed={}
            for cost in ("base","stress"):
                for window in ("full","validation","recent"):
                    m=metrics[f"{window}__{cost}__{c.id}"]
                    checks[f"{window}_{cost}_positive"]=m["profit_after_operating_usd"]>0
                    if window=="full":
                        checks[f"full_{cost}_drawdown"]=m["max_close_drawdown_pct"]<=35
                        checks[f"full_{cost}_20trades"]=m["closed_trades"]>=20
                    elif window=="validation":checks[f"validation_{cost}_5trades"]=m["closed_trades"]>=5
                for lag in (1,2):
                    m=delays[f"lag{lag}__{cost}__{c.id}"]["metrics"]
                    delayed[f"lag{lag}_{cost}_positive"]=m["profit_after_operating_usd"]>0
                    delayed[f"lag{lag}_{cost}_drawdown"]=m["max_close_drawdown_pct"]<=35
            assessments.append({"id":c.id,"historical_pass":all(checks.values()),"robust_pass":all(checks.values()) and all(delayed.values()),
                "checks":checks,"delay_checks":delayed,"failed":[k for k,v in checks.items() if not v],"delay_failed":[k for k,v in delayed.items() if not v]})
        panel=np.column_stack([returns(results[f"evaluation__base__{c.id}"]) for c in CANDIDATES])
        multiplicity=[{"benchmark":b,**old.bootstrap_max_mean(panel,returns(results[f"evaluation__base__{b}"]),block=block)} for b in ("cash","buy_hold50") for block in (30,60)]
        wf_training,wf={},[];balances={"base":10000.,"stress":10000.};curves={"base":[],"stress":[]}
        for year in range(2022,2027):
            tm={}
            for c in CANDIDATES:
                tm[c.id]={}
                for cost in p["costs"]:
                    result,check=simulate(frame,"2020-01-01",f"{year-1}-12-31",c,features,cost)
                    key=f"train{year}__{cost['name']}__{c.id}";wf_training[key]=result
                    tm[c.id][cost["name"]]=result["metrics"];audits.append({"id":key,**check})
            choice=select(tm);item=next((c for c in CANDIDATES if c.id==choice["selected"]),"cash")
            end=f"{year}-12-31" if year<2026 else p["data_end"]
            fold={"year":year,"selection":choice,"training_metrics":tm,"results":{}}
            for cost in p["costs"]:
                cn=cost["name"]
                result,check=simulate(frame,f"{year}-01-01",end,item,features,cost,initial=balances[cn],operating=120)
                audits.append({"id":f"wf{year}_{cn}",**check})
                balances[cn]=result["metrics"]["final_usd"]-result["metrics"]["operating_cost_usd"]
                if balances[cn]<=0:raise ArithmeticError("Insolvent research book")
                net=[dict(x) for x in result["curve"]];net[-1]["equity"]=balances[cn];net[-1]["cash"]=balances[cn]
                curves[cn].extend(net);fold["results"][cn]=result
                result["operating_debit"]={"date":end,"amount_usd":result["metrics"]["operating_cost_usd"],"cash_after":balances[cn]}
            wf.append(fold);print(f"Completed {product} WFA{year}: {choice['selected']}",flush=True)
        wf_summary={}
        for cn,curve in curves.items():
            values=np.array([10000.]+[r["equity"] for r in curve])
            wf_summary[cn]={"net_return_after_operating_pct":100*(balances[cn]/10000-1),"final_after_operating_usd":balances[cn],
                "max_close_drawdown_after_operating_pct":100*float((1-values/np.maximum.accumulate(values)).max())}
        summary={"product":product,"selection":selected,"metrics":list(metrics.values()),"delay_metrics":delay_metrics,"assessments":assessments,
            "multiplicity":multiplicity,"walk_forward_summary":wf_summary,"walk_forward_choices":[{"year":x["year"],"selected":x["selection"]["selected"],
                **{cn+"_return":x["results"][cn]["metrics"]["return_after_operating_pct"] for cn in ("base","stress")}} for x in wf],
            "matrix_runs":len(results),"delay_runs":len(delays),"wf_training_runs":len(wf_training),"wf_fold_runs":10,
            "audit_cases":len(audits),"audit_days":sum(x["days"] for x in audits),"max_audit_error_usd":max(x["max_usd_error"] for x in audits)}
        write(out/"summary.json",summary);write(out/"audits.json",audits)
        pd.DataFrame(metrics.values()).to_csv(out/"metrics.csv",index=False)
        for name,value in (("matrix",results),("delays",delays),("wf_training",wf_training),("walk_forward",wf)):
            with gzip.open(out/f"{name}.json.gz","wt",encoding="utf-8") as stream:json.dump(value,stream,allow_nan=False)
        summaries[product]=summary
    final={"experiment":p["experiment"],"completed_utc":datetime.now(timezone.utc).isoformat(),"assets":summaries,
        "cross_asset_robust_pass":[c.id for c in CANDIDATES if all(next(x for x in summary["assessments"] if x["id"]==c.id)["robust_pass"] for summary in summaries.values())],
        "orders":0,"paid_model_calls":0,"unseen_future_evidence":False}
    write(output/"summary.json",final)
    print(json.dumps({"cross_asset_robust_pass":final["cross_asset_robust_pass"],"audit_cases":sum(x["audit_cases"] for x in summaries.values())}),flush=True)
    return final


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--data-root",required=True);parser.add_argument("--output",required=True)
    args=parser.parse_args();run(args.data_root,args.output)
