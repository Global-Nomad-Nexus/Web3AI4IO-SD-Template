# 生命周期接口合同与迁移记录

接口版本 `shilin_lifecycle_adapter_v1`；状态 `unconfirmed_by_claire`。此版本把 P0 草案变成可执行适配程序，未冻结真实共同 cutoff、死亡定义或真实生态口径。

## 身份与转换

Registry 是创建身份、创建时间与 creator 角色的权威输入，程序不原地改写。`token_id = chain_key + ':token:' + canonical_address`；Base/BSC 使用各自的 eip155 网络前缀且地址转小写，Solana 保留大小写。相同地址跨链不能合并，同名币不能建立身份。

外部可以提供已有 token_id、明确 chain+address，或 `(chain_key, object_id)` 的显式 crosswalk。多个身份字段同时出现必须一致；跨链、缺键、外键未知及歧义 crosswalk 拒绝。`configs/adapter_config.json` 控制别名；timestamp 在该配置中被**显式声明为链上事件 UTC 时间**。其他来源若该字段表示首次观测或抓取时间，必须修改自己的映射配置，不能沿用此别名。

事件字段为 token_id、chain_key、event_type、event_time_utc、observed_at_utc、transaction_id、native_position、source_id、event_evidence_ref、venue_id。场所未知时允许 venue_id 为空，但必须给 missing_reason。原生位置采用 EVM `log:N`、Solana `ix:N[.N]`，交易 hash/signature 不经浮点转换。时间必须显式 UTC ISO8601；显式配置 epoch_seconds 时才转换秒数，毫秒不猜测。事件早于创建、观测早于事件均进入 quarantine。

事件类型：first_trade、graduation、migration、venue_change、activity、inactivity、reactivation、other_evidenced_event。inactivity 只保留有来源证据的记录，不自动生成，不解释为永久死亡；重新活跃事件可继续出现，迁移后也不自动截断。

覆盖字段为 token_id、chain_key、layer_or_venue、interval_start_utc、interval_end_utc、coverage_status、source_id、coverage_evidence_ref；非 complete 状态必须有 missing_reason。状态 complete/partial/unknown/not_applicable/source_missing 分开。区间为 `[start,end)`；同一 source、layer 的相互矛盾覆盖声明全部隔离，不能用矛盾 complete 关闭随访。

## 重复与冲突

事件键：chain+transaction+native_position+event_type。相同语义事件的重复获取折叠为一行，回执保留重复计数与输入行号，并选最早 observed_at；同键的 token、event_time、venue、source 或证据冲突时**所有版本隔离**，不按行序选一个。全部原始错误行以 JSON 写入 quarantine，保留文件、CSV 行号和原因。处理失败返回非零退出码；调用者应解决冲突后重跑，不能把“已隔离”解释为真实数据完整。

`first_seen_in_window` 保留为来源上下文，不赋值给 created_at。外部创建时间或 creator 身份/角色有冲突时拒绝覆盖，来源证据必须在 P5 核对。

## 随访和删失

测试分析窗口为 `[creation, cutoff)`。恰好 cutoff 及之后的事件可保留在事件表，analysis_eligible=false，不计入该次结局。observed_at 是取回时钟，可晚于 cutoff，不代替事件时间。

每个目标独立指定必要 layer。完整覆盖可连续拼接到 cutoff，目标事件未观察到时为 administrative_right_censored；在 cutoff 前中断为 loss_to_followup，只截至连续覆盖终点；从创建时即无覆盖为 unknown，is_right_censored 为空。partial、source_missing、not_applicable 不足以证明无目标事件。事件可在覆盖缺口后真实观察到，但 `first_occurrence_verified=false`，不把它当已证明的首次发生时间。

覆盖证据、连续观察截止、目标事件引用和删失状态均输出。此处为基础接口，不是已经认可的跨层生存分析模型；P5 须确认每个目标需要哪些场所、来源、终止定义及覆盖充分性。

## 合成隔离与真实模式

fixture 在 tests/fixtures，带 dataset_kind=synthetic_test；CLI 测试输出必须位于 test_outputs。真实模式拒绝 synthetic 行；真实结果统计与图集另做标记扫描。没有真实事件输入时左连接保留全部母表，状态 ecosystem_unmatched，不生成死亡。

真实 followup 还要求 joint_definitions_confirmed=true 与显式 cutoff；P4 配置保持 false/null，不生成正式生命周期结局表。测试通过仅证明接口边界行为。

## 迁移记录

| 原草案 | 本版本 |
|---|---|
| token identity 与字段文字约定 | 已实现网络限定身份、显式 crosswalk、可配置字段别名及冲突拒绝 |
| 原生重复规则 | 已实现可审计重复折叠、冲突全量隔离 |
| 覆盖及删失文字约定 | 已实现逐目标连续覆盖、半开时间边界、失访/未知/行政删失 |
| awaiting_integration | 保留；未替换为联合完成 |

后续语义改变需新版本配置与变更记录，不覆盖 P4 冻结候选及原始来源。
