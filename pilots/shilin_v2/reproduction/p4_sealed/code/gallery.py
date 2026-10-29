"""Deterministic five-panel SVG from real frozen tables; PNG via offline librsvg."""
import csv,html,json,math,shutil,subprocess,sys,textwrap
from collections import Counter,defaultdict
from pathlib import Path
CHAINS=['solana:mainnet','eip155:8453','eip155:56'];LABELS=['Solana / Pump.fun','Base / Clanker','BSC / Four.meme V2'];COLORS=['#287b8e','#a067bd','#d89537']

def read(p):
 with Path(p).open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def write(p,values):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=list(values[0]));w.writeheader();w.writerows(values)

def sources(run,out):
 run=Path(run);out=Path(out);data=out/'data';data.mkdir(parents=True,exist_ok=True)
 counts=Counter();samples={};total=0
 with (run/'processed/registry.csv').open(newline='',encoding='utf-8') as f:
  for r in csv.DictReader(f):
   counts[r['chain_key'],r['created_at_utc'][:10]]+=1;total+=1
   if r['chain_key'] not in samples:samples[r['chain_key']]=r
 scope=read(run/'reports/creation_coverage.csv');context=read(run/'processed/context_daily.csv');mappings=read(run/'processed/pm_mapping.csv')
 A=[dict(chain_key=r['chain'],utc_day=r['day'],unique_tokens=counts[r['chain'],r['day']],coverage_status=r['status']) for r in scope]
 B=[]
 for r in scope:
  rows=[x for x in context if x['chain_key']==r['chain'] and x['utc_day']==r['day']]
  B.append(dict(chain_key=r['chain'],utc_day=r['day'],creation_status=r['status'],valid_background_anchors=sum(x['match_status']=='matched_valid' for x in rows),assessed_background_anchors=len(rows)))
 coverage=read(run/'reports/expectation_coverage.csv');C=[]
 for kind in ['verified_token_identity','platform','chain','shared_economic_event']:
  mm=[m for m in mappings if m['link_type']==kind]
  C.append(dict(link_type=kind,distinct_markets=len({m['pm_market_key'] for m in mm}),mapping_rows=len(mm),valid_token_union=max([int(r['valid_token_numerator']) for r in coverage if r['link_type']==kind],default=0) if kind=='platform' else sum(int(r['valid_token_numerator']) for r in coverage if r['link_type']==kind),token_denominator=total))
 terminal=Counter((r['checkpoint'],r['final_state']) for r in read(run/'processed/metadata_coverage.csv'))
 D=[dict(checkpoint=k,terminal_state=s,checkpoints=terminal[k,s],denominator=4668,cohort='legacy_7day_20261008') for k in ['T0','T24','T48','T72'] for s in ['observed','request_failed','parse_failed']]
 # Choose a shared macro outcome by predeclared coverage-first, stable-ID rule.
 macro=[m for m in mappings if m['link_type']=='shared_economic_event']
 choice=sorted(macro,key=lambda m:(-sum(r['mapping_id']==m['mapping_id'] and r['chain_key']==CHAINS[0] and r['match_status']=='matched_valid' for r in context),m['mapping_id']))[0]
 market=next(m for m in read(run/'processed/pm_markets.csv') if m['market_snapshot_id']==choice['market_snapshot_id'])
 E=[]
 for day in sorted({r['utc_day'] for r in context}):
  price=next(r for r in context if r['utc_day']==day and r['chain_key']==CHAINS[0] and r['mapping_id']==choice['mapping_id'])
  E.append(dict(utc_day=day,mapping_id=choice['mapping_id'],pm_outcome_key=choice['pm_outcome_key'],price=price['expectation_at_day_start'],match_status=price['match_status'],effective_information_time_utc=price['effective_information_time_utc'],solana_tokens=counts[CHAINS[0],day],base_tokens=counts[CHAINS[1],day],bsc_tokens=counts[CHAINS[2],day]))
 for name,values in [('A_activity',A),('B_coverage',B),('C_links',C),('D_metadata',D),('E_alignment',E)]:write(data/('panel_'+name+'.csv'),values)
 meta={'selection_rule':'shared economic event; most valid daily UTC-start anchors; mapping_id ascending tie break','mapping_id':choice['mapping_id'],'outcome_id':choice['pm_outcome_key'],'question':market.get('question',market.get('title','')),'close_utc':market.get('scheduled_close_at_utc'),'actual_close_utc':market.get('actual_close_at_utc'),'resolved_utc':market.get('resolved_at_utc'),'window':'[2026-10-08,2026-10-15) UTC','dataset_kind':'real_formal','price_feature_readiness':'retrospective_demonstration_only'}
 (out/'selection.json').write_text(json.dumps(meta,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
 write(out/'real_three_chain_preview.csv',[{k:r.get(k,'') for k in ['token_id','chain_key','platform_id','created_at_utc','creation_event_id','creator_role_definition','native_receipt_raw_ref']} for r in samples.values()])
 return meta

class SVG:
 def __init__(self):self.s=['<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="1640" viewBox="0 0 1800 1640">','<rect width="1800" height="1640" fill="#f4f6f8"/>','<g font-family="DejaVu Sans, Arial, sans-serif" fill="#203345">']
 def text(self,x,y,s,size=19,fill='#203345',weight='normal',anchor='start'):
  self.s.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" font-weight="{weight}" text-anchor="{anchor}">{html.escape(str(s))}</text>')
 def rect(self,x,y,w,h,fill,stroke='none',rx=0):self.s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}"/>')
 def line(self,x1,y1,x2,y2,color='#d8e0e7',width=1):self.s.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}"/>')
 def panel(self,x,y,w,h,label,title,subtitle):
  self.rect(x,y,w,h,'white',rx=14);self.text(x+24,y+40,label,28,'#176477','bold');self.text(x+65,y+40,title,25,weight='bold');self.text(x+25,y+72,subtitle,17,'#536977')
 def finish(self,p):p.write_text('\n'.join(self.s+['</g></svg>'])+'\n')

def draw(out):
 out=Path(out);d=out/'data';A=read(d/'panel_A_activity.csv');B=read(d/'panel_B_coverage.csv');C=read(d/'panel_C_links.csv');D=read(d/'panel_D_metadata.csv');E=read(d/'panel_E_alignment.csv');meta=json.loads((out/'selection.json').read_text());v=SVG()
 v.text(40,54,'Token launch registry | personal delivery candidate',37,weight='bold');v.text(40,89,'P3 v6 frozen evidence  /  08-14 October 2026 UTC  /  367,373 tokens  /  21 closed chain-days',21,'#536977')
 v.panel(30,115,1050,390,'A','Creation activity','Distinct token_id per UTC day; platform/version scope only')
 for i,(chain,label,color) in enumerate(zip(CHAINS,LABELS,COLORS)):
  data=sorted([r for r in A if r['chain_key']==chain],key=lambda r:r['utc_day']);x=85+i*337;y=426;w=277;h=198;maximum=max(int(r['unique_tokens']) for r in data);unit=100 if maximum<1000 else 1000;scale=math.ceil(maximum/unit)*unit
  v.text(x-12,222,label,20,weight='bold')
  for k in range(3):
   yy=y-h*k/2;v.line(x,yy,x+w,yy);v.text(x-8,yy+6,f'{scale*k/2:,.0f}',14,anchor='end')
  for j,r in enumerate(data):
   val=int(r['unique_tokens']);bh=val/scale*h;v.rect(x+j*39+5,y-bh,24,bh,color);v.text(x+j*39+17,451,r['utc_day'][-2:],15,anchor='middle')
  v.text(x+135,480,f"Total {sum(int(r['unique_tokens']) for r in data):,}",19,anchor='middle')
 v.panel(1100,115,670,390,'B','Coverage by day','Creation completeness + valid/assessed background anchors')
 days=sorted({r['utc_day'] for r in B})
 for j,day in enumerate(days):v.text(1307+j*61,239,day[-2:],17,anchor='middle')
 for i,label in enumerate(['Solana','Base','BSC']):
  v.text(1125,285+i*68,label,19)
  for j,day in enumerate(days):
   r=next(r for r in B if r['chain_key']==CHAINS[i] and r['utc_day']==day);complete=r['creation_status'].startswith('complete');x=1280+j*61;y=257+i*68
   v.rect(x,y,56,54,'#daeee9' if complete else '#eeeeee',rx=5);v.text(x+28,y+20,'C' if complete else '?',16,'#17624f',anchor='middle');v.text(x+28,y+42,f"{r['valid_background_anchors']}/{r['assessed_background_anchors']}",14,anchor='middle')
 v.text(1125,484,'C = complete in declared scope; day labels in UTC',16,'#536977')
 v.panel(30,525,850,350,'C','Expectation association','Counts by relationship; mapping rows and tokens have different units')
 names={'verified_token_identity':'Direct token identity','platform':'Platform','chain':'Chain','shared_economic_event':'Shared macro event'}
 v.text(60,649,'Relationship',17,weight='bold');v.text(510,649,'Markets',17,anchor='middle',weight='bold');v.text(635,649,'Mappings',17,anchor='middle',weight='bold');v.text(790,649,'Tokens',17,anchor='middle',weight='bold')
 for i,r in enumerate(C):
  yy=692+i*41;v.text(60,yy,names[r['link_type']],20);v.rect(330,yy-14,100,10,'#e6edf0');v.rect(330,yy-14,int(r['valid_token_union'])/int(r['token_denominator'])*100,10,'#287b8e')
  for x,key in [(510,'distinct_markets'),(635,'mapping_rows'),(790,'valid_token_union')]:v.text(x,yy,f"{int(r[key]):,}",20,anchor='middle')
 v.text(60,859,'Token denominator: 367,373; rows overlap across relationship types.',16,'#536977')
 v.panel(900,525,870,350,'D','Historical metadata observability','Legacy Solana cohort only; 4,668 planned checkpoints at each offset')
 state_colors={'observed':'#287b8e','request_failed':'#bcc6d0','parse_failed':'#c76557'}
 for i,k in enumerate(['T0','T24','T48','T72']):
  y=648+i*43;v.text(925,y+19,k,19);x=995
  for state in state_colors:
   r=next(r for r in D if r['checkpoint']==k and r['terminal_state']==state);w=int(r['checkpoints'])/4668*635;v.rect(x,y,w,27,state_colors[state]);x+=w
  good=next(r['checkpoints'] for r in D if r['checkpoint']==k and r['terminal_state']=='observed');v.text(1642,y+20,good,17)
 for i,(s,label) in enumerate([('observed','Parsed'),('request_failed','Request failed'),('parse_failed','Parse/evidence failed')]):
  x=930+i*261;v.rect(x,829,15,15,state_colors[s]);v.text(x+24,843,label,16)
 v.panel(30,895,1740,650,'E','Fixed expectation and creation alignment','A shared macro outcome; strict prior bucket end; no interpolation or causal interpretation')
 title=meta['question'] or meta['outcome_id']
 for j,t in enumerate(textwrap.wrap(title,width=125)[:2]):v.text(60,1014+j*24,t,20,weight='bold')
 v.text(60,1051,'Scheduled close: '+str(meta['close_utc'])+'; close/resolution not observed inside the displayed week.',16,'#536977');v.text(60,1076,'YES API scalar; daily UTC-start anchor (retrospective demonstration only)',17,'#536977')
 x0=225;step=210;baseline=1210;plotheight=100;last=None
 for tick in [0,0.5,1]:
  y=baseline-tick*plotheight;v.line(x0-20,y,1710,y);v.text(x0-35,y+6,str(tick),16,anchor='end')
 for i,r in enumerate(E):
  x=x0+i*step
  if r['price']:
   y=baseline-float(r['price'])*plotheight
   if last:v.line(last[0],last[1],x,y,'#3465a4',3)
   v.rect(x-4,y-4,8,8,'#3465a4');v.text(x,y-14,f"{float(r['price']):.4g}",17,anchor='middle');last=(x,y)
  else:v.text(x,baseline-45,'NA',18,'#777777',anchor='middle');last=None
 v.text(60,1274,'Created tokens',19,weight='bold');v.text(60,1298,'per UTC day',17,'#536977')
 maximum=math.ceil(max(sum(int(r[k]) for k in ['solana_tokens','base_tokens','bsc_tokens']) for r in E)/10000)*10000
 base=1455;h=140
 for tick in [0,maximum//2,maximum]:
  y=base-tick/maximum*h;v.line(x0-20,y,1710,y);v.text(x0-35,y+6,f'{tick:,}',16,anchor='end')
 for i,r in enumerate(E):
  x=x0+i*step;y=base
  for key,color in zip(['solana_tokens','base_tokens','bsc_tokens'],COLORS):
   bh=int(r[key])/maximum*h;y-=bh;v.rect(x-35,y,70,bh,color)
  v.text(x,1482,r['utc_day'][5:],17,anchor='middle')
 for i,(name,color) in enumerate(zip(['Solana','Base','BSC'],COLORS)):
  v.rect(470+i*230,1511,16,16,color);v.text(498+i*230,1526,name,17)
 v.text(40,1584,'Limits: historical rule revisions and API scalar construction remain unverified. Metadata access is not lifecycle survival.',18,'#536977')
 v.text(40,1614,'Real lifecycle: awaiting_integration. Synthetic fixtures excluded. Sources, units, denominators and reproduction: panel_specs.md.',18,'#536977')
 v.finish(out/'shilin_gallery.svg')

def main():
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--svg-only',action='store_true');a=p.parse_args()
 sources(a.run,a.output);draw(a.output)
 if not a.svg_only:
  exe=shutil.which('rsvg-convert')
  if not exe:raise RuntimeError('offline PNG rendering requires librsvg rsvg-convert; SVG already generated')
  subprocess.run([exe,'--zoom','2','--dpi-x','300','--dpi-y','300','-o',str(a.output/'shilin_gallery.png'),str(a.output/'shilin_gallery.svg')],check=True)
if __name__=='__main__':main()
