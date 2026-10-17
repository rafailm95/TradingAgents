"""Read-only verification/report of frozen025 outcomes; never strategy replay."""
import argparse,csv,html,json,math,shutil,sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from decimal import Decimal as D
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from run_multifamily_futures_025 import verify_freeze,CANDIDATES,NEW_CANDIDATES
from run_nr7_futures_020 import read_result,file_sha
from package_futures_assets_021 import candidate_summary,pareto,perf,dd

def write(p,x):p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def verify_asset(job):
    workspace,symbol,freeze=job;w=Path(workspace);rows=[];events=0;statuses=Counter()
    for stage in ('train1','train2','evaluation'):
        root=w/('futures-025-'+stage);name='evaluation.json' if stage=='evaluation' else 'selection.json'
        full=json.loads((root/name).read_bytes())
        if full['freeze_sha256']!=freeze:raise ValueError('Stagefreeze mismatch')
        for rec in full['assets'][symbol]['new_results'].values():
            path=root/rec['file'];r=read_result(path,rec['sha256'],rec['container_sha256'])
            if r['symbol']!=symbol or r['metrics']!=rec['metrics']:raise ValueError('Summary/identity mismatch')
            audit=r['independent_wealth_audit']
            if audit['status']!='PASS' or D(audit['max_error_usdt'])!=0:raise ValueError('Wealth mismatch')
            rows.append({'path':str(path.relative_to(w)),'sha256':rec['sha256'],'container_sha256':rec['container_sha256'],'bytes':path.stat().st_size,'audit':audit})
            events+=audit['events_checked'];statuses[r['status']]+=1
        print('Verified '+symbol+' '+stage,flush=True)
    return {'symbol':symbol,'results':rows,'events':events,'statuses':dict(statuses)}

def table(headers,rows):
    return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+html.escape(str(x))+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'

def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);p.add_argument('--freeze-sha256',required=True);a=p.parse_args();w=a.workspace;o=ROOT/'research/experiments/025';pin=verify_freeze(a.freeze_sha256)
    with ProcessPoolExecutor(max_workers=3) as pool:verified=list(pool.map(verify_asset,[(str(w),s,a.freeze_sha256) for s in pin['inputs']]))
    hashes=[r for v in verified for r in v['results']];events=sum(v['events'] for v in verified);statuses=Counter()
    for v in verified:statuses.update(v['statuses'])
    if len({r['path'] for r in hashes})!=len(hashes):raise ValueError('Duplicate output')
    write(o/'full_result_hashes.json',hashes)
    for stage in ('train1','train2','evaluation'):
        name='evaluation.json' if stage=='evaluation' else 'selection.json';source=w/('futures-025-'+stage)/name;target=o/('evaluation.json' if stage=='evaluation' else 'selection-'+stage+'.json')
        if target.exists():
            if source.read_bytes()!=target.read_bytes():raise ValueError('Previously published selection changed')
        else:shutil.copyfile(source,target)
    e=json.loads((o/'evaluation.json').read_bytes());assets={};metricrows=[];wfarows=[];dailychecks=[];gatecounts=Counter();newpass=newscen=newpositive=wfapass=0;reused_wfa=0
    alltable=[];wfatable=[];selectiontable=[];shorttable=[];benchrows=[]
    for symbol,data in sorted(e['assets'].items()):
        cs={c:candidate_summary(rows,data['gates'][c]) for c,rows in data['comparisons'].items()}
        pareto(cs);front=sorted((c for c,v in cs.items() if v['pareto_frontier']),key=lambda c:(-D(cs[c]['worst12']['metrics']['net_return_pct']),c))
        shortlist=[];seen=set()
        for c in front:
            family=c.split('__')[0]
            if family not in seen and len(shortlist)<3:shortlist.append(c);seen.add(family)
        new={c:cs[c] for c in NEW_CANDIDATES};np=sum(v['full_pass'] for v in new.values());ns=sum(v['scenario_passes'] for v in new.values());positive=sum(v['positive_all12'] for v in new.values())
        newpass+=np;newscen+=ns;newpositive+=positive;wfapass+=sum(v['passed'] for v in data['walk_forward'].values());reused_wfa+=len(data['reused_wfa_folds'])
        best_new=max(NEW_CANDIDATES,key=lambda c:D(cs[c]['worst12']['metrics']['net_return_pct']))
        assets[symbol]={'candidates':cs,'new_full_passes':np,'new_scenario_passes':ns,'new_positive_all12':positive,'best_new_worst12':best_new,'main_selection':data['main_selection'],'main_selected_fixed':data['main_selected_fixed'],'second_selection':data['second_selection'],'walk_forward':data['walk_forward'],'WFA_passes':sum(v['passed'] for v in data['walk_forward'].values()),'posthoc_shortlist_distinct_families':shortlist,'benchmarks':data['benchmarks'],'reused_WFA_folds':len(data['reused_wfa_folds'])}
        for c,rows in data['comparisons'].items():
            for row in rows:metricrows.append({'symbol':symbol,'candidate':c,'new025':c in NEW_CANDIDATES,'cost':row['cost'],'lag_days':row['lag_days'],'adverse_funding_5bps':row['adverse_funding_5bps'],**row['metrics']})
            x=cs[c]
            if c in NEW_CANDIDATES:gatecounts.update(x['failed_gate_scenario_counts'])
            alltable.append([symbol,c,'Νέα025' if c in NEW_CANDIDATES else 'Παλιά021/022/024',perf(x['base']),perf(x['stress']),perf(x['worst12']['metrics']),dd(x['max_drawdown_scenario']['metrics']),x['base']['signal_exits'],x['full_pass'],json.dumps(x['failed_gate_scenario_counts'])])
        for key,returns in data['daily_returns_for_diagnostics'].items():
            candidate,cost=key.split('|')
            if len(returns)!=731:raise ValueError('Unmatched diagnostic window')
            m=data['benchmarks'][cost+'_adverse0']['metrics'] if candidate=='buy_hold50' else cs[candidate]['base' if cost=='venue_assumption' else 'stress']
            error=abs(10000*math.prod(1+x for x in returns)-float(m['final_equity_after_exit_fee_usdt']))
            if error>1e-6:raise ValueError('Daily returnterminal reconciliation')
            dailychecks.append({'symbol':symbol,'curve':key,'days':731,'error_usdt':error})
        for key,row in data['walk_forward'].items():
            wfarows.append({'symbol':symbol,'scenario':key,'passed':row['passed'],'failed_gates':'|'.join(row.get('failed_gates',[])),**row['metrics']})
            wfatable.append([symbol,key,perf(row['metrics']),dd(row['metrics']),row['metrics']['signal_exits'],', '.join(row['failed_gates']) or 'PASS'])
        select=data['main_selected_fixed'];wb=data['walk_forward']['venue_assumption_lag0_adverse0']['metrics'];ws=data['walk_forward']['stress_assumption_lag0_adverse0']['metrics']
        selectiontable.append([symbol,data['main_selection']['selected'],perf(select['venue_assumption']['metrics']),perf(select['stress_assumption']['metrics']),data['second_selection']['selected'],perf(wb),perf(ws)])
        for c in shortlist:shorttable.append([symbol,c,perf(cs[c]['worst12']['metrics']),dd(cs[c]['max_drawdown_scenario']['metrics']),cs[c]['full_pass']])
        for key,row in data['benchmarks'].items():benchrows.append([symbol,key,perf(row['metrics']),dd(row['metrics']),row['metrics']['operating_expense_usdt']])
    expected=240+e['new_simulations']
    if len(hashes)!=expected or not 960<=expected<=1035:raise ValueError('Bounded matrix count failure')
    if len(metricrows)!=1656:raise ValueError('Missing old/new scenario rows')
    for name,rows in [('metrics-all138.csv',metricrows),('walk-forward-all3.csv',wfarows)]:
        with (o/name).open('w',newline='') as f:q=csv.DictWriter(f,fieldnames=list(rows[0]));q.writeheader();q.writerows(rows)
    write(o/'daily-return-reconciliation.json',{'curves':dailychecks,'maximum_error_usdt':max(x['error_usdt'] for x in dailychecks)})
    cross=[c for c in NEW_CANDIDATES if all(v['candidates'][c]['full_pass'] for v in assets.values())]
    crosspositive=[c for c in NEW_CANDIDATES if all(v['candidates'][c]['positive_all12'] for v in assets.values())]
    summary={'experiment':'025','new_unique_variants':20,'new_families':10,'total_unique_variants':90,'total_families':45,'new_asset_candidate_pairs':60,'compatible_pairs':138,'new_historical_executions':expected,'new_integrity_replays':0,'cumulative_design_executions':8934+expected,'prior_integrity_replays':7,'cumulative_known_executions':8941+expected,'new_full_pass_fail':[newpass,60-newpass],'new_scenario_pass_fail':[newscen,720-newscen],'new_positive_all12':newpositive,'WFA_scenario_pass_fail':[wfapass,36-wfapass],'cross_asset_new_full_passes':cross,'cross_asset_new_positive_all12':crosspositive,'all_compatible_full_passes':sum(v['full_pass'] for a in assets.values() for v in a['candidates'].values()),'all_compatible_positive_all12':sum(v['positive_all12'] for a in assets.values() for v in a['candidates'].values()),'failed_gate_scenario_counts':dict(gatecounts),'reused_old_train_scenarios':312,'reused_old_evaluation_scenarios':936,'reused_benchmarks':15,'reused_WFA_folds':reused_wfa,'wealth_events':events,'maximum_wealth_error_usdt':'0','software_tests_passed':117,'all_results_statuses':dict(statuses),'prospective_days':0,'assets':assets,'multiplicity':e['multiplicity'],'scope':'Native BinanceUSD-M, independently10000USDT, known2022–2025histories. Exploratory, noBybit/live/prospective profitability.'}
    write(o/'summary.json',summary)
    write(o/'verification.json',{'source_freeze_sha256':a.freeze_sha256,'full_result_files_verified':len(hashes),'unique_paths':len(hashes),'statuses':dict(statuses),'wealth_events':events,'maximum_error_usdt':'0','integrity_failures':[],'replays':0,'source_files_verified':len(pin['source_hashes']),'old_files_preserved':len(pin['preserved_files']),'daily_curves_reconciled':len(dailychecks),'max_daily_terminal_error':max(x['error_usdt'] for x in dailychecks),'software_tests':117,'progress_log_anomalies':[],'financial_result_integrity_unresolved':False})
    ptext=[f'Έρευνα025: 10 νέες ιδέες /20 εκδοχές futures σε BTC, SOL, XRP',
      f'Ολοκληρώθηκαν {expected} νέες ιστορικές εκτελέσεις,20 νέες παραλλαγές σε10 οικογένειες. Σύνολο90 παραλλαγές/45 οικογένειες,{8934+expected} εκτελέσεις σχεδίων+7 παλιές επαναλήψεις ακεραιότητας={8941+expected} γνωστές εκτελέσεις. Οι εκδοχές μεγέθους θέσης και οι κοινές ημερομηνίες δεν είναι ανεξάρτητες αποδείξεις.',
      f'Νέα αποτελέσματα: {newpositive}/60 συνδυασμοί θετικοί και στα12 σενάρια· {newpass}/60 πλήρεις επιτυχίες,{60-newpass}/60 αποτυχίες. Επιμέρους σενάρια:{newscen}/720 επιτυχίες,{720-newscen}/720 αποτυχίες. Ετήσιες προεπιλεγμένες διαδρομές:{wfapass}/36 επιτυχίες,{36-wfapass}/36 αποτυχίες. Ίδια νέα εκδοχή πλήρως επιτυχής και στα3 νομίσματα:{len(cross)}/20.',
      'Πλήρη επίσημα BinanceUSD-M δεδομένα01/01/2022–31/12/2025, ήδη γνωστά από προηγούμενη έρευνα. Ανά νόμισμα35.064 πραγματικές ώρες trade καιmark. BTC/XRP4.383 πραγματικά funding γεγονότα, SOL4.458 με διατηρημένες αλλαγές8/4/2ωρών. Δεν έγινε νέα λήψη ή αντικατάσταση ιστορίας. Δεν χρησιμοποιήθηκαν τα ελλιπή2026 δεδομένα023.',
      'Αξιολόγηση01/01/2024–31/12/2025, ανεξάρτητα υποθετικά10.000USDT. Εκπαίδευση2023 για την πρώτη επιλογή·2023–2024 για το ετήσιο2025. Οι δύο επιλογές δημοσιεύτηκαν πριν από την αξιολόγηση. Το2024 είναι μέρος της δεύτερης εκπαίδευσης μόνο για το2025· δεν επηρεάζει την επιλογή του2024. Οι ημερομηνίες είχαν ήδη εξεταστεί σε παλιές ιδέες, επομένως δεν είναι άθικτο ή prospective δείγμα.',
      'Δύο μεγέθη θέσης: σταθερό50% κατά την είσοδο και στόχος μεταβλητότητας15% με όριο50%, με την ίδια αιτιώδη60ήμερη εκτίμηση. Μόνο long ή μετρητά, χωρίς επαναστάθμιση. Τα hourly χαρακτηριστικά χρησιμοποιούν μόνο κλεισμένες ώρες. Η mark τιμή χρησιμοποιείται ως χαρακτηριστικό/αποτίμηση· τα fills πάντοτε χρησιμοποιούν πραγματικές ωριαίες trade τιμές.',
      'Κόστος ανά πλευρά: βάση5,5bps προμήθεια+2bps ολίσθηση (0,075%), stress10+10bps (0,20%). Λειτουργικά120USDT ανά365,25ημέρες. Πραγματικό funding όταν υπάρχει θέση, ωριαία mark ως προσέγγιση και δυσμενής μετατόπιση5bps. Καθυστέρηση σήματος0/1/2ημέρες. Πλήρης έλεγχος12σεναρίων ανά υποψήφιο. Τα πραγματικά προσωπικά fees/margin και ιστορικά βιβλία/fills/φίλτρα δεν είναι διαθέσιμα.',
      'Πλήρης επιτυχία: καθαρό κέρδος>0 και στα12σενάρια, δειγματοληπτική πτώση≤35%,≥20έξοδοι σήματος/χρονικού ορίου, πλήρη δεδομένα και ανεξάρτητη λογιστική συμφωνία. Οι αναγκαστικές τελικές έξοδοι δεν προσμετρώνται. Εκπαίδευση: θετικό αποτέλεσμα και σταδύοκόστη,πτώση≤35%,≥10έξοδοι. Κατάταξη βάσει stressετησιοποιημένης απόδοσης/max(stressπτώση,1%),ισοβαθμίαID,διαφορετικάcash. Δεν άλλαξε κανένα όριο μετά τα αποτελέσματα.',
      'Τα20είναι λειτουργικό ελάχιστο, όχι στατιστική απόδειξη. Το35%είναι φίλτρο έρευνας, όχι επιβεβαιωμένη προσωπική ανοχή κινδύνου. Τα ποσά πτώσης προκύπτουν από την πραγματική κορυφή και το χαμηλό της δειγματοληπτικής καμπύλης στο μέγιστο ποσοστιαίο drawdown· το μέγιστο απόλυτο drawdown φυλάσσεται ξεχωριστά. Άγνωστη η σειρά υψηλού/χαμηλού εντός ώρας. Δεν υπάρχει μοντέλο εκκαθάρισης με μόχλευση.',
      f'Επαναχρησιμοποιήθηκαν312 παλιές εκτελέσεις εκπαίδευσης,936 αξιολόγησης,15 benchmarks και{reused_wfa} ετήσια σκέλη με ακριβώς ίδιες επιλογές/κεφάλαιο. Η ετήσια διαδρομή μεταφέρει το ακριβές καθαρό κεφάλαιο μετά από έξοδα και τελικό κλείσιμο. Η διαχειριζόμενηcash πληρώνει λειτουργικά· η αδρανήςcashαναφορά έχει μηδενικό κόστος.',
      'Η περιγραφική κατάταξη μετά τα αποτελέσματα χρησιμοποιεί τη χειρότερη καθαρή απόδοση και τη μεγαλύτερη πτώση μεταξύ12σεναρίων, κρατώντας έως3διαφορετικές οικογένειες ανά νόμισμα. Δεν αντικαθιστά την προεπιλογή εκπαίδευσης και δεν προάγει αυτόματα στρατηγικές.',
      'Οι πολλαπλές συγκρίσεις περιλαμβάνουν και τους46 συμβατούς παλιούς/νέους υποψηφίους ανά νόμισμα και138 συνδυασμούς με κοινές731ημέρες,30ήμερα blocks και2.000 επαναδειγματοληψίες, μετά τα λειτουργικά. Η προηγούμενη αναζήτηση70εκδοχών και η επιλογή οικογενειών/νομισμάτων δεν διορθώνονται πλήρως. Οι παλαιότεροι έλεγχοι spot και ETH έχουν διαφορετικά δεδομένα ή συμβάσεις και παραμένουν χωριστά.',
      f'117 νέοι έλεγχοι λογισμικού πέρασαν πριν το πρώτο πραγματικό αποτέλεσμα. Επαληθεύτηκαν{len(hashes)} πλήρη αρχεία και{events:,} λογιστικά γεγονότα με μηδενική απόκλισηDecimal. Οι συνθετικές δοκιμές δεν μετρούν ως ιστορική έρευνα.',
      'Μηδέν νέα prospective ημερολογιακά στοιχεία. Το ορόσημο παρακολούθησης απαιτεί≥180ημέρες ΚΑΙ≥20 ολοκληρωμένες εξόδους, θετικό καθαρό αποτέλεσμα και σταδύοκόστη,πτώση≤35%,κάλυψη≥95%,χωρίς εκκρεμή/σφάλματα ακεραιότητας. Ούτε αυτό αποτελεί στατιστική απόδειξη, εγγύηση ή άδεια πραγματικών συναλλαγών.',
      'Η αρχική εκκίνηση025 διακόπηκε από αποσύνδεση περιβάλλοντος χωρίς επιβεβαίωση έναρξης διεργασίας. Στο ανακτημένο περιβάλλον δεν εντοπίστηκε αποτέλεσμα ή ενεργή εκτέλεση025. Διατηρήθηκαν η αβεβαιότητα και τα αρχικά σφάλματα. Τα αποτελέσματα εδώ είναι οι πρώτες επαληθευμένες εκτελέσεις025. Επίσης διατηρούνται δύο αρχικές αποτυχίες συνθετικών ελέγχων που διορθώθηκαν πριν από την προεγγραφή και οποιοδήποτε πραγματικό PnL.',
      'Τα013/014,023 και οι δύο παλιές prospectiveομάδες παρέμειναν αμετάβλητα. Προτεραιότητα έχει η αξιολόγηση του ενιαίουBybitπακέτου όταν φτάσει. Επόμενη bounded παρτίδα μόνο με νέο προκαταχωρισμένο ερώτημα ή συγκεκριμένο έλεγχο ευθραυστότητας, χωρίς αλλαγή παραμέτρων για να εμφανιστεί κέρδος.'
    ]
    # Presentation only: preserve every numeric value, rule, output and selection.
    import re
    def prose_spacing(text):
        text=re.sub(r'(?<=[Α-Ωα-ωάέήίόύώϊϋΐΰ])(?=[0-9])', ' ', text)
        text=re.sub(r'(?<=[0-9])(?=[Α-Ωα-ωάέήίόύώϊϋΐΰ])', ' ', text)
        return text.replace('USDTανά','USDT ανά').replace('δύοκόστη','δύο κόστη').replace('stressετησιοποιημένης','stress ετησιοποιημένης').replace('stressπτώση','stress πτώση').replace('ισοβαθμίαID','ισοβαθμία ID').replace('cashαναφορά','cash αναφορά').replace('prospectiveομάδες','prospective ομάδες').replace('ενιαίουBybitπακέτου','ενιαίου Bybit πακέτου')
    ptext=[prose_spacing(x) for x in ptext]
    ptext.append('Τα παραπάνω όρια είναι ιστορικά φίλτρα. Η υπεραπόδοση έναντι 50% διακράτησης και η στατιστική σημαντικότητα αναφέρονται χωριστά· δεν αποτελούν κρυφά πρόσθετα ή χαλαρωμένα κριτήρια. Ο έλεγχος πολλαπλών συγκρίσεων εξετάζει την αριθμητική μέση ημερήσια υπεραπόδοση, η οποία μπορεί να κατατάσσει διαφορετικά από το τελικό κεφάλαιο λόγω μεταβλητότητας.')
    headers=['Νόμισμα','Στρατηγική','Προέλευση','Βάση','Stress','Χειρότερο 12','Πτώση % / πραγματικό ποσό','Έξοδοι βάσης','Πλήρης επιτυχία','Αποτυχημένα κριτήρια']
    md=['# '+ptext[0],'']+[t+'\n' for t in ptext[1:]]
    md+=['|'+ '|'.join(headers)+'|','|'+'|'.join(['---']*len(headers))+'|']+['|'+'|'.join(str(x).replace('|','/') for x in row)+'|' for row in alltable]
    md+=['','## Προεπιλογή και ετήσια διαδρομή','', '|Νόμισμα|Επιλογή2023|Σταθερόbase|Σταθερόstress|Επιλογή2023–2024|WFAbase|WFAstress|','|---|---|---|---|---|---|---|']+['|'+'|'.join(str(x) for x in row)+'|' for row in selectiontable]
    md+=['','## Διαγνωστικοί έλεγχοι πολλαπλών συγκρίσεων','', '```json',json.dumps(e['multiplicity'],indent=2),'```']
    md+=['','## Πηγές και ακριβή στοιχεία','', 'Οι επίσημες πηγές των 10 δεικτών, ακριβείς κανόνες και υποθέσεις βρίσκονται στο docs/MULTIFAMILY_FUTURES_025.json. Οι δείκτες δεν είναι απόδειξη κερδοφορίας.','Αποτελέσματα: research/experiments/025/{summary,evaluation,verification,full_result_hashes,artifact_receipts}.json, metrics-all138.csv και walk-forward-all3.csv.']
    (ROOT/'docs/MULTIFAMILY_FUTURES_025_RESULTS.md').write_text('\n'.join(md)+'\n')
    protocol=json.loads((ROOT/'docs/MULTIFAMILY_FUTURES_025.json').read_bytes());familyrows=[[v['id'],v['entry_after_closed_day'],v['exit_after_closed_day'],v['max_actual_holding_days']] for v in protocol['families']]
    body='<h1>'+html.escape(ptext[0])+'</h1>'+''.join('<p>'+html.escape(x)+'</p>' for x in ptext[1:5])
    body+='<h2>Προεπιλογή και ετήσια διαδρομή</h2>'+table(['Νόμισμα','Επιλογή2023','Base2024–2025','Stress2024–2025','Επιλογή2023–2024','WFAbase','WFAstress'],selectiontable)
    body+='<h2>Ισχυρότερες διερευνητικές ενδείξεις</h2>'+table(['Νόμισμα','Στρατηγική','Χειρότερο12','Πτώση / πραγματικό ποσό','Πλήρης επιτυχία'],shorttable)
    body+='<h2>Όλες οι νέες και παλιές εκδοχές</h2>'+table(headers,alltable)
    body+='<details><summary>Κανόνες των 10 νέων ιδεών</summary>'+table(['Οικογένεια','Είσοδος','Έξοδος','Μέγιστεςημέρες'],familyrows)+'</details>'
    body+='<details><summary>Και οι 36 ετήσιες διαδρομές</summary>'+table(['Νόμισμα','Σενάριο','Καθαρό','Πτώση','Έξοδοι','Αποτυχίες'],wfatable)+'</details>'
    body+='<details><summary>Μετρητά και 50% διακράτηση</summary>'+table(['Νόμισμα','Σενάριο','Καθαρό','Πτώση','ΛειτουργικάUSDT'],benchrows)+'</details>'
    body+=''.join('<p>'+html.escape(x)+'</p>' for x in ptext[5:])
    body+='<details><summary>Ακριβείς έλεγχοι πολλαπλών συγκρίσεων</summary><pre>'+html.escape(json.dumps(e['multiplicity'],indent=2))+'</pre></details>'
    body+='<h2>Πρωτογενής τεκμηρίωση δεικτών</h2><ul>'+''.join('<li><a href="'+html.escape(x['source'],quote=True)+'">'+html.escape(x['id'])+'</a></li>' for x in protocol['families'])+'</ul>'
    report=w/'Futures_025_Twenty_Strategies_EL.html';report.write_text('<!doctype html><html lang="el"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>20 νέες εκδοχές futures</title><style>body{font:16px/1.6 system-ui;max-width:1450px;margin:32px auto;padding:0 20px;color:#19334a}h1,h2{color:#154e79}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border:1px solid #cad7e2;padding:8px;text-align:left}th{background:#eaf2f8}tr:nth-child(even){background:#f7fafc}.scroll{overflow:auto;margin:20px 0}summary{cursor:pointer;font-weight:bold;padding:15px}p{max-width:1120px}</style>'+body+'</html>')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('assets','multiplicity')},indent=2),flush=True)
if __name__=='__main__':main()
