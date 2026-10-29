"""Scientific SVG previews from actual P2 tables; missing coverage stays explicit."""
from p2io import *
from collections import Counter
import html

def run():
    coverage=read_csv(ROOT/'reports/coverage.csv');registry=read_csv(ROOT/'processed/registry.csv');prices=read_csv(ROOT/'processed/pm_prices.csv')
    order=['solana:mainnet','eip155:8453','eip155:56'];labels=['Solana / Pump.fun','Base / Clanker','BSC / Four.meme V2'];colors=['#7855ad','#246cb2','#bb8721'];counts=Counter(r['chain_key'] for r in registry);cov={r['chain_key']:r for r in coverage}
    hourly=[]
    gaps=read_csv(ROOT/'reports/remaining_ranges.csv')
    for chain in order:
        rows=[r for r in registry if r['chain_key']==chain]
        first_gap=min((int(g['from_block_inclusive']) for g in gaps if g['chain_key']==chain),default=10**20)
        latest=max((epoch(r['created_at_utc']) for r in rows if int(r['block_height_or_slot'])<first_gap),default=1791417600)
        for hour in range(24):
            start=1791417600+hour*3600;end=start+3600;complete=cov[chain]['creation_scope_complete']=='True' or end<=latest
            hourly.append({'chain_key':chain,'hour_start_utc':iso(start),'hour_end_utc':iso(end),'observed_creations':sum(start<=epoch(r['created_at_utc'])<end for r in rows),'coverage_status':'complete_hour_within_contiguous_covered_prefix' if complete else 'partial_or_unknown','plot_count':sum(start<=epoch(r['created_at_utc'])<end for r in rows) if complete else ''})
    write_csv(ROOT/'figures/data/panel_E_hourly_creation_activity.csv',hourly)
    hist=[r for r in prices if 1791417600<=epoch(r['source_timestamp_utc'])<1791504000]
    write_csv(ROOT/'figures/data/panel_E_historical_macro_prices.csv',hist)
    svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="820" viewBox="0 0 1120 820">','<rect width="1120" height="820" fill="#f7f8fa"/>','<style>text{font-family:Arial,sans-serif;fill:#1c2835}.title{font-size:20px;font-weight:bold}.sub{font-size:13px;fill:#526273}.small{font-size:11px}</style>']
    def text(x,y,s,cls='small'):svg.append(f'<text x="{x}" y="{y}" class="{cls}">{html.escape(str(s))}</text>')
    def panel(x,y,w,h,title):svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="white" stroke="#d9e0e5"/>');text(x+20,y+30,title,'title')
    text(28,30,'P2 declared-version pilot | 2026-10-08 UTC','title');text(28,52,'Observed counts reflect recorded query coverage; a partial chain is not a daily platform total.','sub')
    panel(20,75,520,300,'A  Creation records obtained')
    maxn=max(counts.values(),default=1)
    for i,chain in enumerate(order):
        y=150+i*70;width=300*counts[chain]/maxn
        text(40,y-9,labels[i],'sub');svg.append(f'<rect x="40" y="{y}" width="{width:.2f}" height="22" fill="{colors[i]}"/>');text(50+width,y+16,counts[chain]);text(40,y+40,cov[chain]['coverage_status'].replace('_',' '))
    panel(560,75,540,300,'B  Declared creation enumeration coverage')
    for i,chain in enumerate(order):
        r=cov[chain];fraction=(int(r['native_candidates_resolved'])/int(r['native_index_candidate_denominator'])) if r['native_candidates_resolved'] else int(r['positions_covered_by_successful_query_union'])/int(r['declared_positions']);y=155+i*70
        text(580,y-12,labels[i],'sub');svg.append(f'<rect x="580" y="{y}" width="420" height="20" fill="#e9edf1"/><rect x="580" y="{y}" width="{420*fraction:.2f}" height="20" fill="{colors[i]}"/>');text(1010,y+15,f'{fraction:.1%}');text(580,y+40,'Unit: indexed candidate transactions resolved' if r['native_candidates_resolved'] else 'Unit: declared block positions queried')
    panel(20,395,520,350,'C  Semantic expectation link')
    svg.append('<rect x="60" y="465" width="435" height="66" rx="6" fill="#eef2fa"/>');text(80,490,'One fixed FOMC outcome / one shared macro event','sub');text(80,512,'Fed cut 25 bps, Yes | Gamma market 2589811')
    for i,label in enumerate(labels):
        y=570+i*54;svg.append(f'<path d="M275 531 L275 {y-10} L95 {y-10}" fill="none" stroke="{colors[i]}"/>');text(105,y,label,'sub')
    text(45,724,'0 verified individual-token identity forecasts; macro copies are not independent forecasts.')
    panel(560,395,540,350,'E  Historical price / creation alignment')
    text(580,450,'Fixed macro API history scalar (not asserted midpoint or trade)','small')
    if hist:
        lo=min(float(r['price']) for r in hist);hi=max(float(r['price']) for r in hist);span=max(hi-lo,.001)
        points=' '.join(f'{590+460*(epoch(r["bucket_end_utc"])-1791417600)/86400:.2f},{535-60*(float(r["price"])-lo)/span:.2f}' for r in hist)
        svg.append(f'<polyline points="{points}" fill="none" stroke="#263d57" stroke-width="2"/>');text(580,470,f'{hi:g}');text(580,550,f'{lo:g}')
    text(580,575,'Created tokens / hour: only fully covered hours plotted','small')
    ymax=max((int(r['plot_count']) for r in hourly if r['plot_count']!=''),default=1)
    text(580,595,f'Activity scale: 0 to {ymax} tokens/hour; colors match panel A','small')
    for i,chain in enumerate(order):
        rs=[r for r in hourly if r['chain_key']==chain and r['plot_count']!=''];points=' '.join(f'{590+460*(epoch(r["hour_start_utc"])-1791417600)/86400:.2f},{675-80*int(r["plot_count"])/ymax:.2f}' for r in rs)
        if points:svg.append(f'<polyline points="{points}" fill="none" stroke="{colors[i]}" stroke-width="2"/>')
    text(585,699,'00:00');text(1000,699,'24:00 UTC');text(580,723,'Retrospective demonstration; no causal or calibrated-probability claim.')
    text(24,775,'Scope: named Pump.fun instructions, six SDK-listed Base factories, Four.meme V2. Unknown coverage stays missing.','sub');text(24,798,'Source tables and scripts accompany this preview. Full P4 gallery and real lifecycle integration are separate deliverables.','sub');svg.append('</svg>')
    (ROOT/'figures/P2_previews.svg').write_text('\n'.join(svg))
    print('WROTE',ROOT/'figures/P2_previews.svg')
if __name__=='__main__':run()
