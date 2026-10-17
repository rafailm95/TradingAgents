"""Package completed018 diagnostics; never rerun or alter the frozen analysis."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Structure(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = self.rows = 0

    def handle_starttag(self, tag, attrs):
        self.tables += tag == 'table'
        self.rows += tag == 'tr'


def main(output, destination):
    verification = json.loads((output / 'verification.json').read_text())
    for name, digest in verification['output_hashes'].items():
        assert sha(output / name) == digest, name
    summary = json.loads((output / 'summary.json').read_text())
    cases = json.loads((output / 'cases.json').read_text())
    assert len(cases) == 77 and len(summary['candidates']) == 6
    assert sum(x['descriptive_diagnostic_pass'] for x in cases if x['candidate']) == 28
    assert not summary['all12_descriptive_passes']
    page = output / 'Futures_018_Concentration_EL.html'
    parsed = Structure()
    parsed.feed(page.read_text())
    assert (parsed.tables, parsed.rows) == (2, 20)
    freeze = json.loads((ROOT / 'research/experiments/018/freeze.json').read_text())
    for group in ['source_hashes', 'preserved_files']:
        for name, digest in freeze[group].items():
            assert sha(ROOT / name) == digest, name
    assert not destination.exists(), 'Preserve existing archive'
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(output.iterdir()):
            if p.is_file(): z.write(p, 'diagnostics018/' + p.name)
        for p in sorted((ROOT / 'research/experiments/018').iterdir()):
            if p.is_file() and p.name not in ['cases.json', 'summary.json', 'verification.json', 'intent.json']:
                z.write(p, 'repository/' + str(p.relative_to(ROOT)))
        for name in sorted(set(freeze['source_hashes']) | {'scripts/package_futures_concentration_018.py', 'docs/FUTURES_CONCENTRATION_018_RESULTS.md'}):
            if not name.startswith('research/experiments/018/'):
                z.write(ROOT / name, 'repository/' + name)
    with zipfile.ZipFile(destination) as z:
        assert z.testzip() is None
    receipt = {'archive': destination.name, 'sha256': sha(destination), 'bytes': destination.stat().st_size,
               'crc': 'PASS', 'html_structure': {'tables': 2, 'rows': 20},
               'original_output_hashes_verified': True, 'frozen_sources_unchanged': True,
               'input_dependency': 'research/experiments/018/input-reference.json'}
    with (ROOT / 'research/experiments/018/package-verification.json').open('x') as f:
        json.dump(receipt, f, indent=2)
        f.write('\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--destination', type=Path, required=True)
    a = p.parse_args()
    main(a.output, a.destination)
