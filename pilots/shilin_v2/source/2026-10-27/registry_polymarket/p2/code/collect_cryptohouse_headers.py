"""Small key-filtered pages on the officially public CryptoHouse SQL service.

Respect its2000-result-row cap; select at most400 explicitly needed slots.
Do not raise server limits, wrap rows in aggregate arrays, or export full ledger.
"""
from p2io import *
import urllib.parse

def cached_headers():
    out={}
    for path in [ROOT/'reports/query_ledger_solana_mainnet.csv',ROOT/'reports/solana_light_query_ledger.csv']:
        if not path.exists():continue
        for seg in read_csv(path):
            if seg['status']!='complete_segment':continue
            for b in blocks(read_body(ROOT/seg['raw_ref'])):
                h=b['header'];old=out.get(h['number'])
                if old and old['hash']!=h['hash']:raise RuntimeError('Conflicting cached archive block hash')
                out[h['number']]={**h,'source_raw_ref':seg['raw_ref'],'source_id':'SQD_public_portal'}
    return out

def run():
    known=cached_headers();candidates=read_csv(ROOT/'reports/solana_native_creation_candidates.csv')+read_csv(ROOT/'reports/solana_native_index_failed_transactions.csv');wanted=sorted({int(r['slot']) for r in candidates});path=ROOT/'reports/cryptohouse_header_partitions.csv';ledger=read_csv(path) if path.exists() else []
    for seg in ledger:
        if sha(ROOT/seg['raw_ref'])!=seg['sha256']:raise RuntimeError('SQL header raw hash conflict')
        for h in json.loads(read_body(ROOT/seg['raw_ref']))['data']:
            slot=int(h['slot']);known[slot]={'number':slot,'hash':h['block_hash'],'timestamp':int(h['timestamp']),'source_raw_ref':seg['raw_ref'],'source_id':'CryptoHouse_public_SQL'}
    missing=[s for s in wanted if s not in known];c=Client(budget=250)
    for offset in range(0,len(missing),400):
        slots=missing[offset:offset+400]
        q="SELECT slot,block_hash,toUnixTimestamp(block_timestamp) AS timestamp FROM solana.blocks WHERE block_timestamp>=toDateTime('2026-10-08 00:00:00','UTC') AND block_timestamp<toDateTime('2026-10-09 00:00:00','UTC') AND slot IN ("+','.join(map(str,slots))+") ORDER BY slot FORMAT JSON"
        d,m=c.json('https://crypto-clickhouse.clickhouse.com/?'+urllib.parse.urlencode({'user':'crypto','query':q}),label='CryptoHouse_public_needed_slot_header_page')
        if not m['ok'] or not isinstance(d,dict):raise RuntimeError('Public SQL header page failed: '+m['error'])
        data=d['data'];actual=[int(r['slot']) for r in data]
        if actual!=slots or int(d['rows'])!=len(slots):raise RuntimeError('SQL result truncated, missing or conflicting block slots')
        for h in data:
            slot=int(h['slot']);known[slot]={'number':slot,'hash':h['block_hash'],'timestamp':int(h['timestamp']),'source_raw_ref':m['raw_ref'],'source_id':'CryptoHouse_public_SQL'}
        ledger.append({'requested_slots':len(slots),'first_slot':slots[0],'last_slot':slots[-1],'slot_list_hash':sid(slots),'rows':len(data),'status':'passed_exact_slot_set','request_id':m['request_id'],'raw_ref':m['raw_ref'],'sha256':m['sha256'],'retrieved_at_utc':m['retrieved_at_utc'],'source_query_elapsed_seconds':d.get('statistics',{}).get('elapsed','')});write_csv(path,ledger)
        print('SQL_HEADERS',len(wanted)-len(missing)+min(offset+400,len(missing)),'of',len(wanted),flush=True)
        time.sleep(.5)
    conflicts=[r['signature'] for r in candidates if known[int(r['slot'])]['timestamp']!=epoch(r['block_time_utc'])]
    if conflicts:raise RuntimeError('Native signature index/SQL block time conflict')
    write_csv(ROOT/'data/solana_header_sources.csv',[known[s] for s in wanted])
    report={'status':'passed_all_index_candidate_slots_have_time_consistent_block_headers','candidate_slots':len(wanted),'archive_header_slots_reused':sum(known[s]['source_id']=='SQD_public_portal' for s in wanted),'CryptoHouse_SQL_header_slots':sum(known[s]['source_id']=='CryptoHouse_public_SQL' for s in wanted),'time_conflicts':len(conflicts),'public_SQL_access_basis':'https://github.com/ClickHouse/CryptoHouse#direct-connections; public crypto user, blank password; no personal credentials','result_limit_policy':'At most400 rows/request; respects2000 public result cap; no server limit changes','completed_at_utc':now()};write_json(ROOT/'reports/cryptohouse_headers_receipt.json',report);print(json.dumps(report),flush=True)
if __name__=='__main__':run()
