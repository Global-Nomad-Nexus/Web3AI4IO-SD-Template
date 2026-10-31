#!/usr/bin/env python3
"""Rebuild the frozen ecosystem release using Python's standard library."""
import argparse, csv, datetime as dt, hashlib, io, json, math, shutil, statistics, zipfile
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc

def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)

def window(rows, start, end):
    groups = {}
    for r in rows:
        if 'Record role: historical' not in r['supplementary_information']:
            groups.setdefault(r['rule_name'], []).append(r)
    out = []
    for versions in groups.values():
        versions = sorted(versions, key=lambda r:(r['document_date_utc'], r['record_id']))
        pre = [r for r in versions if r['document_date_utc'] < start]
        selected = pre[-1:] + [r for r in versions if start <= r['document_date_utc'] < end]
        for original in selected:
            r = dict(original)
            role = 'baseline document' if r['document_date_utc'] < start else 'document update within window'
            r['supplementary_information'] = (r['supplementary_information'] + f' Window: {role}; {start} <= UTC date < {end}.').strip()
            later = [v for v in selected if v['document_date_utc'] > r['document_date_utc']]
            if later:
                r['supplementary_information'] += f" Next selected version: {later[0]['record_id']} ({later[0]['document_date_utc']})."
            out.append(r)
    order = {'Creation':0,'Trading':1,'Migration':2,'Fees':3}
    return sorted(out, key=lambda r:(order[r['category']], r['rule_name'], r['document_date_utc'], r['record_id']))

def rebuild(job, inputs, output):
    kind = job['kind']; spec = job.get('spec', {})
    source = inputs / job['input'] if job.get('input') else None
    fields = job['fields']
    if kind == 'curated':
        rows = read_csv(source)
        if spec.get('filter'):
            rows = [r for r in rows if r['inclusion_decision'] == 'confirmed_inclusion']
    elif kind == 'binance':
        rows = []
        for item in spec['archives']:
            p = inputs / item['path']; blob = p.read_bytes()
            digest = hashlib.sha256(blob).hexdigest()
            check = p.with_name(p.name+'.CHECKSUM').read_text().split()
            if check[0].lower() != digest or check[1].lstrip('*') != p.name:
                raise ValueError(f'Archive checksum mismatch: {p.name}')
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                raw = list(csv.reader(io.TextIOWrapper(z.open(p.name.replace('.zip','.csv')), encoding='utf-8')))
            step = dt.timedelta(hours=1) if spec['interval']=='1h' else dt.timedelta(days=1)
            for a in raw:
                time = dt.datetime.fromtimestamp(int(a[0])/1_000_000, UTC)
                o,h,l,c = map(Decimal, a[1:5])
                if not 0 < l <= min(o,c) <= max(o,c) <= h:
                    raise ValueError('Invalid OHLC')
                if spec['pair']=='SOLUSDT':
                    r = dict(pair=spec['pair'], time_utc=time.isoformat(), open_usdt=a[1],high_usdt=a[2],low_usdt=a[3],close_usdt=a[4],volume_sol=a[5],volume_usdt=a[7],trade_count=a[8],source_url=item['url'],archive_sha256=digest)
                else:
                    r = dict(pair=item['pair'],interval_start_utc=time.isoformat(),interval_end_utc=(time+step).isoformat(),open_usdc=a[1],high_usdc=a[2],low_usdc=a[3],close_usdc=a[4],volume_base_asset=a[5],quote_volume_usdc=a[7],trade_count=a[8],taker_buy_volume_base_asset=a[9],taker_buy_quote_volume_usdc=a[10],source_url=item['url'],archive_sha256=digest)
                rows.append(r)
        key = 'time_utc' if spec['pair']=='SOLUSDT' else 'interval_start_utc'
        rows.sort(key=lambda r:(r['pair'],r[key]))
    elif kind == 'raydium':
        rows = [dict(time_utc=dt.datetime.fromtimestamp(x['time'],UTC).isoformat(),pool_address=spec['pool'],liquidity_usd=x['liquidity']) for x in json.loads(source.read_text()) if spec['start'] <= dt.datetime.fromtimestamp(x['time'],UTC).date().isoformat() < spec['end']]
        rows.sort(key=lambda r:r['time_utc'])
    elif kind == 'rpc':
        groups = {}
        for r in read_csv(source): groups.setdefault(r['hour_start_utc'], []).append(r)
        selection = read_csv(inputs/'curated/solana/layer2/rpc_hourly_sample_selection.csv')
        selected = {(r['hour_start_utc'],r['slot']) for r in selection}
        actual = {(r['hour_start_utc'],r['slot']) for group in groups.values() for r in group}
        if selected != actual or len(selected) != len(selection): raise ValueError('RPC selection mismatch')
        for group in groups.values():
            for b in group:
                if int(b['transaction_count']) != int(b['successful_transaction_count']) + int(b['failed_transaction_count']):
                    raise ValueError('Inconsistent RPC outcome counts')
        rows = []
        for stamp, group in sorted(groups.items()):
            n = len(group); N = int(group[0]['population_blocks'])
            if n != 50 or len({r['slot'] for r in group}) != n: raise ValueError('Invalid RPC stratum')
            r = dict(hour_start_utc=stamp,hour_end_utc=(dt.datetime.fromisoformat(stamp)+dt.timedelta(hours=1)).isoformat().replace('+00:00','Z'),population_blocks=N,sampled_blocks=n,sampling_fraction=n/N)
            for metric in ['transaction_count','successful_transaction_count','failed_transaction_count']:
                a = [int(b[metric]) for b in group]; estimate = N*statistics.mean(a)
                se = N*math.sqrt((1-n/N)*statistics.variance(a)/n)
                r.update({metric+'_estimate':estimate,metric+'_standard_error':se,metric+'_ci95_low':max(0,estimate-2.009575234489209*se),metric+'_ci95_high':estimate+2.009575234489209*se})
            r.update(tps_estimate=r['transaction_count_estimate']/3600,failed_transaction_share_estimate=r['failed_transaction_count_estimate']/r['transaction_count_estimate'],sample_transaction_count=sum(int(b['transaction_count']) for b in group))
            rows.append(r)
    elif kind == 'price_metrics':
        bars = read_csv(output/spec['dependency']); prices = [float(r['close_usdc']) for r in bars]
        returns = [None]+[math.log(b/a) for a,b in zip(prices,prices[1:])]
        rows = [dict(pair=r['pair'],interval_start_utc=r['interval_start_utc'],available_at_utc=r['interval_end_utc'],close_usdc=r['close_usdc'],log_return_1h='' if i==0 else format(returns[i],'.17g'),rolling_24h_return_std='' if i<24 else format(statistics.stdev(returns[i-23:i+1]),'.17g'),return_observations=0 if i<24 else 24) for i,r in enumerate(bars)]
    elif kind == 'window':
        rows = window(read_csv(output/spec['dependency']),spec['start'],spec['end'])
    elif kind == 'growthepie':
        data = json.loads(source.read_text(), parse_float=Decimal); rows=[]
        for item in data:
            raw=item['payload']; tx=item['metric']=='txcount'
            for point in raw['details']['timeseries']['daily']['data']:
                date=dt.datetime.fromtimestamp(int(point[0])/1000,UTC).date().isoformat()
                if not '2026-10-01' <= date < '2026-10-22': continue
                value = str(int(Decimal(str(point[1])))) if tx else str(point[2])
                rows.append(dict(chain='base',chain_id=8453,date_utc=date,metric='network_transaction_count_provider_defined' if tx else 'network_fees_provider_defined',value=value,unit='transactions' if tx else 'ETH',source_metric='txcount' if tx else 'fees_paid_eth',source='growthepie',source_url=item['url'],source_updated_at_utc=raw['last_updated_utc'],retrieved_at_utc=item['retrieved_at_utc'],source_sha256=item['sha256']))
        rows.sort(key=lambda r:(r['metric'],r['date_utc']))
    elif kind == 'coinmetrics':
        rows=[]
        for item in json.loads(source.read_text()):
            for r in item['data']:
                rows.append(dict(asset=item['asset'].upper(),observation_time_utc=r['time'],market_cap_current_usd=r.get('CapMrktCurUSD',''),market_cap_estimated_usd=r.get('CapMrktEstUSD',''),reported_spot_volume_usd_1d=r.get('volume_reported_spot_usd_1d',''),source_url=item['url']))
        rows.sort(key=lambda r:(r['asset'],r['observation_time_utc']))
    elif kind == 'cmc':
        rows=[]
        for q in json.loads(source.read_text()):
            if not '2026-09-01' <= q['timestamp'][:10] <= '2026-10-27': continue
            usd=next(r for r in q['quote'] if r['name']=='USD')
            rows.append(dict(observation_time_utc=q['timestamp'],market_cap_usd=usd['totalMarketCap'],volume_24h_usd=usd['totalVolume24H'],volume_24h_reported_usd=usd['totalVolume24HReported'],btc_dominance_percent=q['btcDominance'],eth_dominance_percent=q['ethDominance'],source_url=spec['url']))
        rows.sort(key=lambda r:r['observation_time_utc'])
    elif kind == 'coinspectrum':
        obj=json.loads(source.read_text());common=dict(generated_at_utc=obj['generated_at'],archive_capture_utc=spec['archive_capture_utc'],source_url=spec['source_url'],archive_url=spec['archive_url'])
        if 'assets' in obj:
            rows=[dict(**common,asset=a['slug'],symbol=a['symbol'],price_usd=a.get('price_usd'),market_cap_usd=a.get('market_cap_usd'),circulating_supply=(a.get('supply') or {}).get('circulating'),rank=a.get('rank')) for a in obj['assets']]
            rows.sort(key=lambda r:r['asset'])
        else: rows=[dict(**common,total_market_cap_usd=obj['total_market_cap_usd'])]
    elif kind == 'macro':
        obj=json.loads(source.read_text());rows=[]
        for r in obj['effr']:
            if '2026-01-01'<=r['effectiveDate']<='2026-10-27':rows.append(dict(series='EFFR',observation_date=r['effectiveDate'],value=r['percentRate'],unit='percent per annum',frequency='business day',publication_timestamp_utc='',revision_indicator=r.get('revisionIndicator',''),source_url=spec['urls']['nyfed_effr']))
        for sid,unit in [('CUUR0000SA0','index 1982-1984=100'),('LNS14000000','percent')]:
            for r in obj[sid]:
                if r['period'].startswith('M') and r['period']!='M13':
                    date=r['year']+'-'+r['period'][1:]+'-01'
                    if '2026-01-01'<=date<='2026-10-27': rows.append(dict(series=sid,observation_date=date,value=r['value'],unit=unit,frequency='monthly',publication_timestamp_utc='',revision_indicator='',source_url=spec['urls']['bls_'+sid.lower()]))
        rows.sort(key=lambda r:(r['series'],r['observation_date']))
    elif kind == 'treasury':
        import xml.etree.ElementTree as ET
        ns={'m':'http://schemas.microsoft.com/ado/2007/08/dataservices/metadata','d':'http://schemas.microsoft.com/ado/2007/08/dataservices'};rows=[]
        for el in ET.parse(source).findall('.//m:properties',ns):
            date=el.findtext('d:NEW_DATE',default='',namespaces=ns)[:10];value=el.findtext('d:BC_10YEAR',default='',namespaces=ns)
            if '2026-01-01'<=date<='2026-10-27' and value: rows.append(dict(observation_date=date,series='US_TREASURY_10Y_PAR_YIELD',value_percent=value,source_url=spec['url']))
        rows.sort(key=lambda r:r['observation_date'])
    elif kind == 'bls_release':
        rows=read_csv(source)
        for r in rows:
            local=dt.datetime.fromisoformat(r['release_embargo_end_local']).replace(tzinfo=ZoneInfo('America/New_York'))
            r['release_embargo_end_utc']=local.astimezone(UTC).isoformat()
    else: raise ValueError(kind)
    write_csv(output/job['output'],fields,rows)
    return rows

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,required=True,help='Path to the paired data/ directory')
    parser.add_argument('--output',type=Path,required=True,help='New directory for rebuilt CSVs and verification.json')
    args=parser.parse_args(); base=Path(__file__).resolve().parents[1]
    output=args.output.resolve();data=args.data.resolve()
    if output.exists(): raise SystemExit('Choose a new output directory; existing files are preserved.')
    if output==data or data in output.parents: raise SystemExit('Output must be outside the reference data directory.')
    inputs=base/'inputs';jobs=json.loads((base/'jobs.json').read_text())
    checks=json.loads((base/'input-checksums.json').read_text())
    for name,digest in checks.items():
        if hashlib.sha256((inputs/name).read_bytes()).hexdigest()!=digest: raise ValueError(f'Input hash mismatch: {name}')
    # Reference hashes are checked separately from rebuilding; parsers never consume reference outputs.
    manifest=json.loads((base.parent/'metadata/manifest.json').read_text())
    for item in manifest:
        if hashlib.sha256((data/item['path']).read_bytes()).hexdigest()!=item['sha256']:raise ValueError(f'Reference hash mismatch: {item["path"]}')
    output.mkdir(parents=True);results=[]
    for job in jobs:
        rebuild(job,inputs,output)
        got=read_csv(output/job['output']);want=read_csv(data/job['output'])
        if len(got)!=len(want):raise ValueError(f'Row mismatch: {job["output"]}')
        numeric=job['kind']=='rpc'
        for a,b in zip(got,want):
            if a.keys()!=b.keys():raise ValueError('Column mismatch')
            for k in a:
                if a[k]==b[k]:continue
                if numeric:
                    try:
                        if math.isclose(float(a[k]),float(b[k]),rel_tol=1e-12,abs_tol=1e-9):continue
                    except ValueError:pass
                raise ValueError(f'{job["output"]}: {k}: {a[k]!r} != {b[k]!r}')
        results.append(dict(file=job['output'],rows=len(got),kind=job['kind'],comparison='numeric tolerance 1e-12 relative / 1e-9 absolute' if numeric else 'exact field values',byte_identical=(output/job['output']).read_bytes()==(data/job['output']).read_bytes()))
    report=dict(status='Verified',inputs_verified=len(checks),tables=len(results),results=results)
    (output/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(status='Verified',tables=len(results),inputs_verified=len(checks),byte_identical=sum(x['byte_identical'] for x in results))))

if __name__=='__main__':main()
