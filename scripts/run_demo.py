from pathlib import Path
import argparse, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'code/shared'))
from pipeline import TRACKS, run_stage
def main():
    p=argparse.ArgumentParser(description='Offline SYNTHETIC reproduction; all is the full teaching pipeline')
    p.add_argument('--track',choices=(*TRACKS,'all'),default='all')
    p.add_argument('--workdir',type=Path,default=ROOT/'outputs/demo')
    a=p.parse_args()
    for track in TRACKS if a.track=='all' else [a.track]:
        for stage in ['query_data','process_data','analyze_data','technical_validation']:
            w=run_stage(track,stage,a.workdir)
        print(f'{track}: synthetic reference comparison PASS; {w}')
if __name__=='__main__': main()
