"""Verify already-computed020 results and render durable evidence; never runs a strategy."""
import argparse
import csv
from decimal import Decimal as D
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from run_nr7_futures_020 import read_result,verify_freeze,file_sha,engine


def write(path,value):path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
def money(x):return f'{float(x):+,.2f}'
def pct(x):return f'{float(x):+.4f}%'
def pair(m):return f"{pct(m['net_return_pct'])} / {money(m['net_profit_usdt'])} USDT"


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path,required=True);p.add_argument('--freeze-sha256',required=True);a=p.parse_args()
    w=a.workspace;out=ROOT/'research/experiments/020';freeze=verify_freeze(a.freeze_sha256)
    stages={k:json.loads((w/('nr7-020-'+k)/('evaluation.json' if k=='evaluation' else 'selection.json')).read_bytes()) for k in ('train1','train2','evaluation')}
    e=stages['evaluation'];verified=[];events=0
    for stage,s in stages.items():
        for rec in s['new_results'].values():
            path=w/('nr7-020-'+stage)/rec['file']
            r=read_result(path,rec['sha256'],rec['container_sha256'])
            if r['metrics']!=rec['metrics']:raise ValueError('Result metrics mismatch')
            audit=engine.audit_wealth(r);events+=audit['events_checked']
            verified.append({'path':str(path.relative_to(w)),'sha256':rec['sha256'],'container_sha256':file_sha(path),'bytes':path.stat().st_size,'encoding':'base64+gzip','audit':audit})
        shutil.copyfile(w/('nr7-020-'+stage)/('evaluation.json' if stage=='evaluation' else 'selection.json'),out/('evaluation.json' if stage=='evaluation' else 'selection-'+stage+'.json'))
    all_summary={};rows=[]
    for candidate,scenarios in e['comparisons_all10'].items():
        base=next(x for x in scenarios if x['cost']=='venue_assumption' and x['lag_days']==0 and not x['adverse_funding_5bps'])
        stress=next(x for x in scenarios if x['cost']=='stress_assumption' and x['lag_days']==0 and not x['adverse_funding_5bps'])
        worst=min(scenarios,key=lambda x:D(x['metrics']['net_return_pct']))
        dd=max(scenarios,key=lambda x:D(x['metrics']['max_drawdown_pct']))
        gate=e['gates_all10'][candidate]
        all_summary[candidate]={'base':base['metrics'],'stress':stress['metrics'],'worst':worst,'maximum_sampled_drawdown_scenario':dd,
            'scenario_passes':12-len(gate['failed_scenarios']),'scenario_failures':len(gate['failed_scenarios']),'full_pass':gate['historical_screen_pass']}
        for r in scenarios:rows.append({'candidate':candidate,'cost':r['cost'],'lag_days':r['lag_days'],'adverse_funding_5bps':r['adverse_funding_5bps'],'new_execution':r.get('new_execution',False),**r['metrics']})
    with (out/'metrics-all10.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    with (out/'walk-forward.csv').open('w',newline='') as f:
        wr=[{'scenario':k,'passed':v['passed'],'failed_gates':'|'.join(v['failed_gates']),**v['metrics']} for k,v in e['walk_forward'].items()]
        writer=csv.DictWriter(f,fieldnames=list(wr[0]));writer.writeheader();writer.writerows(wr)
    new_summary={c:all_summary[c] for c in engine.NEW_CANDIDATES}
    newruns=len(verified);newpasses=sum(x['full_pass'] for x in new_summary.values())
    scenario_pass=sum(x['scenario_passes'] for x in new_summary.values())
    wfa_pass=sum(v['passed'] for v in e['walk_forward'].values())
    summary={'experiment':'020','new_family':'nr7_close10','new_variants':2,'total_variants':50,'total_families':25,
        'new_design_executions':newruns,'cumulative_design_executions':7495+newruns,'prior_integrity_replays':7,'new_integrity_replays':0,
        'cumulative_known_executions':7502+newruns,'new_fixed_scenario_passes':scenario_pass,'new_fixed_scenario_failures':24-scenario_pass,
        'new_full_passes':newpasses,'new_full_failures':2-newpasses,'all10_full_passes':sum(x['full_pass'] for x in all_summary.values()),
        'all10_scenario_passes':sum(x['scenario_passes'] for x in all_summary.values()),
        'new_results':new_summary,'all10_results':all_summary,'main_selection':e['main_train_selected'],
        'expanding_training_selections':e['expanding_training_selections'],'wfa_scenario_passes':wfa_pass,'wfa_scenario_failures':12-wfa_pass,
        'wfa_full_pass':wfa_pass==12,'wfa':e['walk_forward'],'reused_wfa_folds':e['reused_wfa_folds'],
        'new_wealth_events':events,'wealth_max_error_usdt':'0','multiplicity':e['multiplicity'],
        'new_market_observations':0,'prospective_evidence_days':0,'same_history_not_independent':True}
    write(out/'summary.json',summary);write(out/'full_result_hashes.json',verified)
    verification={'source_freeze_verified':a.freeze_sha256,'frozen_source_files':len(freeze['source_hashes']),'preserved_files':len(freeze['preserved_files']),
        'new_result_hashes_verified':len(verified),'independent_wealth_events':events,'max_error_usdt':'0','input_sha256':freeze['input_sha256'],
        'synthetic_tests_passed':129,'new_tests':18,'integrity_failures_this_batch':[],'reused_paths':'32training+96fixed+5benchmarks+conditional WFA; allreadandhashaudited by frozen runner; none counted as new executions.'}
    write(out/'verification.json',verification)
    lines=['# Batch020 — NR7 daily-close futures results','',
        'Native Binance ETHUSDT perpetual, evaluation2024-01-01..2025-12-31; warmup2022, maintraining2023, expandingtraining2023–2024. Historical reused data, not Bybit or forward validation.', '',
        f'New2variants / total50 /25families; {newruns}new design executions; {7495+newruns}cumulative design+7prior integrity replays={7502+newruns}known executions. No new integrity replay. ReusedWFAfolds={e["reused_wfa_folds"]}.', '',
        f'New full gates: {newpasses}/2 pass; individual scenarios {scenario_pass}/24 pass. All10compatible full gates: {summary["all10_full_passes"]}/10. WFA {wfa_pass}/12 scenario passes; fullpass={wfa_pass==12}.', '',
        '|Candidate|Base net % / USDT|Stress net % / USDT|Worst12 net % / USDT|Base signal exits|Maximum sampled DD % / actual USDT|',
        '|---|---:|---:|---:|---:|---:|']
    for c,s in all_summary.items():
        d=s['maximum_sampled_drawdown_scenario']['metrics']
        lines.append(f"|{c}|{pair(s['base'])}|{pair(s['stress'])}|{pair(s['worst']['metrics'])}|{s['base']['signal_exits']}|{float(d['max_drawdown_pct']):.4f}% / {float(d['cash_at_max_pct_drawdown_usdt']):.2f}|")
    lines+=['',f"Main train-only selected: {e['main_train_selected']}. Annual2024/2025 choices: "+' → '.join(s['selected'] for s in e['expanding_training_selections'])+'.',
        'WFA uses exact capital carry, terminal flatten fees at eachyear boundary; identical019folds reused only after exact identity/capital/date/scenario check. Calendar/WFA periods overlap main evaluation.',
        '', 'Benchmarks over the same fixed evaluation window: '+ '; '.join(k+': '+pair(v['metrics']) for k,v in e['reused_benchmarks'].items()),
        '', 'Costs per side: base5.5bpsfee+2bpsslippage; stress10+10bps.120USDT/year expense included. Real4383funding events; nominal hour-open mark proxy plus adverse5bpsvaluation.35,064tradehours and35,064markhours cover2022–2025. No new data.50%entry cap, fullycash-backed long-or-flat guard. Hypotheticalfilters, unknownpersonal/historicalfees, nohistoricalbooks/fills and noexchangeliquidationmodel.',
        'Cash benchmark0expense; perpetualhold50paysfunding/fees/opex. ManagedWFAcash pays120/year. Drawdowncash is observed peak minus trough at the maximum percentage drawdown, not DD% times initial10000. Maximum cash DD is also retained in CSV/JSON. Hourly sampled DD is not an intrabar execution guarantee.',
        '', 'All10compatible candidates enter centered30dayblock maxmean bootstrap,2000resamples,seed20261017,actualopex.40spot-only candidates excluded as incompatible; priorsearch and reuseddesign/history are not corrected. No statistical/forward confirmation.',
        '', f'129softwaretests (18new); {events:,}independentwealth events, zeroDecimaldiscrepancy. Allsourcefreezes and523priorfiles preserved. Allnewresults hashverified and envelopepersisted. Allfailuregates retained in evaluation.json.',
        '', 'Next bounded step: audit the singleBybitpacket if available; otherwise preregister2026nativefutures dataextension for unchanged candidate rules, coverage first and PnL only after input/freeze publication. Do not tune020 or rerunidentical inputs toseekgreen. No new prospective cohort or real orders.',
        '', 'Preregistration: https://github.com/rafailm95/TradingAgents/commit/2ab77e2141b849faa9f3bc676e509f38a5969fc5',
        'Rules/rationale: docs/NR7_FUTURES_020.json; https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/narrow-range-day-nr7']
    (ROOT/'docs/NR7_FUTURES_020_RESULTS.md').write_text('\n'.join(lines)+'\n')
    table=''
    for c,s in all_summary.items():
        d=s['maximum_sampled_drawdown_scenario']['metrics']
        table+=f"<tr><td>{html.escape(c)}</td><td>{pair(s['base'])}</td><td>{pair(s['stress'])}</td><td>{pair(s['worst']['metrics'])}</td><td>{s['base']['signal_exits']}</td><td>{float(d['max_drawdown_pct']):.2f}% / {float(d['cash_at_max_pct_drawdown_usdt']):,.2f} USDT</td><td>{s['scenario_passes']}/12</td></tr>"
    bench_table=''.join(f"<tr><td>{html.escape(k)}</td><td>{pair(v['metrics'])}</td><td>{float(v['metrics']['max_drawdown_pct']):.2f}% / {float(v['metrics']['cash_at_max_pct_drawdown_usdt']):,.2f} USDT</td><td>{float(v['metrics']['fees_usdt']):.2f}</td><td>{float(v['metrics']['funding_usdt']):+.2f}</td><td>{float(v['metrics']['operating_expense_usdt']):.2f}</td></tr>" for k,v in e['reused_benchmarks'].items())
    wfatable=''.join(f"<tr><td>{k}</td><td>{pair(v['metrics'])}</td><td>{float(v['metrics']['max_drawdown_pct']):.2f}% / {float(v['metrics']['cash_at_max_pct_drawdown_usdt']):,.2f} USDT</td><td>{v['metrics']['signal_exits']}</td><td>{html.escape(', '.join(v['failed_gates']) or 'PASS')}</td></tr>" for k,v in e['walk_forward'].items())
    newtable=''.join(f"<tr><td>{c}</td><td>{r['cost']}</td><td>{r['lag_days']}</td><td>{r['adverse_funding_5bps']}</td><td>{pair(r['metrics'])}</td><td>{float(r['metrics']['max_drawdown_pct']):.2f}% / {float(r['metrics']['cash_at_max_pct_drawdown_usdt']):,.2f} USDT</td></tr>" for c in engine.NEW_CANDIDATES for r in e['comparisons_all10'][c])
    report=f'''<!doctype html><html lang="el"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Futures020 — NR7</title><style>body{{font:16px/1.6 system-ui;color:#15243b;background:#f5f7fb;max-width:1250px;margin:32px auto;padding:24px}}h1,h2{{line-height:1.2}}article{{background:white;padding:26px;border-radius:14px}}table{{border-collapse:collapse;font-size:13px;width:100%}}td,th{{text-align:left;border-bottom:1px solid #d8dfe8;padding:10px}}th{{background:#e8eef6}}.scroll{{overflow:auto}}.lead{{font-size:21px}}.pill{{background:#e6edf5;padding:12px;border-radius:8px}}code{{overflow-wrap:anywhere}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}</style><article>
    <p>Έρευνα020 ·17Οκτωβρίου2026 · BinanceETHUSDT perpetual</p><h1>Νέα οικογένεια NR7: αποτελέσματα και διασταυρώσεις</h1>
    <p class="lead">{newpasses}/2 νέες εκδοχές περνούν όλα τα ιστορικά κριτήρια. {scenario_pass}/24 επιμέρους σενάρια περνούν. Η ιστορική επίδοση δεν αποτελεί επιβεβαίωση μελλοντικού κέρδους.</p>
    <p class="pill">2νέες εκδοχές ·50συνολικά ·25οικογένειες ·{newruns}νέες προσομοιώσεις ·{7502+newruns}γνωστές εκτελέσεις μαζί με7παλιές επαναλήψεις αποκατάστασης. Καμία νέα παρατήρηση αγοράς ή πραγματική εντολή.</p>
    <h2>Τι δοκιμάστηκε</h2><p>Ανοδικό κλείσιμο πάνω από το υψηλό της προηγούμενης ημέρας, εφόσον εκείνη είχε το αυστηρά μικρότερο εύρος υψηλού−χαμηλού των τελευταίων7ημερών. Έξοδος με κλείσιμο κάτω από το προηγούμενο χαμηλό ή μετά από10πραγματικές ημέρες κατοχής. Δύο υπάρχοντα μεγέθη θέσης:50% και στόχος ετήσιας μεταβλητότητας15%, με όριο50%. Εκτέλεση στις01UTC της επόμενης ημέρας, με επιπλέον καθυστέρηση0/1/2ημερών.</p>
    <p>Αυτή είναι δική μας προεγγεγραμμένη προσαρμογή στο ημερήσιο κλείσιμο. Η <a href="https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/narrow-range-day-nr7">τεκμηρίωση StockCharts</a> εξηγεί το μοτίβο και τις ψευδείς διασπάσεις· δεν τεκμηριώνει κερδοφορία της συγκεκριμένης στρατηγικής.</p>
    <h2>Σύγκριση όλων των10συμβατών εκδοχών</h2><p>Περίοδος01/01/2024–31/12/2025. Ανεξάρτητο υποθετικό αρχικό κεφάλαιο10.000USDT ανά εκδοχή. Τα8παλιά αποτελέσματα επαναχρησιμοποιήθηκαν με έλεγχο hash. Πλήρης επιτυχία: θετικό καθαρό αποτέλεσμα, πτώση≤35%, τουλάχιστον20έξοδοι, πλήρη δεδομένα/λογιστικός έλεγχος σε όλα τα12σενάρια. Συνολικά{summary['all10_full_passes']}/10πλήρεις επιτυχίες.</p>
    <div class="scroll"><table><tr><th>Εκδοχή</th><th>Βασικό κόστος</th><th>Αυξημένο κόστος</th><th>Χειρότερο από12</th><th>Έξοδοι βάσης</th><th>Μέγιστη δειγματοληπτική πτώση / πραγματικό ποσό</th><th>Περνούν</th></tr>{table}</table></div>
    <h2>Επιλογή μόνο με παλαιότερα δεδομένα</h2><p>Το2023επέλεξε <b>{e['main_train_selected']}</b>. Η ετήσια διαδρομή επέλεξε {' → '.join(s['selected'] for s in e['expanding_training_selections'])}. Οι επιλογές δημοσιεύτηκαν πριν από την αξιολόγηση. Οι δύο νέες εκδοχές είχαν11εξόδους στο2023και ζημιά και στα δύο κόστη. Η ετήσια διαδρομή περνά{wfa_pass}/12σενάρια. Επαναχρησιμοποιήθηκαν{e['reused_wfa_folds']}πανομοιότυπα ετήσια αποτελέσματα, με έλεγχο ακριβούς κεφαλαίου και κανόνων. Τα χρονικά παράθυρα αλληλεπικαλύπτονται· δεν είναι ανεξάρτητες επιβεβαιώσεις.</p>
    <div class="scroll"><table><tr><th>Σενάριο ετήσιας διαδρομής</th><th>Καθαρό αποτέλεσμα</th><th>Πτώση / ποσό</th><th>Έξοδοι</th><th>Αποτυχίες</th></tr>{wfatable}</table></div>
    <h2>Μετρητά και διακράτηση50%</h2><div class="scroll"><table><tr><th>Σύγκριση</th><th>Καθαρό αποτέλεσμα</th><th>Πτώση / ποσό</th><th>ΠρομήθειεςUSDT</th><th>FundingUSDT</th><th>ΛειτουργικάUSDT</th></tr>{bench_table}</table></div>
    <h2>Και τα24νέα σενάρια</h2><div class="scroll"><table><tr><th>Εκδοχή</th><th>Κόστος</th><th>Καθυστέρηση ημέρες</th><th>Δυσμενές funding</th><th>Καθαρό αποτέλεσμα</th><th>Πτώση / ποσό</th></tr>{newtable}</table></div>
    <h2>Πόσο ρεαλιστικό είναι</h2><p>Πραγματικά επίσημα δεδομένα2022–2025:35.064ωριαίες τιμές συναλλαγών,35.064ωριαίες τιμές mark και4.383γεγονότα funding. Ίδια δεδομένα με017/019, χωρίς νέες παρατηρήσεις. Βασικό κόστος ανά πλευρά:5,5bpsπρομήθεια+2bpsολίσθηση. Αυξημένο:10+10bps. Επιπλέον120USDTανά έτος, πραγματικά funding rates στις στιγμές κατοχής και δυσμενής αποτίμηση5bps. Οι προσωπικές προμήθειες, ιστορικοί κανόνες εντολών και πραγματικές εκτελέσεις δεν είναι γνωστά. Οι κανόνες ελάχιστου βήματος παραμένουν υποθετικοί. Δεν υπάρχει μοντέλο εκκαθάρισης με μόχλευση.</p>
    <p>Η πτώση σε USDT είναι η διαφορά της πραγματικής κορυφής και του επόμενου χαμηλού στην καμπύλη, στο μέγιστο ποσοστιαίο drawdown. Δεν υπολογίζεται ως ποσοστό×10.000. Η ωριαία δειγματοληψία δεν αποδεικνύει ενδοωριαία σειρά τιμών. Το όριο35%είναι ερευνητικό κριτήριο, όχι επιβεβαιωμένη προσωπική ανοχή κινδύνου.</p>
    <p>Τα αδρανή μετρητά έχουν0έξοδα. Το buy-and-hold50%σε perpetual επιβαρύνεται με funding/προμήθειες/λειτουργικά. Η ετήσια διαδρομή πληρώνει κόστος κλεισίματος στο τέλος κάθε έτους, μεταφέρει το ακριβές υπόλοιπο και χρεώνει λειτουργικά ακόμη και όταν επιλέγει μετρητά.</p>
    <h2>Έλεγχοι και όρια συμπερασμάτων</h2><p>129έλεγχοι λογισμικού,18νέοι. {events:,}ανεξάρτητοι λογιστικοί έλεγχοι γεγονότων με μηδενική απόκλιση Decimal. Οι πηγές και523προηγούμενα αρχεία παρέμειναν αμετάβλητα. Όλες οι αποτυχίες διατηρούνται. Οι πολλαπλές συγκρίσεις περιλαμβάνουν και τις10συμβατές εκδοχές, με2.000αναδειγματοληψίες30ήμερων ομάδων. Δεν διορθώνουν όλη την προηγούμενη αναζήτηση ή τη χρήση των ίδιων ιστορικών ημερομηνιών. Οι40εκδοχές που έχουν μόνο spot αποτελέσματα δεν αναμειγνύονται.</p>
    <pre>{html.escape(json.dumps(e['multiplicity'],indent=2))}</pre>
    <p>Δεν υπάρχει ακόμη επιβεβαιωμένη μελλοντική κερδοφορία ή αποτέλεσμα στρατηγικής Bybit. Οι36πραγματικές λήψεις βιβλίου και600funding γεγονότα Bybit παραμένουν χρήσιμες μετρήσεις, όχι πλήρες ιστορικό. Αναμένεται το ήδη ζητημένο ενιαίοBYBIT_SEND_THIS.zip· δεν χρειάζεται νέο ξεχωριστό πακέτο ή κλειδί.</p>
    <h2>Επόμενο περιορισμένο βήμα</h2><p>Προτεραιότητα στον έλεγχο του ενιαίου πακέτου Bybit. Διαφορετικά, προεγγεγραμμένη επέκταση επίσημων futures δεδομένων στο2026για τους αμετάβλητους κανόνες, αφού ελεγχθούν πρώτα τιμές/mark/funding και δημοσιευτούν τα hashes. Χωρίς αλλαγές020για να εμφανιστεί κέρδος, νέες πραγματικές εντολές ή αυτόματη προσθήκη σε paper χαρτοφυλάκιο.</p>
    <p><a href="https://github.com/rafailm95/TradingAgents/commit/2ab77e2141b849faa9f3bc676e509f38a5969fc5">Προεγγραφή πριν από αποτελέσματα</a> · <a href="https://github.com/rafailm95/TradingAgents/blob/codex/research-continuation-20261016/docs/NR7_FUTURES_020_RESULTS.md">Αναλυτική αναφορά και αρχεία αποτελεσμάτων</a></p></article></html>'''
    report=report.replace('BinanceETHUSDT','Binance ETHUSDT').replace('ενιαίοBYBIT_SEND_THIS.zip','ενιαίο BYBIT_SEND_THIS.zip')
    # Typography only; preserve tags/links and machine identifiers.
    report=''.join(part if part.startswith('<') else re.sub(r'(?<=[0-9])(?=[Α-Ωα-ωA-Za-z])|(?<=[Α-Ωα-ω])(?=[0-9])',' ',part)
                   for part in re.split(r'(<[^>]+>)',report))
    (w/'Futures_020_NR7_EL.html').write_text(report)
    print(json.dumps({k:v for k,v in summary.items() if k not in ['new_results','all10_results','wfa','multiplicity']},indent=2))


if __name__=='__main__':main()
