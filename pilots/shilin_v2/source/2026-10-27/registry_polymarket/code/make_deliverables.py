"""Produce the P0/P1 review packet from actual reports, not planned results."""
import collections
import platform
import sys
from common import *

def run():
    audit=json.loads((ROOT/'reports/baseline_audit.json').read_text())
    checks=json.loads((ROOT/'reports/validation_results.json').read_text())
    receipt=json.loads((ROOT/'reports/polymarket_probe_receipt.json').read_text())
    example=json.loads((ROOT/'reports/real_asof_example.json').read_text())
    repro=json.loads((ROOT/'reports/offline_reproduction.json').read_text())
    sources=read_csv(ROOT/'reports/source_capability.csv')
    requests=[json.loads(line) for line in (ROOT/'provenance/requests.jsonl').read_text().splitlines()]
    coverage=read_csv(ROOT/'reports/coverage_summary.csv')
    feasibility=read_csv(ROOT/'reports/polymarket_feasibility.csv')
    markets=read_csv(ROOT/'processed/pm_markets.csv')
    # Actual method-level query ledger, including rejected methods (never zero activity).
    chain_ledger=[]
    for r in requests:
        payload=r.get('request_payload')
        if not payload:continue
        chain_ledger.append({'request_id':r['request_id'],'endpoint':r['url'],'method':payload['method'],'params_json':json.dumps(payload['params'],ensure_ascii=False),'query_purpose':r['label'],'started_at_utc':r['started_at_utc'],'retrieved_at_utc':r['retrieved_at_utc'],'http_status':r['http_status'],'terminal_state':'returned' if r['ok'] else 'request_or_RPC_failed','error':r['error'],'raw_ref':r['raw_ref'],'sha256':r['sha256'],'full_window_coverage':'not_claimed'})
    write_csv(ROOT/'reports/chain_query_ledger.csv',chain_ledger)
    price_rows=read_csv(ROOT/'processed/pm_prices.csv')
    for f in feasibility:
        m=next(m for m in markets if m['pm_market_key']==f['market_key'])
        pts=[p for p in price_rows if p['pm_outcome_key']==f['outcome_key'] and p['eligible_for_asof']=='True']
        covered=0
        for t in range(1791417600,1792022400,86400):
            if epoch(m['opened_at_utc'])<=t<epoch(m['scheduled_close_at_utc']) and any(0<t-epoch(p['effective_information_time_utc'])<=86400 for p in pts):covered+=1
        f['covered_daily_anchors']=covered;f['missing_daily_anchors']=7-covered;f['daily_anchor_denominator']=7
    write_csv(ROOT/'reports/polymarket_feasibility.csv',feasibility)
    ex=example['example'];native=example['creation_native_evidence']
    # Capability matrix deliberately separates price background from creation completeness.
    matrix=[]
    for chain,platform_id,topic in [('solana:mainnet','pump.fun','solana'),('eip155:8453','clanker','base'),('eip155:56','four.meme','bnb')]:
        s=[r for r in sources if r['chain_key']==chain]
        logs=[r for r in s if r['method']=='eth_getLogs']
        logs_ok=[r for r in logs if r['response_state']=='returned']
        price=next((r for r in feasibility if r['topic']==topic),{})
        matrix.append({'chain_key':chain,'platform_id':platform_id,'candidate_window':'legacy_week_20261008_20261015;preferred_pilot_20261008_20261009','historical_start_mid_end_blocks_returned':sum(r['response_state']=='returned' and (r['method']=='getBlock' or r['method']=='timestamp_boundary_verified') for r in s),'historical_transaction_or_receipt_probes_returned':sum(r['response_state']=='returned' and r['method'] in ['getTransaction','eth_getTransactionReceipt'] for r in s),'program_pagination_advanced':'True' if chain=='solana:mainnet' and any(r['pagination_can_advance']=='True' for r in s) else 'not_applicable','factory_logs_status':'not_applicable' if chain=='solana:mainnet' else ('returned_zero_in_three_small_chunks_not_no_activity' if logs_ok else 'unavailable_on_tested_sources'),'factory_log_rows_returned':sum(int(r['actual_record_count']) for r in logs_ok),'common_macro_history_available':bool(ex),'chain_background_history_available':price.get('history_obtained','False'),'chain_background_market_key':price.get('market_key',''),'independent_whole_window_creation_coverage':'not_tested','historical_version_bounds':'unknown','P2_readiness':'conditional_version_and_enumeration_validation_needed' if chain!='eip155:56' else 'blocked_for_factory_log_path_on_tested_public_sources','conclusion':'partial_feasibility'})
    write_csv(ROOT/'reports/three_chain_feasibility.csv',matrix)
    protocol=json.loads((ROOT/'configs/protocol.yaml').read_text());window_matrix=[]
    for window in protocol['candidate_windows']:
        for r in matrix:
            tested=window['window_id'] in ['legacy_week','legacy_day1']
            window_matrix.append({'window_id':window['window_id'],'start_utc':window['start'],'end_utc':window['end'],'chain_key':r['chain_key'],'creation_history_status':'finite_boundary_probes_only' if tested else 'not_tested','price_history_status':'actual_history_obtained' if tested else 'not_tested','full_window_creation_enumeration':'not_run','selection_status':'candidate_not_frozen','role':window['role']})
    write_csv(ROOT/'reports/window_feasibility.csv',window_matrix)
    # One source inventory entry per actually contacted host/root. Public access != redistribution rights.
    from urllib.parse import urlsplit
    inventory=[]
    for origin in sorted({urlsplit(r['url']).scheme+'://'+urlsplit(r['url']).netloc for r in requests}):
        rs=[r for r in requests if r['url'].startswith(origin+'/') or r['url']==origin]
        inventory.append({'source_id':'source:'+sid(origin),'source_url':origin,'access_method':'public GET / read-only JSON-RPC POST','authentication':'none','requires_application':'no','requires_payment':'no_for_tested_requests','public_read_evidence':'HTTP200 observed' if any(r['http_status']==200 for r in rs) else 'no successful response on this run','license':'not_verified','terms_url':'not_verified','redistribution_permission':'not_reviewed;local_only_not_for_public_release','snapshot_at_utc':max(r['retrieved_at_utc'] for r in rs),'restrictions':'Actual endpoint/method failures retained; no inference of complete history','contacted_request_count':len(rs)})
    write_csv(ROOT/'configs/source_inventory.csv',inventory)
    # Raw manifest includes exact responses and derived complete rule text.
    by_ref={r['raw_ref']:r for r in requests};raw_manifest=[]
    for p in sorted((ROOT/'raw').rglob('*')):
        if not p.is_file() or p.suffix=='.json':continue
        ref=str(p.relative_to(ROOT));m=by_ref.get(ref,{})
        raw_manifest.append({'path':ref,'bytes':p.stat().st_size,'sha256':sha(p),'source_url':m.get('url','derived from market snapshot; see processed/pm_markets.csv'),'retrieved_at_utc':m.get('retrieved_at_utc','see parent market snapshot'),'redistribution_status':'not_reviewed_local_only'})
    write_csv(ROOT/'provenance/raw_manifest.csv',raw_manifest)
    grains={'creation_events':('creation_event_id','one enrolled native creation event'),'registry':('token_id','one chain-qualified legacy token'),'token_id_crosswalk':('source_release+legacy_event_key','one legacy event identity mapping'),'metadata_coverage':('source_release+event_key+checkpoint','one legacy event/checkpoint'),'pm_candidate_catalogue':('market_id','one discovered market; bounded nonexhaustive catalogue'),'pm_markets':('market_snapshot_id','one market definition snapshot'),'pm_outcomes':('pm_outcome_key','one outcome asset in P1 snapshot'),'pm_prices':('price_observation_id','one native outcome/observation/resolution/value'),'pm_mapping':('mapping_id','one typed semantic target/outcome mapping'),'token_expectations_at_creation':('expectation_link_id','one token/mapping evaluated at creation; unmatched retained'),'context_daily':('chain_key+platform_id+utc_day+market_key+outcome_key','one declared chain/platform/day/fixed outcome')}
    definitions={
      'token_id':'Chain-qualified token identity. EVM address lower-case, Solana base58 case preserved; never an outcome ID.',
      'creation_event_id':'creation:SHA256(compact UTF-8 JSON array of chain/signature/outer index/inner index) first 32 hex; indices retain legacy 0 outer, positive inner convention.',
      'created_at_utc':'Original chain block_time epoch seconds converted to UTC; never request or first-seen time.',
      'first_decoded_at_utc':'Legacy T0 scheduled_at, used as collector first-decoded clock; provenance retained, not an independent chain timestamp.',
      'retrieved_at_utc':'Original creation-evidence retrieval time if known. Blank on legacy import because not exported.',
      'imported_at_utc':'Time this derived legacy import was generated; excluded from semantic reproducibility comparison.',
      'initial_name':'Not in old export; left missing rather than using current metadata.',
      'initial_symbol':'Not in old export; left missing rather than using current metadata.',
      'initial_metadata_uri':'URI retained from legacy creation record; independent historical creation coverage remains unproved.',
      'creator_address':'Legacy decoded creator argument; not assumed to be fee payer, sender, router, or a natural person.',
      'raw_ref':'Relative path to saved public response; blank for un-revalidated legacy creation evidence.',
      'source_row_ref':'Original legacy file and 1-based physical CSV row including header for traceability.',
      'source_timestamp_utc':'API observation time. With positive resolution it is bucket start, NOT information availability time.',
      'bucket_end_utc':'source timestamp + resolution_seconds; conservative information end used for joining.',
      'effective_information_time_utc':'Bucket end, required strictly before anchor; scalar construction remains unspecified.',
      'resolution_seconds':'Per-point width from Data API v2. Zero ticks excluded in P1 pending settlement classification.',
      'price':'Literal API price scalar (0–1). Not asserted calibrated probability, trade price, midpoint, or token-specific forecast.',
      'price_age_hours':'(creation anchor - information end)/3600; primary maximum 24 hours, sensitivity 12/48.',
      'match_status':'matched_valid means price-time validity for retrospective demonstration only; feature_readiness carries historical-rule limitation.',
      'review_status':'retrospective_mapping; current rules reviewed, historical rule revision archive not obtained.',
      'asset_id_raw':'Exact string supplied by Gamma clobTokenIds, matched to labels in native array order; never rounded.',
      'asset_id_type':'Native field provenance; CTF/position contract identity not guessed from a numeric ID.',
      'rule_known_from_utc':'Earliest verified historical knowledge of this rule version. Empty because no historical rule archive was retrieved.',
      'rules_ref':'Full description/resolution rules copied verbatim from saved Gamma market snapshot; hash in rules_sha256.',
      'actual_close_at_utc':'Only returned actual-close evidence; missing stays missing, never replaced by scheduled end.',
      'resolved_at_utc':'Only returned resolution time evidence; missing stays missing.',
      'legacy_enrolled_creation_count':'Legacy enrolled unique token count for Solana only; Base/BSC missing is not zero activity.',
      'evidence_status':'evidence_missing flags four missing-selected-snapshot checkpoints; original terminal state is retained.'}
    schema={'schema_version':'registry_pm_minimal_v1','id_algorithm':'SHA256 of compact UTF-8 JSON array, ensure_ascii=false, first 32 hex; namespaced prefixes','identity_rule':'chain_key+:token:+canonical_address; internal Solana chain alias not claimed CAIP-compliant','missing_rule':'CSV empty string corresponds to unknown/not applicable/not exported; explicit status identifies cause. Never convert missing to numeric zero.','time_rule':'UTC ISO8601 Z; raw block_time in legacy dictionary is Unix seconds; strict bucket-end < anchor','schemas':{}}
    dictionary=[]
    for p in sorted((ROOT/'processed').glob('*.csv')):
        data=read_csv(p);columns=list(data[0]) if data else []
        pk,grain=grains[p.stem]
        schema['schemas'][p.stem]={'file':str(p.relative_to(ROOT)),'primary_key_components':pk.split('+'),'row_grain':grain,'columns':columns,'rows':len(data),'data_status':'real_legacy_or_public_API_not_synthetic'}
        for col in columns:
            dtype='string'
            if col in ['price','price_age_hours','delay_from_creation_seconds']:dtype='decimal_string'
            if col.endswith('_utc'):dtype='UTC_ISO8601_string'
            if col in ['resolution_seconds','outcome_index','block_height_or_slot','outer_instruction_index','inner_instruction_index']:dtype='integer_decimal_string'
            dictionary.append({'table':p.stem,'column':col,'dtype':dtype,'row_grain':grain,'definition':definitions.get(col,col.replace('_',' ')+'; literal source/derived status, see code '+('build_views.py' if p.stem in ['pm_mapping','context_daily','token_expectations_at_creation'] else ('polymarket.py' if p.stem.startswith('pm_') else 'p0_baseline.py'))),'unit':'hours' if col=='price_age_hours' else ('seconds' if col=='resolution_seconds' else ('0_to_1' if col=='price' else '')),'timezone':'UTC' if col.endswith('_utc') else '', 'allowed_values':'source literal; controlled status values preserved in output','null_reason':'explicit associated status; unexported attributes/raw retrieval clocks stay missing','derivation':'see code and source/raw row references','source':str(p.relative_to(ROOT)),'primary_or_foreign_key':'PK component' if col in pk.split('+') else ('FK' if col in ['token_id','creation_event_id','market_snapshot_id','pm_outcome_key','mapping_id','price_observation_id'] else ''),'version':'registry_pm_minimal_v1'})
    write_json(ROOT/'configs/schema.json',schema);write_csv(ROOT/'configs/data_dictionary.csv',dictionary)
    usage=collections.Counter(str(r['http_status']) for r in requests)
    resources={'recorded_network_requests':len(requests),'HTTP_status_counts':dict(usage),'JSON_RPC_or_HTTP_errors':sum(not r['ok'] for r in requests),'saved_response_bytes':sum(r['saved_bytes'] for r in requests),'total_request_elapsed_seconds':round(sum(r['elapsed_seconds'] for r in requests),4),'network_wire_bytes':'not_measured','offline_elapsed_seconds':repro['elapsed_seconds'],'offline_peak_child_rss_bytes_on_this_macOS':repro['child_peak_rss_raw'],'whole_session_peak_memory':'not_measured','whole_session_wall_time':'not_measured; recorded requests span '+min(r['started_at_utc'] for r in requests)+' to '+max(r['retrieved_at_utc'] for r in requests),'python':sys.version,'platform':platform.platform(),'workspace_bytes_before_final_reports':sum(p.stat().st_size for p in ROOT.rglob('*') if p.is_file()),'probe_rounds':'source round 170 calls; market round 26 calls; initial/time-semantics/docs and fallback rounds separately logged; max per module round configured, not a claim of total <=220'}
    write_json(ROOT/'reports/resources.json',resources);write_csv(ROOT/'reports/resources.csv',[{'metric':k,'value':json.dumps(v,ensure_ascii=False) if isinstance(v,dict) else v} for k,v in resources.items()])
    # All stage gates are stated as evidence-qualified outcomes.
    gate={'P0':'passed','P0_A':'passed','P0_B':'passed_private_draft','P1_work_status':'completed_feasibility_investigation','G1':'passed_for_limited_retrospective_time_alignment_demonstration','P1_overall_feasibility':'partial','P2_started':False,'P2_window_frozen':False,'P2_prerequisite_gaps':['BSC historical factory-log public path unresolved on three tested providers','Platform historical version boundaries unknown','Base finite 20-block probes returned zero logs; does not show absence of creations','Historical rule revisions not obtained; retrospective demonstration only','API scalar construction not verified as trade/midpoint; no calibrated probability claim'],'joint_lifecycle':'awaiting_integration','common_cutoff_utc':None,'contacts_sent':False,'external_publish':False,'verification_status':'VERIFIED_FOR_REPORTED_LOCAL_TRANSFORMS_AND_FINITE_PUBLIC_PROBES;NOT_WHOLE_WINDOW_COMPLETENESS'}
    write_json(ROOT/'reports/stage_gates.json',gate)
    chain_lines='\n'.join(f'| {r["chain_key"]} / {r["platform_id"]} | {r["historical_start_mid_end_blocks_returned"]} | {r["historical_transaction_or_receipt_probes_returned"]} | {r["factory_logs_status"]} | {r["conclusion"]} |' for r in matrix)
    market_lines='\n'.join(f'| {m["market_id"]} | {m["question"]} | 432 | 1800 秒 | limited_for_demonstration |' for m in markets)
    (ROOT/'reports/P0_P1_完成报告.md').write_text(f'''# P0 / P1 执行与验收报告

日期：2026-10-27（北京时间）。新成果全部位于本目录；旧七日包只读。

**P0 已通过；P1 的有限可行性调查已完成，结论为部分可行。G1 的真实历史时间连接展示通过，尚不具备无条件启动三链全窗口实采的依据。** 本报告不是 P2 三链 Registry 完成证明。

## P0 实际交付

- 复用并重新运行旧 `rq_feasibility_audit.py`，参考聚合结果一致；旧六表及协议文件 SHA-256 均未变化。
- 6 张 CSV 行数：4,668 / 18,672 / 60,779 / 16,744 / 133,888 / 18,672。2,993 个 creator 地址，不能解释为自然人数。
- `processed/token_id_crosswalk.csv`、`registry.csv`、`creation_events.csv` 各 4,668 行；身份唯一、无窗口外事件，均明确标为 legacy_import。
- `processed/metadata_coverage.csv` 保留全部 18,672 检查点及原终态、计划/实际时间；完整字段观察转换仍属 P3 范围。
- 四个缺快照检查点已定位到 event_key、checkpoint、request_id，见 `unresolved_cases.csv`。4 笔链上未取回交易保留为一组 4 笔；本地缺具体签名，不编造逐条身份。
- 平台版本表保留官方源修订与本地 ABI/IDL 哈希，历史有效边界标 unknown；范围起止块未伪填。
- 分层协议、候选窗口、最小 schema、逐列字典、私人生命周期接口草案已建立；共同 cutoff 留空、真实生命周期未启用。
- 地址级创建者集中度 D 面板预览及源表已生成。旧周发行总体仍未独立枚举。

## P1 实际交付

共执行 {receipt['search_request_count']} 次有页码、开闭市过滤和停止原因的候选搜索，得到 {receipt['catalogue_markets']} 个去重候选 market。搜索受预设上限约束，部分分页未穷尽；不能称为 Polymarket 全目录。Pump.fun 上市/收入等完整类别将在 G1 后按 P2/P3 继续。

以下四个真实 market 的 Yes outcome 已取得完整规则、原生 ID、接口版本、原始响应和价格历史。每个取回 432 点，覆盖 10 月 6 日至 14 日，含用于旧周日初连接的前置两天；研究窗口内每个为 336 点。共 1,728 点，全部为 1,800 秒桶；Fed 历史通过两页取完。未拼接 CLOB 与 Data API 序列。

| Market ID | 问题 | 历史点（含前置期） | 实际分辨率 | 用途 |
|---|---|---:|---|---|
{market_lines}

价格定义保留为 API history scalar / 市场预期代理。接口未说明标量是 midpoint、成交价还是其他构造；因此不使用“日收盘”“精确概率”或“已证明可用于经济变化分析”等表述。历史规则版本档案未取得，映射明确为 retrospective_mapping；`rule_known_from_utc` 留空，不能称为已认证的当时可用预测特征。

### 真实时间连接

- 创建代币：`{ex['token_id']}`。
- 创建时刻：**{ex['anchor_time_utc']}**；通过官方 Solana RPC 重取交易，检查执行成功，并用对应 legacy 解码器核对 mint、creator、原生指令位置和 slot。
- 连接市场：Fed 2026 年 10 月降息 25 bps，Gamma market **2589811**，Yes asset ID 保留为精确字符串。
- 价格桶：**{ex['bucket_start_utc']} 至 {ex['bucket_end_utc']}**；价格 **{ex['price']}**。
- 桶信息结束时间比创建早 5 秒。官方 Data API OpenAPI 明确：聚合 timestamp 为桶起点，观测发生于 `[timestamp, timestamp + resolution_seconds)`；代码使用桶结束严格早于锚点，而非直接使用桶起点。
- 4,668 / 4,668 个 legacy 代币均保留在左连接中，并具备该宏观背景的有效价格时间锚点。直接代币身份匹配为 **0 / 4,668**。不能把宏观背景覆盖率解释为逐币上市概率。
- 三链 × 七日背景网格 21 / 21 格具备同一个宏观题目的日初背景；这不证明任一链创建完整。创建与背景覆盖同时完整的格数目前为 0 / 21。

### 三链来源能力

| 链与平台 | 起/中/末历史块 | 历史交易/receipt 探测 | 工厂日志 | 结论 |
|---|---:|---:|---|---|
{chain_lines}

Solana 官方 RPC 可返回三处历史块/交易和可推进的两页程序历史；PublicNode Solana 连接失败有记录。Base 主公共端点出现 429，另一公开提供者的三段 20 块工厂日志查询返回空数组；只说明这些小段及登记地址的返回，不证明平台无创建。BSC 主端点返回 limit exceeded，BNB 官方文档说明主公共端点禁用 eth_getLogs；PublicNode 返回 403，1RPC 对目标历史区间返回 header not found。有限备用探测后停止，没有购买服务、申请密钥或扫描全链。

### 验证与复现

- 实际数据验证 {len(checks['checks'])} 项，error 级失败 **0**；另有 4 类已知限制（4 未取回交易、4 缺快照、3 链全窗口未枚举、4 个规则版本档案未取得）。这些不是已修复项。
- 8 项隔离的合成边界测试通过：同秒排除、未结束桶排除、结算/模糊 tick 排除、陈旧度、非法价格和链限定身份。测试不混入真实表。
- 固定本地输入离线重建通过，网络请求 **0**，七张核心派生表的语义指纹一致。生成/映射操作时钟排除在语义指纹之外。
- 已记录公共请求 {len(requests)} 次，保存响应 {resources['saved_response_bytes']:,} 字节；请求日志含 HTTP/RPC 失败。离线重建耗时 {repro['elapsed_seconds']} 秒，macOS 子进程峰值 RSS {repro['child_peak_rss_raw']:,} 字节。全会话峰值内存和网络线缆流量未测量。
- 原始 API 响应及规则快照只作本地证据；来源许可/再分发尚未核实，本轮没有公开发布。

## 接下来如何推进

1. P2 前解决 BSC 的公开历史日志来源或设计可验证的 receipt 路径；核实各平台历史工厂/版本边界与创建事件定义。不能拿 Base 空日志或 BSC 错误当零发行。
2. 试点优先候选仍为 `[2026-10-08, 2026-10-09)` UTC。当前只完成能力抽查，尚未冻结最终 P2 范围，也未完成整日全部合格创建。
3. 保留这次有限展示的 API 标量及回溯规则限制。若用途升级为严格事前特征，补历史规则版本证据和价格构造定义，再升级验证状态。
4. 旧周全窗口重建、4 笔交易签名追查及原始正文恢复归 P3B；真实生命周期、共同 cutoff 与 Claire 对齐归 P5。

## 证据入口

`baseline_audit.json`、`legacy_rq_audit.json`、`source_capability.csv`、`three_chain_feasibility.csv`、`market_search_log.csv`、`polymarket_feasibility.csv`、`real_asof_example.json`、`validation_results.json`、`offline_reproduction.json`、`stage_gates.json`；根目录 README 提供复现命令。

官方来源：[历史 API 与 OpenAPI](https://docs.polymarket.com/api-reference/markets/get-a-tokens-price-history)、[CLOB 历史接口](https://docs.polymarket.com/api-reference/markets/get-prices-history)、[搜索接口](https://docs.polymarket.com/api-reference/search/search-markets-events-and-profiles)、[Base 网络](https://docs.base.org/get-started/connect-to-base)、[Solana 历史区块](https://solana.com/docs/rpc/http/getblock)、[BNB 公共 RPC 限制](https://docs.bnbchain.org/bnb-smart-chain/developers/json_rpc/json-rpc-endpoint/)、[1RPC 公共网络](https://docs.1rpc.io/using-the-web3-api/networks)。价格时间规范原始 Markdown/OpenAPI 已保存在 `raw/rules/`。
''',encoding='utf-8')
    (ROOT/'manuscript/shilin_sections.md').write_text(f'''# Shilin 组件持续写作记录：P0/P1

Material Passport：academic-research-suite / experiment-agent；模式 run + validate；2026-10-27；状态仅核实本报告所述离线变换与有限公开探测，非整周完整性证明。版本 registry_pm_p0p1_v1。下文是阶段性方法记录，P4 再形成正式五节稿。

## Methods

We retained the six archived tables for the enrolled Pump.fun cohort in [2026-10-08T00:00:00Z, 2026-10-15T00:00:00Z). The cohort contains 4,668 creation records and is not an independently verified census of platform launches. A chain-qualified, case-preserving Solana token identifier was assigned to each mint. Original event keys, transaction signatures and instruction positions were retained in a crosswalk. Chain block timestamps were converted from Unix seconds to UTC; T0 scheduling represents the collector's first-decoded clock, whereas T24/T48/T72 schedules derive from block time. Missing initial names and symbols were not reconstructed from current metadata.

We conducted a bounded public-source feasibility search covering active and closed Polymarket events, retaining query filters, pages, stopping reasons, native market/outcome identifiers and complete rule snapshots. Seventeen search requests yielded 270 distinct candidate markets; the search was not exhaustive. Four selected Yes outcomes were queried through Data API v2 over an explicit interval including two days of lookback. The 1,728 returned observations had a reported 1,800-second resolution. We did not infer whether the scalar represents a midpoint or a trade. Official OpenAPI defines aggregate timestamps as bucket starts. We therefore required timestamp plus resolution to be strictly earlier than each creation anchor, with a primary 24-hour maximum age and 12/48-hour sensitivity checks. Zero-resolution observations were excluded pending settlement classification. The selected Fed contract was linked as a shared economic event; it was not treated as a prediction about individual launch tokens. Rule snapshots were retrieved retrospectively and historical rule-version availability remains unverified.

## Data Records

The legacy six-table dictionary is `configs/legacy_six_table_dictionary.csv`. The new minimal schema and per-column dictionary are `configs/schema.json` and `configs/data_dictionary.csv`. Creation events, one-token Registry records and the crosswalk each contain 4,668 rows; metadata coverage retains all 18,672 planned checkpoints. The P1 layer contains a 270-market bounded catalogue, four market snapshots, eight outcome identifiers, 1,728 historical prices, one typed macro mapping, 4,668 creation-anchor results and a 21-row chain/platform/day background grid. CSV identifiers are strings and must not be converted through floating-point spreadsheet formats. Request provenance, complete raw responses and hashes are stored separately; permission to redistribute these source materials has not been established.

## Data Overview

The retained cohort contains 2,993 creator addresses, which are not identified individuals. The original terminal ledger reports 16,736 observed, 1,924 request-failed and 12 parse-failed checkpoints. Four successful-request checkpoints have no selected snapshot, so the 12 parse-failed states cannot all be attributed to malformed JSON. Shared macro price-time anchors were available for 4,668 of 4,668 enrolled tokens. No direct token-identity mapping was established (0/4,668). The 21/21 background-day availability count does not imply complete creation coverage; no whole-window three-chain cohort has yet been enumerated.

## Technical Validation

The reused legacy audit matched reference aggregates and input hashes. Three predetermined Solana boundary/midpoint transactions were fetched from the public official RPC and their mint, creator, instruction position, successful execution and slot were rechecked using the corresponding legacy decoder. These three checks do not validate the full cohort denominator. Twenty-nine actual-data checks reported zero error-level failures, with explicitly retained completeness and evidence limitations. Eight synthetic boundary tests passed separately. A zero-network offline rebuild reproduced semantic outputs while excluding generation/mapping-operation timestamps from comparison. BSC historical factory-log access remained unavailable on tested providers; Base returned zero logs in finite diagnostic chunks only. Neither result was interpreted as zero platform activity.

## Usage Notes

Use `token_id_crosswalk.csv` to recover each legacy key. Join metadata by legacy event/request identifiers and retain the full Registry with left joins. For the real example, token `{ex['token_id']}` was created at {ex['anchor_time_utc']}; its Fed Yes price {ex['price']} came from the bucket ending {ex['bucket_end_utc']}, five seconds earlier. Select by information-end time, never by bucket start alone. Preserve missing reasons, distinguish shared macro background from verified token identity, and do not treat repeated macro values across tokens as independent forecasts. The example is a retrospective time-alignment demonstration, not a certified contemporaneously specified forecasting feature. The original historical response bodies cannot be replayed from the slim legacy package. Real lifecycle data and the common cutoff remain awaiting integration.
''',encoding='utf-8')
    (ROOT/'README.md').write_text('''# Registry / Polymarket：P0 与 P1

本目录是 2026-10-27 新建工作区。先读 [P0/P1 完成报告](reports/P0_P1_完成报告.md)。

**P0 通过；P1 有限调查完成，技术结论部分可行，真实历史时间连接展示通过。** BSC 历史日志路径、平台历史版本边界、价格标量定义与历史规则修订证据仍有限制。P2 尚未开始，候选试点窗口未冻结。

## 入口

- `processed/`：真实 legacy Registry / crosswalk / metadata coverage，以及真实 Polymarket 目录、规则索引、outcome、历史、映射和左连接。
- `configs/`：分层协议、私人接口草案、平台版本、来源/许可状态、schema、两份逐列字典。
- `reports/`：审计、异常、三链能力、市场搜索、覆盖、验证、资源和离线复现。
- `raw/` 与 `provenance/`：原始响应、完整规则、请求日志和哈希；只作本地证据，未核实再分发许可。
- `figures/`：D 面板 SVG/PNG 预览及实际源表；不是 P4 完整五面板。
- `manuscript/shilin_sections.md`：五节持续写作记录，非最终投稿稿。
- `tests/`、`test_outputs/`：隔离的合成边界测试；未进入真实数据。

## 离线复现

Python 3.10+，核心脚本仅使用标准库；不需安装依赖，不启动网络：

```bash
python3 code/reproduce_offline.py
python3 -m unittest discover -s tests -v
python3 code/make_deliverables.py
```

从本目录运行，或使用脚本绝对路径。旧包位置由代码相对项目根解析。离线重建从旧六表与已存原始响应生成结果；保留既有采集快照，不证明过去网页可重新取回同一字节。`make_deliverables.py` 最后刷新当前文件清单。

## 独立公开源重取

下列命令会访问公共 API，不属于零网络离线复现。会保存新请求/失败；`--refresh` 会更新当前快照指针，但旧响应正文与日志仍保留：

```bash
python3 code/probe_sources.py
python3 code/probe_log_fallbacks.py
python3 code/polymarket.py
python3 code/build_views.py
python3 code/validate.py
```

每轮设超时和请求上限；历史方法拒绝是可行性结果。源探测代码已加入首次 403/429/limit 拒绝后停止该提供者方法的规则。第一轮原始失败记录全部保留，没有隐藏。共同 cutoff 留空不阻止这些个人任务；真实生命周期分析保持禁用。

## 关键边界

4,668 是旧纳入队列，不是整周发行总量；4 笔链上未取回交易和四个缺快照检查点未伪称修复。当前只有共享宏观映射，直接身份匹配为零。价格时间合法不代表历史规则版本已证明，`feature_readiness` 保留回溯展示限制。Base/BSC 未采集的创建数留空，不写成零。没有联系 Claire、改写原归档或公开发布。本目录为个人阶段工作成果，非联合生命周期数据发布。
''',encoding='utf-8')
    (ROOT/'figures/panel_specs.md').write_text('''# P0 D 面板预览

问题：旧纳入队列的创建集中在多少 creator 地址上？

源：只读 launch_events.csv.creator，一行一个旧创建；2,993 地址、4,668 事件。按地址计数，创建数降序排列；横轴为累计地址比例，纵轴为累计旧纳入创建比例。单位为份额，分母固定为地址数和旧队列事件数；不是整周平台发行总体，不是持币集中度，也不是自然人集中度。

代码：code/p0_baseline.py；源表 figures/data/panel_D_creator_concentration.csv；SVG 为标准矢量图，PNG 为本次预览。虚线表示均等份额参考。旧队列覆盖缺口不能解释为零活动。A/B/C/E 与 P4 组合图尚未生成，不列为 P0/P1 完成项。
''',encoding='utf-8')
    write_json(ROOT/'reports/run_receipt.json',{'completed_at_utc':now(),'stage_gates':gate,'resources':resources,'legacy_inputs_unchanged':audit['checks']['all_legacy_files_unchanged'],'tests_passed':8,'actual_data_check_count':len(checks['checks']),'source_requests_are_read_only':True,'outputs_root':str(ROOT)})
    files=[]
    for p in sorted(ROOT.rglob('*')):
        if p.is_file() and p.name!='file_manifest.csv' and '__pycache__' not in p.parts:
            files.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p),'redistribution_status':'local_review_packet_not_public_release'})
    write_csv(ROOT/'provenance/file_manifest.csv',files)
    print(json.dumps({'report':str(ROOT/'reports/P0_P1_完成报告.md'),'manifest_files':len(files),'P0':gate['P0'],'P1':gate['P1_overall_feasibility']},ensure_ascii=False))

if __name__=='__main__':run()
