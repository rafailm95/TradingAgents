"""Export completed Binance017 results without strategy reruns or retuning."""
import argparse,gzip,hashlib,html,json,shutil,zipfile
from datetime import datetime,timezone
from decimal import Decimal as D
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FREEZE_SHA='59291edfbb05990fd32ebd0be369ac22be1c4c75842a2d6e0a85fd5b5797c807'
FREEZE_COMMIT='4c788ab5861dc7bc10fcf5d42f74f80155298ef9'
SELECTION_COMMIT='6e6ee508e1cf244fa80d239ef47cab8b9805b31e'
SELECTION_SHA='5a60dfc9c11d3cb286adea86a62533be2231dbcf314598f9560791b763012895'
LABELS={'sma200_band__vol15_cap50':'SMA200 · θέση βάσει μεταβλητότητας','regression_trend__fixed50':'Γραμμική τάση · 50%','keltner_breakout__fixed50':'Διάσπαση Keltner · 50%','obv_breakout__fixed50':'Διάσπαση OBV · 50%','aroon_trend__fixed50':'Τάση Aroon · 50%','cci_reversion__fixed50':'Επαναφορά CCI · 50%'}
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def n(v):return f'{D(v):+,.2f}'
def net(m):return n(m['net_return_pct'])+'% / '+n(m['net_profit_usdt'])+' USDT'
def dd(m):return f"{D(m['max_drawdown_pct']):.2f}% / {D(m['cash_at_max_pct_drawdown_usdt']):,.2f} USDT"
def table(head,rows):return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+html.escape(x)+'</th>' for x in head)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'
def main(base):
    train=base/'binance-017-training';evaluation=base/'binance-017-evaluation';repo=ROOT/'research/experiments/017'
    f=read(repo/'freeze.json');assert sha(repo/'freeze.json')==FREEZE_SHA
    for group in ('source_hashes','preserved_files'):
        for p,h in f[group].items():assert sha(ROOT/p)==h,p
    rawroot=base/'binance-017-accepted'
    rawmanifest=read(rawroot/'manifest.json')
    assert sha(rawroot/'manifest.json')=='23268b1511dcc6b0ef877ae0ff493d4ad76d607f3d94c4a44b88f32cc16f55e4'
    for item in rawmanifest['files']+rawmanifest.get('supplemental_daily',[]):
        rawpath=rawroot/item['relative']
        assert sha(rawpath)==item['sha256'], str(rawpath)
        assert sha(Path(str(rawpath)+'.CHECKSUM'))==item['checksum_sha256']
    assert sha(base/'binance-017-normalized.json.gz')==f['normalized_input_sha256']
    recovery=read(repo/'result-recovery.json')
    assert recovery['status']=='RECOVERED_BYTE_IDENTICAL'
    assert sha(train/'selection.json')==SELECTION_SHA
    training=read(train/'selection.json');ev=read(evaluation/'evaluation.json');assert ev['selection_sha256']==SELECTION_SHA
    records=[]
    for symbol,cs in training['results'].items():
        for c,costs in cs.items():records += [(train,r) for r in costs.values()]
    for symbol,cs in ev['results'].items():
        for c,rs in cs.items():records += [(evaluation,r) for r in rs]
    for symbol,rs in ev['benchmarks'].items():records += [(evaluation,r) for r in rs.values()]
    assert len(records)==89
    cases=[];hashes={};events=0;maxerror=D(0);complete=0
    for folder,record in records:
        path=folder/record['file'];assert sha(path)==record['sha256']
        with gzip.open(path,'rb') as stream:r=json.load(stream)
        assert r['metrics']==record['metrics'] and r['status']==record['status']
        audit=r['independent_wealth_audit'];assert audit['status']=='PASS';events+=audit['events_checked'];maxerror=max(maxerror,D(audit['max_error_usdt']));complete+=r['status']=='COMPLETE'
        cases.append({'stage':'training' if folder==train else 'evaluation','file':record['file'],'status':r['status'],'symbol':r['symbol'],'candidate':r['candidate'],'benchmark':r['benchmark'],'cost':r['cost'],'lag':r['lag_days'],'adverse_funding':r['adverse_funding_5bps'],'metrics':r['metrics'],'intrahour_excursion':r['intrahour_excursion'],'wealth_audit':audit})
        hashes[folder.name+'/'+path.name]=record['sha256']
    candidates=list(LABELS);rows=[];details=[];summary_rows=[]
    for c in candidates:
        group=[r for r in cases if r['stage']=='evaluation' and r['candidate']==c]
        assert len(group)==12
        nominal=lambda cost:next(r for r in group if r['cost']==cost and r['lag']==0 and not r['adverse_funding'])
        b,t=nominal('venue_assumption'),nominal('stress_assumption');worst=min(group,key=lambda r:D(r['metrics']['net_return_pct']));risk=max(group,key=lambda r:D(r['metrics']['max_drawdown_pct']))
        gate=ev['gates']['ETHUSDT'][c];fails=sorted({reason for s in gate['failed_scenarios'] for reason in s['reasons']})
        row=[LABELS[c],net(b['metrics']),net(t['metrics']),net(worst['metrics']),dd(risk['metrics']),b['metrics']['signal_exits'],'Περνά ιστορικά' if gate['historical_screen_pass'] else ', '.join(fails)]
        rows.append(row);summary_rows.append({'candidate':c,'baseline':b['metrics'],'stress':t['metrics'],'worst':worst,'risk':risk,'gate':gate})
        details.append('<details><summary>'+html.escape(LABELS[c])+' — όλα τα σενάρια</summary>'+table(['Κόστη','Πρόσθετες ημέρες','Δυσμενής αποτίμηση funding','Καθαρό αποτέλεσμα','Πτώση','Κατάσταση'],[[r['cost'],r['lag'],'Ναι' if r['adverse_funding'] else 'Όχι',net(r['metrics']),dd(r['metrics']),r['status']] for r in group])+'</details>')
    all_pass=[c for c in candidates if ev['gates']['ETHUSDT'][c]['historical_screen_pass']]
    best=max(summary_rows,key=lambda r:D(r['baseline']['net_return_pct']))
    selected=training['selection']['ETHUSDT']['selected'];assert selected=='cash'
    cash=next(r for r in cases if r['benchmark']=='cash')
    benchmark=[r for r in cases if r['benchmark']=='buy_hold50' and not r['adverse_funding']]
    trrows=[[LABELS[c],net(training['results']['ETHUSDT'][c]['venue_assumption']['metrics']),net(training['results']['ETHUSDT'][c]['stress_assumption']['metrics']),training['results']['ETHUSDT'][c]['venue_assumption']['metrics']['signal_exits']] for c in candidates]
    costs=[[LABELS[r['candidate']],n(r['baseline']['realized_price_pnl_usdt']),n(r['baseline']['funding_usdt']),n(r['baseline']['fees_usdt']),n(r['baseline']['operating_expense_usdt']),n(r['baseline']['net_profit_usdt'])] for r in summary_rows]
    body='<p class="eyebrow">FUTURES · BINANCE · ΕΡΕΥΝΑ 017</p><h1>Πραγματικό ιστορικό perpetuals, χωριστά από την Bybit</h1>'
    body+=f'<p class="lead">Ολοκληρώθηκαν 89 προσομοιώσεις στο ETHUSDT: 12 εκπαίδευσης, 72 αξιολόγησης και 5 σημεία αναφοράς. {len(all_pass)} από τις έξι στρατηγικές πέρασαν όλα τα ιστορικά κριτήρια στα 12 σενάρια. Η επιλογή που κλειδώθηκε από το 2023 ήταν μετρητά, με αποτέλεσμα αξιολόγησης {net(cash["metrics"])}.</p>'
    body+=f'<div class="callout"><b>Ισχυρότερο βασικό ιστορικό αποτέλεσμα: {html.escape(LABELS[best["candidate"]])}</b><br>{net(best["baseline"])} με βασικά κόστη · {net(best["stress"])} με αυξημένα.<br>Χειρότερο από 12 σενάρια: {net(best["worst"]["metrics"])}. Η παρατήρηση γίνεται μετά τη σύγκριση· δεν ήταν η προεπιλεγμένη στρατηγική.</div>'
    body+='''<p>Περίοδος αξιολόγησης <b>1/1/2024–31/12/2025</b>. Κάθε ανεξάρτητη προσομοίωση ξεκινά με <b>10.000 USDT</b>. Τα ποσοστά αφορούν ολόκληρη την περίοδο και το αρχικό κεφάλαιο, όχι ετήσιο εισόδημα ούτε απόδοση επί μοχλευμένου margin. Όλες οι στρατηγικές αγοράζουν ή μένουν σε μετρητά, με όριο θέσης 50% κατά την είσοδο και χωρίς δανεισμό. Δεν δοκιμάστηκε short σε αυτή τη μεταφορά.</p>
<h2>Πραγματικά δεδομένα και ποιότητα</h2><p>Χρησιμοποιήθηκαν επίσημα Binance Vision δεδομένα futures για το 2022–2025: 35.064 ωριαία candles συναλλαγών, 35.064 mark-price candles και 4.383 πραγματικά funding events. Επαληθεύτηκαν τα δημοσιευμένα SHA256 για 144 μηνιαία και 4 ημερήσια αρχεία. Το 2022 χρησιμοποιείται για προθέρμανση δεικτών, το 2023 για επιλογή και το 2024–2025 για αξιολόγηση.</p>
<p>Τα μηνιαία mark αρχεία έλειπαν για 2/10/2022 και 24/2/2023. Οι 48 ώρες αποκαταστάθηκαν αποκλειστικά από τα αντίστοιχα επίσημα ημερήσια αρχεία. Ελέγχθηκαν επίσης 48 γειτονικές ώρες που συμφωνούν ακριβώς μεταξύ μηνιαίων και ημερήσιων αρχείων. Δεν επινοήθηκαν τιμές ούτε χρηματοδοτήσεις.</p>
<p>Το BTC αποκλείστηκε λόγω μπλοκαρισμένου mark αρχείου Φεβρουαρίου 2023. Το LTC αποκλείστηκε μετά τον εντοπισμό 120 ωρών που λείπουν από μηνιαία αρχεία συναλλαγών του 2022. Τα εμπόδια διατηρήθηκαν και η τελική επιλογή του ETH έγινε πριν από αποδόσεις. Η μελέτη συνεπώς δεν αποδεικνύει ότι το αποτέλεσμα ισχύει σε πολλά νομίσματα.</p>
<h2>Όλες οι στρατηγικές και αποτυχίες</h2><p>Βασικό σενάριο ανά πλευρά: προμήθεια 0,055% και ολίσθηση 0,020%. Αυξημένο: 0,100% και 0,100%. Πρόκειται για σταθερές ερευνητικές υποθέσεις συγκρίσιμες με το προετοιμασμένο τεστ Bybit, όχι για επαληθευμένη προσωπική ή ιστορική προμήθεια Binance. Περιλαμβάνεται πραγματικό ιστορικό funding με μοντελοποιημένη αποτίμηση και λειτουργικό κόστος 120 USDT/έτος.</p>'''
    headers=['Στρατηγική','Βασικά κόστη','Αυξημένα κόστη','Χειρότερο από 12','Μεγαλύτερη πτώση','Έξοδοι βάσης','Κριτήρια']
    body+=table(headers,rows)
    body+='''<p class="small">Τα 12 σενάρια είναι 2 κόστη × 3 καθυστερήσεις σήματος (0/1/2 ημέρες) × 2 αποτιμήσεις funding. Η πτώση είναι πραγματική διαφορά προηγούμενης κορυφής και επόμενου χαμηλού της μοντελοποιημένης καμπύλης· το ποσό αντιστοιχεί στη μέγιστη ποσοστιαία πτώση, όχι σε πολλαπλασιασμό του αρχικού κεφαλαίου. Μετρώνται ωριαία ανοίγματα/κλεισίματα και λογιστικά γεγονότα. Η ακριβής ενδοωριαία διαδρομή παραμένει άγνωστη.</p>
<p class="small">NONPOSITIVE_NET = μη θετικό καθαρό αποτέλεσμα. DRAWDOWN_OVER_35PCT = πτώση πάνω από 35%. FEWER_THAN_20_SIGNAL_EXITS = λιγότερες από 20 ολοκληρωμένες εξόδους στρατηγικής. Η υποχρεωτική τελευταία έξοδος στο τέλος του τεστ δεν μετρά ως τέτοια έξοδος. Το 35% είναι φίλτρο έρευνας, όχι προσωπικά αποδεκτός κίνδυνος.</p>'''
    body+=''.join(details)
    body+='<h2>Γιατί η προεπιλογή έμεινε σε μετρητά</h2><p>Στο 2023 και οι έξι στρατηγικές είχαν θετικό αποτέλεσμα στα δύο σενάρια κόστους, αλλά μόνο 1–8 εξόδους η καθεμία, κάτω από το προκαθορισμένο ελάχιστο 10. Δεν μειώθηκε το όριο αφού είδαμε τις αποδόσεις.</p>'+table(['Στρατηγική','2023 βασικά','2023 αυξημένα','Έξοδοι / ελάχιστο 10'],trrows)
    body+='<h2>Από πού προκύπτει το αποτέλεσμα</h2><p>Βασικό σενάριο χωρίς πρόσθετη καθυστέρηση. Ποσά σε USDT: μεταβολή τιμής + funding − προμήθειες − λειτουργικά έξοδα = καθαρό αποτέλεσμα. Η ολίσθηση περιλαμβάνεται ήδη στις τιμές εκτέλεσης.</p>'+table(['Στρατηγική','Τιμή','Funding ±','Προμήθειες','Λειτουργικά','Καθαρό'],costs)
    body+='<h2>Σημεία αναφοράς</h2>'+table(['Περίπτωση','Κόστη','Καθαρό αποτέλεσμα','Πτώση'],[['Μετρητά','Χωρίς λειτουργικό κόστος',net(cash['metrics']),dd(cash['metrics'])]]+[['Αγορά/διακράτηση perpetual με θέση 50%',r['cost'],net(r['metrics']),dd(r['metrics'])] for r in benchmark])
    body+='''<h2>Τι μοντελοποιείται και τι παραμένει άγνωστο</h2><p>Τα σήματα σχηματίζονται σε πλήρως κλεισμένες ημερήσιες μπάρες. Η εκτέλεση γίνεται στο άνοιγμα της ώρας 01:00 UTC της επόμενης επιλέξιμης ημέρας, με δυσμενή ολίσθηση. Το funding χρησιμοποιεί την πραγματική διακρατούμενη ποσότητα και το καταγεγραμμένο επιτόκιο. Οι πραγματικές χρονικές αποκλίσεις των καταγραφών ήταν έως 31 ms μετά το ονομαστικό όριο· διατηρούνται στην είσοδο και αντιστοιχίζονται στο ίδιο όριο, χωρίς μεταβολή θέσης εκεί.</p>
<p>Η τιμή διακανονισμού funding προσεγγίζεται από το mark open της αντίστοιχης ώρας, με χωριστό δυσμενές σενάριο 5 μονάδων βάσης. Αυτή η ευαισθησία δεν αποτελεί αποδεδειγμένο ανώτατο όριο σφάλματος. Οι τρέχοντες κανόνες εντολών δεν ήταν προσβάσιμοι: χρησιμοποιείται υποθετικό μικρό βήμα ποσότητας/τιμής, όχι επαληθευμένα όρια ανταλλακτηρίου. Δεν υπάρχουν ιστορικό order book, ουρά εκτέλεσης, μερικά fills ή προσωπική προμήθεια.</p>
<p>Ο λογιστικός έλεγχος σταματά αν δεν καλύπτεται πλήρως η ονομαστική έκθεση μαζί με έξοδα εξόδου. Δεν είναι μοντέλο liquidation με πραγματικό isolated/cross margin. Το αποτέλεσμα αφορά υποθετικές εκτελέσεις σε πραγματική ιστορία Binance και δεν μεταφέρεται αυτόματα στην Bybit.</p>
<h2>Περιορισμοί της έρευνας</h2><p>Οι έξι οικογένειες είχαν ήδη επιλεγεί από παλιότερες, συσχετισμένες δοκιμές spot. Η χρονολογική επιλογή του 2023 δεν αναιρεί αυτή την προηγούμενη αναζήτηση. Δεν υπολογίζεται νέα διαδοχική ετήσια αξιολόγηση σε αυτό το πείραμα και δεν προβάλλεται ισχυρισμός στατιστικής σημαντικότητας. Τα εναλλακτικά κόστη, οι καθυστερήσεις και τα funding σενάρια δεν είναι ανεξάρτητα δείγματα.</p>'''
    body+=f'<p>Πέρασαν 78 έλεγχοι λογισμικού, από τους οποίους 25 νέοι. Οι {len(cases)} λογιστικές διαδρομές ελέγχθηκαν ανεξάρτητα σε {events:,} γεγονότα, με μέγιστη απόκλιση {maxerror} USDT. Ολοκληρώθηκαν κανονικά {complete}/{len(cases)} σενάρια. Μηδενικές πραγματικές εντολές.</p>'
    body+='''<p>Συνολικά 7.427 καταγεγραμμένες εκτελέσεις του ερευνητικού σχεδιασμού, συν δύο επαναλήψεις αποκατάστασης αρχείων: 7.429 εκτελέσεις συνολικά. Δύο αναλυτικά αρχεία βρέθηκαν κενά στον τελικό έλεγχο. Ανακατασκευάστηκαν με τους ίδιους παγωμένους κανόνες και συμφώνησαν byte προς byte με τα αρχικά SHA256· τα κενά αρχεία και το συμβάν διατηρήθηκαν. Η αιτία απώλειας δεν είναι γνωστή. Οι μοναδικές παραλλαγές παραμένουν 46 σε 23 οικογένειες: εδώ μεταφέρθηκαν έξι υπάρχουσες, δεν προστέθηκαν νέοι κανόνες. Το ήδη παγωμένο Bybit τεστ και οι παλιές ομάδες παρακολούθησης παραμένουν χωριστά.</p>
<p class="small">Δεδομένα: <a href="https://github.com/binance/binance-public-data">Binance Vision / Binance Public Data</a>. Χρήση για προσωπική, μη παραγωγική ιστορική έρευνα. Δεδομένα και παράγωγη ανάλυση υπό <a href="https://creativecommons.org/licenses/by-nc-sa/4.0/">CC BY-NC-SA 4.0</a> σύμφωνα με τους <a href="https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md">όρους συνόλου δεδομένων</a>. Καμία έγκριση ή συνεργασία Binance υπονοείται.</p>'''
    body+=f'<details><summary>Ίχνος ελέγχου και αναπαραγωγή</summary><p>Πάγωμα πριν από αποδόσεις: <a href="https://github.com/rafailm95/TradingAgents/commit/{FREEZE_COMMIT}">{FREEZE_COMMIT}</a>. Επιλογή πριν από αξιολόγηση: <a href="https://github.com/rafailm95/TradingAgents/commit/{SELECTION_COMMIT}">{SELECTION_COMMIT}</a>.</p><p>Freeze SHA256: <code>{FREEZE_SHA}</code>. Input SHA256: <code>{f["normalized_input_sha256"]}</code>.</p><p>Στο συνοδευτικό ZIP διατηρούνται οι πραγματικές είσοδοι με προέλευση και hashes, οι πλήρεις καμπύλες, fills, funding events, αποτυχίες και προδιαγραφές. Πηγή αριθμών: αμετάβλητα αποτελέσματα των παγωμένων κανόνων.</p></details>'
    page='<!doctype html><html lang="el"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Binance futures017 — αποτελέσματα ETH</title><style>body{font-family:system-ui,sans-serif;background:#f4f6fa;color:#17283d;line-height:1.65;margin:0}main{max-width:1150px;margin:auto;padding:28px 18px 60px}h1{font-size:clamp(28px,5vw,43px);line-height:1.2}h2{margin-top:34px;font-size:22px}.eyebrow{font-size:12px;letter-spacing:1.2px;color:#53677c}.lead{font-size:19px}.callout{background:#e2eee9;border-left:5px solid #29735c;padding:20px;border-radius:5px}.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;background:white;font-size:13px}th,td{text-align:left;padding:11px;border-bottom:1px solid #dce3eb;vertical-align:top}th{background:#19334e;color:white}td{min-width:88px}tr:nth-child(even){background:#f0f4f8}.small{font-size:13px;color:#536277}details{background:white;border:1px solid #dce2ec;border-radius:6px;margin:14px 0;padding:14px}summary{cursor:pointer;font-weight:650}code{overflow-wrap:anywhere}a{color:#145c9c}</style></head><body><main>'+body+'</main></body></html>'
    report=base/'Futures_Binance_017_EL.html';report.write_text(page)
    summary={'experiment':'binance_perpetual_017_v1','completed_utc':datetime.now(timezone.utc).isoformat(),'venue':'Binance USD-M perpetual','symbols':['ETHUSDT'],'evaluation':['2024-01-01','2025-12-31'],'training_selection':selected,'training_selection_sha256':SELECTION_SHA,'historical_screen_passes':all_pass,'new_simulations':89,'training_simulations':12,'evaluation_simulations':72,'benchmark_simulations':5,'completed_scenarios':complete,'new_unique_variants':0,'cumulative_known_simulations':7429,'cumulative_design_runs':7427,'additional_integrity_replays':2,'cumulative_unique_variants':46,'cumulative_families':23,'wealth_audit_events':events,'max_wealth_error_usdt':str(maxerror),'candidates':summary_rows,'benchmark_summaries':[r for r in cases if r['benchmark']],'real_orders':0,'not_bybit':True}
    write(repo/'summary.json',summary);write(repo/'case-summaries.json',cases);write(repo/'full_result_hashes.json',hashes);shutil.copyfile(evaluation/'evaluation.json',repo/'evaluation.json')
    md = '# Binance perpetual 017 results\n\n'
    md += 'Native ETHUSDT data for 2022–2025: 35,064 trade hours, 35,064 mark hours and 4,383 funding events. Verified 144 monthly and four daily official archives. Recovered 48 missing mark hours from official daily data; 48 overlapping hours agree exactly. BTC was blocked by network access and LTC had 120 missing trade hours; neither receives a return score.\n\n'
    md += f'Completed 89 runs: 12 training, 72 evaluation and five benchmarks. {len(all_pass)} of six variants pass all 12 historical scenarios. Training in 2023 selected cash because all six had fewer than 10 signal exits (1–8), despite positive profit under both costs. Evaluation covers 2024-01-01 through 2025-12-31. Each account starts with 10,000 USDT. Returns are for the whole period, not margin ROI or forecasts.\n\n'
    md += '| Candidate | Base net % / USDT | Stress net % / USDT | Worst of 12 scenarios | Worst sampled DD % / actual USDT | Base signal exits | Historical pass |\n|---|---|---|---|---|---|---|\n'
    for r in summary_rows:
        md += '| ' + ' | '.join([r['candidate'], net(r['baseline']), net(r['stress']), net(r['worst']['metrics']), dd(r['risk']['metrics']), str(r['baseline']['signal_exits']), str(r['gate']['historical_screen_pass'])]) + ' |\n'
    md += '\nThe descriptive opportunity ranking preserves positive candidates even when a formal gate fails. It is computed after viewing results and does not replace the frozen training selection. All failures and every scenario remain in evaluation.json.\n\n'
    md += 'Cost assumptions per side: 5.5 bps fee plus 2 bps slippage in the baseline, and 10 plus 10 bps in stress; operating expense is 120 USDT/year. Funding uses actual archived rates and held quantity with an hourly mark-open proxy and a separate adverse 5 bps valuation. Timestamp offsets of 0–31 ms are retained and mapped to the nominal eight-hour boundary, without position changes there. Hypothetical fine-lot filters use 1e-8 precision; Binance exchangeInfo returned HTTP 451 and was not bypassed. Historical fills, order books and personal fees are unavailable. A fully cash-backed guard is used; it is not an exchange liquidation model. Signals are daily, long or flat; no shorts were tested.\n\n'
    md += f'Validation: 78 software tests passed, including 25 new tests; {events:,} independent wealth events checked with maximum error {maxerror} USDT. All 89 result-file hashes were verified. Cumulative design executions: 7,427, plus two integrity replays (7,429 total executions), with 46 unique variants in 23 families. Correlated, overlapping tests are not independent evidence. Frozen sources were not changed after outcomes. Bybit 013 and both prospective cohorts remain unchanged.\n\n'
    md += f'Pre-outcome freeze: `{FREEZE_SHA}` at commit `{FREEZE_COMMIT}`. Training selection published before evaluation at `{SELECTION_COMMIT}`, selection SHA256 `{SELECTION_SHA}`.\n\n'
    md += 'Reproduction, from the repository root with the pinned runtime:\n\n```bash\n'
    md += f'python scripts/run_binance_replay_017.py --input INPUT.json.gz --sha256 {f["normalized_input_sha256"]} --engine-freeze-sha256 {FREEZE_SHA} --stage train --output NEW_TRAIN\n'
    md += f'python scripts/run_binance_replay_017.py --input INPUT.json.gz --sha256 {f["normalized_input_sha256"]} --engine-freeze-sha256 {FREEZE_SHA} --stage evaluate --training-directory NEW_TRAIN --selection-sha256 {SELECTION_SHA} --output NEW_EVALUATION\n```\n\n'
    md += 'Source: [Binance Vision public archives](https://github.com/binance/binance-public-data). Dataset and derived analysis: CC BY-NC-SA 4.0, for personal, non-production research. No exchange endorsement is implied. Source code retains its repository license. No claim of Bybit profitability.\n'
    (ROOT/'docs/BINANCE_PERPETUAL_017_RESULTS.md').write_text(md)
    archive=base/'Futures_Binance_017_Evidence.zip'
    # Two reconstructed results matched the original manifest byte for byte; preserve the loss evidence too.
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for directory in (train,evaluation,base/'binance-017-accepted',base/'binance-017-result-recovery'):
            for p in sorted(directory.rglob('*')):
                if p.is_file():z.write(p,str(p.relative_to(base)),compress_type=zipfile.ZIP_STORED if p.suffix in ('.gz','.zip') else zipfile.ZIP_DEFLATED)
        z.write(base/'binance-017-normalized.json.gz','binance-017-normalized.json.gz',compress_type=zipfile.ZIP_STORED)
        sources=set(f['source_hashes'])|set(f['preserved_files'])|{'research/experiments/017/freeze.json','research/experiments/017/summary.json','research/experiments/017/evaluation.json','research/experiments/017/case-summaries.json','research/experiments/017/full_result_hashes.json','research/experiments/017/training-selection.json','docs/BINANCE_PERPETUAL_017_RESULTS.md','scripts/build_binance_report_017.py','scripts/recover_binance_results_017.py','research/experiments/017/result-recovery.json'}
        for p in sorted(sources):z.write(ROOT/p,'repository/'+p)
        for p in sorted((repo/'access').glob('*')):z.write(p,'repository/'+str(p.relative_to(ROOT)))
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    verify={'verified_utc':datetime.now(timezone.utc).isoformat(),'freeze_sha256':FREEZE_SHA,'freeze_commit':FREEZE_COMMIT,'selection_commit':SELECTION_COMMIT,'sources_unchanged_after_outcomes':True,'result_hashes_verified':89,'historical_runs':89,'integrity_replays':2,'raw_archive_hashes_reverified':148,'complete_runs':complete,'audit_events':events,'max_error_usdt':str(maxerror),'report':{'name':report.name,'sha256':sha(report),'bytes':report.stat().st_size},'evidence':{'name':archive.name,'sha256':sha(archive),'bytes':archive.stat().st_size,'crc':'PASS'},'real_orders':0}
    write(repo/'verification.json',verify);print(json.dumps(verify),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);a=p.parse_args();main(a.base)
