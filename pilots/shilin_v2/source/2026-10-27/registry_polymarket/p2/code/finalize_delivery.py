"""Update current-stage pointers only after the complete P2 gate has passed."""
from p2io import *
from collections import Counter
from report import run as report_run

def run():
    result=json.loads((ROOT/'reports/validation_results.json').read_text())
    if result['status']!='passed_for_declared_platform_version_scope':raise RuntimeError('Cannot finalize an unpassed P2')
    from reproduce_offline import inputs,fingerprints
    replay=json.loads((ROOT/'reports/offline_reproduction.json').read_text())
    if replay['input_hashes']!=inputs() or replay['second_output_hashes']!=fingerprints():raise RuntimeError('Evidence changed since verified rebuild')
    rows=read_csv(ROOT/'processed/registry.csv');counts=dict(Counter(r['chain_key'] for r in rows))
    p=PARENT/'reports/stage_gates.json';gate=json.loads(p.read_text())
    gate.update(P2_status='complete_for_declared_platform_version_scope',P2_remaining_creation_gap=None,P2_completed_at_utc=now(),P2_counts_by_chain=counts,P2_validation_report='p2/reports/validation_results.json',P2_prerequisite_gaps=['Historical rule revisions and scalar trade/midpoint construction remain unverified; retrospective demonstration only','Only declared platform versions;Four.meme V1 excluded;full proxy histories not claimed'],verification_status='P2_FULL_DECLARED_DAY_CREATION_SCOPE_AND_FIXED_INPUT_REPRODUCTION_VERIFIED;P0P1_HISTORICAL_REPORT_PRESERVED')
    gate['P2_resolved_sources']={'Solana':'65-page official mandatory-PDA index,595 public SVS full-transaction pages,all native candidates resolved,independent block hashes/time;55508 creates','Base':'full-day declared native log range,every receipt/header;197 creates','BSC':'full-day declared Four.meme V2 log range,every native receipt/header/field;6211 creates'};write_json(p,gate)
    p=PARENT/'configs/protocol.yaml';protocol=json.loads(p.read_text());protocol['status']='P2_complete_for_declared_platform_version_scope';protocol['P2_protocol_ref']='p2/configs/pilot_protocol.json';write_json(p,protocol)
    readme=PARENT/'README.md';s=readme.read_text();marker='## P2 后续工作';s=s.split(marker)[0].rstrip()+f'''\n\n{marker}\n\nP2 已完成声明平台版本范围内的共同整日试点：2026-10-08 至 2026-10-09 UTC。共 {len(rows):,} 个不同 token_id（Solana 55,508，Base 197，BSC 6,211），创建范围、链上证据和固定输入零网络复现均通过验收。见 [P2 执行报告](p2/reports/P2_执行与验收报告.md)、[P2 数据与代码](p2/README.md) 和 [P2 持续稿](p2/manuscript/P2_sections_update.md)。\n\n上方 P0/P1 的可行性与未采集状态是该阶段结束时的历史记录，P2 新结果单独保存。Solana 的完整性采用必需 PDA 完整交易枚举，旧 SQD slot 扫描覆盖仍按实际保留。宏观映射仍限回溯展示；真实生命周期和共同 cutoff 未接入。\n\n根 provenance/file_manifest.csv 记录本层文件与 P2 子清单；P2 完整文件哈希由 p2/provenance/file_manifest.csv 单独维护。\n''';readme.write_text(s)
    manuscript=PARENT/'manuscript/shilin_sections.md';s=manuscript.read_text();marker='## P2 后续阶段记录';s=s.split(marker)[0].rstrip()+f'\n\n{marker}\n\nP0/P1 以上文字保留为阶段记录。P2 已生成 {len(rows):,} 条声明版本范围内的真实整日创建和预期连接，完整方法、计数与验收见 [P2 更新稿](../p2/manuscript/P2_sections_update.md) 与 [P2 报告](../p2/reports/P2_执行与验收报告.md)。P2 未接入真实生命周期，也未改写旧归档。\n';manuscript.write_text(s)
    report_run()
    files=[]
    for f in sorted(PARENT.rglob('*')):
        if not f.is_file() or '__pycache__' in f.parts or f==PARENT/'provenance/file_manifest.csv':continue
        if ROOT in f.parents and f!=ROOT/'provenance/file_manifest.csv':continue
        files.append({'path':str(f.relative_to(PARENT)),'bytes':f.stat().st_size,'sha256':sha(f),'scope':'P2_child_manifest' if f==ROOT/'provenance/file_manifest.csv' else 'P0P1_parent_files_and_current_stage_pointers'})
    write_csv(PARENT/'provenance/file_manifest.csv',files)
    print(json.dumps({'status':gate['P2_status'],'total_tokens':len(rows),'counts_by_chain':counts,'parent_manifest_rows':len(files)},ensure_ascii=False))
if __name__=='__main__':run()
