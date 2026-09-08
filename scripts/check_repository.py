"""Check syntax, notebook structure, repository links and release inventories."""
from pathlib import Path
import argparse, ast, json, re, xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]

def require(condition, message):
    if not condition:
        raise SystemExit(message)

def files():
    excluded={'.git','outputs','dist','__pycache__','.ipynb_checkpoints'}
    return sorted(p for p in ROOT.rglob('*') if p.is_file() and not excluded.intersection(p.relative_to(ROOT).parts))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--allow-unpinned',action='store_true')
    args=parser.parse_args();errors=[];all_files=files();notebooks=[];code_count=0
    for p in all_files:
        if p.suffix=='.py':ast.parse(p.read_text(),filename=str(p))
        if p.suffix=='.json':json.loads(p.read_text())
        if p.suffix=='.ipynb':
            n=json.loads(p.read_text());notebooks.append(p)
            require(n['nbformat']==4 and n['nbformat_minor']==5, f'{p.name}: expected notebook format 4.5')
            ids=[c['id'] for c in n['cells']]
            require(len(ids)==len(set(ids)), f'{p.name}: duplicate cell IDs')
            content='\n'.join(c['source'] if isinstance(c['source'],str) else ''.join(c['source']) for c in n['cells'])
            for part in ['i','ii','iii','iv','v','vi','vii','viii']:
                require(content.count(f'id="part-{part}"')==1, f'{p.name}: missing or repeated part {part}')
            if not args.allow_unpinned:
                require('PIN_CODE_COMMIT' not in content, f'{p.name}: unresolved code pin')
                require(re.search(r'CODE_COMMIT = "[0-9a-f]{40}"',content), f'{p.name}: invalid code pin')
            for i,c in enumerate(n['cells']):
                if c['cell_type']=='code':
                    code_count+=1
                    require(c['execution_count'] is None and c['outputs']==[], f'{p.name}: distribute clean unexecuted cells')
                    ast.parse(c['source'],filename=f'{p.name}:cell{i}')
            for rel in re.findall(r'https://github.com/sunshineluyao/Web3AI4IO-SD-Template/blob/[^/\s)]+/([^\s)]+)',content):
                if not (ROOT/rel).exists():errors.append(f'{p.name}: missing code/data link {rel}')
        if p.suffix=='.md':
            s=p.read_text()
            for target in re.findall(r'(?<!!)\[[^\]]*\]\(([^\s)]+)\)',s):
                if target.startswith(('https:','http:','mailto:','#')):continue
                target=target.split('#')[0]
                if target and not (p.parent/target).resolve().exists():errors.append(f'{p.relative_to(ROOT)}: missing {target}')
        if p.stat().st_size > 2_000_000:errors.append(f'Unexpected large file: {p.name}')
    require(len(notebooks)==3, 'Expected exactly three tutorials')
    svg=ET.parse(ROOT/'assets/pipeline.svg').getroot()
    tags=[n.tag.split('}')[-1] for n in svg.iter()]
    require('title' in tags and 'desc' in tags and 'text' in tags, 'SVG lacks accessible live text')
    require(not {'image','script','foreignObject'}.intersection(tags), 'SVG contains prohibited embedded content')
    for r in json.loads((ROOT/'metadata/result_index.json').read_text()):
        for field in ['original_sources','query_code','queried_data','process_code','processed_data','analysis_code','result_outputs']:
            require((ROOT/r[field]).exists(), f'{r["result_id"]}: missing {field}')
        require(r['evidence_status']=='SYNTHETIC', f'{r["result_id"]}: incorrect fixture status')
    if errors:raise SystemExit('\n'.join(errors))
    print(f'PASS: {len(all_files)} files; {len(notebooks)} notebooks; {code_count} code cells; syntax, local links, SVG and result paths.')

if __name__=='__main__':main()
