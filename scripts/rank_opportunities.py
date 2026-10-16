"""Reproduce post-hoc opportunity discovery from verified experiment011 curves."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO))
from tradingagents.opportunity_discovery import rank_asset


def run(source,out,freeze_sha):
    freeze_path=REPO/'research/experiments/012/freeze.json'
    raw=freeze_path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=freeze_sha:raise ValueError('Freeze hash mismatch')
    freeze=json.loads(raw)
    for path,sha in freeze['sources'].items():
        if hashlib.sha256((REPO/path).read_bytes()).hexdigest()!=sha:raise ValueError('Changed source '+path)
    hashes=json.loads((REPO/'research/experiments/011/full_result_hashes.json').read_text())
    out.mkdir(parents=True,exist_ok=False)
    result={'protocol':'docs/OPPORTUNITY_DISCOVERY_012.json','freeze_sha256':freeze_sha,'assets':{},
            'new_strategy_simulations':0,'independent_future_observations':0}
    for asset in ('BTC-USD','ETH-USD','LTC-USD'):
        data={}
        for name in ('matrix','delays'):
            key=f'{asset}/{name}.json.gz';raw=(source/key).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=hashes[key]:raise ValueError('Input hash mismatch '+key)
            data[name]=json.loads(gzip.decompress(raw))
        check=json.loads((REPO/f'research/experiments/011/{asset}/assessment.json').read_text())
        ranked=rank_asset(asset,data['matrix'],data['delays'],check)
        (out/f'{asset}.json').write_text(json.dumps(ranked,indent=2,allow_nan=False)+'\n')
        result['assets'][asset]={'shortlist':ranked['shortlist_distinct_families'],
            'ranked_count':len(ranked['rows']),'historical_robust_passes':sum(r['historical_robust_pass'] for r in ranked['rows'])}
        print(asset,result['assets'][asset],flush=True)
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--freeze-sha',required=True);a=p.parse_args();run(a.source,a.output,a.freeze_sha)
