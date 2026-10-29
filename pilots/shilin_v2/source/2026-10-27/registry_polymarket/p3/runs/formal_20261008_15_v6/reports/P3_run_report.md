# P3 数据与验证记录

状态：passed_for_declared_P3_scope。本运行类型：P3_formal。正式 P3 完成：True。

Registry 367373 个币；预期长表 6156902 行。

- solana:mainnet 2026-10-08: complete_for_declared_address_topic_scope
- eip155:8453 2026-10-08: complete_for_declared_address_topic_scope
- eip155:56 2026-10-08: complete_for_declared_address_topic_scope
- solana:mainnet 2026-10-09: complete_for_declared_address_topic_scope
- eip155:8453 2026-10-09: complete_for_declared_address_topic_scope
- eip155:56 2026-10-09: complete_for_declared_address_topic_scope
- solana:mainnet 2026-10-10: complete_for_declared_address_topic_scope
- eip155:8453 2026-10-10: complete_for_declared_address_topic_scope
- eip155:56 2026-10-10: complete_for_declared_address_topic_scope
- solana:mainnet 2026-10-11: complete_for_declared_address_topic_scope
- eip155:8453 2026-10-11: complete_for_declared_address_topic_scope
- eip155:56 2026-10-11: complete_for_declared_address_topic_scope
- solana:mainnet 2026-10-12: complete_for_declared_address_topic_scope
- eip155:8453 2026-10-12: complete_for_declared_address_topic_scope
- eip155:56 2026-10-12: complete_for_declared_address_topic_scope
- solana:mainnet 2026-10-13: complete_for_declared_address_topic_scope
- eip155:8453 2026-10-13: complete_for_declared_address_topic_scope
- eip155:56 2026-10-13: complete_for_declared_address_topic_scope
- solana:mainnet 2026-10-14: complete_for_declared_address_topic_scope
- eip155:8453 2026-10-14: complete_for_declared_address_topic_scope
- eip155:56 2026-10-14: complete_for_declared_address_topic_scope

历史规则与价格构造限制仍保留；真实生命周期 awaiting_integration；共同 cutoff 为空。4 笔缺签名交易及缺正文检查点保留在异常表，不能视为已修复。

## Methods
逐日、声明地址/事件范围，原生交易/receipt 与区块证据核验；创建资格不使用 URI、交易或迁移结果。预期按 outcome/mapping 连接，桶结束严格早于锚点，24 小时主陈旧度及12/48小时敏感性。

## Data Records
实际文件、哈希、粒度及列见 provenance/processed_manifest.csv 和 configs/data_dictionary.csv。

## Data Overview
按链数量：{"eip155:56":35777,"eip155:8453":1535,"solana:mainnet":330061}。直接身份与背景覆盖分别见 reports/expectation_coverage.csv，日背景见 background_day_coverage.csv。

## Technical Validation
检查 35 项；失败 0 项；待完成覆盖 0 项。完整记录见 validation_checks.csv。

## Usage Notes
按 token_id 左连接；长表行数不是币数。原始18,672个历史计划不扩写，新增币未历史采集。此稿按当前验证结果生成，不宣称因果或已认证事前特征。
