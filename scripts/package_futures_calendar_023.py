"""Preserve blocked023 collection, synthetic verification and unchanged prior evidence."""
import argparse,base64,csv,hashlib,html,json,shutil,sys,zipfile
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tradingagents.binance_assets_021 import sha

def write(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')
def archive(folder,target):
    entries=[]
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(folder.rglob('*')):
            if p.is_file():
                raw=p.read_bytes();name=p.relative_to(folder).as_posix();i=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));i.compress_type=zipfile.ZIP_DEFLATED;z.writestr(i,raw)
                entries.append({'path':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    with zipfile.ZipFile(target) as z:
        if z.testzip():raise ValueError('Archive CRC')
        for e in entries:
            if hashlib.sha256(z.read(e['path'])).hexdigest()!=e['sha256']:raise ValueError('Archive member changed')
    return entries

def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);a=p.parse_args();w=a.workspace;o=ROOT/'research/experiments/023';raw=w/'futures-023-extension'
    partial=json.loads((o/'partial-data-audit.json').read_bytes());old=json.loads((ROOT/'research/experiments/022/summary.json').read_bytes())
    coll=json.loads((o/'collection-freeze.json').read_bytes())
    for group in ('source_hashes','preserved_files'):
        for name,digest in coll[group].items():
            if sha(ROOT/name)!=digest:raise ValueError('Prior file changed: '+name)
    testlog=(w/'research023-engine-tests-attempt1.log').read_text()
    if '23 passed' not in testlog or 'FAILED' in testlog:raise ValueError('Synthetic preflight not passing')
    shutil.copyfile(w/'research023-engine-tests-attempt1.log',o/'adapter-preflight-attempt1.log')
    pre={'software_tests_passed_this_invocation':73,'collection_suite':50,'adapter_suite':23,'new_tests':35,'synthetic_matrix_executions':179,'new_historical_executions':0,'initial_test_failures':[],'commands':['python -m pytest --noconftest -q tests/test_binance_archive.py tests/test_futures_assets_021.py tests/test_futures_extension_023.py','python -m pytest --noconftest -q tests/test_futures_calendar_023.py'],'stdout_sha256':sha(o/'adapter-preflight-attempt1.log')}
    write(o/'adapter-preflight.json',pre)
    # Preserve every downloaded archive/checksum/receipt and every failed request.
    datadir=o/'data';datadir.mkdir(exist_ok=True);datazip=w/'Futures_023_Partial_Data.zip';members=archive(raw,datazip)
    encoded=base64.b64encode(datazip.read_bytes()).decode();(datadir/'partial-public-archives.zip.b64').write_text(encoded+'\n')
    write(datadir/'manifest.json',{'encoding':'base64 of ZIP','archive_sha256':sha(datazip),'archive_bytes':datazip.stat().st_size,'files':members,'status':'INCOMPLETE_NOT_REPLAY_ELIGIBLE','new_strategy_simulations':0})
    sourcefiles=['tradingagents/futures_calendar_023.py','scripts/run_futures_calendar_023.py','scripts/audit_partial_futures_023.py','scripts/package_futures_calendar_023.py','tests/test_futures_calendar_023.py','tradingagents/futures_replay_019.py','tradingagents/sol_funding_022.py','scripts/run_futures_assets_021.py','scripts/run_funding_futures_019.py','scripts/run_nr7_futures_020.py','scripts/run_binance_replay_017.py','tradingagents/funding_signal_019.py','tradingagents/nr7_futures_020.py']
    # Only files actually imported by current frozen engine are included; fail on missing names.
    sourcefiles=[x for x in sourcefiles if (ROOT/x).exists()]
    freeze={'experiment':'023','phase':'SYNTHETIC_ADAPTER_ONLY_NO_ELIGIBLE_REAL_INPUTS','collection_remote_commit':'771004075dbc50c9d631f91c08d076942e907dad','collection_freeze_sha256':sha(o/'collection-freeze.json'),'source_hashes':{p:sha(ROOT/p) for p in sourcefiles},'preserved_files':coll['preserved_files'],'preflight_sha256':sha(o/'adapter-preflight.json'),'runtime':{'numpy':'2.3.5','pandas':'2.2.3','python-dotenv':'1.2.4','pytest':'9.1.1'},'eligible_inputs':{},'real_pnl_allowed':False,'next_required_checkpoint':'Publish engine-freeze.json with complete independently pinned old/new inputs before training; then publish training selection hash before evaluation. Do not create an engine input freeze from partial data.'}
    write(o/'adapter-freeze.json',freeze)
    coverage=[]
    for s,v in partial['assets'].items():
        for kind,count in v['observed_rows'].items():coverage.append({'symbol':s,'series':kind,'observed_rows':count,'expected_rows':v['expected_full_rows'][kind],'coverage_pct':100*v['coverage_fraction'][kind],'eligible':False})
    with (o/'coverage.csv').open('w',newline='') as f:
        q=csv.DictWriter(f,fieldnames=list(coverage[0]));q.writeheader();q.writerows(coverage)
    refs={}
    for s,v in old['assets'].items():
        c=v['candidates']['obv_breakout__fixed50'];refs[s]={'candidate':'obv_breakout__fixed50','origin':'REUSED_021_022_NOT_NEW023','worst12':c['worst12']['metrics'],'max_drawdown_scenario':c['max_drawdown_scenario']['metrics'],'base_signal_exits':c['base']['signal_exits'],'full_pass':c['full_pass'],'main_selection':v['main_selection'],'old_wfa':v['wfa']}
    summary={'experiment':'023','status':'BLOCKED_DATA_NO_STRATEGY_OUTCOMES','collection_commit':'771004075dbc50c9d631f91c08d076942e907dad','collection_freeze_sha256':sha(o/'collection-freeze.json'),'adapter_freeze_sha256':sha(o/'adapter-freeze.json'),'data_archive_sha256':sha(datazip),'data_eligibility_pass_fail':[0,3],'planned_asset_candidate_pairs_not_evaluated':18,'planned_eval_scenarios_not_evaluated':216,'new_strategy_passes':None,'new_strategy_failures':None,'new_unique_variants':0,'total_unique_variants':50,'total_families':25,'new_historical_executions':0,'new_integrity_replays':0,'cumulative_design_executions':7902,'cumulative_known_executions':7909,'verified_archive_checksums':66,'public_GET_attempts':135,'failed_GETs':3,'retries':0,'missing_mark_UTC_date':'2026-06-29','coverage':coverage,'software':pre,'preserved_prior_files':len(coll['preserved_files']),'old_reference_OBV':refs,'old_all18_full_pass_fail':[0,18],'old_all216_scenario_pass_fail':[0,216],'old_all36_WFA_pass_fail':[0,36],'old_positive_all12_pairs':10,'prospective_evidence_days':0,'classification':'Incomplete new Binance history. Prior positive metrics are descriptive reused2024–2025 evidence, not new023, Bybit results or prospective confirmation.'}
    write(o/'summary.json',summary)
    write(o/'verification.json',{'data_zip_crc_pass':True,'data_archive_member_hashes_verified':len(members),'source_hashes_verified':len(freeze['source_hashes']),'prior_files_verified':len(coll['preserved_files']),'old022_summary_sha256':sha(ROOT/'research/experiments/022/summary.json'),'collection_freeze_unchanged':True,'runtime_pins_unchanged':True,'tests':pre,'historical_results':0})
    regpath=ROOT/'research/registry.json';reg=json.loads(regpath.read_bytes());now=datetime.now(timezone.utc).isoformat()
    if not any(x['id']=='023' for x in reg['completed']):reg['completed'].append({'id':'023','status':'COLLECTION_ATTEMPT_CLOSED_DATA_BLOCKED','completed_utc':now,'protocol':'docs/FUTURES_CALENDAR_023.json','report':'docs/FUTURES_CALENDAR_023_RESULTS.md','results':'research/experiments/023','preregistration_commit':summary['collection_commit'],'freeze_sha256':summary['collection_freeze_sha256'],'adapter_freeze_sha256':summary['adapter_freeze_sha256'],'new_variants':0,'new_historical_simulations':0,'data_eligibility_pass_fail':[0,3],'strategy_pass_fail':None,'unassessed_asset_candidate_pairs':18,'unassessed_eval_scenarios':216,'verified_archives':66,'software_tests':73,'new_tests':35,'attempts':[{'id':'023-initial','status':'ALL_THREE_ACCESS_BLOCKED_AUGUST_MARK_403','new_simulations':0,'retry_count':0}],'conclusion':'66 official archives verified; perasset5832trade/5064mark/636funding. June29markday absent. Augustmark request403 stops eachasset. No shortenedwindow, pricefills, outcomes or retuning. Adapter23synthetictests passes; realinputfreeze absent. All previousresults preserved.'})
    reg['active_experiment']=None;reg['updated_utc']=now
    reg['queue']=[x for x in reg['queue'] if x['id']!='023']
    reg['queue'].append({'id':'023','status':'BLOCKED_PENDING_COMPLETE_INPUTS_NO_AUTOMATIC_RETRY','next':'Preserve initial023; resume only with a distinct permitted input acquisition and exact missing source hashes, no access bypass or shortened dates. Completeinputfreeze and selection checkpoint required.013prioritized if unifiedBybitpacket arrives.'})
    reg['next_action']='Prioritize audit of unifiedBybitpacket for013.023 is data-blocked and cannot yieldPnL. While awaiting inputs, a future bounded distinct causal futures family may use unchanged fullyvalidated2022–2025 BTC/SOL/XRP histories under a separatelypublished024 freeze; no automatic rerun of023 or oldvariants.'
    reg['count_note']='7902 design scenario executions +7 prior integrity replays=7909 known executions;50 uniquevariants/25families.023 adds0 historicalexecutions,0variants;179 synthetic software executions do not count as research evidence.'
    reg['cumulative_known_design_runs_through_023']=7902;reg['additional_integrity_replays_023']=0;reg['cumulative_known_executions_through_023']=7909;write(regpath,reg)
    lines=['# Έρευνα 023 — κριτήρια και πραγματικό εμπόδιο δεδομένων','',
    '**Δεν προέκυψε νέα επιβεβαιωμένη κερδοφόρα στρατηγική.** Η προσπάθεια νέων ημερομηνιών έκλεισε με ελλιπή δεδομένα για BTC, SOL και XRP. Μηδέν νέες ιστορικές προσομοιώσεις, μηδέν νέες παραλλαγές. Παραμένουν 50 εκδοχές /25 οικογένειες και7.909 γνωστές εκτελέσεις (7.902σχέδια+7παλιές επαναλήψεις ακεραιότητας).','',
    'Προκαταχώριση πριν τη συλλογή: '+summary['collection_commit']+'. Στόχος01/01/2026–30/09/2026, εκπαίδευση2023–2025, ωριαίες τιμές/mark και πραγματικό funding. Οι έξι στρατηγικές θα έμεναν αμετάβλητες. Δεν υπολογίστηκε ούτε εκπαίδευση ούτε αξιολόγηση λόγω αποκλεισμού δεδομένων.','',
    'Στις17/10/2026 επαληθεύτηκαν66 επίσημα αρχεία με τα δημοσιευμέναSHA256 καιCRC. Η πρόσβαση στο mark Αυγούστου2026 επέστρεψε403 και για τα3νομίσματα. Κάθε συλλέκτης σταμάτησε αμέσως, χωρίς επανάληψη/παράκαμψη. Συνολικά135GET προσπάθειες,3αποτυχημένες.','',
    '|Κάθε νόμισμα|Τιμές|Mark|Funding|','|---|---:|---:|---:|','|BTC, SOL, XRP|5.832/6.552 ώρες (89,01%)|5.064/6.552 ώρες (77,29%)|636/819 γεγονότα (77,66%)|','',
    'Τα διαθέσιμα trade αρχεία καλύπτουνΙανουάριο–Αύγουστο, mark/fundingΙανουάριο–Ιούλιο. Λείπει επιπλέον όλη η29/06/2026 από κάθε mark σειρά. Δεν έγινε συμπλήρωση τιμών ούτε περικοπή του παραθύρου. Επιτυχίες πληρότητας0/3, αποτυχίες3/3·18συνδυασμοί/216σενάρια ΔΕΝ αξιολογήθηκαν, επομένως δεν χαρακτηρίζονται στρατηγικές αποτυχίες.','',
    '## Τα κριτήρια που καθορίστηκαν πριν από τα αποτελέσματα','',
    '1. Καθαρό αποτέλεσμα **>0** μετά από προμήθειες, ολίσθηση, πραγματικό funding όταν κρατείται θέση και120USDT/έτος λειτουργικά. Υποθετικό ανεξάρτητο κεφάλαιο10.000USDT, long ή μετρητά, είσοδος έως50% έκθεση.',
    '2. Θετικό σε **όλα τα12σενάρια**: δύο κόστη × καθυστέρηση0/1/2ημερών × δύο αποτιμήσεις funding. Ανά πλευρά βάση5,5bpsfee+2bpsslippage=0,075%, stress10+10bps=0,20%. Η δυσμενής αποτίμηση funding μετακινεί την mark κατά5bps· δεν αντικαθιστά τα πραγματικά rates.',
    '3. Μέγιστη δειγματοληπτική πτώση **≤35%** και τουλάχιστον **20έξοδοι σήματος/χρονικού ορίου** σε κάθε σενάριο. Τα τελικά αναγκαστικά κλεισίματα δεν μετρούν. Τα20 είναι ελάχιστο λειτουργικό δείγμα, όχι στατιστική απόδειξη·35% είναι φίλτρο έρευνας, όχι επιβεβαιωμένη προσωπική ανοχή κινδύνου.',
    '4. Επιλογή μόνο από προηγούμενα έτη. Εκπαίδευση απαιτεί θετικό αποτέλεσμα και στα δύο κόστη,≤35%πτώση,≥10εξόδους. Κατάταξη stressετησιοποιημένης απόδοσης/max(stressπτώση,1%), ισοβαθμία μεID, διαφορετικάcash. Η επιλογή δημοσιεύεται πριν τον έλεγχο επόμενης περιόδου.',
    '5. Πλήρη επαληθευμένα ιστορικά δεδομένα και ανεξάρτητη λογιστική συμφωνία. Σύγκριση με αδρανήcash και50%διακράτηση με ρητά κόστη. Όλες οι αποτυχίες/παραλλαγές διατηρούνται, χωρίς ρύθμιση μετά τα αποτελέσματα. Οι έλεγχοι πολλαπλών συγκρίσεων δεν διορθώνουν πλήρως την παλιά αναζήτηση50εκδοχών.',
    '6. Για μεταγενέστερο ορόσημο παρακολούθησης: **≥180ημερολογιακές ημέρες ΚΑΙ≥20ολοκληρωμένες εξόδους**, θετικό καθαρό αποτέλεσμα και στα δύο κόστη,πτώση≤35%,κάλυψη≥95%,κανένα εκκρεμές/σφάλμα ακεραιότητας. Δεν αποτελεί εγγύηση ή άδεια πραγματικών συναλλαγών.','',
    '## Θετικά ευρήματα που διατηρούνται — παλιό διάστημα2024–2025','',
    'Η ίδια OBVfixed50 παρέμεινε θετική και στα12σενάρια και στα3νομίσματα. Πρόκειται για ήδη δημοσιευμένα021/022 αποτελέσματα, όχι νέα023 ή μελλοντική επιβεβαίωση. Ποσά σεUSDT από χωριστά10.000USDT.','',
    '|OBV|Χειρότερο καθαρό /12|Μέγιστη ποσοστιαία πτώση και πραγματικό ποσό κορυφής–χαμηλού|Έξοδοι βάσης|','|---|---:|---:|---:|']
    for s,v in refs.items():
        m=v['worst12'];d=v['max_drawdown_scenario'];lines.append(f"|{s}|{float(m['net_return_pct']):+.2f}% /{float(m['net_profit_usdt']):+,.2f}USDT|{float(d['max_drawdown_pct']):.2f}% /{float(d['cash_at_max_pct_drawdown_usdt']):,.2f}USDT|{v['base_signal_exits']}|")
    lines+=['','Στα ίδια παλιά18asset–strategyζεύγη:10θετικά σεόλα12, αλλά0/18πλήρεις επιτυχίες,0/216επιμέρους επιτυχίες και0/36ετήσιες διαδρομές. Η αρχική επιλογή2023ήτανcash και στα3· το2025επιλέχθηκεOBV. Η επιλογή με χρονολογική προεκπαίδευση έχασε:','', '|Παλιά WFA2024–2025|Βάση|Stress|','|---|---:|---:|']
    for s,v in refs.items():
        ms=[v['old_wfa'][k+'_lag0_adverse0']['metrics'] for k in ('venue_assumption','stress_assumption')]
        lines.append('|'+s+'|'+'|'.join(f"{float(m['net_return_pct']):+.2f}% /{float(m['net_profit_usdt']):+,.2f}USDT" for m in ms)+'|')
    lines+=['','Η διαχειριζόμενηcash πληρώνει λειτουργικά, η αδρανήςcashαναφορά όχι. Τα κόστη λογαριασμού, margin, ιστορικά φίλτρα, βιβλία εντολών/fills δεν είναι επιβεβαιωμένα. Δεν υπάρχει μοντέλο εκκαθάρισης με μόχλευση. Οι πτώσεις είναι δειγματοληπτικές· άγνωστη η σειρά υψηλού/χαμηλού μέσα στην ώρα. Πρόκειται γιαBinanceUSD-M, όχιBybit.','',
    '73έλεγχοι λογισμικού πέρασαν (35νέοι). Η νέα γέφυρα ημερομηνιών και η επαναχρησιμοποίηση του προεπιλεγμένου2026σεναρίου ελέγχθηκαν σε179συνθετικές εκτελέσεις, που δεν μετρούν ως ιστορική έρευνα. Ο κώδικας είναι παγωμένος μόνο για συνθετικό έλεγχο· δεν υπάρχει engine-freeze.jsonμε επιλέξιμα πραγματικά δεδομένα. Δεν επιτρέπεται πραγματικό replay πριν από νέο checkpointεισόδων και μεταγενέστεροselectioncheckpoint.','',
    'Επόμενο χρήσιμο βήμα: προτεραιότητα στο ενιαίοBybitπακέτο όταν φτάσει. Η023μένει αποκλεισμένη ώσπου να υπάρχουν νόμιμα πλήρη στοιχεία. Στο μεταξύ επόμενη χωριστά προκαταχωρισμένη παρτίδα μπορεί να εξετάσει μία διαφορετική αιτιώδη οικογένεια futures στα ήδη πλήρη, αμετάβλητα2022–2025BTC/SOL/XRP, με δύο τρόπους μεγέθους θέσης και όλα τα ίδια φίλτρα. Δεν ξεκίνησε άλλη οικογένεια σε αυτή την προσπάθεια.','',
    'Ακριβή αρχεία: research/experiments/023/{summary,partial-data-audit,verification,adapter-freeze,artifact_receipts}.json καιcoverage.csv. Πλήρες μερικό inputZIP: data/partial-public-archives.zip.b64, SHA256 '+sha(datazip)+'.','',
    'Πρωτογενής τεκμηρίωση αρχείων/checksums: https://github.com/binance/binance-public-data .']
    (ROOT/'docs/FUTURES_CALENDAR_023_RESULTS.md').write_text('\n'.join(lines)+'\n')
    # Standalone readable report without optional renderer dependencies.
    body=[];in_table=False
    for line in lines:
        if line.startswith('|'):
            if set(line.replace('|','').replace(':','').replace('-',''))==set():continue
            if not in_table:body.append('<div class="scroll"><table>');in_table=True
            body.append('<tr>'+''.join('<td>'+html.escape(c)+'</td>' for c in line.strip('|').split('|'))+'</tr>');continue
        if in_table:body.append('</table></div>');in_table=False
        if line.startswith('## '):body.append('<h2>'+html.escape(line[3:])+'</h2>')
        elif line.startswith('# '):body.append('<h1>'+html.escape(line[2:])+'</h1>')
        elif line:body.append('<p>'+html.escape(line).replace('**','')+'</p>')
    if in_table:body.append('</table></div>')
    report=w/'Futures_023_Criteria_EL.html';report.write_text('<!doctype html><html lang="el"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Έρευνα023 — Κριτήρια</title><style>body{font:17px/1.6 system-ui;max-width:1150px;margin:40px auto;padding:0 22px;color:#192b39}h1,h2{color:#173c65}table{border-collapse:collapse;width:100%;font-size:15px}td{border:1px solid #c9d5e0;padding:10px}tr:first-child{background:#e8eff6;font-weight:bold}.scroll{overflow:auto}p{margin:17px 0}</style>'+''.join(body)+'</html>')
    print(json.dumps({'summary':str(o/'summary.json'),'report':str(report),'raw_archive_bytes':datazip.stat().st_size,'encoded_bytes':len(encoded),'adapter_freeze_sha256':summary['adapter_freeze_sha256'],'preserved_files':len(coll['preserved_files'])}))
if __name__=='__main__':main()
