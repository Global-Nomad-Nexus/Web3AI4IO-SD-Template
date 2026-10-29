"""Independent streaming counts plus a claim ledger for existing P3 prose (read only)."""
import argparse,csv,json,re,sys
from collections import Counter,defaultdict
from pathlib import Path

def read(p):
 with p.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def write(p,rows):
 with p.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
 p=argparse.ArgumentParser();p.add_argument('--run',required=True,type=Path);p.add_argument('--report',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args();root=a.run;out=a.output;out.mkdir(parents=True,exist_ok=True)
 manifest=read(root/'provenance/processed_manifest.csv');metrics={Path(r['path']).stem+'_rows':int(r['rows']) for r in manifest}
 chains=Counter();days=Counter();ids=set();mintimes=[]
 for r in read(root/'processed/registry.csv'):
  chains[r['chain_key']]+=1;days[r['created_at_utc'][:10],r['chain_key']]+=1;ids.add(r['token_id']);mintimes.append(r['created_at_utc'])
 metrics.update(registry_tokens=len(ids),counts_by_chain=dict(chains),first_creation=min(mintimes),last_creation=max(mintimes))
 counts=Counter();matchedids=set();n=0
 with (root/'processed/token_expectations_at_creation.csv').open(newline='',encoding='utf-8') as f:
  for r in csv.DictReader(f):
   counts[r['match_status']]+=1;n+=1
   if r['match_status']=='matched_valid':matchedids.add(r['token_id'])
 metrics.update(expectation_assessments=n,expectation_status=dict(counts),tokens_with_any_background=len(matchedids))
 cat=read(root/'processed/pm_candidate_catalogue.csv');maps=read(root/'processed/pm_mapping.csv');markets=read(root/'processed/pm_markets.csv');cov=read(root/'processed/metadata_coverage.csv')
 metrics.update(candidate_unique_markets=len({r['market_id'] for r in cat}),rule_hashes=len({r['rules_sha256'] for r in markets}),mapping_types=dict(Counter(r['link_type'] for r in maps)),metadata_states=dict(Counter(r['final_state'] for r in cov)),metadata_any_json_tokens=len({r['token_id'] for r in cov if r['final_state']=='observed'}),legacy_tokens=len({r['token_id'] for r in cov}),metadata_timeliness=dict(Counter(r.get('timing_status',r.get('lateness_status','')) for r in cov)))
 qa=json.loads((root/'reports/native_QA_receipt.json').read_text());valid=json.loads((root/'reports/validation_results.json').read_text());metrics.update(native_qa_cases=qa['checked'],native_qa_groups=qa['groups'],real_checks=len(valid['checks']),real_failed=sum(c['status']=='failed' for c in valid['checks']))
 lines=a.report.read_text().splitlines();claims=[]
 def claim(key,actual,pattern,needle='',scope='P3_existing_report'):
  found=[(i+1,line) for i,line in enumerate(lines) if (not needle or needle in line) and re.search(pattern,line)]
  claims.append(dict(claim_id=key,scope=scope,actual=json.dumps(actual,ensure_ascii=False),expected_expression=pattern,status='passed' if found else 'failed',source_file=str(a.report),source_lines=json.dumps([i for i,_ in found]),evidence_excerpt=found[0][1] if found else 'not found'))
 def number(v):return f'{v:,}'.replace(',','[,]?')
 claim('registry_total',len(ids),number(len(ids)),'不同代币')
 for c in chains:claim('chain_total_'+c,chains[c],number(chains[c]),'最终数据包含')
 claim('assessments',n,number(n),'连接评估记录');claim('matched_assessments',counts['matched_valid'],number(counts['matched_valid']),'有效连接')
 claim('invalid_mapping_rows',counts['mapping_outside_validity'],number(counts['mapping_outside_validity']),'300,690')
 for table in manifest:
  name=Path(table['path']).name;value=int(table['rows']);claim('table_rows_'+name,value,number(value),name)
 for day in sorted({k[0] for k in days}):
  values=[days[day,c] for c in ['solana:mainnet','eip155:8453','eip155:56']];values.append(sum(values));pattern=r'\|\s*'+day+r'\s*\|'+''.join(r'\s*'+number(v)+r'\s*\|' for v in values)
  claim('daily_counts_'+day,values,pattern)
 for key,value,needle in [('candidate_unique_markets',metrics['candidate_unique_markets'],'去重后'),('rule_hashes',metrics['rule_hashes'],'不同规则'),('legacy_tokens',metrics['legacy_tokens'],'旧七日队列'),('metadata_any_json_tokens',metrics['metadata_any_json_tokens'],'至少有一次历史 JSON'),('native_qa_cases',qa['checked'],'固定种子原生 QA'),('native_qa_groups',qa['groups'],'固定种子原生 QA'),('real_checks',len(valid['checks']),'项数据验收')]:claim(key,value,number(value),needle)
 for kind,value in metrics['metadata_states'].items():claim('metadata_'+kind,value,number(value),'| '+kind+' |')
 for kind,value in metrics['mapping_types'].items():claim('mapping_'+kind,value,number(value),{'chain':'条链背景','platform':'条平台背景','shared_economic_event':'条共享经济事件背景'}[kind])
 claim('direct_identity_mappings',0,r'直接币身份映射.*?0')
 # The shorter existing five-section manuscript has its own clock and count assertions.
 manuscript=root/'manuscript/P3_sections.md';text=manuscript.read_text()
 for name,value in [('registry',len(ids)),('expectations',n),*list(chains.items()),('real_checks',len(valid['checks']))]:
  claims.append(dict(claim_id='manuscript_'+name,scope='P3_existing_five_sections',actual=str(value),expected_expression=str(value),status='passed' if str(value) in text else 'failed',source_file=str(manuscript),source_lines=json.dumps([i+1 for i,line in enumerate(text.splitlines()) if str(value) in line]),evidence_excerpt='numeric literal checked against rebuilt tables/revalidation'))
 # All concrete 15-table row counts are checked against actual reconstructed rows by
 # accept_delivery; this audit adds semantic status, unique token and prose checks.
 source_metrics={k:v for k,v in metrics.items()};(out/'metrics.json').write_text(json.dumps(source_metrics,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
 write(out/'prose_number_checks.csv',claims)
 failure=[r['claim_id'] for r in claims if r['status']!='passed'];(out/'receipt.json').write_text(json.dumps(dict(status='passed' if not failure else 'failed',checks=len(claims),failed=failure,article_modified=False,scope='core counts, daily activity, table rows, metadata states, market mappings, existing five-section prose; not an editorial/content review'),ensure_ascii=False,indent=2)+'\n')
 print('NUMERIC_AUDIT',len(claims),'claims',failure,flush=True)
 if failure:raise SystemExit(1)
if __name__=='__main__':main()
