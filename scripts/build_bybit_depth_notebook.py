"""Build an additive depth-first Colab notebook from the frozen history notebook."""
import argparse
import base64
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HISTORY_NOTEBOOK_SHA='1163c80229bdd0710bb405ec90147fe1e203750f43a3757748ea6af3b8b4216d'


def build(output):
    original=(ROOT/'notebooks/Bybit_History_One_Click.ipynb').read_bytes()
    if hashlib.sha256(original).hexdigest()!=HISTORY_NOTEBOOK_SHA:
        raise ValueError('Frozen history notebook changed')
    template=json.loads(original)
    setup=''.join(next(c for c in template['cells'] if c['cell_type']=='code')['source'])
    old=(ROOT/'scripts/collect_bybit_history_browser.py').read_bytes()
    new=(ROOT/'scripts/collect_bybit_depth_browser.py').read_bytes()
    replacements={base64.b64encode(old).decode():base64.b64encode(new).decode(),
                  hashlib.sha256(old).hexdigest():hashlib.sha256(new).hexdigest(),
                  'collect_bybit_history_browser.py':'collect_bybit_depth_browser.py',
                  '/content/Bybit_Browser_History_20261018':'/content/Bybit_Browser_Depth_20261018'}
    for before,after in replacements.items():
        if setup.count(before)!=1: raise ValueError('Unexpected frozen setup structure')
        setup=setup.replace(before,after)
    cells=[]
    def md(text):cells.append({'cell_type':'markdown','metadata':{},'source':text.splitlines(keepends=True)})
    def code(text,metadata=None):cells.append({'cell_type':'code','metadata':metadata or {},'execution_count':None,
                                             'outputs':[],'source':text.splitlines(keepends=True)})
    md('''# Bybit — ξεκινάμε με βάθος αγοράς, έπειτα ιστορικό

Πάτησε **Runtime / Χρόνος εκτέλεσης → Run all / Εκτέλεση όλων**, με CPU. Αν ζητηθεί, συνδέσου στο Google και επίλεξε «Run anyway». Δεν χρειάζεται λογαριασμός ή κλειδί Bybit, εγκατάσταση Python, GPU ή πρόσβαση στο Drive.

Για **BTC, ETH, LTC, SOL, XRP** ξεκινά αμέσως η πρώτη δειγματοληψία βιβλίου. Στόχος:25γύροι με τουλάχιστον5λεπτά μεταξύ τους, περίπου2ώρες συνολικά. Κάθε γύρος ζητά δύο βιβλία ανά νόμισμα με απόσταση τουλάχιστον2δευτερολέπτων, έως1000επίπεδα, ticker, instrument και πρόσφατες συναλλαγές. Έως250βιβλία αν όλες οι απαντήσεις είναι έγκυρες. Είναι στιγμιότυπα και δείγμα συναλλαγών, όχι πλήρης συνεχής ροή ή πραγματικές εκτελέσεις.

Μετά συλλέγει/επαναχρησιμοποιεί το ίδιο ιστορικό026 (trade/mark/funding και τα πρόσθετα στοιχεία). **Ένα τελικό BYBIT_SEND_THIS.zip περιλαμβάνει βάθος και ιστορικό.** Ενημερώνεται ενδιάμεσα μετά από κάθε γύρο. Μπορείς να κατεβάσεις το διαθέσιμο ZIP από το Files/Αρχεία αν χρειαστεί να σταματήσεις. Για ομαλή διακοπή πάτησε Stop μία φορά και περίμενε να κλείσει το ZIP.

**Δεν είναι ολοκλήρωση72ωρών.** Ο πραγματικός χρόνος, οι επιτυχείς γύροι και τα κενά καταγράφονται. Το αρχικό πλήρες πακέτοWindows παραμένει διαθέσιμο για τον στόχο72ωρών. Οι δωρεάν χρόνοιColab δεν είναι εγγυημένοι· κράτησε τη σελίδα ανοιχτή και κατέβασε το αρχείο πριν χαθεί το runtime. Μέγιστος χρόνος αιτημάτων ανά πάτημα6ώρες. Σε αποκλεισμό σταματά χωρίς παράκαμψη ή αυτόματο retry του αποκλεισμού. Η πραγματική πρόσβασηColab→Bybit δεν έχει επαληθευτεί εδώ.

**Αν τρέχει ήδη το παλιό notebook:** άφησέ το να ολοκληρωθεί και κατέβασε το ZIP. Έπειτα χρησιμοποίησε την προαιρετική εισαγωγή παρακάτω. Τα δύοnotebooks δεν θεωρούνται ότι μοιράζονται runtime. Δεν χρειάζεται να ξανακατεβάσεις επαληθευμένες ιστορικές σελίδες που εισάγονται σωστά.
''')
    code(setup)
    md('''## Μόνο αν έχεις ήδη το προηγούμενο αποτέλεσμα

Αν έχεις ήδη κατεβάσει **BYBIT_SEND_THIS.zip**, τσέκαρε **IMPORT_EXISTING_ZIP** πριν από το Run all. Όταν εμφανιστεί το κουμπί, διάλεξε εκείνο τοZIP. Δεν επιλέγεις το αρχικό πακέτοκώδικα. Αν δεν έχεις προηγούμενοZIP, άφησε το κουτάκι κενό. Η εισαγωγή ελέγχει το αρχείο πριν το χρησιμοποιήσει και δεν εκτελεί περιεχόμενό του.
''')
    code('''#@title Προαιρετική εισαγωγή προηγούμενου ZIP
IMPORT_EXISTING_ZIP = False #@param {type:"boolean"}
import collect_bybit_depth_browser as collector
if pathlib.Path(collector.__file__).resolve() != (ROOT/'scripts/collect_bybit_depth_browser.py').resolve():
    raise RuntimeError('Unexpected collector module')
OUT = ROOT/'browser_depth_data'
if IMPORT_EXISTING_ZIP:
    if OUT.exists() and any(OUT.iterdir()):
        print('Υπάρχει ήδη συνεδρία. Θα συνεχιστεί, χωρίς νέα εισαγωγή.')
    else:
        from google.colab import files
        selected = files.upload()
        if len(selected) != 1: raise RuntimeError('Επίλεξε ακριβώς ένα προηγούμενο ZIP')
        payload = next(iter(selected.values()))
        if len(payload) > 480_000_000: raise RuntimeError('Το αρχείο υπερβαίνει το όριο')
        incoming = ROOT/'uploaded_previous_packet.zip'
        if incoming.exists() and incoming.read_bytes() != payload:
            raise RuntimeError('Υπάρχει διαφορετικό προηγούμενοZIP. Δεν αντικαθίσταται.')
        incoming.write_bytes(payload)
        result = collector.import_packet(incoming,hashlib.sha256(payload).hexdigest(),OUT)
        print('Έλεγχος και εισαγωγή ολοκληρώθηκαν. Οι προηγούμενες σελίδες διατηρούνται.')
        del selected, payload
''',{'cellView':'form'})
    code('''result = collector.collect(OUT)
print('Έγκυρα βιβλία:',result['summary']['live']['valid_books'])
print('Πραγματικό διάστημα δείγματος (ώρες):',result['summary']['live']['observed_span_hours'])
''')
    code('''from google.colab import files
target = ROOT/'BYBIT_SEND_THIS.zip'
if target.is_file():
    print('Ανέβασε στη συνομιλία μόνο αυτό: BYBIT_SEND_THIS.zip')
    files.download(str(target))
else:
    print('Δεν υπάρχειZIP. Κράτησε το μήνυμα σφάλματος για έλεγχο.')
''')
    md('''Αν η λήψη δεν ξεκινήσει: **Files/Αρχεία → Bybit_Browser_Depth_20261018 → BYBIT_SEND_THIS.zip → Download**. Αν χαθεί απότομα τοruntime, μπορεί να χαθούν αρχεία που δεν κατέβασες. Η αποθήκευση τουnotebookστοDrive δεν σημαίνει ότι σώζονται τα δεδομένα τουruntime.

Καμία στρατηγική ή εντολή δεν εκτελείται. Το δείγμα χρησιμοποιείται για έλεγχο spread/βάθους και υποθετικού κόστους, όχι για πιστοποίησηκερδοφορίας. Πηγές: [Bybitorderbook](https://bybit-exchange.github.io/docs/v5/market/orderbook), [ColabFAQ](https://research.google.com/colaboratory/faq.html). Παγωμένες013/014/026πηγές αμετάβλητες. Πακέτο026SHA256a741d8c87462efa806d8f8ad778b3cabe35447d535864e99ad6f20fc60685ea5.
''')
    for i,c in enumerate(cells):c['id']=f'bybit-depth-{i}'
    obj={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'name':'python3','display_name':'Python3'},
        'language_info':{'name':'python'},'colab':{'name':'Bybit_Depth_and_History_One_Click.ipynb'}},'cells':cells}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(obj,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    return {'filename':output.name,'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
            'wrapper_sha256':hashlib.sha256(new).hexdigest()}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(build(a.output)))
