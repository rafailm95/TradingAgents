"""Verify completed022 artifacts and report reused021 comparisons; never replay."""
import argparse,csv,html,json,shutil,sys
import math
from collections import Counter
from decimal import Decimal as D
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from run_sol_funding_022 import verify_freeze,CANDIDATES
from run_nr7_futures_020 import read_result,file_sha
from package_futures_assets_021 import candidate_summary,pareto,perf,dd

def write(p,x):p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def table(headers,rows):
    return '<div class="scroll"><table><tr>'+''.join('<th>'+html.escape(str(x))+'</th>' for x in headers)+'</tr>'+''.join('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in row)+'</tr>' for row in rows)+'</table></div>'

def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);p.add_argument('--freeze-sha256',required=True);a=p.parse_args();w=a.workspace;o=ROOT/'research/experiments/022'
    pin=verify_freeze(a.freeze_sha256);hashes=[];events=0;allstatuses=Counter()
    for stage in ('train1','train2','evaluation'):
        folder=w/('futures-022-'+stage);name='evaluation.json' if stage=='evaluation' else 'selection.json'
        value=json.loads((folder/name).read_bytes())
        if value['freeze_sha256']!=a.freeze_sha256:raise ValueError('Wrong stage freeze')
        for s,data in value['assets'].items():
            for record in data['new_results'].values():
                path=folder/record['file'];r=read_result(path,record['sha256'],record['container_sha256'])
                if r['symbol']!=s or r['metrics']!=record['metrics']:raise ValueError('Result identity/summary mismatch')
                audit=r['independent_wealth_audit']
                if audit['status']!='PASS' or D(audit['max_error_usdt'])!=0:raise ValueError('Wealth mismatch')
                events+=audit['events_checked'];allstatuses[r['status']]+=1
                hashes.append({'path':str(path.relative_to(w)),'sha256':record['sha256'],'container_sha256':record['container_sha256'],'bytes':path.stat().st_size,'audit':audit})
        shutil.copyfile(folder/name,o/('evaluation.json' if stage=='evaluation' else 'selection-'+stage+'.json'))
    if len(hashes)!=125 or len({x['path'] for x in hashes})!=125:raise ValueError('Incomplete125matrix')
    write(o/'full_result_hashes.json',hashes)
    e=json.loads((o/'evaluation.json').read_bytes());old=json.loads((ROOT/'research/experiments/021/evaluation.json').read_bytes())
    merged={**old['assets'],**e['assets']};assert set(merged)=={'BTCUSDT','SOLUSDT','XRPUSDT'}
    daily_checks=[]
    for symbol,data in merged.items():
        for key,returns in data['daily_returns_for_diagnostics'].items():
            candidate,cost=key.split('|')
            if len(returns)!=731:raise ValueError('Unmatched daily diagnostic dates')
            if candidate=='buy_hold50':m=data['benchmarks'][cost+'_adverse0']['metrics']
            else:m=next(x['metrics'] for x in data['comparisons'][candidate] if x['cost']==cost and x['lag_days']==0 and not x['adverse_funding_5bps'])
            reconstructed=10000*math.prod(1+x for x in returns);error=abs(reconstructed-float(m['final_equity_after_exit_fee_usdt']))
            if error>1e-6:raise ValueError('Daily-return terminal wealth mismatch')
            daily_checks.append({'symbol':symbol,'curve':key,'days':731,'terminal_error_usdt':error})
    write(o/'daily-return-reconciliation.json',{'curves':daily_checks,'maximum_error_usdt':max(x['terminal_error_usdt'] for x in daily_checks),'shared_dates':'2024-01-01..2025-12-31'})
    asset_summaries={};metricrows=[];wfarows=[];tablerows=[];wfatab=[];benchtab=[];selecttab=[];shortlist=[];failurecounts=Counter()
    for symbol,data in sorted(merged.items()):
        cs={c:candidate_summary(rows,data['gates'][c]) for c,rows in data['comparisons'].items()};short=pareto(cs)
        chosen=data['main_selection']['selected'];second=data['second_selection']['selected']
        selected=cs[chosen] if chosen!='cash' else {'base':data['benchmarks']['cash']['metrics'],'stress':data['benchmarks']['cash']['metrics']}
        origin='Νέο 022' if symbol=='SOLUSDT' else 'Διατηρημένο 021'
        asset_summaries[symbol]={'origin':origin,'candidates':cs,'full_passes':sum(x['full_pass'] for x in cs.values()),'scenario_passes':sum(x['scenario_passes'] for x in cs.values()),'positive_all12':sum(x['positive_all12'] for x in cs.values()),'main_selection':data['main_selection'],'main_selected_outcome':selected,'second_selection':data['second_selection'],'wfa':data['walk_forward'],'wfa_scenario_passes':sum(x['passed'] for x in data['walk_forward'].values()),'benchmarks':data['benchmarks'],'shortlist_posthoc':short}
        selecttab.append([symbol,chosen,perf(selected['base']),perf(selected['stress']),second,perf(data['walk_forward']['venue_assumption_lag0_adverse0']['metrics']),perf(data['walk_forward']['stress_assumption_lag0_adverse0']['metrics'])])
        shortlist.append(symbol+': '+', '.join(c+' ('+perf(cs[c]['worst12']['metrics'])+')' for c in short))
        for c,x in cs.items():
            tablerows.append([symbol+' / '+c,origin,perf(x['base']),perf(x['stress']),perf(x['worst12']['metrics']),dd(x['max_drawdown_scenario']['metrics']),x['base']['signal_exits'],str(x['full_pass']),str(x['failed_gate_scenario_counts'])])
            if symbol=='SOLUSDT':failurecounts.update(x['failed_gate_scenario_counts'])
        for c,rows in data['comparisons'].items():
            for row in rows:metricrows.append({'symbol':symbol,'origin_batch':'022' if symbol=='SOLUSDT' else '021','candidate':c,'cost':row['cost'],'lag_days':row['lag_days'],'adverse_funding_5bps':row['adverse_funding_5bps'],**row['metrics']})
        for key,row in data['walk_forward'].items():
            wfarows.append({'symbol':symbol,'origin_batch':'022' if symbol=='SOLUSDT' else '021','scenario':key,'passed':row['passed'],'failed_gates':'|'.join(row['failed_gates']),**row['metrics']})
            wfatab.append([symbol,key,perf(row['metrics']),dd(row['metrics']),row['metrics']['signal_exits'],', '.join(row['failed_gates']) or 'PASS'])
        for key,row in data['benchmarks'].items():
            m=row['metrics'];benchtab.append([symbol,key,perf(m),dd(m),m['fees_usdt'],m['funding_usdt'],m['operating_expense_usdt']])
    for name,rows in [('metrics-all18.csv',metricrows),('walk-forward-all3.csv',wfarows)]:
        with (o/name).open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    sol=asset_summaries['SOLUSDT'];cross=[c for c in CANDIDATES if all(x['candidates'][c]['full_pass'] for x in asset_summaries.values())]
    summary={'experiment':'022','new_unique_variants':0,'total_unique_variants':50,'total_families':25,'new_asset_candidate_pairs':6,'combined_asset_candidate_pairs':18,'new_design_executions':125,'reused_design_executions_021':250,'cumulative_design_executions':7902,'prior_integrity_replays':7,'new_integrity_replays':0,'cumulative_known_executions':7909,'new_full_passes':sol['full_passes'],'new_full_failures':6-sol['full_passes'],'new_scenario_passes':sol['scenario_passes'],'new_scenario_failures':72-sol['scenario_passes'],'new_positive_all12':sol['positive_all12'],'new_WFA_passes':sol['wfa_scenario_passes'],'new_WFA_failures':12-sol['wfa_scenario_passes'],'combined_full_passes':sum(x['full_passes'] for x in asset_summaries.values()),'combined_full_failures':18-sum(x['full_passes'] for x in asset_summaries.values()),'combined_scenario_passes':sum(x['scenario_passes'] for x in asset_summaries.values()),'combined_positive_all12':sum(x['positive_all12'] for x in asset_summaries.values()),'cross_asset_full_passes':cross,'assets':asset_summaries,'new_failed_gate_scenario_counts':dict(failurecounts),'wealth_events':events,'max_wealth_error_usdt':'0','software_tests_passed':157,'new_software_tests':29,'prospective_evidence_days':0,'multiplicity':e['multiplicity'],'coverage':pin['inputs']['SOLUSDT']['audit'],'classification':'Exploratory native Binance futures; no Bybit, actual fills or forward profit validation'}
    write(o/'summary.json',summary)
    verify={'engine_freeze_sha256':a.freeze_sha256,'preserved_files_verified':len(pin['preserved_files']),'source_hashes_verified':len(pin['source_hashes']),'full_results_verified':len(hashes),'result_status_counts':dict(allstatuses),'wealth_events':events,'max_error_usdt':'0','integrity_failures':[],'new_integrity_replays':0,'software_tests':157,'new_tests':29,'new_synthetic_matrix_executions':125,'inherited_synthetic_matrix_executions':125,'prior021_results_not_rerun':True,'daily_diagnostic_curves_reconciled':len(daily_checks),'max_daily_terminal_error_usdt':max(x['terminal_error_usdt'] for x in daily_checks)}
    write(o/'verification.json',verify)
    headers=['Νόμισμα / στρατηγική','Προέλευση','Βασικό καθαρό','Αυξημένο κόστος','Χειρότερο /12','Μέγιστη πτώση / ποσό','Έξοδοι βάσης','Πλήρης επιτυχία','Αποτυχημένα κριτήρια /12']
    text=[f'Έρευνα 022: SOL και συνδυασμένη εικόνα BTC / SOL / XRP',
        f'125 νέες ιστορικές εκτελέσεις SOL, 0 νέες παραλλαγές στρατηγικής. 50 εκδοχές / 25 οικογένειες συνολικά. 7.902 εκτελέσεις σχεδίων + 7 παλιές επαναλήψεις αποκατάστασης = 7.909 γνωστές εκτελέσεις. Τα 250 BTC/XRP αποτελέσματα 021 επαναχρησιμοποιήθηκαν χωρίς επανεκτέλεση.',
        f"SOL: {sol['positive_all12']}/6 θετικά και στα 12 σενάρια, {sol['full_passes']}/6 πλήρεις επιτυχίες, {6-sol['full_passes']}/6 αποτυχίες. Επιμέρους σενάρια {sol['scenario_passes']}/72 επιτυχίες, {72-sol['scenario_passes']}/72 αποτυχίες. Ετήσια διαδρομή {sol['wfa_scenario_passes']}/12 επιτυχίες, {12-sol['wfa_scenario_passes']}/12 αποτυχίες.",
        f"Στα τρία νομίσματα: {summary['combined_positive_all12']}/18 συνδυασμοί θετικοί σε όλα τα σενάρια, {summary['combined_full_passes']}/18 πλήρεις επιτυχίες. Διασταύρωση της ίδιας στρατηγικής σε όλα τα νομίσματα: {len(cross)}/6. Οι δοκιμές μοιράζονται ημερολογιακά έτη και δεν είναι ανεξάρτητη μελλοντική επιβεβαίωση.",
        'Επίσημα Binance USD-M δεδομένα 01/01/2022–31/12/2025. SOL: 35.064 ώρες τιμών και 35.064 ώρες mark, 4.458 πραγματικές χρεώσεις funding. Επαληθεύτηκαν 144 μηνιαία και 10 ημερήσια αρχεία με SHA256 και CRC. Οι 168 ανακτημένες ώρες είναι πραγματικά ημερήσια στοιχεία, με 72 ακριβείς επικαλύψεις. Χωρίς τεχνητές τιμές ή νέα λήψη δεδομένων.',
        'Το funding αλλάζει 8h→4h→2h→8h τον Νοέμβριο 2022. Κρατήθηκαν οι πραγματικοί χρόνοι, τα rates και οι ετικέτες διαστήματος. Η πρώτη ετικέτα 2h ακολουθεί 4ωρη απόσταση. Ο έλεγχος πληρότητας είναι υπό τον παγωμένο παρατηρημένο ρυθμό των επίσημων αρχείων, χωρίς ανεξάρτητη επιβεβαίωση όλων των μεταβάσεων από API. Μέγιστη χρονική απόκλιση 31ms. Η παλιά απόρριψη 021 παραμένει αμετάβλητη.',
        'Αξιολόγηση 01/01/2024–31/12/2025, ανεξάρτητα υποθετικά κεφάλαια 10.000 USDT. Το 2022 είναι προετοιμασία. Πρώτη επιλογή μόνο από το 2023· δεύτερη μόνο από 2023–2024 για το 2025. Οι επιλογές δημοσιεύτηκαν πριν από τα επόμενα στάδια. Οι παρακάτω ισχυρότερες ιδέες επιλέγονται περιγραφικά μετά τα αποτελέσματα και δεν αντικαθιστούν την προεπιλογή.',
        'Κόστος ανά πλευρά: 5,5 bps προμήθεια + 2 bps ολίσθηση, ή αυξημένο 10 + 10 bps. Λειτουργικά 120 USDT/365,25 ημέρες, δηλαδή 240,164271 USDT στο πλήρες διετές παράθυρο. Πραγματικό funding μόνο όταν υπάρχει θέση, με ωριαία mark ως προσέγγιση και δυσμενή ευαισθησία 5 bps. Επιπλέον καθυστέρηση 0/1/2 ημερών. Daily κλειστό σήμα D, εκτέλεση D+1+lag στις 01UTC.',
        'Μόνο long ή μετρητά, αρχική έκθεση έως 50%, πλήρης κάλυψη από μετρητά. Τα βήματα ποσότητας/τιμής είναι υποθετικές παραδοχές, όχι επαληθευμένα ιστορικά φίλτρα. Προσωπικές προμήθειες, margin, ιστορικά βιβλία και fills άγνωστα. Δεν υπάρχει μοντέλο εκκαθάρισης με μόχλευση. Δεν είναι αποτέλεσμα Bybit.',
        'Πλήρης ιστορική επιτυχία απαιτεί σε κάθε ένα από τα 12 σενάρια καθαρό κέρδος, πτώση ≤35%, ≥20 εξόδους σήματος/χρονικού ορίου, πλήρη κάλυψη και λογιστικό έλεγχο. Η εκπαίδευση απαιτεί ≥10 εξόδους και θετικό αποτέλεσμα και στα δύο κόστη. Αναγκαστικά τελικά κλεισίματα δεν μετρούν ως έξοδοι σήματος. Τα όρια δεν χαμηλώθηκαν.',
        'Η πτώση σε USDT είναι η διαφορά της πραγματικής κορυφής και του χαμηλού της δειγματοληπτικής καμπύλης στο μέγιστο ποσοστιαίο drawdown. Το μέγιστο απόλυτο cash drawdown διατηρείται ξεχωριστά στα ακριβή αρχεία. Η σειρά ενδοωριαίου υψηλού/χαμηλού δεν είναι γνωστή.',
        'Η ετήσια διαδρομή κλείνει θέσεις με κόστος και μεταφέρει το ακριβές κεφάλαιο, χωρίς επαναφορά σε 10.000. Η διαχειριζόμενη επιλογή cash πληρώνει τα λειτουργικά· ο συγκριτικός δείκτης αδρανών μετρητών έχει μηδενικό κόστος. Η διακράτηση 50% perpetual πληρώνει fees, funding, λειτουργικά και τελικό κλείσιμο.',
        f'157 έλεγχοι λογισμικού, 29 νέοι. Τα 125 νέα συνθετικά σενάρια και η επανάληψη 125 παλιών σεναρίων ελέγχου λογισμικού δεν μετρούν ως ιστορική έρευνα. Επαληθεύτηκαν και τα 125 νέα αρχεία και {events:,} λογιστικά γεγονότα, με μηδενική απόκλιση Decimal.',
        'Οι διαγνωστικοί έλεγχοι πολλαπλών συγκρίσεων καλύπτουν και τις έξι στρατηγικές ανά νόμισμα και όλους τους 18 συμβατούς συνδυασμούς, με κοινά 30ήμερα blocks και 2.000 αναδειγματοληψίες. Περιλαμβάνουν τα λειτουργικά έξοδα. Δεν διορθώνουν την προηγούμενη αναζήτηση 50 εκδοχών ή την επιλογή νομισμάτων/οικογενειών. Οι 4 άλλες ETH εκδοχές και 40 spot εκδοχές διατηρούν τα προηγούμενα διαγνωστικά, χωρίς ανάμειξη ασύμβατων συμβολαίων. Η αριθμητική μέση ημερήσια απόδοση μπορεί να ταξινομεί διαφορετικά από το τελικό ανατοκισμένο κεφάλαιο.',
        'Μηδέν νέες prospective ημέρες. Επιβεβαίωση δεν προκύπτει από ένα κερδοφόρο backtest. Το ορόσημο παρακολούθησης παραμένει ≥180 ημερολογιακές ημέρες ΚΑΙ ≥20 ολοκληρωμένες έξοδοι ανά υποψήφιο, θετικό καθαρό αποτέλεσμα στα δύο κόστη, πτώση ≤35%, κάλυψη ≥95%, χωρίς εκκρεμή ή αποτυχημένο έλεγχο ακεραιότητας. Δεν δίνει άδεια πραγματικών συναλλαγών.',
        'Τα παλιά spot πειράματα, οι επτά prospective υποψήφιοι και τα Bybit 013/014 παρέμειναν αμετάβλητα. Προτεραιότητα έχει το ήδη ζητημένο ενιαίο BYBIT_SEND_THIS.zip όταν φτάσει. Επόμενη εναλλακτική: ένας χωριστά παγωμένος έλεγχος μεταγενέστερων κοινών futures ημερομηνιών, μετά από έλεγχο πραγματικής κάλυψης, χωρίς αλλαγή των έξι στρατηγικών ή αυτόματη προαγωγή.'
    ]
    md=['# '+text[0],'']+[p+'\n' for p in text[1:]]
    md+=['|'+ '|'.join(headers)+'|','|'+'|'.join(['---']*len(headers))+'|']+['|'+ '|'.join(str(c).replace('|','/') for c in row)+'|' for row in tablerows]
    md+=['','## Chronological selection and WFA','', '|Asset|Train1 choice|Fixed base|Fixed stress|Train2 choice|WFA base|WFA stress|','|---|---|---|---|---|---|---|']+['|'+'|'.join(str(x) for x in row)+'|' for row in selecttab]
    md+=['','## Descriptive Pareto leads','']+shortlist+['','Exact metrics: research/experiments/022/{summary,verification,evaluation,full_result_hashes}.json, metrics-all18.csv and walk-forward-all3.csv.','Sources: https://github.com/binance/binance-public-data and https://www.binance.com/en/support/announcement/detail/e8be17e1e544418490e86723d84759f0 .']
    (ROOT/'docs/SOL_FUNDING_022_RESULTS.md').write_text('\n'.join(md)+'\n')
    body='<h1>'+html.escape(text[0])+'</h1>'+''.join('<p>'+html.escape(x)+'</p>' for x in text[1:6])
    body+='<h2>Όλες οι στρατηγικές — 2024–2025</h2>'+table(headers,tablerows)
    body+='<h2>Επιλογή πριν από την αξιολόγηση</h2>'+table(['Νόμισμα','Επιλογή 2023','Σταθερό base','Σταθερό stress','Επιλογή 2023–2024','Ετήσιο base','Ετήσιο stress'],selecttab)
    body+='<h2>Ισχυρότερα διερευνητικά ευρήματα</h2>'+''.join('<p>'+html.escape(x)+'</p>' for x in shortlist)
    body+='<h2>Ετήσια διαδρομή και αποτυχημένα κριτήρια</h2>'+table(['Νόμισμα','Σενάριο','Καθαρό','Πτώση / ποσό','Έξοδοι','Αποτυχίες'],wfatab)
    body+='<h2>Μετρητά και διακράτηση 50%</h2>'+table(['Νόμισμα','Σενάριο','Καθαρό','Πτώση / ποσό','Fees USDT','Funding USDT','Λειτουργικά USDT'],benchtab)
    body+='<h2>Μέθοδος και περιορισμοί</h2>'+''.join('<p>'+html.escape(x)+'</p>' for x in text[6:])
    body+='<details><summary>Ακριβείς πολλαπλές συγκρίσεις</summary><pre>'+html.escape(json.dumps(e['multiplicity'],indent=2))+'</pre></details>'
    body+='<p><a href="https://github.com/rafailm95/TradingAgents/blob/codex/research-continuation-20261016/docs/SOL_FUNDING_022_RESULTS.md">Δημοσιευμένα αποτελέσματα και αναπαραγωγή</a> · <a href="https://github.com/binance/binance-public-data">Επίσημα δεδομένα Binance</a> · <a href="https://www.binance.com/en/support/announcement/detail/e8be17e1e544418490e86723d84759f0">Ανακοίνωση αλλαγής funding</a></p>'
    document='<!doctype html><html lang="el"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Futures 022 BTC SOL XRP</title><style>body{font:16px/1.55 system-ui;background:#f3f6fa;color:#182b42;max-width:1480px;margin:24px auto;padding:24px}article{background:white;padding:30px;border-radius:12px}table{border-collapse:collapse;font-size:13px;min-width:900px;width:100%}td,th{padding:9px;border-bottom:1px solid #d8e0eb;text-align:left}th{background:#e8eef5}.scroll{overflow:auto}h1,h2{line-height:1.2}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><article>'+body+'</article></html>'
    (w/'Futures_022_SOL_BTC_XRP_EL.html').write_text(document)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('assets','coverage','multiplicity')},indent=2))

if __name__=='__main__':main()
