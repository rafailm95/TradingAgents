"""Export completed016evidence without rerunning or altering frozen simulations."""
import argparse
from datetime import datetime,timezone
import gzip,hashlib,html,json,shutil,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FREEZE_SHA='b215ddf0986511c619144ddca6202d115316bb34324e6a1beee2fc8974a70c49'
FREEZE_COMMIT='d38e671fee368f7118e1c884f1d126bf39fc1863'
PRODUCTS=('BTC-USD','ETH-USD','LTC-USD')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def fmt(v):return f'{v:+,.2f}'
def net(p,c):return f'{fmt(p)}% / {fmt(c)} USD'
def table(headers,rows):return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+html.escape(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(c))+'</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table></div>'
def main(results,dest):
    frozen=read(ROOT/'research/experiments/016/freeze.json');assert sha(ROOT/'research/experiments/016/freeze.json')==FREEZE_SHA
    for group in ('source_hashes','preserved_files'):
        for p,h in frozen[group].items():assert sha(ROOT/p)==h,p
    hashes=read(results/'full_result_hashes.json')
    for p,h in hashes.items():assert sha(results/p)==h,p
    s=read(results/'summary.json'); assert s['historical_simulations']==s['audit_cases']==174
    assets={p:read(results/p/'assessment.json') for p in PRODUCTS}
    assert all(len(a['comparison46'])==len({r['id'] for r in a['comparison46']})==46 for a in assets.values())
    historical=[(p,a['id']) for p,v in assets.items() for a in v['assessments'] if a['historical_pass']]
    robust=[(p,a['id']) for p,v in assets.items() for a in v['assessments'] if a['robust_pass']]
    assert historical==[('LTC-USD','peer_reversion60__vol15_cap50')] and not robust
    repo_out=ROOT/'research/experiments/016'
    for name in ('summary.json','full_result_hashes.json','run_manifest.json'):
        shutil.copyfile(results/name,repo_out/name)
    for p in PRODUCTS:
        (repo_out/p).mkdir(exist_ok=True)
        for name in ('assessment.json','audits.json','selection_before_evaluation.json'):
            shutil.copyfile(results/p/name,repo_out/p/name)
    labels={'fixed50':'Σταθερή θέση 50%','vol15_cap50':'Θέση βάσει μεταβλητότητας'}
    rows=[];mdrows=[]
    for p,a in assets.items():
        for row in a['new_opportunities']:
            base,stress=row['scenarios'][:2]; dd=max(row['scenarios'],key=lambda x:x['max_drawdown_pct'])
            cols=[p[:3],labels[row['id'].split('__')[1]],net(base['return_pct'],base['pnl_usd']),net(stress['return_pct'],stress['pnl_usd']),net(row['worst_return_pct'],row['worst_pnl_usd']),f"{dd['max_drawdown_pct']:.2f}% / {dd['amount_at_max_pct_usd']:,.2f} USD"]
            rows.append(cols); english=list(cols); english[1]=row['id'].split('__')[1]; mdrows.append('| '+' | '.join(english)+' |')
    ltc=assets['LTC-USD']['new_opportunities'][1]
    lagrows=[[str(x['lag_days']),x['cost'],net(x['return_pct'],x['pnl_usd']),f"{x['max_drawdown_pct']:.2f}% / {x['amount_at_max_pct_usd']:,.2f} USD"] for x in ltc['scenarios']]
    wfrows=[]
    for p,a in assets.items():
        b,t=[a['walk_forward_summary'][c] for c in ('base','stress')]
        wfrows.append([p[:3],net(b['net_return_pct'],b['net_profit_usd']),net(t['net_return_pct'],t['net_profit_usd'])])
    shortlist=[]
    for p,a in assets.items():
        for row in a['comparison46'][:5]:shortlist.append([p[:3],row['id'],net(row['worst_return_pct'],row['worst_pnl_usd']),'Περνά τα παλιά ιστορικά φίλτρα' if row['historical_robust_pass'] else 'Αποτυγχάνει σε φίλτρα'])
    body='''<p class="eyebrow">ΕΡΕΥΝΑ ΣΤΡΑΤΗΓΙΚΩΝ · ΔΟΚΙΜΗ 016</p><h1>Θετική ένδειξη στο Litecoin, με αδυναμία στην καθυστέρηση</h1>
<p class="lead">Ολοκληρώθηκαν 174 νέες ιστορικές προσομοιώσεις. Η αγορά μετά από μεγάλη σχετική υποχώρηση έδωσε θετικό αποτέλεσμα στο Litecoin με θέση βάσει μεταβλητότητας. Περνά τα βασικά ιστορικά φίλτρα, αλλά αποτυγχάνει στους ελέγχους καθυστερημένης εκτέλεσης. Καμία νέα παραλλαγή δεν περνά το πλήρες σύνολο κριτηρίων.</p>
<div class="callout"><b>+18,30% / +1.830,36 USD</b> με βασικά κόστη · <b>+10,97% / +1.096,86 USD</b> με αυξημένα κόστη.<br>Litecoin, 1/1/2024–15/10/2026, υποθετικό αρχικό κεφάλαιο 10.000 USD. Συνολική απόδοση της περιόδου, όχι ετήσια ούτε πρόβλεψη.</div>
<p>Τα δεδομένα είναι ημερήσιες τιμές Coinbase USD spot. Τα αποτελέσματα δεν αποτελούν μέτρηση κερδοφορίας Bybit perpetuals. Το χωριστό τεστ Bybit περιμένει το ήδη ζητημένο ενιαίο BYBIT_SEND_THIS.zip. Δεν χρειάζεται άλλο επιμέρους αρχείο ή API key για αυτή τη δοκιμή.</p>
<h2>Τι δοκιμάστηκε</h2><p>Συγκρίνουμε τη λογαριθμική πορεία κάθε νομίσματος με τον μέσο όρο των άλλων δύο. Αγορά όταν η σχετική απόκλιση πέσει πάνω από δύο τυπικές αποκλίσεις κάτω από τον μέσο όρο των προηγούμενων 60 ημερών. Έξοδος στην επαναφορά ή 20 ημέρες μετά την πραγματική είσοδο. Εκτέλεση στο επόμενο άνοιγμα. Μόνο αγορά ή μετρητά, χωρίς μόχλευση ή short.</p>
<p>Δύο μεγέθη θέσης: 50% των διαθέσιμων μετρητών στην είσοδο, ή μέγεθος βάσει μεταβλητότητας με όριο 50% στην είσοδο. Κάθε νόμισμα έχει ανεξάρτητο υποθετικό λογαριασμό 10.000 USD· τα ποσά δεν αθροίζονται σαν να προέρχονται από ένα κοινό κεφάλαιο. Το βάρος της θέσης μπορεί να αλλάζει μετά την είσοδο.</p>
<h2>Όλες οι νέες παραλλαγές</h2><p>Περίοδος 1/1/2024–15/10/2026. Βασικά κόστη: προμήθεια 0,60% + ολίσθηση 0,10% ανά πλευρά. Αυξημένα: 1,20% + 0,25% ανά πλευρά. Περιλαμβάνεται λειτουργικό κόστος 120 USD/έτος. Πρόκειται για τα παλιά σενάρια spot, όχι για τις προμήθειες του λογαριασμού Bybit.</p>'''
    headers=['Νόμισμα','Μέγεθος θέσης','Βασικά κόστη','Αυξημένα κόστη','Χειρότερο από 6 σενάρια','Μεγαλύτερη πτώση % / ποσό']
    body+=table(headers,rows)
    body+='''<p class="small">Τα έξι σενάρια συνδυάζουν δύο κόστη με πρόσθετη καθυστέρηση 0, 1 ή 2 ημερών. Η πτώση υπολογίζεται από πραγματική προηγούμενη κορυφή σε επόμενο χαμηλό της ημερήσιας καμπύλης, με ημερήσια κατανομή λειτουργικού κόστους ως διαγνωστικό. Το ποσό στην τελευταία στήλη αντιστοιχεί στη μέγιστη ποσοστιαία πτώση· δεν είναι απλώς 10.000 × ποσοστό. Το παγωμένο λογιστικό μοντέλο χρεώνει το λειτουργικό κόστος στο τέλος κάθε παραθύρου. Ενδοημερήσιες πτώσεις δεν καταγράφονται σε αυτή τη μελέτη.</p>
<h2>Γιατί κρατάμε την ένδειξη, αλλά όχι ως επιβεβαιωμένο αποτέλεσμα</h2><p>Η επιλογή με βάση μόνο το 2020–2023 επέλεξε τη μεταβλητή θέση στο Litecoin πριν αξιολογήσει το 2024–2026. Η ίδια παραλλαγή έχει θετικό αποτέλεσμα στις χωριστές περιόδους 2024–2025 και 2026 έως 15/10 και στα δύο κόστη. Όμως ολοκλήρωσε μόλις 14 συναλλαγές στην περίοδο αξιολόγησης, και το κέρδος εξαρτάται έντονα από το πότε εκτελείται το σήμα.</p>'''
    body+=table(['Πρόσθετη καθυστέρηση ημερών','Σενάριο κόστους','Καθαρό αποτέλεσμα','Μέγιστη πτώση % / ποσό'],lagrows)
    body+='''<p>Η καθυστέρηση μίας ή δύο ημερών είναι έλεγχος αντοχής του σήματος, όχι εκτίμηση της πραγματικής δικτυακής καθυστέρησης στην Bybit. Στην κανονική εκτέλεση τα θετικά αποτελέσματα του 2024 συνυπάρχουν με ζημιογόνο 2025. Δεν αλλάξαμε κανόνες μετά την εμφάνιση αυτών των αποτελεσμάτων.</p>
<h2>Διαδοχική ετήσια αξιολόγηση</h2><p>Περίοδος 1/1/2022–15/10/2026. Πριν από κάθε έτος επιλέγεται μία από τις δύο νέες παραλλαγές μόνο από τα προηγούμενα έτη. Αν καμία δεν πληροί τα κριτήρια, ο λογαριασμός παραμένει σε μετρητά. Οι θέσεις κλείνουν στο τέλος κάθε έτους, το υπόλοιπο μεταφέρεται και τα λειτουργικά έξοδα αφαιρούνται.</p>'''
    body+=table(['Νόμισμα','Βασικά κόστη','Αυξημένα κόστη'],wfrows)
    body+='''<p>Στο Bitcoin όλα τα έτη παρέμειναν σε μετρητά: η απώλεια 574,62 USD οφείλεται αποκλειστικά στα μοντελοποιημένα λειτουργικά έξοδα. Το παθητικό σημείο αναφοράς μετρητών έχει μηδενικό κόστος. Στο Litecoin επιλέχθηκε η μεταβλητή θέση και στα πέντε έτη. Η διαδοχική αξιολόγηση και η σταθερή περίοδος 2024–2026 επικαλύπτονται· δεν είναι ανεξάρτητες αποδείξεις και δεν αθροίζονται.</p>
<h2>Σύγκριση με προηγούμενες ιδέες</h2><p>Διατηρήθηκαν και κατατάχθηκαν και οι 46 παραλλαγές ανά νόμισμα. Η κατάταξη προτάσσει την επιτυχία στα ιστορικά φίλτρα και κατόπιν τη σχέση χειρότερης απόδοσης και πτώσης. Κρατά και ισχυρές αποδόσεις που αποτυγχάνουν σε κριτήρια. Οι παρακάτω παλιές ενδείξεις δεν είναι νέα αποτελέσματα ούτε αφορούν Bybit.</p>'''
    body+=table(['Νόμισμα','Στρατηγική','Χειρότερο αποτέλεσμα 6 σεναρίων','Έλεγχοι'],shortlist)
    for p,a in assets.items():
        body+='<details><summary>'+p[:3]+' — Όλες οι 46 παραλλαγές και αποτυχίες</summary>'
        body+=table(['Σειρά','Παραλλαγή','Χειρότερο αποτέλεσμα','Αποτυχημένα κριτήρια'],[[r['review_rank'],r['id'],net(r['worst_return_pct'],r['worst_pnl_usd']),', '.join(r['failed']) or 'Κανένα από τα παλιά ιστορικά φίλτρα'] for r in a['comparison46']])+'</details>'
    body+='''<h2>Πόση εμπιστοσύνη δικαιολογείται</h2><p>Το ίδιο ιστορικό έχει χρησιμοποιηθεί σε πολλές προηγούμενες δοκιμές. Οι 46 παραλλαγές, τα τρία νομίσματα και τα επαναλαμβανόμενα σενάρια δεν αποτελούν ανεξάρτητα δείγματα. Ο διαγνωστικός έλεγχος πολλαπλών συγκρίσεων με 2.000 επαναδειγματοληψίες και ομάδες 30/60 ημερών δεν δίνει ισχυρή στατιστική ένδειξη: p περίπου 0,206–0,420 έναντι μετρητών και 0,556–1,000 έναντι αγοράς/διακράτησης 50%. Δεν περιλαμβάνει λειτουργικά έξοδα και δεν διορθώνει ολόκληρο το ιστορικό αναζήτησης.</p>
<p>Η μελέτη περιορίζεται σε τρία ήδη επιλεγμένα νομίσματα, ημερήσια candles, απλοποιημένη ολίσθηση και προμήθειες spot. Δεν περιλαμβάνει ιστορικό βάθος αγοράς, funding perpetuals, ουρά εκτέλεσης, επίδραση εντολών ή επαλήθευση προσωπικής προμήθειας Bybit. Η σχετική υποχώρηση μπορεί να συνεχιστεί αντί να ανακάμψει.</p>
<h2>Επαλήθευση και επόμενο βήμα</h2>'''
    body+=f"<p>170 έλεγχοι λογισμικού πέρασαν, από τους οποίους 25 νέοι. Επαληθεύτηκαν 174 λογιστικές διαδρομές και {s['audit_days']:,} ημερήσια σημεία, με μέγιστη διαφορά ανεξάρτητου υπολογισμού {s['max_wealth_error_usd']:.3g} USD. Συνολικά: 7.338 ιστορικές εκτελέσεις σε επικαλυπτόμενα δεδομένα, 46 παραλλαγές μεγέθους θέσης και 23 οικογένειες ιδεών. Μηδενικές πραγματικές εντολές.</p>"
    body+='''<p>Η νέα ιδέα στο Litecoin παραμένει υποψήφια για μελλοντική, χωριστά παγωμένη αξιολόγηση. Δεν προστίθεται αυτόματα στα ήδη παγωμένα τεστ Bybit ή στις ομάδες παρακολούθησης. Προτεραιότητα έχει η αξιολόγηση των έξι ήδη επιλεγμένων στρατηγικών στα πραγματικά δεδομένα Bybit όταν φτάσει το ενιαίο αρχείο.</p>
<p class="small">Θεωρητικό πλαίσιο: <a href="https://www.newyorkfed.org/research/staff_reports/sr187.html">Tobias Adrian — Inference, Arbitrage, and Asset Price Volatility</a>, New York Fed. Η πηγή συζητά προσωρινές και μόνιμες πτώσεις· δεν τεκμηριώνει την κερδοφορία της συγκεκριμένης υλοποίησης και δεν αναπαράγουμε το μοντέλο της.</p>'''
    body+=f'<details><summary>Πάγωμα κανόνων και ίχνος ελέγχου</summary><p>Freeze SHA256: <code>{FREEZE_SHA}</code></p><p>Προδημοσίευση: <a href="https://github.com/rafailm95/TradingAgents/commit/{FREEZE_COMMIT}">{FREEZE_COMMIT}</a>. Ολοκλήρωση UTC: {s["completed_utc"]}.</p><p>Το συνοδευτικό ZIP περιέχει τις πλήρεις νέες καμπύλες, fills, trades, ελέγχους, επιλογές εκπαίδευσης και πηγές. Τα παλιά δεδομένα αναφοράς 011/015 παραμένουν στα προηγούμενα αρχεία τεκμηρίωσης και αναγνωρίζονται με τα ακριβή hashes.</p></details>'
    page='<!doctype html><html lang="el"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Στρατηγικές 016 — Litecoin και σχετική επαναφορά</title><style>body{font-family:system-ui,sans-serif;background:#f4f6fa;color:#15243a;line-height:1.65;margin:0}main{max-width:1100px;margin:auto;padding:28px 18px 60px}h1{font-size:clamp(28px,5vw,43px);line-height:1.2}h2{margin-top:36px;font-size:23px}.eyebrow{font-size:12px;letter-spacing:1.3px;color:#58677c}.lead{font-size:19px}.callout{background:#e0eee9;border-left:5px solid #29755c;padding:20px;border-radius:5px}.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;background:white;font-size:13px}th,td{text-align:left;padding:12px;border-bottom:1px solid #dfe4ed;vertical-align:top}th{background:#162c46;color:white}td{min-width:95px}tr:nth-child(even){background:#f2f5f8}.small{font-size:13px;color:#536277}details{background:#fff;border:1px solid #dce2ec;border-radius:6px;margin:16px 0;padding:14px}summary{cursor:pointer;font-weight:650}code{overflow-wrap:anywhere}a{color:#115898}</style></head><body><main>'+body+'</main></body></html>'
    report=dest/'Trading_Strategies_016_EL.html';report.write_text(page)
    md='# Peer-relative reversion016 results\n\nCompleted all174preregistered simulations. One of6asset/variant pairs passes the historical gate: LTC peer_reversion60__vol15_cap50. None passes the complete historical-plus-delay gate. Preserve this positive but execution-sensitive idea; no retuning or promotion.\n\n'
    md+='Evaluation2024-01-01..2026-10-15,independent10000USDspotaccounts. Basefee60bps+slippage10bps/side;stress120+25;opex120USD/year. Not Bybit fees or perpetual returns. Total-period returns,not annual.\n\n| Asset | Sizing | Base net%/USD | Stress net%/USD | Worst6scenarios%/USD | Worst DD%/actualUSD |\n|---|---|---|---|---|---|\n'+'\n'.join(mdrows)+'\n\n'
    md+='LTCvol:base+18.3036%/1830.36USD,stress+10.9686%/1096.86USD;14completed trades. Lag1stress-5.0691%/-506.91USD;lag2stress-6.3245%/-632.45USD;lag2base-0.2377%/-23.77USD. Full,validation,recent windows pass both costs, but3delayprofit gates fail. Main2020–2023selector chosevolforETH/LTC andcashforBTC. This selection and the historical windows are reused research history,not freshholdout.\n\n'
    md+='Annual expanding WFA2022..2026-10-15:\n'+''.join(f'- {p}:base{a["walk_forward_summary"]["base"]["net_return_pct"]:.6f}% ({a["walk_forward_summary"]["base"]["net_profit_usd"]:.2f}USD);stress{a["walk_forward_summary"]["stress"]["net_return_pct"]:.6f}% ({a["walk_forward_summary"]["stress"]["net_profit_usd"]:.2f}USD).\n' for p,a in assets.items())
    md+='\nBTCWFA remainedcash everyyear;the loss is managedopex only. LTCvolselectedeveryfold. WFA overlapsfixedwindow;no addition/independenceclaim.\n\nAll46candidates perasset retained,including old stronger ideas and allfailedgates. Conditional46candidate blockbootstrap p~.206–.420vscash,.556–1.000vshold50. Operatingexpense excluded;priorsearchnotcorrected. Gates use originalbeforeexternalexpense closeDD;reportedcashDD usesdailyexpenseallocationdiagnostic.35%researchgate is not user risk approval.\n\n'
    md+=f'174wealthaudits,{s["audit_days"]}auditpoints,maxerror{s["max_wealth_error_usd"]:.12g}USD.170preflighttests,25new.7338historical scenario executions,46variants,23families;correlated repetitions,not independent evidence.\n\nFreeze{FREEZE_SHA};publishedbeforeoutcomesat{FREEZE_COMMIT}. Sourcesunchangedafteroutcomes. Noorders,nocohortchanges.013Bybitstillawaitsonepacket.\n\n'
    md+='Reproduce from repository root with the pinned Python3.12,numpy2.3.5,pandas2.2.3,dotenv1.2.4 environment:\n\n```bash\npython scripts/run_peer_reversion_lab.py --output NEW_OUTPUT_DIRECTORY --reference-root PATH_TO_011_FULL_RESULTS --reference-015-root PATH_TO_015_FULL_RESULTS --freeze-sha '+FREEZE_SHA+'\n```\n\nPrimary conceptual source:https://www.newyorkfed.org/research/staff_reports/sr187.html. Temporary versus permanent declines motivate competing effects;this is a custom long/flat crypto rule,not a replication or arbitrage/cointegration claim.\n'
    (ROOT/'docs/PEER_REVERSION_016_RESULTS.md').write_text(md)
    archive=dest/'Trading_Strategies_016_Evidence.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(results.rglob('*')):
            if p.is_file():z.write(p,'results/'+str(p.relative_to(results)))
        sourcepaths=set(frozen['source_hashes'])|{'research/experiments/016/freeze.json','docs/PEER_REVERSION_016_RESULTS.md','scripts/build_peer_reversion_016_report.py'}
        for p in sorted(sourcepaths):z.write(ROOT/p,'repository/'+p)
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    verification={'verified_utc':datetime.now(timezone.utc).isoformat(),'freeze_commit':FREEZE_COMMIT,'freeze_sha256':FREEZE_SHA,'historical_runs':174,'new_variants':2,'audit_cases':174,'audit_points':s['audit_days'],'max_wealth_error_usd':s['max_wealth_error_usd'],'all_result_hashes_verified':True,'result_files':len(hashes),'source_rules_changed_after_outcomes':False,'preserved_files_verified':len(frozen['preserved_files']),'archive':{'name':archive.name,'sha256':sha(archive),'bytes':archive.stat().st_size,'crc':'PASS'},'report':{'name':report.name,'sha256':sha(report),'bytes':report.stat().st_size},'new_historical_passes':len(historical),'new_delay_robust_passes':len(robust),'real_orders':0}
    write(repo_out/'verification.json',verification)
    print(json.dumps(verification))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);p.add_argument('--destination',type=Path,required=True);a=p.parse_args();main(a.results,a.destination)
