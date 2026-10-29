# Shilin v2：代码与数据使用指南

本分支整理了两套真实成果：原始 Pump.fun 七日纳入＋72 小时复访，以及 2026-10-27 目录中的三链 Registry / Polymarket 新实验。正式数据全部保留，不做抽样删行。原始工作目录保持原位。

| 数据 | 数量与范围 | 状态 |
|---|---|---|
| 原始七日＋72h | 4,668 个创建事件；18,672 个观察计划；133,888 条字段记录；六张 CSV | 运行结束，历史校验仍为 `INCOMPLETE`，4 笔交易未取回 |
| 新实验 P3 v6 | 367,373 个代币；Solana 330,061、Base 1,535、BSC 35,777；15 张表 | 声明地址/topic/layout 范围内 35/35 验收通过 |
| Polymarket 对齐 | 6,156,902 条评估，5,856,212 条有效 | 28 条背景映射，直接币身份映射为 0；不作因果或正式事前特征解释 |
| P4 接口与图集 | 五面板、接口测试、独立封装验收 | 原独立验收 55/55 通过；真实生命周期待接入 |

共同创建窗口为 `[2026-10-08 00:00, 2026-10-15 00:00) UTC`。原始复访点为 T0/T24/T48/T72；T0 使用首次解码时间，其他点按创建区块时间安排。新补录不伪造历史元数据观察。

从仓库根目录执行：

```bash
python3 pilots/shilin_v2/tools/data.py list
python3 pilots/shilin_v2/tools/data.py verify --deep
python3 pilots/shilin_v2/tools/data.py restore --output outputs/shilin_v2
```

数据以带表头的 gzip CSV 分块保存，字段和整条 CSV 记录不会被截断。恢复工具校验每块与原始整表 SHA-256，保留原字节、顺序、缺失状态和长整数。`registry` 与 `creation_events` 的原始文件内容完全一致，存储一份，恢复时生成两个文件名。

[`source/`](../source/) 保留采集、处理、验证代码、测试、冻结协议和现行报告。相对目录结构沿用原项目；原 README 的历史路径应在恢复工作区或完整输入胶囊中查找。旧版本、重复归档、缓存、过程日志和无用途副本不重复上传。

完整原始响应、规范化链上证据、上游输入与锁定依赖单独放在 [GitHub Release](https://github.com/Global-Nomad-Nexus/Web3AI4IO-SD-Template/releases/tag/shilin-v2-20261029) 的 `inputs.tar.gz` 中。读取正式 CSV 不需要先下载它；完整离线重建需要该胶囊。下载、恢复封装和原验收命令见 [复现指南](REPRODUCE.md)。

历史 P4 文档中的“仅本地审阅”描述的是当时的候选包，本次上传单独标记为 `shilin-v2-20261029`。原来源权利登记保留未知／未审核状态，本次公开上传不会自动授予第三方数据许可。详见 [数据权利与来源](../DATA_RIGHTS.md)。

本分支不声称全链全部创建覆盖，不把元数据请求失败解释为死亡，也不声称真实生命周期、共同 cutoff、官方 Croissant 校验或论文投稿已经完成。
