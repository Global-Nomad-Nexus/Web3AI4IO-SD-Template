"""Check the adapter against the full real Registry without inventing ecosystem events."""
import argparse,csv,hashlib,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from lifecycle_adapter import Adapter

def main():
 p=argparse.ArgumentParser();p.add_argument('--registry',required=True,type=Path);p.add_argument('--crosswalk',required=True,type=Path);p.add_argument('--config',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args();start=time.monotonic()
 fields=['token_id','chain_key','token_address_canonical','created_at_utc','creator_address','creator_role_definition']
 with a.registry.open(newline='',encoding='utf-8') as f:registry=[{k:r[k] for k in fields} for r in csv.DictReader(f)]
 with a.crosswalk.open(newline='',encoding='utf-8') as f:
  crosswalk=[dict(chain_key=r['token_id'].split(':token:',1)[0],object_id=r['legacy_event_key'],token_id=r['token_id']) for r in csv.DictReader(f)]
 adapter=Adapter(registry,json.loads(a.config.read_text()),crosswalk,'real');joined=adapter.join([],[])
 expected={r['token_id'] for r in registry};actual={r['token_id'] for r in joined};created={r['token_id']:r['created_at_utc'] for r in registry}
 checks={'left_join_tokens_preserved':actual==expected and len(joined)==len(registry),'creation_times_unchanged':all(r['created_at_utc']==created[r['token_id']] for r in joined),'all_no_ecosystem_input_explicit_unmatched':all(r['ecosystem_match_status']=='ecosystem_unmatched' for r in joined),'no_death_or_outcome_labels_generated':all('death' not in r and 'outcome' not in r for r in joined),'crosswalk_all_keys_resolved':len(crosswalk)==4668}
 result=dict(status='passed' if all(checks.values()) else 'failed',scope='real_registry_identity_readiness_only; no real lifecycle event supplied',registry_tokens=len(registry),crosswalk_rows=len(crosswalk),checks=checks,real_lifecycle_integration_status='awaiting_integration',outcome_followup_generated=False,common_cutoff_utc=None,elapsed_seconds=round(time.monotonic()-start,3),adapter_sha256=hashlib.sha256(Path(__file__).with_name('lifecycle_adapter.py').read_bytes()).hexdigest())
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
 if result['status']!='passed':raise SystemExit(1)
if __name__=='__main__':main()
