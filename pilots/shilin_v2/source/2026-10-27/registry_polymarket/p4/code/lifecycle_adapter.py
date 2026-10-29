"""Versioned lifecycle adapter. Standard library only; no implicit identity inference.

Events/coverage are quarantined on errors. Registry rows are never mutated.
Interval semantics are [start,end), including the analysis interval [creation,cutoff).
"""
from __future__ import annotations
import argparse, csv, hashlib, json, re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

VERSION = 'shilin_lifecycle_adapter_v1'
KINDS = {'first_trade','graduation','migration','venue_change','activity','inactivity','reactivation','other_evidenced_event'}
STATUSES = {'complete','partial','unknown','not_applicable','source_missing'}
CHAINS = {'solana:mainnet','eip155:8453','eip155:56'}


def timestamp(value, unit='iso8601'):
    if unit == 'epoch_seconds':
        if isinstance(value, bool) or not re.fullmatch(r'\d+(\.\d+)?',str(value)):
            raise ValueError('invalid epoch seconds')
        value = float(value)
        if value > 100_000_000_000: raise ValueError('milliseconds forbidden in epoch_seconds')
        return datetime.fromtimestamp(value, timezone.utc)
    if not isinstance(value,str) or not value.endswith(('Z','+00:00')) or 'T' not in value:
        raise ValueError('explicit UTC ISO8601 required; no naive/local/numeric clock')
    return datetime.fromisoformat(value.replace('Z','+00:00'))


def iso(value): return value.isoformat(timespec='microseconds' if value.microsecond else 'seconds').replace('+00:00','Z')

def identity(chain, address):
    if chain not in CHAINS: raise ValueError('unsupported chain_key')
    if chain.startswith('eip155:'):
        if not re.fullmatch(r'0x[0-9a-fA-F]{40}',str(address)): raise ValueError('invalid EVM address')
        address = address.lower()
    elif not re.fullmatch(r'[1-9A-HJ-NP-Za-km-z]{32,44}',str(address)):
        raise ValueError('invalid case-preserved Solana address')
    return chain+':token:'+address


def stable(value): return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:32]

def rows(path):
    with Path(path).open(newline='',encoding='utf-8') as f: return list(csv.DictReader(f))

def write(path, values, fields):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(values)


class Adapter:
    def __init__(self, registry, config, crosswalk=(), mode='real'):
        if mode not in {'real','synthetic_test'}: raise ValueError('invalid mode')
        self.config=config;self.mode=mode;self.registry={};self.errors=[];self.notes=[]
        if config['interface_version']!=VERSION: raise ValueError('unsupported interface version')
        for r in registry:
            tid=identity(r['chain_key'],r['token_address_canonical'])
            if tid!=r['token_id'] or tid in self.registry: raise ValueError('invalid/duplicate Registry token_id')
            timestamp(r['created_at_utc'])
            if mode=='real' and r.get('dataset_kind')=='synthetic_test': raise ValueError('synthetic Registry forbidden')
            self.registry[tid]=dict(r)
        self.cross={}
        for r in crosswalk:
            key=(self.chain(r['chain_key']),r['object_id'])
            if key in self.cross and self.cross[key]!=r['token_id']: raise ValueError('ambiguous crosswalk')
            if r['token_id'] not in self.registry or not r['token_id'].startswith(key[0]+':token:'):
                raise ValueError('crosswalk foreign key/chain mismatch')
            self.cross[key]=r['token_id']

    def chain(self,value):
        aliases=self.config.get('chain_aliases',{})
        # JSON mapping keys are strings; never accept ambiguous chain-free addresses.
        value=aliases.get(str(value),value)
        if value not in CHAINS: raise ValueError('unsupported chain_key')
        return value

    def normalize(self,row,table):
        out=dict(row)
        if self.mode=='real' and row.get('dataset_kind')=='synthetic_test': raise ValueError('synthetic row forbidden in real mode')
        if self.mode=='synthetic_test' and row.get('dataset_kind')!='synthetic_test': raise ValueError('fixture must declare dataset_kind=synthetic_test')
        for alias,target in self.config.get('field_mapping',{}).get(table,{}).items():
            if alias in row and row[alias] not in ('',None):
                same_chain=target=='chain_key' and out.get(target) not in ('',None) and self.chain(out[target])==self.chain(row[alias])
                if out.get(target) not in ('',None) and str(out[target])!=str(row[alias]) and not same_chain:
                    raise ValueError('conflicting alias '+alias+' -> '+target)
                out[target]=row[alias]
        if out.get('chain_key') not in ('',None): out['chain_key']=self.chain(out['chain_key'])
        candidates=[]
        if out.get('token_id'): candidates.append(out['token_id'])
        if out.get('token_address_raw'):
            if not out.get('chain_key'): raise ValueError('address requires explicit chain_key')
            candidates.append(identity(out['chain_key'],out['token_address_raw']))
        if out.get('object_id'):
            if not out.get('chain_key'): raise ValueError('object_id crosswalk requires chain_key')
            key=(out['chain_key'],out['object_id'])
            if key not in self.cross: raise ValueError('object_id missing from explicit crosswalk')
            candidates.append(self.cross[key])
        if not candidates: raise ValueError('missing token identity')
        if len(set(candidates))!=1: raise ValueError('identity fields disagree')
        tid=candidates[0]
        if tid not in self.registry: raise ValueError('token_id missing from Registry')
        r=self.registry[tid]
        if out.get('chain_key') and out['chain_key']!=r['chain_key']: raise ValueError('token_id/chain_key conflict')
        out.update(token_id=tid,chain_key=r['chain_key'])
        if out.get('created_at_utc') and timestamp(out['created_at_utc'])!=timestamp(r['created_at_utc']):
            raise ValueError('creation clock conflict; Registry is authoritative')
        if out.get('creator_role_definition') and out['creator_role_definition']!=r.get('creator_role_definition'):
            raise ValueError('creator role conflict')
        if out.get('creator_address'):
            actual=out['creator_address'];expected=r.get('creator_address','')
            if r['chain_key'].startswith('eip155:'):actual=actual.lower();expected=expected.lower()
            if actual!=expected or out.get('creator_role_definition',r.get('creator_role_definition'))!=r.get('creator_role_definition'):
                raise ValueError('creator identity/role conflict')
        # first_seen_in_window is retained as source context, never mapped to creation.
        if out.get('interface_version',VERSION)!=VERSION: raise ValueError('unsupported row interface version')
        out['interface_version']=VERSION
        return out

    def diagnostic(self,source,line,code,row):
        self.errors.append({'source_file':source,'row_number':line,'reason':str(code),'raw_row_json':json.dumps(row,ensure_ascii=False,sort_keys=True),'dataset_kind':self.mode})

    def events(self,values,source='events.csv',cutoff=None):
        grouped=defaultdict(list)
        for line,row in enumerate(values,2):
            try:
                e=self.normalize(row,'events')
                for k in ['event_type','event_time_utc','observed_at_utc','source_id','transaction_id','native_position','event_evidence_ref']:
                    numeric_time=k in ['event_time_utc','observed_at_utc'] and self.config.get('time_units',{}).get(k)=='epoch_seconds' and isinstance(e.get(k),(int,float)) and not isinstance(e.get(k),bool)
                    if not numeric_time and (not isinstance(e.get(k),str) or not e[k].strip()): raise ValueError('required nonempty string '+k)
                if e['event_type'] not in KINDS:raise ValueError('unsupported event_type')
                if not isinstance(e['native_position'],str) or not re.fullmatch(r'(log:\d+|ix:\d+(?:\.\d+)*)',e['native_position']):
                    raise ValueError('native_position must be log:N or ix:N[.N]')
                if e['chain_key'].startswith('eip155:'):
                    if not re.fullmatch(r'0x[0-9a-fA-F]{64}',e['transaction_id']):raise ValueError('invalid EVM transaction hash')
                    e['transaction_id']=e['transaction_id'].lower()
                    if not e['native_position'].startswith('log:'):raise ValueError('EVM requires log position')
                else:
                    if not re.fullmatch(r'[1-9A-HJ-NP-Za-km-z]{64,88}',e['transaction_id']):raise ValueError('invalid Solana signature')
                    if not e['native_position'].startswith('ix:'):raise ValueError('Solana requires instruction path')
                prefix,position=e['native_position'].split(':',1)
                e['native_position']=prefix+':'+'.'.join(str(int(part)) for part in position.split('.'))
                units=self.config.get('time_units',{})
                t=timestamp(e['event_time_utc'],units.get('event_time_utc','iso8601'))
                observed=timestamp(e['observed_at_utc'],units.get('observed_at_utc','iso8601'))
                if observed<t:raise ValueError('observation before event')
                if t<timestamp(self.registry[e['token_id']]['created_at_utc']):raise ValueError('event before creation')
                if not e.get('venue_id') and not e.get('missing_reason'):raise ValueError('missing venue requires missing_reason')
                e['event_time_utc']=iso(t);e['observed_at_utc']=iso(observed)
                key=(e['chain_key'],e['transaction_id'],e['native_position'],e['event_type'])
                e['lifecycle_event_id']='lifecycle:'+stable(key)
                e['analysis_eligible']=not cutoff or t<timestamp(cutoff)
                grouped[key].append((e,row,line))
            except (ValueError,KeyError,TypeError,OverflowError) as error:self.diagnostic(source,line,error,row)
        accepted=[]
        # Different token/time/venue/source evidence payloads at the same native identity
        # are conflicts. All conflicting versions are quarantined, independent of order.
        compare=['token_id','event_time_utc','venue_id','event_evidence_ref','source_id','creator_address','creator_role_definition']
        for key,group in grouped.items():
            payloads={tuple(str(e.get(k,'')) for k in compare) for e,_,_ in group}
            if len(payloads)>1:
                for _,raw,line in group:self.diagnostic(source,line,'conflicting repeated native event; all versions quarantined',raw)
            else:
                chosen=min((e for e,_,_ in group),key=lambda e:timestamp(e['observed_at_utc']))
                accepted.append(chosen)
                if len(group)>1:self.notes.append({'reason':'exact_repeat_collapsed','event_id':chosen['lifecycle_event_id'],'rows':len(group),'source_rows':[v[2] for v in group]})
        return sorted(accepted,key=lambda e:(e['token_id'],e['event_time_utc'],e['lifecycle_event_id']))

    def coverage(self,values,source='coverage.csv'):
        accepted=[];seen=set()
        for line,row in enumerate(values,2):
            try:
                e=self.normalize(row,'coverage')
                for k in ['layer_or_venue','interval_start_utc','interval_end_utc','coverage_status','source_id','coverage_evidence_ref']:
                    if not isinstance(e.get(k),str) or not e[k].strip():raise ValueError('required nonempty string '+k)
                if e['coverage_status'] not in STATUSES:raise ValueError('unsupported coverage_status')
                a=timestamp(e['interval_start_utc']);b=timestamp(e['interval_end_utc'])
                if not a<b:raise ValueError('empty/reversed coverage interval')
                if e['coverage_status']!='complete' and not e.get('missing_reason'):raise ValueError('non-complete interval requires missing_reason')
                e['interval_start_utc']=iso(a);e['interval_end_utc']=iso(b)
                key=tuple(str(e.get(k,'')) for k in ['token_id','layer_or_venue','interval_start_utc','interval_end_utc','coverage_status','source_id','coverage_evidence_ref'])
                if key not in seen:
                    e['_source_row']=line;accepted.append(e);seen.add(key)
            except (ValueError,KeyError,TypeError) as error:self.diagnostic(source,line,error,row)
        # Within one source/layer contradictory overlapping claims cannot close followup.
        groups=defaultdict(list);bad=set()
        for i,e in enumerate(accepted):groups[(e['token_id'],e['layer_or_venue'],e['source_id'])].append((i,e))
        for group in groups.values():
            ordered=sorted(group,key=lambda x:x[1]['interval_start_utc'])
            for n,(i,a) in enumerate(ordered):
                for j,b in ordered[n+1:]:
                    if timestamp(b['interval_start_utc'])>=timestamp(a['interval_end_utc']):break
                    if a['coverage_status']!=b['coverage_status']:
                        bad.update([i,j])
        for i in sorted(bad):self.diagnostic(source,accepted[i].get('_source_row',0),'contradictory overlapping coverage',accepted[i])
        return [e for i,e in enumerate(accepted) if i not in bad]

    def join(self,events,coverage):
        ev=defaultdict(list);cv=defaultdict(list)
        for e in events:ev[e['token_id']].append(e)
        for c in coverage:cv[c['token_id']].append(c)
        return [{**r,'ecosystem_match_status':'matched' if ev[tid] or cv[tid] else 'ecosystem_unmatched',
                 'lifecycle_event_count':len(ev[tid]),'coverage_interval_count':len(cv[tid]),
                 'real_lifecycle_integration_status':'awaiting_integration' if self.mode=='real' else 'synthetic_test',
                 'dataset_kind':self.mode} for tid,r in self.registry.items()]

    def followup(self,events,coverage,cutoff,targets):
        stop=timestamp(cutoff);out=[]
        for tid,r in self.registry.items():
            start=timestamp(r['created_at_utc'])
            if stop<=start:raise ValueError('cutoff must be later than every creation')
            for target,layer in targets.items():
                if target not in KINDS:raise ValueError('unsupported target')
                intervals=[c for c in coverage if c['token_id']==tid and c['layer_or_venue']==layer]
                complete=sorted((max(start,timestamp(c['interval_start_utc'])),min(stop,timestamp(c['interval_end_utc']))) for c in intervals if c['coverage_status']=='complete')
                cursor=start;refs=[]
                for a,b in complete:
                    if a>cursor:break
                    if b>cursor:cursor=b
                # A target can be observed even after a gap, but first occurrence time is
                # unverified unless coverage is contiguous from creation through that event.
                observed=sorted((e for e in events if e['token_id']==tid and e['event_type']==target and timestamp(e['event_time_utc'])<stop),key=lambda e:e['event_time_utc'])
                first=observed[0] if observed else None
                if first:
                    status='observed_event';end=timestamp(first['event_time_utc']);censored=False
                elif cursor>=stop:status='administrative_right_censored';end=stop;censored=True
                elif cursor>start:status='loss_to_followup';end=cursor;censored=True
                else:status='unknown';end=start;censored=None
                out.append({'token_id':tid,'target_event_type':target,'layer_or_venue':layer,'followup_start_utc':iso(start),'analysis_cutoff_utc':cutoff,
                            'status':status,'event_observed':bool(first),'is_right_censored':censored,'followup_end_utc':iso(end),
                            'contiguous_observed_until_utc':iso(cursor),'first_occurrence_verified':bool(first and cursor>timestamp(first['event_time_utc'])),
                            'lifecycle_event_id':first['lifecycle_event_id'] if first else '',
                            'coverage_evidence_refs':json.dumps(sorted({c['coverage_evidence_ref'] for c in intervals}),ensure_ascii=False),
                            'dataset_kind':self.mode})
        return out


def validate_expectation_proxy(price, anchor):
    """Gate for external expectation handoffs; historical scalar can stay restricted.
    No source-time substitution, current quotes or settlement payouts as expectations.
    """
    if price.get('price_role') != 'historical_bucket':
        raise ValueError('only explicitly historical bucket observations may be linked')
    if price.get('is_settlement_point') not in (False, 'false', 'False'):
        raise ValueError('settlement/unknown points excluded')
    start=timestamp(price['bucket_start_utc']);end=timestamp(price['bucket_end_utc'])
    if not start<end<timestamp(anchor):raise ValueError('whole bucket must end strictly before anchor')
    from decimal import Decimal
    value=Decimal(str(price['price']))
    if not value.is_finite() or not 0<=value<=1:raise ValueError('invalid probability scalar')
    return 'retrospective_demonstration_only' if price.get('price_definition_status')=='unconfirmed_API_scalar' else 'time_valid_requires_semantic_review'


def run_cli():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ['registry','config','output']:p.add_argument('--'+arg,required=True,type=Path)
    for arg in ['events','coverage','crosswalk']:p.add_argument('--'+arg,type=Path)
    p.add_argument('--mode',choices=['real','synthetic_test'],default='real');p.add_argument('--cutoff')
    args=p.parse_args();config=json.loads(args.config.read_text())
    if args.mode=='synthetic_test' and 'test_outputs' not in args.output.resolve().parts:raise ValueError('synthetic outputs must be under test_outputs')
    if args.cutoff and args.mode=='real' and not config.get('joint_definitions_confirmed'):
        raise ValueError('real outcomes require confirmed P5 definitions and cutoff')
    if args.output.exists() and any(args.output.iterdir()):raise ValueError('output directory must be empty')
    args.output.mkdir(parents=True,exist_ok=True)
    adapter=Adapter(rows(args.registry),config,rows(args.crosswalk) if args.crosswalk else [],args.mode)
    events=adapter.events(rows(args.events) if args.events else [],str(args.events),args.cutoff)
    coverage=adapter.coverage(rows(args.coverage) if args.coverage else [],str(args.coverage))
    joined=adapter.join(events,coverage)
    write(args.output/'identity_join.csv',joined,list(joined[0]) if joined else ['token_id'])
    if args.events:write(args.output/'lifecycle_events.csv',events,list(events[0]) if events else ['lifecycle_event_id'])
    if args.coverage:write(args.output/'observation_coverage.csv',coverage,list(coverage[0]) if coverage else ['token_id'])
    if args.cutoff:
        if args.mode=='real' and not config.get('joint_definitions_confirmed'):raise ValueError('real outcomes require confirmed P5 definitions and cutoff')
        outcomes=adapter.followup(events,coverage,args.cutoff,config['target_layers'])
        write(args.output/'outcome_followup.csv',outcomes,list(outcomes[0]))
    write(args.output/'quarantine.csv',adapter.errors,['source_file','row_number','reason','raw_row_json','dataset_kind'])
    (args.output/'receipt.json').write_text(json.dumps({'interface_version':VERSION,'mode':args.mode,'registry_tokens':len(adapter.registry),'joined_tokens':len(joined),'accepted_events':len(events),'accepted_coverage':len(coverage),'quarantined_rows':len(adapter.errors),'duplicates':adapter.notes,'real_lifecycle_integration_status':'awaiting_integration','common_cutoff_utc':None,'status':'passed' if not adapter.errors else 'failed_with_quarantine'},indent=2))
    if adapter.errors:raise SystemExit(1)


if __name__=='__main__':run_cli()
