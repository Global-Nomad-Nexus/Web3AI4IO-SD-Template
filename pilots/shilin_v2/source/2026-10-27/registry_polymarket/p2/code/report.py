"""Generate a review packet that tracks the actual P2 gate without upgrading partial data."""
from p2io import *
from collections import Counter
import html

def run():
    cfg=json.loads((ROOT/'configs/pilot_protocol.json').read_text());validation=json.loads((ROOT/'reports/validation_results.json').read_text());coverage=read_csv(ROOT/'reports/coverage.csv');registry=read_csv(ROOT/'processed/registry.csv');joins=read_csv(ROOT/'processed/token_expectations_at_creation.csv');versions=json.loads((ROOT/'configs/platform_events.json').read_text())
    passed=validation['status']=='passed_for_declared_platform_version_scope';counts=Counter(r['chain_key'] for r in registry);matched=Counter(r['chain_key'] for r in joins if r['match_status']=='matched_valid')
    requests=[json.loads(line) for line in (ROOT/'provenance/requests.jsonl').read_text().splitlines()]
    resources={'recorded_HTTP_attempts':len(requests),'statuses':dict(Counter(str(r['http_status']) for r in requests)),'saved_decompressed_response_bytes':sum(r['saved_bytes'] for r in requests),'actual_stored_raw_response_bytes':sum(p.stat().st_size for p in (ROOT/'raw').glob('*.body*')),'sum_request_elapsed_seconds_including_parallel':round(sum(r['elapsed_seconds'] for r in requests),3),'wall_time_span':min(r['started_at_utc'] for r in requests)+' to '+max(r['retrieved_at_utc'] for r in requests),'peak_memory':'see offline_reproduction child RSS; collection peak not measured','network_wire_bytes':'not_measured; decompressed JSON bytes are not wire traffic','concurrency':'SVS four in-flight reads, global<=3.3RPC/s within documented5RPS; SQL sequential<=400 result rows per request within2000 row cap; independent BSC audit','retry_policy':'bounded retries; case-insensitive Retry-After; source overcapacity attempts retained','accounting_limit':'Controlled SIGINT restarts may interrupt a request before its metadata line is saved; recorded requests are not claimed to equal all wire attempts.','rate_header_fix':'Early attempts did not recognize lowercase retry-after; corrected before resumed collection. All saved early failures retained.'}
    write_json(ROOT/'reports/resources.json',resources)
    scope=[]
    for v in versions:
        rows=[r for r in registry if r['chain_key']==v['chain_key'] and r['program_or_factory_address']==v['address']]
        scope.append({'chain_key':v['chain_key'],'platform_id':v['platform_id'],'platform_version':v['version'],'program_or_factory':v['address'],'creation_event':v['event_name'],'topic0':v['topic0'],'ABI_path':v['abi_path'],'ABI_sha256':v['abi_sha256'],'source_revision':v['source_revision'],'frozen_window_start':cfg['creation_start_utc'],'frozen_window_end':cfg['creation_end_utc'],'observed_creations':len(rows),'first_observed_creation_utc':min((r['created_at_utc'] for r in rows),default=''),'last_observed_creation_utc':max((r['created_at_utc'] for r in rows),default=''),'deployment_or_upgrade_bounds':'not_inferred_from_first_seen','version_claim':'exact pinned event layout at named address; no complete proxy implementation lineage claim'})
    write_csv(ROOT/'configs/platform_scope.csv',scope)
    # Document all actual output columns with row grains and exact identity/time rules.
    grains={'registry':'one canonical chain-qualified token','creation_events':'one native creation instruction/log','pm_markets':'one market-definition snapshot','pm_outcomes':'one native market outcome asset','pm_prices':'one historical outcome/price observation','pm_mapping':'one typed semantic relationship','token_expectations_at_creation':'one token/mapping evaluated at creation','pm_match_status':'one token/link-type assessment','context_daily':'one chain/UTC-day/fixed macro outcome'}
    dictionary=[];schema={}
    special={'token_id':'chain_key+:token:+canonical address; EVM lower-case, Solana case preserved','creation_event_id':'creation:+SHA256(compact JSON array(chain,transaction,native position)) first 32 hex','native_instruction_path':'Call-tree address from native outer index and inner stackHeight; matches SQD path semantics, not the legacy flattened inner index','initial_metadata_uri':'Literal creation URI; empty preserved; not a qualification filter','creator_address':'Creator/admin/deployer role from exact native field; role is recorded separately; not a natural-person identity','first_decoded_at_utc':'Blank on historical backfill; no fabricated historical T0','effective_information_time_utc':'Historical price bucket END, required strictly earlier than creation anchor','feature_readiness':'Retrospective demonstration only; no verified historical rule revisions','raw_ref':'P2 relative normalized/native response plus block locator; native_receipt_raw_ref and native_block_raw_ref link original source responses','instruction_commitment_evidence_ref':'Native atomic transaction/log proof or saved independent SQD instruction-state response; unknown commitment is not admitted','retrieved_at_utc':'Original saved full-native-response retrieval time; source references retain exact per-response provenance','is_direct_token_identity_match':'False; shared macro context is not a prediction about this token','historical_metadata_status':'P2 tokens do not inherit legacy T0/T24/T48/T72 observations'}
    for path in sorted((ROOT/'processed').glob('*.csv')):
        rows=read_csv(path);cols=list(rows[0]) if rows else []
        schema[path.stem]={'row_grain':grains.get(path.stem,path.stem),'columns':cols,'rows':len(rows),'identifier_type':'exact_string','time_type':'ISO8601 UTC Z'}
        for col in cols:dictionary.append({'table':path.stem,'column':col,'dtype':'UTC_ISO8601_string' if col.endswith('_utc') else ('decimal_string' if col in ['price','price_age_hours'] else 'exact_source_string'),'row_grain':grains.get(path.stem,path.stem),'definition':special.get(col,col.replace('_',' ')+'; preserved source/derived value; see decoder/build source and referenced evidence'),'unit':'hours' if col=='price_age_hours' else ('seconds' if col=='resolution_seconds' else ''),'timezone':'UTC' if col.endswith('_utc') else '', 'null_reason':'not exported / not applicable / not historically collected; associated status explains cause; never substitute zero','derivation':'code/decode.py or code/build.py','source':str(path.relative_to(ROOT)),'primary_or_foreign_key':'ID reference' if col.endswith('_id') or col.endswith('_key') else '', 'version':cfg['protocol_version']})
    write_csv(ROOT/'configs/data_dictionary.csv',dictionary);write_json(ROOT/'configs/schema.json',schema)
    lines='\n'.join(f'| {r["chain_key"]} | {r["admitted_unique_tokens"]} | {matched[r["chain_key"]]} | {r["native_candidates_resolved"]+"/"+r["native_index_candidate_denominator"] if r["native_index_candidate_denominator"] else str(int(r["declared_positions"])-int(r["positions_not_yet_enumerated"]))+"/"+r["declared_positions"]} | {"候选交易" if r["native_index_candidate_denominator"] else "区块位置"} | {r["coverage_status"]} |' for r in coverage)
    status='已通过声明平台版本范围的 P2 验收' if passed else 'P2 进行中，尚未通过完整窗口验收'
    qa=json.loads((ROOT/'reports/native_QA_receipt.json').read_text()) if (ROOT/'reports/native_QA_receipt.json').exists() else {}
    sol=json.loads((ROOT/'reports/solana_native_creation_receipt.json').read_text()) if (ROOT/'reports/solana_native_creation_receipt.json').exists() else {}
    headers=json.loads((ROOT/'reports/cryptohouse_headers_receipt.json').read_text()) if (ROOT/'reports/cryptohouse_headers_receipt.json').exists() else {}
    bsc=json.loads((ROOT/'reports/bsc_all_native_QA_receipt.json').read_text()) if (ROOT/'reports/bsc_all_native_QA_receipt.json').exists() else {}
    (ROOT/'reports/P2_执行与验收报告.md').write_text(f'''# P2 执行与验收报告

更新：{now()}。状态：**{status}**。

## 冻结范围

共同创建窗口为 `[2026-10-08T00:00:00Z, 2026-10-09T00:00:00Z)`。这是 P0/P1 预先列出的首选完整 UTC 日，未按价格方向或代币成功挑选。三链边界已以原生 RPC 核验“前一块时间 < 起止时刻 ≤ 边界块时间”。Solana 归档 timestamp lookup 一度返回晚于真实边界的 slot，因此未采用该定位，改用官方 RPC 二分定位；冲突与原始响应均保留。

纳入 Solana/Pump.fun 的成功且 committed 的 create/create_v2；Base/Clanker 官方 SDK 列出的六个工厂版本（v0、v1、v2、v3、v3.1、v4）的 TokenCreated；BSC/Four.meme V2 TokenManager2 的 TokenCreate。失败交易/回滚指令排除。空 URI、后来未交易/毕业/迁移或元数据失败不构成排除理由。

**版本边界：** Four.meme 官方集成资料明确只支持 V2，本试点将 V1 列为范围外，未对其构造未经核验的解码器；不能将本结果称为全部 Four.meme 版本或三链全部发行的总体。部署与代理升级的完整历史未从首条事件时间推断。Pump.fun 窗口前后两份官方 IDL 的创建 discriminator、前三个字符串和 creator 前缀及 mint 账户位置一致；额外可选参数字节保留，未强行按当前完整尾部布局解释。

## 当前实际结果

| 链 | 不同 token_id | 有效宏观价格锚点 | 已完成/应完成 | 计量单位 | 覆盖状态 |
|---|---:|---:|---:|---|---|
{lines}

三链的完整性依据不同，计量单位不能混合。Solana 最终采用必需 mint-authority PDA 的完整原生交易索引及逐笔交易解码；Base/BSC 采用声明区块范围的创建日志查询闭合。`coverage.csv` 保留原 SQD slot 扫描的真实完成数；`remaining_ranges.csv` 是被新路径替代的旧扫描缺段，**未把它改写为 100% slot 扫描**。最终创建范围是否仍有缺口见 `remaining_creation_gaps.csv`。

## 来源与逐条证据

Base 使用公开原生 RPC 的 10,000 块分段日志读取；197 条入选创建日志逐条与 receipt 和区块头对账。BSC 使用 SQD public Portal 分段读取，完整范围闭合；全部 {bsc.get('creation_logs_checked',0)} 条创建也已核对原生 receipt、字段、sender、区块哈希和时间，失败 {bsc.get('failures',0)} 条。

Solana 在公开归档持续过载后，改为三类公开来源组合。官方 RPC 对必需 mint-authority PDA `TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM` 完整分页，65 页跨过日初边界；官方 IDL 和 PDA 种子/程序哈希证明声明的 create/create_v2 必须引用它。Vibe Station 官方公布的免认证 `/historical` 接口取回 595 个原生交易页，59,404 笔成功/失败签名、slot、交易序号和错误状态均与官方索引完全一致，其中 55,686 笔成功、3,718 笔失败。索引成员不会自动成为创建记录，仍须有真实 discriminator、原生账户/参数和 committed 证据。

创建路径由原生 outer index、inner stackHeight 重建。成功交易的顶层指令具有原子成功证据；嵌套指令要求自身和全部内层祖先成功，外层成功由交易状态证实。无法判断的状态留待独立证据解决。最终未知状态 {sol.get('unknown_commitment_instructions',0)} 条，原生与已有 SQD 指令交叉核对 {sol.get('archive_native_instruction_comparisons',0)} 条，冲突 {sol.get('conflicts',0)} 条。成功但没有合格 committed 创建的候选交易 {sol.get('successful_candidates_without_committed_creation',0)} 笔，未误纳为代币。

全部 {headers.get('candidate_slots',0)} 个候选 slot 都取得区块哈希和一致时间，其中复用 SQD 区块头 {headers.get('archive_header_slots_reused',0)} 个，CryptoHouse 官方公开 SQL 补齐 {headers.get('CryptoHouse_SQL_header_slots',0)} 个。SQL 每次最多取 400 个明确需要的 slot，遵守公共 2,000 行结果限制；未修改服务端限制。Vibe 读取全局不超过约 3.3 RPC/s，低于其公开 5 RPS，使用官方 zstd 压缩；所有响应保留哈希并无损保存。

Vibe 的 `status=success` 探测仍返回失败交易，因此正式读取不依赖该服务端过滤，明确按原生 meta.err 分类并对账。其他公开源的 403、429、无历史数据、TLS 失败及原归档 529 均保留；没有绕过认证、购买服务或提交链上交易。

独立原生 RPC 抽查按 chain/version、固定种子 20261027 选取最多 10 条，当前已执行 {qa.get('archive_sample_checks',0)} 条，失败 {qa.get('archive_sample_failures',0)} 条；若尚未达到目标数，验收保持 pending。原生抽查是程序回放核验，不冒称人工检查，也不证明绝对零遗漏。

## 预期整合

三链共享同一场 2026 年 10 月 FOMC 事件背景。市场为 Gamma 2589811，问题为 Fed 降息 25 bps，Yes 原生 asset ID 保留为精确字符串。P1 已取回的固定历史输入原样引用。以桶起点加实际 resolution_seconds 得到信息结束时间，要求严格早于创建，主陈旧度上限 24 小时；不使用结算点、当前价或同秒未知先后价格。

Registry 左连接保留所有已纳入 token_id；共享宏观背景不是普通代币的上市概率。映射为 retrospective_mapping，历史规则版本档案与标量是成交价还是 midpoint 仍未确认；结果限定为可复现的回溯时间连接展示。P2 新补录代币未继承旧 T0/T24/T48/T72。

## 验收与复现

当前验证状态：`{validation['status']}`。检查包括声明创建范围闭合、Solana 完整候选逐笔解决、主外键、去重、失败执行排除、价格桶结束时间、陈旧度、母表保留、原始响应哈希和原生 QA。未解决的候选/执行状态或声明创建范围缺口不允许验收。10 个合成解码和回滚/日志截断边界测试隔离在 tests/，不计入真实 Registry。零网络复现从固定原始交易、区块证据及 P1 市场输入重建两次，要求 processed CSV 逐字节一致。

代码、配置、查询账本、原生响应和逐列字典均在本目录。`README.md` 给出采集续跑与零网络重建命令。原始第三方响应只作本地审阅证据，未核实可再分发许可，本轮未公开发布；共同生命周期 cutoff 仍空，Claire 真实生态数据未接入。

## 主要入口

- `processed/creation_events.csv`、`registry.csv`、`token_expectations_at_creation.csv`。
- `reports/coverage.csv`、`remaining_ranges.csv`、`validation_results.json`、`native_QA.csv`。
- `reports/solana_native_creation_receipt.json`、`vibe_history_receipt.json`、`cryptohouse_headers_receipt.json`、`bsc_all_native_QA.csv`。
- `reports/three_chain_display_samples.csv`：每链按创建时间/ID 固定排序取前 10 条展示，底层保留实际枚举全表，不能以展示行替代窗口总体。
- `configs/pilot_protocol.json`、`platform_events.json`、`platform_scope.csv`、`data_dictionary.csv`。
- `provenance/requests.jsonl`、`file_manifest.csv`：请求、响应、哈希与范围。

官方规范：[Solana 原生账户索引](https://solana.com/docs/rpc/http/getsignaturesforaddress)、[Vibe 公开历史接口](https://docs.solanavibestation.com/api-reference/historical/gettransactionsforaddress.md)、[CryptoHouse 官方公共连接](https://github.com/ClickHouse/CryptoHouse#direct-connections)、[SQD 流与续传](https://docs.sqd.dev/en/portal/solana/api)、[Clanker SDK](https://github.com/clanker-devco/clanker-sdk)、[Four.meme V2 定义](https://github.com/four-meme-community/four-meme-ai/blob/c81f0eebbabec16998b2457f7e881e1b70b86420/skills/four-meme-integration/references/event-listening.md)。
''',encoding='utf-8')
    (ROOT/'README.md').write_text('''# P2 三链共同整日试点

先读 [执行与验收报告](reports/P2_执行与验收报告.md)，并以 `reports/validation_results.json` 为完成状态依据。部分数据不会被标为完整 P2。

窗口：2026-10-08 至 2026-10-09 UTC，含起点、不含终点。范围：Pump.fun create/create_v2、SDK 列出的 Base/Clanker 六个版本、Four.meme V2。V1 未核验，明确范围外。全部结果是声明来源/地址/事件定义下的队列，不是全链发行总体。

## 公开源继续采集

```bash
python3 code/prepare.py
python3 code/collect_base_rpc.py
python3 code/continue_collection.py --chain eip155:56
python3 code/solana_index.py
python3 code/collect_vibe_partitions.py
python3 code/collect_cryptohouse_headers.py
python3 code/prepare_vibe_creations.py
python3 code/decode.py
python3 code/build.py
python3 code/bsc_full_receipt_qa.py
python3 code/native_qa.py --limit 10
python3 code/decode.py
python3 code/audit_native_index.py
python3 code/reproduce_offline.py
python3 code/validate.py
python3 code/report.py
```

采集只进行公开读取，不签名/提交交易。查询缓存成功响应、保留失败并从持久化检查点续跑；遵守 Retry-After 和各来源限制，不启动同一账本的两个写入进程。Solana 最终使用完整 PDA 账户交易索引和全部原生交易解码，区块头来自已保存归档及官方公开 CryptoHouse SQL；旧 SQD slot 缺段保留，未冒充全 slot 扫描。原始 Vibe 响应无损 gzip 保存在 .body.gz，read_body() 自动解压；Python3.14 可用标准库 zstd 解码官方传输压缩，旧 Python 会回退普通传输。核心 ABI 解码依赖 vendor/ 中固定的 eth-abi 5.2.0、eth-hash 0.7.1，未修改系统环境。

## 零网络重建

在停止采集、固定输入后运行：

```bash
python3 -m unittest discover -s tests -v
python3 code/reproduce_offline.py
python3 code/audit_native_index.py
python3 code/validate.py
python3 code/figures.py
python3 code/write_manuscript.py
python3 code/report.py
```

这些重建命令不请求网络；reproduce_offline.py 会从固定原始交易、区块证据开始，重复执行 prepare_vibe_creations、decode、build，比较全部 processed CSV 字节哈希。native_qa 与采集命令是独立公开源再取验证。运行测试时将输出同时保存到 reports/unit_tests.log，验收读取该记录。父目录 P0/P1 的固定 Fed 市场/规则/价格 CSV 作为输入，原始 refs 中 ../ 指回父工作区。不要单独搬走本文件夹而丢失这些固定输入。新补录代币的历史元数据状态是 not_collected_historically_P2，不伪装旧观察。

## 状态和数据精度

ID/地址/原始整数均按字符串读取，避免电子表格浮点损坏。0 与缺失分开；覆盖未知的空白不是零活动。宏观链接与直接代币身份链接分开计数，当前只用 shared_economic_event。价格时间有效不代表历史规则版本已认证。
''',encoding='utf-8')
    status={'P2_status':'complete_for_declared_platform_version_scope' if passed else 'in_progress','validation_status':validation['status'],'window_start_utc':cfg['creation_start_utc'],'window_end_utc':cfg['creation_end_utc'],'counts_by_chain':dict(counts),'known_scope_exclusions':cfg['known_scope_exclusions'],'lifecycle':'awaiting_integration','cutoff':None,'updated_at_utc':now()}
    write_json(ROOT/'reports/stage_status.json',status)
    manifest=[]
    for p in sorted(ROOT.rglob('*')):
        if p.is_file() and 'vendor' not in p.parts and '__pycache__' not in p.parts and p.name!='file_manifest.csv' and not p.name.endswith('_collection.log'):
            manifest.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p),'redistribution':'local_review_only'})
    write_csv(ROOT/'provenance/file_manifest.csv',manifest)
    print(json.dumps(status,ensure_ascii=False),flush=True)
if __name__=='__main__':run()
