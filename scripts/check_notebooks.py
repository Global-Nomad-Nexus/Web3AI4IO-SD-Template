"""Execute all tutorial code cells locally; keep distributable notebooks unexecuted."""
from pathlib import Path
import argparse, contextlib, io, json, os

ROOT=Path(__file__).resolve().parents[1]

def require(condition, message):
    if not condition:
        raise ValueError(message)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--public-clone',action='store_true',help='Use each notebook pinned public checkout instead of the local source override')
    args=parser.parse_args()
    if args.public_clone:os.environ.pop('WEB3SD_LOCAL_REPO',None)
    else:os.environ['WEB3SD_LOCAL_REPO']=str(ROOT)
    total=0
    for path in sorted((ROOT/'notebooks').glob('*.ipynb')):
        n=json.loads(path.read_text());ns={'__name__':'__main__'};count=0
        for index,cell in enumerate(n['cells']):
            if cell['cell_type']!='code':continue
            source=cell['source'] if isinstance(cell['source'],str) else ''.join(cell['source'])
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    exec(compile(source,f'{path.name}:cell{index}','exec', optimize=0),ns)
            except Exception as exc:
                raise RuntimeError(f'{path.name}, cell {index}: {exc}') from exc
            count+=1
        receipt=json.loads(ns['receipt_path'].read_text())
        require(receipt['code_verification']==('pinned_checkout' if args.public_clone else 'local_override'),
                f'{path.name}: unexpected code verification mode')
        require(ns['archive'].is_file(), f'{path.name}: missing output archive')
        print(f'{path.name}: {count} cells executed; reference PASS; valid run receipt and ZIP; {receipt["code_verification"]}')
        total+=count
    print(f'PASS: {total} code cells. This is local execution, not a hosted Google Colab session.')

if __name__=='__main__':main()
