import importlib.util,hashlib,warnings,zipfile
from pathlib import Path
from decimal import Decimal
import pytest

P=Path(__file__).resolve().parents[1]/'scripts/audit_bybit_capture.py'
spec=importlib.util.spec_from_file_location('audit_bybit_capture',P)
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)


def make(tmp_path,names):
    p=tmp_path/'capture.zip'
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',UserWarning)
        with zipfile.ZipFile(p,'w') as z:
            for n in names:z.writestr(n,b'{}')
    return p,hashlib.sha256(p.read_bytes()).hexdigest()


def test_duplicate_names_rejected(tmp_path):
    p,sha=make(tmp_path,['summary.json','summary.json'])
    with pytest.raises(ValueError,match='Duplicate'):a.load_archive(p,sha)


def test_paths_never_extracted(tmp_path):
    p,sha=make(tmp_path,['../summary.json'])
    with pytest.raises(ValueError,match='Non-flat'):a.load_archive(p,sha)
    assert not (tmp_path.parent/'summary.json').exists()


def test_external_hash_required(tmp_path):
    p,sha=make(tmp_path,['summary.json'])
    with pytest.raises(ValueError,match='hash mismatch'):a.load_archive(p,'0'*64)


def test_independent_cash_oracle():
    levels=[['100','1'],['102','2'],['105','5']]
    assert a.independent_sweep(levels,Decimal('2.5'))==Decimal('253')
    assert a.independent_sweep(levels,Decimal('1'))==Decimal('100')
    with pytest.raises(ValueError,match='shortfall'):a.independent_sweep(levels,Decimal('9'))


def test_nonfinite_payload_refused():
    with pytest.raises(ValueError,match='Non-finite'):a.loads('{"price": NaN}')
