"""Build a self-contained CPU-only Colab notebook from exact packet026 bytes."""
import argparse
import base64
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKET_SHA = 'a741d8c87462efa806d8f8ad778b3cabe35447d535864e99ad6f20fc60685ea5'


def build(packet, output):
    data = Path(packet).read_bytes()
    if hashlib.sha256(data).hexdigest() != PACKET_SHA:
        raise ValueError('Original delivered packet026 hash differs')
    wrapper = (ROOT/'scripts/collect_bybit_history_browser.py').read_bytes()
    setup = '''import base64, hashlib, io, json, pathlib, sys, zipfile
if sys.version_info < (3,10):
    raise RuntimeError('Χρειάζεται Python 3.10 ή νεότερο')
ROOT = pathlib.Path('/content/Bybit_Browser_History_20261018')
ROOT.mkdir(parents=True, exist_ok=True)
packet = base64.b64decode(PACKET_B64, validate=True)
if hashlib.sha256(packet).hexdigest() != PACKET_SHA:
    raise RuntimeError('Αποτυχία ελέγχου αρχικού πακέτου')
with zipfile.ZipFile(io.BytesIO(packet)) as z:
    prefix = 'Bybit_Complete_Packet/'
    if z.testzip(): raise RuntimeError('CRC mismatch')
    for info in z.infolist():
        if not info.filename.startswith(prefix): raise RuntimeError('Unexpected path')
        relative = pathlib.PurePosixPath(info.filename[len(prefix):])
        if relative.is_absolute() or '..' in relative.parts: raise RuntimeError('Unsafe path')
        path = ROOT.joinpath(*relative.parts)
        raw = z.read(info)
        if path.exists() and path.read_bytes() != raw: raise RuntimeError('Existing source changed')
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists(): path.write_bytes(raw)
wrapper = base64.b64decode(WRAPPER_B64, validate=True)
if hashlib.sha256(wrapper).hexdigest() != WRAPPER_SHA:
    raise RuntimeError('Αποτυχία ελέγχου συλλέκτη')
path = ROOT/'scripts/collect_bybit_history_browser.py'
if path.exists() and path.read_bytes() != wrapper: raise RuntimeError('Existing wrapper changed')
path.write_bytes(wrapper)
sys.path.insert(0,str(ROOT/'scripts'))
print('Έτοιμο. Δεν χρειάζεται κλειδί Bybit, εγκατάσταση ή πρόσβαση στο Google Drive.')
'''
    definitions = ('PACKET_SHA = '+repr(PACKET_SHA)+'\nPACKET_B64 = '+repr(base64.b64encode(data).decode())
                   +'\nWRAPPER_SHA = '+repr(hashlib.sha256(wrapper).hexdigest())
                   +'\nWRAPPER_B64 = '+repr(base64.b64encode(wrapper).decode())+'\n')
    cells = []
    def md(text): cells.append({'cell_type':'markdown','metadata':{},'source':text.splitlines(keepends=True)})
    def code(text): cells.append({'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],
                                  'source':text.splitlines(keepends=True)})
    md('''# Bybit — συλλογή ιστορικού από τον browser

Πάτησε **Runtime / Χρόνος εκτέλεσης → Run all / Εκτέλεση όλων** (CPU). Αν ζητηθεί, συνδέσου στον δικό σου λογαριασμό Google και επίλεξε «Run anyway». Δεν χρειάζεται σύνδεση ή κλειδί Bybit. Στο κινητό μπορεί να βοηθήσει η «Προβολή υπολογιστή» του browser.

**BTC, ETH, LTC, SOL, XRP.** Το notebook ζητά το ίδιο ιστορικό του πακέτου026: ωριαίες τιμές trade/mark/index/premium από2021 (μόνο όπου υπάρχουν), funding, 365ημέρες5λεπτων, 30ημέρες1λεπτων, open interest, ratio και risk tiers. Τα κενά παραμένουν κενά. Ο αρχικός πυρήνας013 διατηρείται αμετάβλητος.

**Αυτή η ευκολότερη επιλογή συλλέγει ιστορικό, όχι την επιπλέον ζωντανή παρακολούθηση72ωρών.** Δεν αντικαθιστά όλη τη μέτρηση βάθους του πλήρους πακέτου. Η δωρεάν λειτουργία του Colab έχει χρονικά όρια και πιθανές διακοπές. Κράτησε τη σελίδα ανοικτή και κατέβασε το αποτέλεσμα μόλις τελειώσει. Αν χαθεί ολόκληρο το runtime πριν τη λήψη, τα τοπικά αρχεία του μπορεί να χαθούν. Δεν δίνεται πρόσβαση στο Drive.

Η πρόσβαση του Colab στη Bybit **δεν έχει επαληθευτεί εδώ**. Σε αποκλεισμό σταματά και δίνει ZIP με το σφάλμα· δεν αλλάζει host/περιοχή και δεν χρησιμοποιεί proxy. Μέγιστος χρόνος ενός πατήματος4ώρες, χωρίς υπόσχεση ολοκλήρωσης. Το ίδιο runtime κρατά επαληθευμένες σελίδες για συνέχιση. Απότομη διακοπή του runtime δεν εγγυάται ZIP.

Στο τέλος ανέβασε εδώ **μόνο το BYBIT_SEND_THIS.zip**, ακόμη και αν αναφέρει ελλείψεις. Δεν εκτελούνται στρατηγικές ή πραγματικές εντολές. Για οποιαδήποτε προσομοίωση θα προηγηθεί ανεξάρτητος έλεγχος κάλυψης και ακεραιότητας.
''')
    code(definitions+setup)
    code('''import collect_bybit_history_browser as collector
if pathlib.Path(collector.__file__).resolve() != (ROOT/'scripts/collect_bybit_history_browser.py').resolve():
    raise RuntimeError('Unexpected collector module')
result = collector.collect(ROOT/'browser_history_data')
''')
    code('''from google.colab import files
target = ROOT/'BYBIT_SEND_THIS.zip'
if target.is_file():
    print('Κατέβασε αυτό το αρχείο και ανέβασέ το στη συνομιλία: BYBIT_SEND_THIS.zip')
    files.download(str(target))
else:
    print('Δεν δημιουργήθηκε ZIP. Κράτησε το μήνυμα σφάλματος για έλεγχο.')
''')
    md('''Αν ο browser δεν ξεκινήσει τη λήψη, άνοιξε το εικονίδιο **Files/Αρχεία** αριστερά και βρες `Bybit_Browser_History_20261018/BYBIT_SEND_THIS.zip` → Download. Δεν χρειάζεται να στείλεις τα άλλα αρχεία.

Πηγές: [Bybit API](https://bybit-exchange.github.io/docs/v5/market/kline), [Google Colab όρια](https://research.google.com/colaboratory/faq.html). Παγωμένη βάση: TradingAgents source commit9f824bb65116ce00fab411abbbaa4b3d6872aaa9, packet SHA256a741d8c87462efa806d8f8ad778b3cabe35447d535864e99ad6f20fc60685ea5. Αυτό το notebook είναι πρόσθετος τρόπος συλλογής, χωρίς αλλαγή των013/014/026πηγών.
''')
    obj={'nbformat':4,'nbformat_minor':5,'metadata':{
        'kernelspec':{'name':'python3','display_name':'Python 3'},
        'language_info':{'name':'python'},'colab':{'name':'Bybit_History_One_Click.ipynb'}},'cells':cells}
    for i,c in enumerate(cells): c['id']=f'bybit-history-{i}'
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(obj,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    return {'filename':output.name,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
            'bytes':output.stat().st_size,'wrapper_sha256':hashlib.sha256(wrapper).hexdigest(),
            'packet_sha256':PACKET_SHA}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--packet',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(build(a.packet,a.output)))
