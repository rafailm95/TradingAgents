"""Build the experiment007 Greek HTML report and evidence bundle, offline.

Reporting only; requires matplotlib in addition to the research dependencies.
Usage: python scripts/report_strategy_families.py --results DIR --output DIR
"""
import argparse
import hashlib
import html
import io
import json
import zipfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def build(results, output):
    s = json.loads((results/"summary.json").read_text())
    protocol = json.loads((results/"protocol.json").read_text())
    register = json.loads((results/"experiment_register.json").read_text())
    metrics = {(m["id"],m["window"],m["cost"]):m for m in s["metrics"]}
    esc = html.escape
    ids = [a["id"] for a in s["assessments"]]
    assessments = {a["id"]:a for a in s["assessments"]}
    passed = [a["id"] for a in s["assessments"] if a["historical_screen_pass"]]
    robust = [a["id"] for a in s["assessments"] if a["delay_robust_screen_pass"]]
    def m(cid,window="evaluation",cost="stress"):
        return metrics[cid,window,cost]
    def pct(value):
        return f"{value:+.2f}%"
    def table(headers,rows):
        return '<div class="scroll"><table><thead><tr>'+''.join(f'<th>{esc(x)}</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{x}</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'
    chart_ids = sorted(ids,key=lambda c:m(c)["return_after_operating_pct"])
    fig, ax = plt.subplots(figsize=(10,10.8),layout="constrained")
    y = np.arange(len(chart_ids))
    ax.barh(y+.18,[m(c,cost="base")["return_after_operating_pct"] for c in chart_ids],.35,color="#267d91",label="Base costs")
    ax.barh(y-.18,[m(c)["return_after_operating_pct"] for c in chart_ids],.35,color="#d76c38",label="Stress costs")
    ax.set_yticks(y,[c.replace("__vol15_cap50"," · vol15 cap50").replace("__fixed50"," · fixed50") for c in chart_ids],fontsize=9)
    ax.axvline(0,color="#25364b",lw=.8)
    ax.set_xlabel("Cumulative return after trading costs and $120/year operating expense (%)")
    ax.set_title("24 new variants · BTC/USD · 2024-01-01 to 2026-10-15",loc="left",pad=14)
    ax.grid(axis="x",alpha=.2);ax.set_axisbelow(True);ax.legend(loc="lower right")
    for side in ("top","right","left"): ax.spines[side].set_visible(False)
    chart=io.StringIO();fig.savefig(chart,format="svg",metadata={"Date":None});plt.close(fig)
    svg=chart.getvalue();svg=svg[svg.index('<svg'):]
    summary_rows=[]
    for cid in ids:
        a=assessments[cid]
        worst=min(x["return_after_operating_pct"] for x in s["delay_metrics"] if x["id"]==cid and x["cost"]=="stress")
        summary_rows.append([esc(cid),pct(m(cid,"full","base")["return_after_operating_pct"]),pct(m(cid,"full")["return_after_operating_pct"]),
            f'{m(cid,"full")["max_close_drawdown_pct"]:.2f}%',str(m(cid,"full")["closed_trades"]),
            pct(m(cid,"validation")["return_after_operating_pct"]),pct(m(cid,"recent")["return_after_operating_pct"]),str(m(cid,"recent")["closed_trades"]),
            pct(m(cid,cost="base")["return_after_operating_pct"]),pct(m(cid)["return_after_operating_pct"]),pct(worst),
            '<span class="pass">Αρχικό: πέρασε</span>' if a["historical_screen_pass"] else 'Αρχικό: απέτυχε'])
    summary_table=table(["Παραλλαγή","2020–26 βασικό","2020–26 αυξημένο","Πτώση 2020–26 αυξημένο","Συναλλαγές 2020–26","2024–25 αυξημένο","2026 αυξημένο","Συναλλαγές 2026","2024–26 βασικό","2024–26 αυξημένο","Χειρότερη καθυστέρηση αυξημένο","Αρχικό φίλτρο"],summary_rows)
    delay_rows=[]
    for cid in passed:
        vals={(x["lag"],x["cost"]):x for x in s["delay_metrics"] if x["id"]==cid}
        delay_rows.append([esc(cid),pct(m(cid)["return_after_operating_pct"]),pct(vals[1,"stress"]["return_after_operating_pct"]),pct(vals[2,"stress"]["return_after_operating_pct"])])
    delay_table=table(["Αρχικά θετική παραλλαγή","Χωρίς επιπλέον καθυστέρηση","+1 ημέρα σήματος","+2 ημέρες σήματος"],delay_rows)
    selected=s["selection"]["selected"]
    compare=[selected,"sma200_band__vol15_cap50","breakout20__vol15_cap50","buy_hold50","cash"]
    comparison=table(["Στρατηγική / σημείο αναφοράς","2024–26 βασικό","2024–26 αυξημένο","Πτώση αυξημένο","Συναλλαγές"],[[esc(c),pct(m(c,cost="base")["return_after_operating_pct"]),pct(m(c)["return_after_operating_pct"]),f'{m(c)["max_close_drawdown_pct"]:.2f}%',str(m(c)["closed_trades"])] for c in compare])
    wf=table(["Έτος","Επιλογή πριν το έτος","Βασικό","Αυξημένο"],[[str(f["year"]),esc(f["selected"]),pct(f["base_return_after_operating_pct"]),pct(f["stress_return_after_operating_pct"])] for f in s["walk_forward_choices"]])
    family_labels={"kama_trend":"Προσαρμοζόμενος μέσος KAMA","keltner_breakout":"Διάσπαση καναλιού Keltner","adx_directional":"Κατεύθυνση και ισχύς τάσης ADX","ichimoku_trend":"Τάση Ichimoku","aroon_trend":"Πρόσφατα υψηλά και χαμηλά Aroon","regression_trend":"Κλίση γραμμικής παλινδρόμησης","cmo_momentum":"Ορμή Chande CMO","stochastic_pullback":"Υποχώρηση με Stochastic","cci_reversion":"Επιστροφή με CCI","squeeze_breakout":"Διάσπαση μετά από συμπίεση μεταβλητότητας","obv_breakout":"Διάσπαση με όγκο OBV","cmf_trend":"Ροή όγκου CMF και τάση"}
    families=table(["Οικογένεια","Κωδικός"],[[esc(label),esc(code)] for code,label in family_labels.items()])
    failures=''.join('<details><summary>'+esc(a["id"])+f' · {len(a["failed"])} αρχικές αποτυχίες, {len(a["delay_failed"])} αποτυχίες καθυστέρησης</summary><pre>'+esc(json.dumps({"initial_failed":a["failed"],"delay_failed":a["delay_failed"]},indent=2))+'</pre></details>' for a in s["assessments"])
    bootstrap=table(["Σημείο αναφοράς","Μπλοκ ημερών","Διερευνητικό p"],[[x["benchmark"],str(x["block_days"]),f'{x["family_adjusted_p_exploratory"]:.3f}'] for x in s["multiplicity"]])
    raw_table=table(["Παραλλαγή","Ομάδα","Περίοδος","Κόστος","Καθαρή απόδοση","Μέγιστη πτώση","Συναλλαγές"],[[esc(x["id"]),x["cohort"],x["window"],x["cost"],pct(x["return_after_operating_pct"]),f'{x["max_close_drawdown_pct"]:.2f}%',str(x["closed_trades"])] for x in s["metrics"]])
    tests=(output/"strategy-families-tests.txt").read_text()
    css='''*{box-sizing:border-box}body{font-family:system-ui,sans-serif;color:#203248;background:#f1f4f8;margin:0;line-height:1.6}main{max-width:1180px;margin:auto;padding:28px 24px 70px}h1{font-size:clamp(28px,5vw,45px);line-height:1.15;letter-spacing:-1px}h2{font-size:23px;margin-top:36px}p{max-width:950px}header{border-bottom:3px solid #267d91;padding-bottom:16px}.eyebrow{letter-spacing:2px;font-size:12px;font-weight:700;color:#267d91}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:24px 0}.card{background:white;border-radius:10px;padding:18px;border:1px solid #d9e1ea}.card strong{font-size:32px;display:block}.callout{background:#fff2e5;border-left:5px solid #d76c38;padding:16px 20px}.muted{color:#52677c;font-size:14px}.scroll{overflow:auto;border:1px solid #d8e0e9;border-radius:8px;background:white;margin:16px 0}table{border-collapse:collapse;width:100%;font-size:13px}td,th{text-align:right;padding:10px 12px;border-bottom:1px solid #e3e8ef;white-space:nowrap}th{background:#e7edf4;color:#233f5b}td:first-child,th:first-child{text-align:left}tr:hover{background:#edf6f8}.pass{color:#17695b;font-weight:700}details{background:#fff;border:1px solid #d8e0e9;border-radius:6px;margin:9px 0;padding:12px}summary{cursor:pointer;font-weight:600}pre{font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere}code{font-size:12px;overflow-wrap:anywhere}a{color:#14677e}input{font:inherit;width:100%;max-width:600px;padding:10px;border:1px solid #b5c3d0;border-radius:6px}.chart{background:white;border-radius:10px;padding:8px;overflow:auto}.chart svg{width:100%;height:auto;min-width:650px}li{margin:6px 0}footer{border-top:1px solid #bdccd8;margin-top:36px;padding-top:12px}@media(max-width:650px){main{padding:20px 14px}.cards{grid-template-columns:repeat(2,1fr)}.card{padding:12px}h2{font-size:21px}}'''
    doc=f'''<!doctype html><html lang="el"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TradingBot · 24 νέες παραλλαγές</title><style>{css}</style></head><body><main>
<header><p class="eyebrow">TRADINGAGENTS / ΙΣΤΟΡΙΚΟ ΠΕΙΡΑΜΑ 007 / 16 ΟΚΤΩΒΡΙΟΥ 2026</p><h1>24 νέες παραλλαγές.<br>Πέντε αρχικές επιτυχίες, καμία πλήρως ανθεκτική.</h1><p>Προστέθηκαν 12 οικογένειες σε δύο μεγέθη θέσης και συγκρίθηκαν με τις 16 προηγούμενες παραλλαγές. Το αποτέλεσμα είναι ολοκληρωμένο ιστορικό πείραμα· δεν αποτελεί πραγματικό κέρδος ή πρόβλεψη εισοδήματος.</p></header>
<div class="cards"><div class="card"><strong>24</strong>νέες παραλλαγές</div><div class="card"><strong>{len(passed)}/24</strong>πέρασαν το αρχικό φίλτρο</div><div class="card"><strong>{len(robust)}/24</strong>πέρασαν και τις καθυστερήσεις</div><div class="card"><strong>{s['audit_cases']:,}</strong>προσομοιώσεις και έλεγχοι υπολοίπων</div></div>
<div class="callout"><strong>Κύριο εύρημα:</strong> το θετικό ιστορικό αποτέλεσμα αρκετών στρατηγικών χάνεται με μεγαλύτερα κόστη ή με καθυστέρηση των σημάτων. Δεν προστέθηκε νέα στρατηγική στην παγωμένη, προγραμματισμένη παρακολούθηση των δύο προηγούμενων υποψηφίων.</div>
<p class="muted">BTC-USD / Coinbase / ημερήσια OHLCV 01/01/2019–15/10/2026, 2.845 κεριά. Οι αποδόσεις ξεκινούν από 01/01/2020. Όλα αυτά τα δεδομένα έχουν ήδη χρησιμοποιηθεί σε προηγούμενη έρευνα: οι μεταγενέστερες περίοδοι δεν είναι αθέατο, ανεξάρτητο δείγμα.</p>
<h2>Η επιλογή πριν από την αξιολόγηση</h2><p>Με βάση μόνο το διάστημα 2020–2023, επιλέχθηκε η <strong>{esc(selected)}</strong>. Στο 2024–15/10/2026 απέδωσε <strong>{pct(m(selected,cost='base')['return_after_operating_pct'])}</strong> με βασικά κόστη και <strong>{pct(m(selected)['return_after_operating_pct'])}</strong> με αυξημένα. Το 2026 μόνο έδωσε {pct(m(selected,'recent','base')['return_after_operating_pct'])} / {pct(m(selected,'recent')['return_after_operating_pct'])} αντίστοιχα.</p>{comparison}
<p class="muted">Τα ποσοστά είναι συνολικά για την περίοδο, όχι ετήσια. Το buy_hold50 ξεκινά με 50% σε BTC και δεν επαναφέρει το βάρος. Δεν είναι εξισωμένο ως προς τον κίνδυνο με κάθε υποψήφιο. Οι δείκτες αναφοράς cash/buy-hold δεν χρεώνονται το ετήσιο λειτουργικό έξοδο.</p>
<h2>Ποιες οικογένειες προστέθηκαν</h2>{families}<p>Κάθε οικογένεια εξετάστηκε με <code>fixed50</code>: 50% των διαθέσιμων μετρητών ανά είσοδο, και <code>vol15_cap50</code>: μικρότερη θέση όταν αυξάνεται η πρόσφατη μεταβλητότητα, με ανώτατο αρχικό ποσοστό 50%. Το βάρος μεταβάλλεται με την τιμή· δεν εγγυάται κίνδυνο 15% ή διαρκές όριο 50%.</p>
<h2>Όλες οι νέες παραλλαγές, χωρίς απόκρυψη αποτυχιών</h2><p>Το γράφημα αφορά 01/01/2024–15/10/2026. Τα αποτελέσματα περιλαμβάνουν τις συναλλακτικές χρεώσεις και το λειτουργικό κόστος.</p><div class="chart">{svg}</div>
<p><label for="filter">Φίλτρο ονόματος στρατηγικής:</label><br><input id="filter" type="search" placeholder="π.χ. aroon ή vol15"></p><div id="candidate-table">{summary_table}</div>
<p class="muted">Πτώση = μέγιστη πτώση ημερήσιου υπολοίπου πριν από την εξωτερική αφαίρεση του λειτουργικού κόστους. Η πλήρης περίοδος είναι 2020–15/10/2026. Το 2026 είναι έως 15 Οκτωβρίου. Οι πέντε αρχικές επιτυχίες βασίζονται σε μόλις 1–2 κλεισμένες συναλλαγές στο 2026.</p>
<h2>Γιατί οι πέντε αρχικές επιτυχίες δεν περνούν το πλήρες φίλτρο</h2><p>Με αυξημένα κόστη στο 2024–15/10/2026, όλες γίνονται ζημιογόνες σε τουλάχιστον μία καθυστέρηση σήματος:</p>{delay_table}
<p>Η δοκιμή μεταφέρει μαζί το σήμα εισόδου, το σήμα εξόδου και την πληροφορία μεταβλητότητας κατά μία ή δύο ημέρες. Τα χρονικά όρια κατοχής μετρούν από την πραγματική είσοδο, ενώ η τελική ρευστοποίηση διατηρεί την ίδια ημερομηνία. Πρόκειται για έλεγχο ευαισθησίας σε καθυστερημένα σήματα, όχι για προσομοίωση βιβλίου εντολών ή πραγματικής διακοπής υπηρεσίας.</p>
<p>Η εκ των υστέρων υψηλότερη νέα απόδοση στην περίοδο αξιολόγησης ήταν της <code>regression_trend__fixed50</code>: {pct(m('regression_trend__fixed50')['return_after_operating_pct'])} με αυξημένα κόστη. Δεν περνά: έχει μόνο 17 πλήρεις ιστορικές συναλλαγές αντί των απαιτούμενων 20 και πλήρη πτώση {m('regression_trend__fixed50','full')['max_close_drawdown_pct']:.2f}% αντί ορίου 35%. Η έκδοση με μεταβλητό μέγεθος θέσης επίσης έχει μόνο 17 συναλλαγές. Τα κριτήρια δεν χαλάρωσαν μετά το αποτέλεσμα.</p>
<h2>Ετήσια επιλογή με προηγούμενα δεδομένα</h2><p>Για κάθε έτος από το 2022, η επιλογή έγινε με τα διαθέσιμα ιστορικά δεδομένα έως το προηγούμενο έτος. Σε κάθε αλλαγή έτους έκλεινε η θέση και μεταφερόταν το υπόλοιπο μετά το λειτουργικό έξοδο. Η διαδικασία επέλεξε CMF vol15 και στα πέντε έτη.</p>{wf}
<p>Συνολικά 2022–15/10/2026: <strong>{pct(s['walk_forward_summary']['base']['net_return_after_operating_pct'])}</strong> βασικό και <strong>{pct(s['walk_forward_summary']['stress']['net_return_after_operating_pct'])}</strong> αυξημένο κόστος. Μέγιστη ημερήσια πτώση μετά τις ετήσιες χρεώσεις: {s['walk_forward_summary']['base']['max_close_drawdown_after_operating_pct']:.2f}% / {s['walk_forward_summary']['stress']['max_close_drawdown_after_operating_pct']:.2f}%. Τα 2022, 2025 και 2026 ήταν αρνητικά. Η διαφορετική αφετηρία κεφαλαίου και οι ετήσιες επανεκκινήσεις εξηγούν γιατί τα αποτελέσματα διαφέρουν από τις ανεξάρτητες περιόδους του πίνακα.</p>
<h2>Πολλαπλές δοκιμές και αβεβαιότητα</h2><p>Ο κοινός διερευνητικός έλεγχος περιλαμβάνει και τις 40 παραλλαγές, με 2.000 επαναδειγματοληψίες κοινών χρονικών μπλοκ. Σε σύγκριση με μετρητά, το p είναι περίπου 0,174–0,204: δεν προκύπτει συμβατική στατιστική ένδειξη υπεροχής στο επίπεδο 5% με αυτόν τον συγκεκριμένο έλεγχο. Σε σύγκριση με buy_hold50, καμία δεν έχει θετικό μέσο ημερήσιο αριθμητικό πλεονέκτημα στην περίοδο αξιολόγησης· αυτό δεν συγκρίνει ισότιμο κίνδυνο.</p>{bootstrap}
<p class="muted">Ο έλεγχος περιλαμβάνει συναλλακτικά κόστη, αλλά όχι το εξωτερικό λειτουργικό κόστος. Δεν διορθώνει όλα τα παλαιότερα πειράματα ή τις ανθρώπινες επιλογές σχεδιασμού. Δεν είναι υπολογισμός πλήρους Probability of Backtest Overfitting και δεν αποδεικνύει μελλοντική κερδοφορία.</p>
<h2>Παραδοχές και τεχνική επαλήθευση</h2><ul><li>Αρχικό υποθετικό κεφάλαιο $10.000 ανά ανεξάρτητη προσομοίωση· χωρίς δανεισμό ή short.</li><li>Σήμα στο κλείσιμο, εκτέλεση στο επόμενο άνοιγμα. Οι τιμές εκτέλεσης είναι ιδεατές με δυσμενή ολίσθηση· δεν μοντελοποιούνται διαθέσιμη ρευστότητα ή μερική εκτέλεση.</li><li>Ανά πλευρά: βασικό κόστος 0,60% προμήθεια + 0,10% ολίσθηση· αυξημένο 1,20% + 0,25%. Εξετάστηκαν επίσης μηδενικά κόστη και 0,10% + 0,05%. Πρόκειται για παραδοχές, όχι τιμοκατάλογο λογαριασμού.</li><li>Λειτουργικό κόστος $120/έτος, αναλογικά στις ημέρες και πριν από φόρους. Δεν αφαιρείται από το ημερήσιο ταμείο του βασικού πίνακα αλλά στο τέλος της περιόδου.</li><li>Η πτώση βασίζεται στα ημερήσια κλεισίματα και μπορεί να υποτιμά τις ενδοημερήσιες απώλειες. Τα δεδομένα όγκου αφορούν μόνο Coinbase.</li><li>{register['focused_tests']} εστιασμένοι έλεγχοι πέρασαν, {register['new_tests']} νέοι. Έλεγχοι αιτιότητας, γνωστών αριθμητικών περιπτώσεων, χρονισμού και λογιστικής διατήρησης.</li><li>{s['audit_cases']:,} έλεγχοι υπολοίπων σε {s['audit_days']:,} ημέρες προσομοίωσης, μέγιστη απόκλιση {s['max_audit_usd_error']:.3g} USD.</li><li>Οι 400 προηγούμενες προσομοιώσεις αναπαράχθηκαν ακριβώς, σε ολόκληρα ημερήσια υπόλοιπα και συναλλαγές. Τα 14 παγωμένα αρχεία της προγραμματισμένης παρακολούθησης παρέμειναν ίδια.</li><li>Μία εκτέλεση ιστορικού πειράματος, μηδέν αλλαγές κανόνων λόγω κερδοφορίας, μηδέν πραγματικές εντολές ή κλήσεις μοντέλων από τον ερευνητικό κώδικα.</li></ul>
<details><summary>Αποτελέσματα ελέγχων λογισμικού</summary><pre>{esc(tests)}</pre></details>
<h2>Αναλυτικά αρχεία και δυνατότητα αναπαραγωγής</h2><p>Το συνοδευτικό ZIP περιλαμβάνει 880 πλήρεις βασικές προσομοιώσεις, 96 καθυστερημένες, 240 προσομοιώσεις εκπαίδευσης ανά ετήσιο βήμα, 10 ετήσια χαρτοφυλάκια, όλες τις συναλλαγές, τα ημερήσια υπόλοιπα, τα αποτυπώματα αρχείων και τις ακριβείς παραδοχές. Περιλαμβάνει επίσης την ανάλυση συγκέντρωσης των κερδών στις μεγαλύτερες συναλλαγές.</p>
<details><summary>Οι 880 συνοπτικές εγγραφές: νέες, προηγούμενες και δείκτες αναφοράς</summary>{raw_table}</details>
<details><summary>Κάθε αποτυχημένο κριτήριο ανά παραλλαγή</summary>{failures}</details>
<details><summary>Παγωμένο πρωτόκολλο και ακριβείς μαθηματικοί κανόνες</summary><pre>{esc(json.dumps(protocol,indent=2,ensure_ascii=False))}</pre></details>
<details><summary>Συγκέντρωση κερδών και ετήσιες αποδόσεις πλήρων καμπυλών</summary><p>Η αφαίρεση του μεγαλύτερου κερδοφόρου trade είναι λογιστική απόδοση συνεισφοράς, όχι νέο backtest με επανυπολογισμό θέσεων.</p><pre>{esc(json.dumps(s['diagnostics'],indent=2))}</pre></details>
<details><summary>Πηγές μεθοδολογίας</summary><p>Οι πηγές εξηγούν τους δείκτες και τον κίνδυνο υπερπροσαρμογής. Οι συγκεκριμένοι συνδυασμοί, σπόροι, όρια και κανόνες ορίζονται από το πρωτόκολλο και δεν αποτελούν ισχυρισμό ότι εφαρμόστηκε κάποια έτοιμη εμπορική στρατηγική.</p><ul>{''.join('<li><a href="'+esc(u)+'">'+esc(u)+'</a></li>' for u in protocol['references'])}</ul></details>
<details><summary>Κατάσταση εργασίας</summary><pre>RESOLVED: 12 νέες οικογένειες, 24 παραλλαγές, 1.226 προσομοιώσεις, 266 tests.
OPEN: Ανεξάρτητη μελλοντική ένδειξη κερδοφορίας για τις νέες οικογένειες.
IMPLEMENTATION_READY: Ναι, για αναπαραγωγή ιστορικής έρευνας.
MATERIAL_BLOCKER: Καμία νέα παραλλαγή δεν περνά το πλήρες παγωμένο φίλτρο.
NEXT_IMPLEMENTATION_SLICE: Συνέχιση της ήδη προγραμματισμένης παρακολούθησης των δύο αρχικών υποψηφίων· καμία αυτόματη προσθήκη νέου υποψηφίου.
DONE_CONDITION: Πλήρης πίνακας, έλεγχοι καθυστέρησης/λογιστικής, αναφορά και αποδεικτικά παραδομένα.
EXECUTION_ENVIRONMENT: Python3.12.14 / numpy2.3.5 / pandas2.2.3 / τοπική ιστορική έρευνα.
REQUIRED_MODE: Research + frozen paper observation. No real orders.</pre></details>
<footer class="muted">Πρωτόκολλο SHA256: <code>{s['protocol_sha256']}</code><br>Δεδομένα SHA256: <code>{s['csv_sha256']}</code><br>Η έρευνα τελείωσε χωρίς νέα προσθήκη στη λίστα εικονικής παρακολούθησης.</footer>
</main><script>document.getElementById('filter').addEventListener('input',function(){{const q=this.value.toLowerCase();document.querySelectorAll('#candidate-table tbody tr').forEach(r=>r.hidden=!r.cells[0].textContent.toLowerCase().includes(q));}});</script></body></html>'''
    target=output/"TradingBot_24_New_Strategies_EL.html"
    target.write_text(doc,encoding="utf-8")
    md=f'''# Strategy families experiment007 — completed

Added12 families ×2 entry sizes =24 variants; compared against legacy16 and4 benchmarks. One fixed historical run; no result-driven tuning. All historical dates had already been inspected, so chronological evaluation is not a blind holdout.

- 880 matrix +96 signal-delay +240 WFA training +10 annual ledgers =1,226 audited simulations.
- {s['audit_days']:,} daily audit points; maximum reconciliation error {s['max_audit_usd_error']:.3g} USD.
- 266 focused tests passed (54new); 400 legacy ledgers reproduced exactly. Full application CI not claimed.
- Train2020–2023 selected `{selected}`: evaluation2024–2026-10-15 after operating expense {pct(m(selected,cost='base')['return_after_operating_pct'])} base / {pct(m(selected)['return_after_operating_pct'])} stress.
- Five historical screen passes: {', '.join('`'+c+'`' for c in passed)}. All fail at least one delay case;0 complete passes.
- WFA2022–2026-10-15 net after annual expense: {pct(s['walk_forward_summary']['base']['net_return_after_operating_pct'])} base / {pct(s['walk_forward_summary']['stress']['net_return_after_operating_pct'])} stress. Negative2022,2025,2026.
- Conditional40-candidate bootstrap p versuscash0.174–0.204; no positive arithmetic-mean excess overbuy_hold50. Not full prior-search correction, not risk matching, and excludes operating expense.
- No new paper candidates, real orders, paid models, or scheduled campaign changes.

## All24 results

Returns include transaction costs and external operating assumption120USD/year on initial10000USD. Matrix drawdown is close-only, before external expense. All returns are cumulative, not annualized.

| Candidate |2024–26 base|2024–26 stress|Worst delayed stress|Initial screen|
|---|---:|---:|---:|---|
'''
    for cid in ids:
        worst=min(x["return_after_operating_pct"] for x in s["delay_metrics"] if x["id"]==cid and x["cost"]=="stress")
        md+=f"|{cid}|{pct(m(cid,cost='base')['return_after_operating_pct'])}|{pct(m(cid)['return_after_operating_pct'])}|{pct(worst)}|{'PASS' if assessments[cid]['historical_screen_pass'] else 'FAIL'}|\n"
    md+='''
## Reproduce

```bash
python -m pip install -r requirements-research.txt
python scripts/run_strategy_families.py --csv /absolute/path/btc_coinbase_daily.csv --output /absolute/path/new-result-directory
python -m pytest --noconftest tests/test_strategy_families.py tests/test_strategy_lab.py -q
```

The runner requires the exact CSV and protocol hashes. Existing output directories are rejected. It verifies all14 pinned paper-campaign sources unchanged. No network calls in the runner. The separate HTML reporting script additionally requires matplotlib, a completed experiment register and the test log; it is not part of the scheduled runtime.

RESOLVED: Frozen12-family experiment, complete failure retention and ledger audits.
OPEN: Independent future evidence for new families.
IMPLEMENTATION_READY: Historical research reproduction only.
MATERIAL_BLOCKER: No new candidate passes every frozen criterion.
NEXT_IMPLEMENTATION_SLICE: Preserve and continue existing two-candidate scheduled observation.
DONE_CONDITION: Reproducible results, tests, report and evidence delivered.
EXECUTION_ENVIRONMENT: Python3.12.14, numpy2.3.5, pandas2.2.3.
REQUIRED_MODE: Research and frozen paper observation; no orders.
'''
    repo=Path(__file__).resolve().parents[1]
    (repo/"docs/STRATEGY_FAMILIES_RESULTS.md").write_text(md)
    (results/"README.md").write_text(md)
    (results/"software_tests.txt").write_text(tests)
    # Inventory excludes itself and all version-controlled code; evidence is data/results.
    inventory={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(results.iterdir()) if p.is_file() and p.name!='evidence_inventory.json'}
    (results/"evidence_inventory.json").write_text(json.dumps(inventory,indent=2))
    archive=output/"TradingBot_24_New_Strategies_Evidence.zip"
    with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as bundle:
        for path in sorted(results.iterdir()):
            if path.is_file():bundle.write(path,arcname=path.name)
    print(json.dumps({"report":str(target),"evidence":str(archive),"report_bytes":target.stat().st_size,"evidence_bytes":archive.stat().st_size}))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    build(args.results,args.output)
