"""Verify every019 result, export exact metrics and render a Greek report.
No strategy replays or parameter changes. Run after the frozen matrix completes.
"""
import csv
import base64
from decimal import Decimal as D
import gzip
import hashlib
import html
import json
import re
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from tradingagents import futures_replay_019 as engine
from tradingagents.funding_signal_019 import NEW_CANDIDATES
from run_funding_futures_019 import verify_freeze, INPUT_SHA, file_sha

WORK = ROOT.parent
OUT = ROOT/'research/experiments/019'
BASE = 'https://github.com/rafailm95/TradingAgents'
FREEZE_SHA = '04c9fb5a8ea26ee1ed3640ec75f2ef524dd50ffce1f9603bbb261ce941ad541d'


def write(path, value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def n(value):
    return f'{float(value):,.2f}'


def main():
    pin=verify_freeze(FREEZE_SHA)
    a=json.loads((WORK/'funding019-train1/selection.json').read_bytes())
    b=json.loads((WORK/'funding019-train2/selection.json').read_bytes())
    e=json.loads((WORK/'funding019-evaluation/evaluation.json').read_bytes())
    recovery=json.loads((WORK/'funding019-result-recovery/receipt.json').read_bytes())
    if recovery['status']!='PASS' or recovery['additional_integrity_replays']!=4:
        raise ValueError('Incomplete recovery')
    recovered={x['file']:x for x in recovery['recovered']}
    recovery2=json.loads((WORK/'funding019-result-recovery-v2/receipt.json').read_bytes())
    if recovery2['status']!='PASS':raise ValueError('Second recovery incomplete')
    records=[]
    for directory, source in [('funding019-train1',a['new_results']),
                              ('funding019-train2',b['new_results']),
                              ('funding019-evaluation',e['new_results'])]:
        for rec in source.values():
            path=WORK/directory/rec['file']
            original_path=directory+'/'+rec['file']
            if path.stat().st_size==0 and directory=='funding019-evaluation' and rec['file'] in recovered:
                if recovered[rec['file']]['sha256']!=rec['sha256']:
                    raise ValueError('Recovery pin mismatch')
                path=WORK/'funding019-result-recovery'/rec['file']
            raw=path.read_bytes()
            encoding='gzip'
            if not raw and rec['file']=='wfa_2024_venue_assumption_lag0_adverse1.json.gz':
                path=WORK/'funding019-result-recovery-v2/recovered-result-envelope.json'
                if file_sha(path)!=recovery2['envelope_sha256']:raise ValueError('Envelope hash failed')
                raw=base64.b64decode(json.loads(path.read_bytes())['data'],validate=True)
                encoding='base64+gzip'
            if not raw or hashlib.sha256(raw).hexdigest()!=rec['sha256']:
                raise ValueError('Output integrity failed: '+str(path))
            r=json.loads(gzip.decompress(raw))
            audit=engine.audit_wealth(r)
            if r['metrics']!=rec['metrics'] or r['status']!=rec['status']:
                raise ValueError('Result summary mismatch')
            records.append({'path':str(path.relative_to(WORK)),'original_path':original_path,'sha256':rec['sha256'],
                            'bytes':path.stat().st_size,'container_sha256':file_sha(path),'encoding':encoding,'audit':audit})
    if len(records)!=68 or len({r['path'] for r in records})!=68:
        raise ValueError('Expected exact68 distinct new runs')
    rows=[]
    for candidate, cases in e['comparisons_all8'].items():
        for r in cases:
            rows.append({'candidate':candidate,'cost':r['cost'],'lag':r['lag_days'],
                         'adverse_funding':r['adverse_funding_5bps'],'new':candidate in NEW_CANDIDATES,
                         'status':r['status'],**r['metrics']})
    with (OUT/'metrics.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    concise={}
    for candidate,cases in e['comparisons_all8'].items():
        base=next(r for r in cases if r['cost']=='venue_assumption' and r['lag_days']==0 and not r['adverse_funding_5bps'])
        stress=next(r for r in cases if r['cost']=='stress_assumption' and r['lag_days']==0 and not r['adverse_funding_5bps'])
        worst=min(cases,key=lambda x:D(x['metrics']['net_profit_usdt']))
        dd=max(cases,key=lambda x:D(x['metrics']['max_drawdown_pct']))
        concise[candidate]={'base':base['metrics'],'stress':stress['metrics'],
            'worst12':worst,'largest_sampled_pct_dd':dd,
            'positive_scenarios':sum(D(r['metrics']['net_profit_usdt'])>0 for r in cases),
            'scenario_gate_passes':12-len(e['gates_all8'][candidate]['failed_scenarios']),
            'gate':e['gates_all8'][candidate]}
    newpasses=sum(e['gates_all8'][c]['historical_screen_pass'] for c in NEW_CANDIDATES)
    verification={'status':'PASS','new_files_verified':len(records),
        'new_wealth_events':sum(r['audit']['events_checked'] for r in records),
        'maximum_decimal_discrepancy_usdt':str(max(D(r['audit']['max_error_usdt']) for r in records)),
        'preserved_old_files':len(pin['preserved_files']),'software_tests':111,'new_tests':33,
        'preflight_failure':'One test import-path failure corrected before freeze; retained in preflight.json.',
        'new_strategy_replays_for_verification':0,'input_sha256':file_sha(WORK/'binance-017-normalized.json.gz')}
    verification['additional_integrity_replays']=5
    verification['recovery']='Four original zero-byte files retained; one first-recovery file became zero-byte again. One bounded second recovery uses an fsynced base64 envelope. All68resolved outputs match original manifestSHA exactly. Both failures preserved, cause unknown; no rule/input/metric changes.'
    if verification['input_sha256']!=INPUT_SHA: raise ValueError('Input changed')
    summary={'experiment':'019','period':'2024-01-01..2025-12-31','venue':'BinanceUSD-METHUSDT',
        'new_families':1,'total_families':24,'new_variants':2,'total_variants':48,
        'new_simulations':68,'new_integrity_replays':5,'cumulative_design_executions':7495,'cumulative_including7recovery':7502,
        'new_full_gate_passes':newpasses,'new_full_gate_failures':2-newpasses,
        'new_scenario_gate_passes':sum(concise[c]['scenario_gate_passes'] for c in NEW_CANDIDATES),
        'new_scenario_gate_failures':24-sum(concise[c]['scenario_gate_passes'] for c in NEW_CANDIDATES),
        'all8_gate_passes':sum(v['gate']['historical_screen_pass'] for v in concise.values()),
        'wfa_scenario_passes':sum(v['passed'] for v in e['walk_forward'].values()),
        'wfa_scenario_failures':sum(not v['passed'] for v in e['walk_forward'].values()),
        'training_selections':[a['selection'],b['selection']],'candidates':concise,
        'walk_forward':e['walk_forward'],'multiplicity':e['multiplicity'],
        'new_prospective_observations':0,'real_orders':0}
    write(OUT/'summary.json',summary);write(OUT/'verification.json',verification)
    write(OUT/'recovery-receipt.json',recovery)
    write(OUT/'recovery-v2-receipt.json',recovery2)
    write(OUT/'full_result_hashes.json',records)
    (OUT/'evaluation.json').write_bytes((WORK/'funding019-evaluation/evaluation.json').read_bytes())
    write(OUT/'input-reference.json',{'library_file_id':'libfile_4a34e6a7d2dc8191bca89e277b1fbd97',
        'archive_sha256':pin['archive_sha256'],'normalized_sha256':INPUT_SHA,
        'normalized_in_this_evidence':True,'raw_017_archive_separately_persisted':True})
    heading='Futures019 — Funding και έλεγχος σε επόμενα έτη'
    lines=['# '+heading,'','Ημερομηνία αναφοράς:2026-10-17. Πραγματικά ιστορικά δεδομένα Binance ETHUSDT, εικονικοί λογαριασμοί10.000USDT. Αξιολόγηση1/1/2024–31/12/2025. Καμία πραγματική εντολή ή νέα μελλοντική παρατήρηση.','',
        f"Νέα οικογένεια: funding_carry7_momentum28, δύο μεγέθη θέσης. {newpasses}/2 περνούν όλα τα ιστορικά κριτήρια. {summary['new_scenario_gate_passes']}/24 νέα σενάρια περνούν, {summary['new_scenario_gate_failures']}/24 αποτυγχάνουν. Σύνολο48παραλλαγές/24οικογένειες,68νέες εκτελέσεις και5επαναλήψεις αποκατάστασης. Συνολικά7.495σχεδιασμένες+7επαναλήψεις αποκατάστασης=7.502γνωστές εκτελέσεις. Οι προσομοιώσεις δεν είναι ανεξάρτητα δείγματα.",'',
        '| Παραλλαγή | Βασικό καθαρό | Αυξημένο κόστος | Χειρότερο από12 | Μέγιστη δειγματοληπτική DD και πραγματικό ποσό | Έξοδοι βασικού | Περνά σενάρια |',
        '|---|---|---|---|---|---|---|']
    for candidate,v in concise.items():
        def pnl(m):return n(m['net_return_pct'])+'% / '+n(m['net_profit_usdt'])+' USDT'
        d=v['largest_sampled_pct_dd']['metrics']
        lines.append('|'+candidate+'|'+pnl(v['base'])+'|'+pnl(v['stress'])+'|'+pnl(v['worst12']['metrics'])+'|'+n(d['max_drawdown_pct'])+'% / '+n(d['cash_at_max_pct_drawdown_usdt'])+' USDT|'+str(v['base']['signal_exits'])+'|'+str(v['scenario_gate_passes'])+'/12|')
    lines+=['','Τα θετικά σενάρια της νέας οικογένειας εμφανίστηκαν με καθυστέρηση δύο ημερών: fixed50 +25,31% (+2.530,83USDT) βασικό και +20,17% (+2.016,68USDT) αυξημένο κόστος· vol15 +9,11% (+910,91USDT) και +7,02% (+702,00USDT). Αντίθετα, με καθυστέρηση μίας ημέρας ήταν ζημιογόνα. Δεν επιλέγουμε εκ των υστέρων το ευνοϊκό timing: η έντονη αλλαγή προσήμου αποτυγχάνει στον κανόνα αντοχής σε όλες τις καθυστερήσεις. Οι ακριβείς τιμές και τα12σενάρια διατηρούνται στοmetrics.csv.','',
        'Οι έξι παλιές σειρές είναι τα επαληθευμένα αποτελέσματα017, επαναχρησιμοποιημένα χωρίς νέες εκτελέσεις. Η μέγιστη DD μπορεί να προέρχεται από διαφορετικό σενάριο από το χειρότερο κέρδος. Τα χρηματικά ποσά DD υπολογίζονται από το πραγματικό peak και trough της καμπύλης, όχι από το αρχικό κεφάλαιο.','',
        '## Επιλογή πριν από την αξιολόγηση και walk-forward','',
        'Εκπαίδευση2023 → '+a['selection']['selected']+'. Εκπαίδευση2023–2024 → '+b['selection']['selected']+'. Και οι δύο επιλογές δημοσιεύθηκαν πριν από τις αντίστοιχες αξιολογήσεις. Η πρώτη είναι και η στατική επιλογή για ολόκληρο2024–2025.','',
        '| Walk-forward | Καθαρό αποτέλεσμα | DD | Έξοδοι | Αποτυχημένα κριτήρια |','|---|---|---|---|---|']
    for key,v in e['walk_forward'].items():
        m=v.get('metrics',{})
        lines.append('|'+key+'|'+n(m['net_return_pct'])+'% / '+n(m['net_profit_usdt'])+' USDT|'+n(m['max_drawdown_pct'])+'% / '+n(m['cash_at_max_pct_drawdown_usdt'])+' USDT|'+str(m['signal_exits'])+'|'+', '.join(v['failed_gates'])+'|')
    lines+=['','Το walk-forward κλείνει τη θέση στο τέλος κάθε έτους, χρεώνει την έξοδο και μεταφέρει ακριβώς το υπόλοιπο στο επόμενο. Δεν κάνει ανανέωση κεφαλαίου. Κάθε νέα επιλογή χρησιμοποιεί μόνο προηγούμενα έτη. Οι δύο περίοδοι και τα παλιά τεστ μοιράζονται το ίδιο ιστορικό, άρα δεν αποτελούν ανεξάρτητη επιβεβαίωση.','',
        '## Κόστη, αναφορές και περιορισμοί','',
        'Βασικό ανά πλευρά:5,5bpsπρομήθεια+2bpsολίσθηση. Αυξημένο:10+10bps. Διαχειριστικό έξοδο120USDT/έτος και πραγματικές ιστορικές χρεώσεις funding, με τιμή mark ανοίγματος ώρας ως προσέγγιση και ξεχωριστή δυσμενή μετατόπιση5bps. Τα προσωπικά fees και τα ιστορικά orderbooks/ακριβή fills παραμένουν άγνωστα. Long/flat,50%ανώτατη έκθεση εισόδου, πλήρης κάλυψη με μετρητά· δεν υπάρχει μοντέλο μοχλευμένης εκκαθάρισης.','',
        'Αδρανή μετρητά:0%,0USDT,χωρίς διαχειριστικό έξοδο. Τα50%buy-and-holdperpetual πληρώνουν ίδιες προμήθειες,fundingκαι120USDT/έτος. Η αυτόματη παρακολούθηση walk-forward χρεώνει το έξοδο ακόμη και όταν επιλέγει μετρητά.','',
        '| Benchmark | Απόδοση | DD |','|---|---|---|']
    for key,r in e['reused017_benchmarks'].items():
        m=r['metrics'];lines.append('|'+key+'|'+n(m['net_return_pct'])+'% / '+n(m['net_profit_usdt'])+' USDT|'+n(m['max_drawdown_pct'])+'% / '+n(m['cash_at_max_pct_drawdown_usdt'])+' USDT|')
    lines+=['','Κάλυψη:35.064ωριαίες τιμές συναλλαγών και35.064mark,4.383fundingevents,2022–2025. Πλήρης προγραμματισμένη κάλυψηETH για αυτό το διάστημα· δεν σημαίνει πλήρη αγορά ή τρέχουσα ρευστότητα. BTC/LTC παραμένουν εκτός λόγω των προηγούμενων συγκεκριμένων περιορισμών πρόσβασης/κενών. Δεν έχει εντοπιστεί το ενιαίο BYBIT_SEND_THIS.zip. Διατηρούνται οι ήδη πραγματικές36μετρήσεις βιβλίου και600fundingeventsBybit, χωρίς εξαγωγή κέρδους στρατηγικής από αυτές.','',
        '## Πολλαπλές συγκρίσεις','']
    for key,v in e['multiplicity'].items():
        lines.append('- '+key+': exploratoryp='+str(v['family_adjusted_p_exploratory'])+'.')
    lines+=['','Ο έλεγχος περιλαμβάνει τις8συμβατές nativefuturesπαραλλαγές και τα έξοδα. Οι40άλλες έχουν ασύμβαταspotδεδομένα. Δεν διορθώνει ολόκληρη την προηγούμενη αναζήτηση ή τις επιλογές σχεδιασμού, δεν είναι πλήρεςPBOκαι δεν αποτελεί στατιστική επιβεβαίωση.','',
        'Παλαιό θετικό εύρημα:OBVείχε θετικό αποτέλεσμα και στα12σενάρια017,αλλά λίγες εξόδους. Ο έλεγχος018έδειξε ότι χωρίς τη μεγαλύτερη κερδοφόρα συναλλαγή το στατικό υπόλοιπο βασικού αποτελέσματος ήταν−98,73USDT. Αυτό διατηρείται ως ένδειξη συγκέντρωσης, όχι ως νέα εκτέλεση ή τροποποιημένη στρατηγική.','',
        f"Επαλήθευση:{verification['new_files_verified']}πλήρη νέα αποτελέσματα,{verification['new_wealth_events']}ανεξάρτητοι λογιστικοί έλεγχοι συμβάντων,μέγιστη απόκλιση{verification['maximum_decimal_discrepancy_usdt']}USDT.111softwaretests,33νέα. Όλα τα487προϋπάρχοντα προστατευμένα αρχεία διατηρήθηκαν. Μία αποτυχία εισαγωγής testmodule διορθώθηκε πριν από τοfreeze και καταγράφηκε. Τέσσερα αρχεία βρέθηκαν μηδενικού μεγέθους μετά την αρχική καταγραφή τους. Τα διατηρήσαμε και ανακατασκευάσαμε μόνο αυτά, με απολύτως ίδια αρχικάSHA256. Η αιτία παραμένει άγνωστη. Ένα ανακατασκευασμένο αρχείο έγινε ξανά κενό. Ακολούθησε μία ακόμη, ξεχωριστά προεγγεγραμμένη ανακατασκευή με διαφορετική αποθήκευση και ακριβή επαλήθευση. Συνολικά5επαναλήψεις αποκατάστασης, δύο διατηρημένες αποτυχίες· κανένα αποτέλεσμα ή κανόνας δεν άλλαξε.",'',
        'Επόμενο περιορισμένο βήμα:προτεραιότητα στον έλεγχο του ενιαίουBybitπακέτου και στο αμετάβλητο013. Αν ακόμη λείπει, μία ξεχωριστά προεγγεγραμμένη επέκταση σε διαφορετικό χρονικό τμήμα επίσημωνnativefuturesδεδομένων για εξωτερικό έλεγχο των παγωμένων κανόνων· χωρίς αλλαγή παραμέτρων ή χαρακτηρισμό ως μελλοντικής απόδειξης.','',
        'Κανένας αυτόματος χαρακτηρισμός επιβεβαιωμένης κερδοφορίας:το μελλοντικό ορόσημο απαιτεί τουλάχιστον180ημερολογιακές ημέρες και20ολοκληρωμένες εξόδους,θετικό καθαρό και στα δύο κόστη,DD≤35%,κάλυψη≥95%και κανένα σφάλμα ακεραιότητας. Ακόμη κι αυτό είναι ορόσημο παρακολούθησης,όχι άδεια πραγματικών συναλλαγών.','',
        '## Πηγές και αναπαραγωγή','',
        '- Μηχανισμόςfunding:https://www.binance.com/en/support/faq/detail/360033525031 (ανάγνωση17/10/2026,ενημέρωσησελίδας6/3/2026). Η στρατηγική είναι δική μας ερευνητική υπόθεση,όχι συμπέρασμα της πηγής.',
        '- Επίσημααρχεία:https://github.com/binance/binance-public-data . Προσωπική μη παραγωγική έρευνα με τους όρους του datasetCCBY-NC-SA4.0· καμία έγκριση από τοανταλλακτήριο.',
        '- Προειδοποίησηπολλαπλώνδοκιμών:https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf (Baileyetal.,27/2/2015).',
        '- Freeze:'+BASE+'/commit/4119be986ec89e9ab5288aaa3e3121a8a99d7ce3',
        '- Επιλογή2023:'+BASE+'/commit/ba36d9cd4621d3bb81807a3127e3ee85b78c97d0',
        '- Επιλογή2023–2024:'+BASE+'/commit/83a0b9f8f1d7ffb44c0342a601178b957078cdd5','',
        'Exactmetadata:research/experiments/019/{freeze,selection1,selection2,evaluation,summary,verification,full_result_hashes}.json καιmetrics.csv. Οι εντολές αναπαραγωγής περιλαμβάνονται στοREPRODUCE.md. Όλα τα αποτελέσματα/αποτυχίες διατηρούνται.']
    lines = [re.sub(r'(?<=[Α-Ωα-ωά-ώ])(?=[0-9A-Za-z])|(?<=[0-9A-Za-z])(?=[Α-Ωα-ωά-ώ])', ' ', line)
             .replace('softwaretests', 'έλεγχοι λογισμικού').replace('nativefutures', 'native futures')
             .replace('buy-and-holdperpetual', 'buy-and-hold perpetual')
             .replace('Exactmetadata:', 'Ακριβή δεδομένα: ') for line in lines]
    md='\n'.join(lines)+'\n'
    (ROOT/'docs/FUNDING_FUTURES_019_RESULTS.md').write_text(md)
    # Simple accessible self-contained report; tables preserve exact comparisons.
    body=[];table=False;ul=False
    for line in lines:
        if line.startswith('|'):
            if line.startswith('|---'):continue
            if not table:body.append('<div class="scroll"><table>');table=True
            tag='th' if 'Παραλλαγή' in line or 'Walk-forward' in line or 'Benchmark' in line else 'td'
            body.append('<tr>'+''.join('<'+tag+'>'+html.escape(x)+'</'+tag+'>' for x in line.strip('|').split('|'))+'</tr>')
        else:
            if table:body.append('</table></div>');table=False
            if line.startswith('# '):body.append('<h1>'+html.escape(line[2:])+'</h1>')
            elif line.startswith('## '):body.append('<h2>'+html.escape(line[3:])+'</h2>')
            elif line:body.append('<p>'+html.escape(line)+'</p>')
    if table:body.append('</table></div>')
    report=WORK/'Futures_019_Funding_EL.html'
    report.write_text('<!doctype html><html lang="el"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+heading+'</title><style>body{font:16px/1.6 system-ui,sans-serif;max-width:1150px;margin:32px auto;padding:0 20px;color:#172838;background:#f8fafc}h1{font-size:30px}h2{margin-top:34px}.scroll{overflow:auto;background:white;border:1px solid #ccd6df;border-radius:8px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:10px;border-bottom:1px solid #ddd;text-align:left}th{background:#e8f0f7}p{overflow-wrap:anywhere}@media print{body{margin:0;font-size:11px}.scroll{overflow:visible}table{font-size:9px}}</style><main>'+''.join(body)+'</main></html>')
    print(json.dumps({'summary':str(OUT/'summary.json'),'report':str(report),'verification':verification},ensure_ascii=False))


if __name__=='__main__':main()

