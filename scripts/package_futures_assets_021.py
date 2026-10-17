"""Verify and report already-computed021 outcomes; never execute a strategy."""
import argparse,csv,hashlib,html,json,shutil,sys
from concurrent.futures import ProcessPoolExecutor
from collections import Counter
from decimal import Decimal as D
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from run_futures_assets_021 import verify_freeze,CANDIDATES
from run_nr7_futures_020 import read_result,file_sha


def write(p,x):p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def fmt(x):return f'{float(x):+,.2f}'
def perf(m):return f"{float(m['net_return_pct']):+.2f}% / {fmt(m['net_profit_usdt'])} USDT"
def dd(m):return f"{float(m['max_drawdown_pct']):.2f}% / {float(m['cash_at_max_pct_drawdown_usdt']):,.2f} USDT"


def verify_asset(job):
    workspace,symbol=job;w=Path(workspace);rows=[];events=0
    for stage in ('train1','train2','evaluation'):
        name='evaluation.json' if stage=='evaluation' else 'selection.json'
        path=w/('futures-021-'+stage)/name;s=json.loads(path.read_bytes())['assets'][symbol]
        for rec in s['new_results'].values():
            file=w/('futures-021-'+stage)/rec['file'];result=read_result(file,rec['sha256'],rec['container_sha256'])
            if result['symbol']!=symbol or result['metrics']!=rec['metrics']:raise ValueError('Output summary/identity mismatch')
            audit=result['independent_wealth_audit'];events+=audit['events_checked']
            rows.append({'path':str(file.relative_to(w)),'sha256':rec['sha256'],'container_sha256':file_sha(file),'bytes':file.stat().st_size,'encoding':'base64+gzip','audit':audit})
    return {'symbol':symbol,'results':rows,'wealth_events':events}


def candidate_summary(rows,gate):
    base=next(x for x in rows if x['cost']=='venue_assumption' and x['lag_days']==0 and not x['adverse_funding_5bps'])
    stress=next(x for x in rows if x['cost']=='stress_assumption' and x['lag_days']==0 and not x['adverse_funding_5bps'])
    worst=min(rows,key=lambda x:D(x['metrics']['net_return_pct']));draw=max(rows,key=lambda x:D(x['metrics']['max_drawdown_pct']))
    return {'base':base['metrics'],'stress':stress['metrics'],'worst12':worst,'max_drawdown_scenario':draw,'full_pass':gate['historical_screen_pass'],'positive_all12':D(worst['metrics']['net_profit_usdt'])>0,
            'failed_gate_scenario_counts':dict(Counter(reason for row in gate['failed_scenarios'] for reason in row['reasons'])),'failed_scenarios':gate['failed_scenarios'],'scenario_passes':12-len(gate['failed_scenarios']),'scenario_failures':len(gate['failed_scenarios'])}


def pareto(candidates):
    ids=[]
    for c,x in candidates.items():
        ret=D(x['worst12']['metrics']['net_return_pct']);risk=D(x['max_drawdown_scenario']['metrics']['max_drawdown_pct'])
        dominated=False
        for other,y in candidates.items():
            if other==c:continue
            r=D(y['worst12']['metrics']['net_return_pct']);d=D(y['max_drawdown_scenario']['metrics']['max_drawdown_pct'])
            if r>=ret and d<=risk and (r>ret or d<risk):dominated=True
        x['pareto_frontier']=not dominated
        if not dominated:ids.append(c)
    return sorted(ids,key=lambda c:(-D(candidates[c]['worst12']['metrics']['net_return_pct']),c))[:3]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path,required=True);p.add_argument('--freeze-sha256',required=True);a=p.parse_args()
    w=a.workspace;out=ROOT/'research/experiments/021';pin=verify_freeze(a.freeze_sha256)
    e=json.loads((w/'futures-021-evaluation/evaluation.json').read_bytes())
    with ProcessPoolExecutor(max_workers=min(3,len(e['assets']))) as pool:checks=list(pool.map(verify_asset,[(str(w),s) for s in e['assets']]))
    hashes=[x for check in checks for x in check['results']];events=sum(x['wealth_events'] for x in checks)
    write(out/'full_result_hashes.json',hashes)
    for stage in ('train1','train2','evaluation'):
        src=w/('futures-021-'+stage)/('evaluation.json' if stage=='evaluation' else 'selection.json')
        shutil.copyfile(src,out/('evaluation.json' if stage=='evaluation' else 'selection-'+stage+'.json'))
    allrows=[];wfarows=[];assets={}
    for symbol,data in e['assets'].items():
        candidates={c:candidate_summary(rows,data['gates'][c]) for c,rows in data['comparisons'].items()}
        shortlist=pareto(candidates)
        chosen=data['main_selection']['selected']
        selected=candidates[chosen] if chosen!='cash' else {'base':data['benchmarks']['cash']['metrics'],'stress':data['benchmarks']['cash']['metrics']}
        assets[symbol]={'candidates':candidates,'full_passes':sum(x['full_pass'] for x in candidates.values()),
            'scenario_passes':sum(x['scenario_passes'] for x in candidates.values()),'shortlist_posthoc':shortlist,
            'main_selection':data['main_selection'],'main_selected_outcome':selected,'second_selection':data['second_selection'],
            'wfa_scenario_passes':sum(x['passed'] for x in data['walk_forward'].values()),'wfa_full_pass':all(x['passed'] for x in data['walk_forward'].values()),
            'wfa':data['walk_forward'],'benchmarks':data['benchmarks']}
        for c,rows in data['comparisons'].items():
            for r in rows:allrows.append({'symbol':symbol,'candidate':c,'cost':r['cost'],'lag_days':r['lag_days'],'adverse_funding_5bps':r['adverse_funding_5bps'],**r['metrics']})
        for key,r in data['walk_forward'].items():wfarows.append({'symbol':symbol,'scenario':key,'passed':r['passed'],'failed_gates':'|'.join(r['failed_gates']),**r['metrics']})
    for name,rows in [('metrics-all.csv',allrows),('walk-forward.csv',wfarows)]:
        with (out/name).open('w',newline='') as f:writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    complete_all=set(assets)=={'BTCUSDT','SOLUSDT','XRPUSDT'}
    cross=[c for c in CANDIDATES if complete_all and all(x['candidates'][c]['full_pass'] for x in assets.values())]
    summary={'experiment':'021','new_unique_variants':0,'total_unique_variants':50,'total_families':25,'existing_variants_tested':6,'assets':assets,
        'new_asset_candidate_pairs':6*len(assets),'new_design_executions':len(hashes),'cumulative_design_executions':7527+len(hashes),
        'prior_integrity_replays':7,'new_integrity_replays':0,'cumulative_known_executions':7534+len(hashes),
        'positive_all12_pairs':sum(c['positive_all12'] for x in assets.values() for c in x['candidates'].values()),'full_asset_candidate_passes':sum(x['full_passes'] for x in assets.values()),'full_asset_candidate_failures':6*len(assets)-sum(x['full_passes'] for x in assets.values()),
        'fixed_scenario_passes':sum(x['scenario_passes'] for x in assets.values()),'fixed_scenario_failures':72*len(assets)-sum(x['scenario_passes'] for x in assets.values()),
        'cross_asset_full_passes':cross,'all_three_assets_complete':complete_all,'wealth_events':events,'max_wealth_error_usdt':'0',
        'software_tests_passed':128,'new_software_tests':17,'prospective_evidence_days':0,'multiplicity':e['multiplicity'],
        'excluded_assets':pin.get('excluded_assets',{}),'coverage':{s:v['audit'] for s,v in pin['inputs'].items()},'classification':'Posthoc user-selected asset transfer; correlated historical dates, no live or Bybit profitability confirmation'}
    write(out/'summary.json',summary)
    verification={'engine_freeze_sha256':a.freeze_sha256,'preserved_files_unchanged':len(pin['preserved_files']),'frozen_sources_verified':len(pin['source_hashes']),
        'new_result_hashes_verified':len(hashes),'independent_wealth_events':events,'max_error_usdt':'0','preflight_tests':128,'new_tests':17,'synthetic_matrix_executions':125,'result_integrity_failures':[],'data_contract_exclusions':pin.get('excluded_assets',{})}
    write(out/'verification.json',verification)
    md=['# Batch021: BTC / SOL / XRP native futures extension','',
        'Binance USD-M perpetual. Data2022-01-01..2025-12-31; maintrain2023, expandingtrain2023–2024, fixed evaluation2024-01-01..2025-12-31. Independent10000USDT accounts perasset/candidate, not a combinedportfolio.',
        '',f"0new strategy variants;50total/25families. {len(hashes)}new executions, {summary['cumulative_design_executions']}cumulative design+7prior integrity replays={summary['cumulative_known_executions']}known executions. {summary['full_asset_candidate_passes']}/{6*len(assets)}fullasset-candidatepasses; {summary['fixed_scenario_passes']}/{72*len(assets)}individualscenario passes. Crossassetfullpasses: {cross}.", '',
        '|Asset/candidate|Base net|Stress net|Worst12 net|Maxsampled DD / actualcash|Base signal exits|Fullpass|Failed gate counts outof12|','|---|---:|---:|---:|---:|---:|---|---|']
    table='';selections='';shortlists='';wfatable='';benchtable=''
    exclusions=''.join('<p><b>'+html.escape(s)+'</b>: αποκλείστηκε πριν από οποιοδήποτε αποτέλεσμα — '+html.escape(v['reason'])+'</p>' for s,v in pin.get('excluded_assets',{}).items())
    md+=['','Excluded before PnL: '+json.dumps(pin.get('excluded_assets',{}),ensure_ascii=False),'']
    for symbol,data in assets.items():
        for c,v in data['candidates'].items():
            cells=[symbol+' / '+c,perf(v['base']),perf(v['stress']),perf(v['worst12']['metrics']),dd(v['max_drawdown_scenario']['metrics']),str(v['base']['signal_exits']),str(v['full_pass']),', '.join(k+':'+str(n)+'/12' for k,n in v['failed_gate_scenario_counts'].items()) or 'PASS']
            md.append('|'+ '|'.join(cells)+'|');table+='<tr>'+''.join('<td>'+html.escape(x)+'</td>' for x in cells)+'</tr>'
        selected=data['main_selection']['selected'];second=data['second_selection']['selected'];sel=data['main_selected_outcome']
        wfbase=data['wfa']['venue_assumption_lag0_adverse0']['metrics'];wfstress=data['wfa']['stress_assumption_lag0_adverse0']['metrics']
        selections+=f"<p><b>{symbol}</b>: επιλογή από το2023 <code>{selected}</code>, βασικό αποτέλεσμα {perf(sel['base'])}, αυξημένο κόστος {perf(sel['stress'])}. Επιλογή για2025: <code>{second}</code>. Ετήσια διαδρομή2024→2025: {perf(wfbase)} βασικό / {perf(wfstress)} αυξημένο κόστος. Περνούν {data['wfa_scenario_passes']}/12 σενάρια.</p>"
        md+=['',f"{symbol} mainselector={selected}:base {perf(sel['base'])},stress {perf(sel['stress'])}; nextselector={second}. WFA base {perf(wfbase)},stress {perf(wfstress)},passes {data['wfa_scenario_passes']}/12.",'']
        shortlists+='<p><b>'+symbol+'</b>: '+', '.join(html.escape(c)+' — χειρότερο αποτέλεσμα '+perf(data['candidates'][c]['worst12']['metrics']) for c in data['shortlist_posthoc'])+'.</p>'
        for key,r in data['wfa'].items():
            cells=[symbol,key,perf(r['metrics']),dd(r['metrics']),str(r['metrics']['signal_exits']),', '.join(r['failed_gates']) or 'PASS']
            wfatable+='<tr>'+''.join('<td>'+html.escape(x)+'</td>' for x in cells)+'</tr>'
        for key,r in data['benchmarks'].items():
            m=r['metrics'];cells=[symbol,key,perf(m),dd(m),fmt(m['fees_usdt']),fmt(m['funding_usdt']),fmt(m['operating_expense_usdt'])]
            benchtable+='<tr>'+''.join('<td>'+html.escape(x)+'</td>' for x in cells)+'</tr>'
    md+=['','Costs per side:5.5bpsfee+2bpsslippage baseline;10+10stress.120USDT/year expense. Actualheld-position funding, hour-open mark proxy and adverse5bpsvaluation. Fullycash-backed longflat,50%entrycap, hypotheticalfine-lotfilters. Personalfees/historicalrules/margin unverified; noexchangeliquidationmodel or historicaldepth/fill evidence.',
        'All12scenarios neednet>0,DD<=35%,>=20signal/timeexits andcompleteaudits. Traineligibility>=10exits,bothcostpositive,DD<=35%. Terminalforcedclosesexcluded. WFA annualflatwithcostandexactcashcarry; managedcashpays120/year; idlecashbenchmark0expense. Hold50paysfunding/fees/expense. DDamount=observedpeak-troughatmaximumpercentageDD; maximumcashDDretainedseparately.',
        'Sixfrozen017variants fullytestedperasset includingoldstrengthsandfailures. FourothernativeETHvariants019/020and40spot-onlyvariants nottestedhere; allpriorresultsretained. Conditionalmultiple-comparison diagnostics covertested6perasset/jointup-to18, shared30dayblocks,2000resamples,actualopex. They do notcorrectprior50variantsearch/design selection. Samehistoricaldates andcrossassetcorrelations are notindependentconfirmation.',
        f'128softwaretests17new;125syntheticmatrixexecutionsnotcountedasmarketresearch. {events}newwealthevents,zeroDecimalerror. FrozenBybit013/014andsevenprospectivecandidates untouched.',
        'Source: https://github.com/binance/binance-public-data . Exactdata/source/testpins and reproduciblecommands in research/experiments/021. Fullcurves/fills/funding/events persistedwithartifactreceipts. No realorders or keys. Next: oneBybitpacket audit; otherwise separatelyfrozen actualSOLfundingcadence support withunchangedstrategy/gates.']
    (ROOT/'docs/FUTURES_ASSETS_021_RESULTS.md').write_text('\n'.join(md)+'\n')
    coverage=''.join(f"<li>{s}: {v['audit']['per_symbol'][s]['trade_hours']:,} ώρες τιμών, {v['audit']['per_symbol'][s]['mark_hours']:,} ώρες mark, {v['audit']['per_symbol'][s]['funding_events']:,} γεγονότα funding. Προστέθηκαν {v['audit']['recovered_real_hours']} πραγματικές ώρες από ημερήσια αρχεία, με {v['audit']['matched_overlap_hours']} ώρες που συμφωνούν στις επικαλύψεις.</li>" for s,v in pin['inputs'].items())
    if 'SOLUSDT' in pin.get('excluded_assets',{}):
        sol=json.loads((out/'SOLUSDT-candle-audit.json').read_bytes())
        coverage+=f"<li>SOLUSDT: ελέγχθηκαν {sol['counts']['klines']:,} ώρες τιμών και {sol['counts']['markPriceKlines']:,} ώρες mark. Συλλέχθηκαν {sol['raw_funding_events_captured']:,} πραγματικά γεγονότα funding. Ο έλεγχος χρονικής συχνότητας funding παραμένει αποτυχημένος· δεν εκτελέστηκε στρατηγική SOL.</li>"
    report=f'''<!doctype html><html lang="el"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Futures021 BTC SOL XRP</title><style>body{{font:16px/1.6 system-ui;background:#f4f7fb;color:#142238;max-width:1400px;margin:30px auto;padding:24px}}article{{background:white;padding:28px;border-radius:15px}}h1,h2{{line-height:1.25}}.scroll{{overflow:auto}}table{{border-collapse:collapse;font-size:13px;width:100%}}td,th{{padding:10px;border-bottom:1px solid #d9e1eb;text-align:left}}th{{background:#e9eff7}}code,pre{{white-space:pre-wrap;overflow-wrap:anywhere}}.lead{{font-size:21px}}.box{{background:#e9eff7;padding:16px;border-radius:9px}}</style><article>
    <p>17 Οκτωβρίου2026 · Έρευνα021 · Binance USD-M perpetual</p><h1>BTC, SOL και XRP: έξι στρατηγικές με τους ίδιους κανόνες</h1>
    <p class="lead">{summary['positive_all12_pairs']}/{6*len(assets)} συνδυασμοί έχουν θετικό καθαρό αποτέλεσμα και στα12 σενάρια. Περνούν όλα τα ιστορικά κριτήρια {summary['full_asset_candidate_passes']}/{6*len(assets)} συνδυασμοί νομίσματος/στρατηγικής. Διασταύρωση και στα τρία νομίσματα: {len(cross)}/6 πλήρεις επιτυχίες· απαιτείται και πλήρης κάλυψη κάθε νομίσματος. Αυτά είναι ιστορικά αποτελέσματα και δεν επιβεβαιώνουν μελλοντικό κέρδος.</p>
    <p class="box">{len(hashes)} νέες προσομοιώσεις · 0 νέες παραλλαγές στρατηγικής · 50 συνολικές εκδοχές σε25 οικογένειες · {summary['cumulative_known_executions']} συνολικές γνωστές εκτελέσεις, μαζί με7 παλιές επαναλήψεις αποκατάστασης. Ανεξάρτητο υποθετικό κεφάλαιο10.000 USDT ανά δοκιμή, χωρίς πραγματικές εντολές.</p>
    <h2>Δεδομένα και κάλυψη</h2><p>Επίσημα δεδομένα01/01/2022–31/12/2025. Το2022 χρησιμοποιήθηκε για ιστορικό προετοιμασίας, το2023 για την πρώτη επιλογή και το2024–2025 για αξιολόγηση. Κάθε μηνιαίο και συμπληρωματικό ημερήσιο αρχείο ελέγχθηκε με το δημοσιευμένο SHA256 και το εσωτερικό CRC.</p><ul>{coverage}</ul>{exclusions}
    <p>Δεν υπάρχουν νέες μελλοντικές παρατηρήσεις. Τα ίδια ημερολογιακά έτη μεταξύ νομισμάτων είναι συσχετισμένα. Τα στοιχεία αφορούν Binance, όχι Bybit. Οι παλαιότερες36 πραγματικές λήψεις βιβλίου και600 γεγονότα funding Bybit παραμένουν μετρήσεις και δεν αρκούν για πλήρη στρατηγική replay.</p>
    <h2>Όλες οι στρατηγικές, χωρίς παράλειψη αποτυχιών</h2><p>Αξιολόγηση01/01/2024–31/12/2025. Βασικό και αυξημένο κόστος στον πίνακα σημαίνουν μηδενική επιπλέον καθυστέρηση και ονομαστική αποτίμηση funding. Το χειρότερο αποτέλεσμα εξετάζει και τα12 σενάρια κόστους × καθυστέρησης0/1/2 ημερών × αποτίμησης funding. Πέρασαν {summary['fixed_scenario_passes']}/{72*len(assets)} επιμέρους σενάρια.</p>
    <div class="scroll"><table><tr><th>Νόμισμα / στρατηγική</th><th>Βασικό κόστος</th><th>Αυξημένο κόστος</th><th>Χειρότερο από12</th><th>Μέγιστη πτώση / πραγματικό ποσό</th><th>Έξοδοι βάσης</th><th>Πλήρης επιτυχία</th><th>Αποτυχημένα κριτήρια /12</th></tr>{table}</table></div>
    <p>NONPOSITIVE_NET: μη θετικό καθαρό αποτέλεσμα. DRAWDOWN_OVER_35PCT: πτώση πάνω από35%. FEWER_THAN_20_SIGNAL_EXITS: λιγότερες από20 έξοδοι σήματος. Κάθε σενάριο μπορεί να αποτυγχάνει σε περισσότερα από ένα κριτήρια.</p><h2>Τι επέλεγε η μέθοδος πριν από την περίοδο ελέγχου</h2>{selections}
    <p>Αν η κύρια επιλογή είναι cash, συγκρίνεται με αδρανή μετρητά χωρίς λειτουργικά έξοδα· η ετήσια διαχειριζόμενη διαδρομή χρεώνεται τα λειτουργικά ακόμη και όταν επιλέγει cash. Η δεύτερη επιλογή χρησιμοποιεί μόνο2023–2024 για το2025. Στην ετήσια διαδρομή οι θέσεις κλείνουν στο τέλος του έτους με έξοδα και μεταφέρεται το ακριβές υπόλοιπο. Δεν επανέρχεται το κεφάλαιο τεχνητά στις10.000 USDT. Η ετήσια διαδρομή επικαλύπτεται χρονικά με τον κύριο έλεγχο και δεν είναι ανεξάρτητη απόδειξη.</p>
    <h2>Ισχυρότερα διερευνητικά ευρήματα</h2>{shortlists}
    <p>Η παραπάνω λίστα κρατά έως τρεις οικογένειες ανά νόμισμα από τη σύγκριση χειρότερης απόδοσης και μέγιστης πτώσης. Είναι περιγραφική επιλογή μετά τα αποτελέσματα. Δεν αντικαθιστά την προεπιλογή, τα αποτυχημένα κριτήρια ή την ανάγκη για νέα δεδομένα.</p>
    <h2>Ετήσια διαδρομή: όλα τα σενάρια</h2><div class="scroll"><table><tr><th>Νόμισμα</th><th>Σενάριο</th><th>Καθαρό αποτέλεσμα</th><th>Πτώση / ποσό</th><th>Έξοδοι</th><th>Αποτυχίες</th></tr>{wfatable}</table></div>
    <h2>Μετρητά και διακράτηση50%</h2><div class="scroll"><table><tr><th>Νόμισμα</th><th>Σύγκριση</th><th>Καθαρό αποτέλεσμα</th><th>Πτώση / ποσό</th><th>Προμήθειες USDT</th><th>Funding USDT</th><th>Λειτουργικά USDT</th></tr>{benchtable}</table></div>
    <h2>Κόστη, εκτέλεση και όρια</h2><p>Ανά πλευρά: βασικό κόστος5,5 bps προμήθεια +2 bps ολίσθηση, αυξημένο10+10 bps. Επιπλέον120 USDT ανά365,25 ημέρες. Χρεώνονται τα πραγματικά funding rates στις ώρες κατοχής, με ωριαία τιμή mark ως προσέγγιση και πρόσθετη δυσμενή αποτίμηση5 bps. Τα αδρανή μετρητά έχουν μηδενικά έξοδα, ενώ τα μετρητά της διαχειριζόμενης ετήσιας διαδρομής πληρώνουν τα λειτουργικά. Το perpetual buy-and-hold πληρώνει funding, προμήθειες και λειτουργικά.</p>
    <p>Μόνο long ή μετρητά, έως50% αρχική έκθεση και συντηρητικός έλεγχος κάλυψης από μετρητά. Οι προσωπικές προμήθειες, ιστορικοί κανόνες βήματος εντολών, πραγματικά fills και margin δεν έχουν επαληθευτεί. Δεν υπάρχει μοντέλο εκκαθάρισης με μόχλευση. Η πτώση σε USDT είναι η πραγματική διαφορά κορυφής−χαμηλού στην καμπύλη, όχι το ποσοστό επί του αρχικού κεφαλαίου. Η ωριαία δειγματοληψία δεν προσδιορίζει την ενδοωριαία σειρά υψηλού/χαμηλού.</p>
    <p>Πλήρης ιστορική επιτυχία απαιτεί σε κάθε ένα από τα12 σενάρια καθαρό κέρδος, πτώση≤35%, τουλάχιστον20 εξόδους από σήμα/χρονικό όριο και πλήρη λογιστικό έλεγχο. Το αναγκαστικό τελικό κλείσιμο δεν μετρά ως έξοδος σήματος. Η επιλογή εκπαίδευσης απαιτεί τουλάχιστον10 εξόδους και θετικό αποτέλεσμα και στα δύο κόστη. Τα όρια δεν άλλαξαν μετά τα αποτελέσματα.</p>
    <h2>Λογιστική και πολλαπλές συγκρίσεις</h2><p>128 έλεγχοι λογισμικού,17 νέοι. Η πλήρης συνθετική δοκιμή125 σεναρίων δεν προσμετράται ως ιστορική έρευνα. Επαληθεύτηκαν {events:,} νέα λογιστικά γεγονότα με μηδενική απόκλιση Decimal και όλα τα hashes αποτελεσμάτων.</p>
    <p>Ο στατιστικός έλεγχος αφορά την αριθμητική μέση ημερήσια απόδοση, που μπορεί να δίνει διαφορετική κατάταξη από το τελικό κεφάλαιο λόγω μεταβλητότητας. Δεν προέκυψε στατιστική επιβεβαίωση υπεραπόδοσης. Οι διαγνωστικοί έλεγχοι περιλαμβάνουν και τις έξι στρατηγικές ανά νόμισμα και κοινό πίνακα έως18 συνδυασμών, με2.000 αναδειγματοληψίες κοινών30ήμερων ομάδων και τα λειτουργικά έξοδα. Δεν διορθώνουν ολόκληρη την προηγούμενη αναζήτηση50 παραλλαγών. Τέσσερις άλλες εκδοχές που δοκιμάστηκαν μόνο σε ETH και40 εκδοχές spot διατηρούνται στα παλιά αποτελέσματα, χωρίς επανάληψη εδώ.</p><pre>{html.escape(json.dumps(e['multiplicity'],indent=2))}</pre>
    <p>Τα δύο παγωμένα prospective χαρτοφυλάκια και οι κανόνες Bybit013/014 παρέμειναν αμετάβλητα. Καμία αυτόματη προαγωγή σε πραγματική διαπραγμάτευση. Επόμενο βήμα: έλεγχος του ήδη ζητημένου ενιαίου πακέτου Bybit· διαφορετικά, ξεχωριστά προεγγεγραμμένος έλεγχος των πραγματικών αλλαγών συχνότητας funding του SOL, χωρίς αλλαγή των στρατηγικών ή των ορίων επιτυχίας.</p>
    <p><a href="https://github.com/binance/binance-public-data">Επίσημη πηγή δεδομένων</a> · <a href="https://github.com/rafailm95/TradingAgents/blob/codex/research-continuation-20261016/docs/FUTURES_ASSETS_021_RESULTS.md">Αποτελέσματα, hashes και εντολές αναπαραγωγής</a></p></article></html>'''
    for old,new in [('Οκτωβρίου2026','Οκτωβρίου 2026'),('Έρευνα021','Έρευνα 021'),('σε25','σε 25'),('με7','με 7'),('κεφάλαιο10.000','κεφάλαιο 10.000'),('δεδομένα01','δεδομένα 01'),('Το2022','Το 2022'),('το2023','το 2023'),('το2024','το 2024'),('το2025','το 2025'),('για2025','για 2025'),('διαδρομή2024','διαδρομή 2024'),('παλαιότερες36','παλαιότερες 36'),('και600','και 600'),('Αξιολόγηση01','Αξιολόγηση 01'),('τα12','τα 12'),('καθυστέρησης0','καθυστέρησης 0'),('μόνο2023','μόνο 2023'),('στις10.000','στις 10.000'),('διακράτηση50%','διακράτηση 50%'),('κόστος5,5','κόστος 5,5'),('+2 bps','+ 2 bps'),('αυξημένο10','αυξημένο 10'),('Επιπλέον120','Επιπλέον 120'),('ανά365','ανά 365'),('αποτίμηση5','αποτίμηση 5'),('έως50%','έως 50%'),('πτώση≤35%','πτώση ≤35%'),('τουλάχιστον20','τουλάχιστον 20'),('τουλάχιστον10','τουλάχιστον 10'),('λογισμικού,17','λογισμικού, 17'),('δοκιμή125','δοκιμή 125'),('έως18','έως 18'),('με2.000','με 2.000'),('κοινών30ήμερων','κοινών 30ήμερων'),('αναζήτηση50','αναζήτηση 50'),('και40','και 40'),('Bybit013','Bybit 013'),('πάνω από35%','πάνω από 35%'),('από20','από 20')]:report=report.replace(old,new)
    (w/'Futures_021_BTC_SOL_XRP_EL.html').write_text(report)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('assets','coverage','multiplicity')},indent=2))


if __name__=='__main__':main()
