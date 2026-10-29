# P4 本地交接材料（未发送）

个人候选 `p4_personal_candidate_20261029`；接口 `shilin_lifecycle_adapter_v1`，unconfirmed_by_claire；真实生态 awaiting_integration；共同 cutoff=null。本轮依用户要求不写或改文章。

Shilin 的数据基线为 P3 v6，窗口 `[2026-10-08,2026-10-15)` UTC。367,373 个不同代币：Solana/Pump.fun 330,061，Base/Clanker 1,535，BSC/Four.meme V2 35,777；只声明登记地址、事件和布局范围，Four.meme V1 不在范围内。三链21个链日闭合。

数据见 data/*.csv.gz；字典 data_dictionary.csv；逐表行数、列和哈希见 data_manifest.csv；原始和规范化证据见 inputs.tar.gz。三链各一条真实预览见 figures/real_three_chain_preview.csv；它们是展示，不替代完整正式数据。

Polymarket 有60个市场、120个 outcome、175,054个历史点、28条映射（链22、平台1、共享经济事件5、直接身份0）。6,156,902条评估含5,856,212条有效连接；宏观背景不等于新币自己的概率。桶结束严格早于锚点，映射和市场有效期、24h主陈旧度及12/48h敏感性保留。历史规则修订和API标量构造未认证，维持 retrospective_demonstration_only。

旧4,668币、18,672计划与133,888字段观察保留；新补录不伪装历史观察。缺失的旧HTTP正文、4笔缺精确签名交易及4个缺快照检查点仍明确未知。图集 figures/shilin_gallery.svg、.png；D只表示旧Solana元数据覆盖。

可从新目录离线重建，命令见 README。实际最终验收证据存于P4 reports/final_acceptance；接口逐案例证据见 test_outputs/final_interface，不与真实数据验证混为一个分母。既有P3五节文本为只读快照，数字核对见 reports/counts_audit，本次不新写联合稿件。

希望后续返回的最小数据：明确链与地址/旧object_id的crosswalk；有链上时间、原生位置、来源和证据的首次交易、毕业、迁移、后续场所与活动长表；逐币逐层/场所覆盖区间、状态和缺失原因。字段、时区与重复规则见 docs/interface_contract.md。没有数据的币也必须保留，覆盖未知不能解释为无事件或死亡。

P5共同决定项见 joint_revision_checklist.md。真实随访不应在毕业、迁移或某个T72检查点自动结束。接口兼容不代表正式队列随访已经完成。
