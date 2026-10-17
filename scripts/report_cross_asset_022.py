"""Descriptive all-six cross-asset positive-count supplement; no replay or ranking."""
import argparse,html,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);a=p.parse_args();o=ROOT/'research/experiments/022';s=json.loads((o/'summary.json').read_bytes())
    candidates=list(s['assets']['SOLUSDT']['candidates']);common=[c for c in candidates if all(x['candidates'][c]['positive_all12'] for x in s['assets'].values())]
    result={'classification':'Descriptive posthoc sign check across all six preregistered candidates; not replacement for full gates, training selection or prior-search correction. Correlated dates, no future validation.','candidates_checked':candidates,'positive_in_every_cost_lag_funding_scenario_on_all3':common,'full_cross_asset_passes':s['cross_asset_full_passes']}
    (o/'cross-asset-positive.json').write_text(json.dumps(result,indent=2)+'\n')
    s['cross_asset_positive_all12']=common;s['combined_scenario_failures']=216-s['combined_scenario_passes'];s['combined_WFA_passes']=sum(x['wfa_scenario_passes'] for x in s['assets'].values());s['combined_WFA_failures']=36-s['combined_WFA_passes']
    (o/'summary.json').write_text(json.dumps(s,indent=2,ensure_ascii=False)+'\n')
    paragraph=f"Κοινή ιστορική θετική ένδειξη: {len(common)}/6 στρατηγικές έχουν θετικό αποτέλεσμα και στα 12 σενάρια και στα τρία νομίσματα: {', '.join(common) or 'καμία'}. Πρόκειται για περιγραφικό έλεγχο όλων των έξι ήδη παγωμένων στρατηγικών, όχι ανεξάρτητη μελλοντική επιβεβαίωση ή αλλαγή των πλήρων κριτηρίων."
    h=a.workspace/'Futures_022_SOL_BTC_XRP_EL.html';text=h.read_text();marker='<h2>Όλες οι στρατηγικές'
    if '<!--cross022-->' in text:raise ValueError('Supplement already applied; preserve exact report')
    h.write_text(text.replace(marker,'<!--cross022--><p><strong>'+html.escape(paragraph)+'</strong></p>'+marker,1))
    d=ROOT/'docs/SOL_FUNDING_022_RESULTS.md';d.write_text(d.read_text()+'\n'+paragraph+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
