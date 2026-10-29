# P3：已完成的正式一周数据

最终运行是 [formal_20261008_15_v6](runs/formal_20261008_15_v6/)，完成于北京时间 2026-10-29 07:28:56。共同创建窗口为 [2026-10-08, 2026-10-15) UTC。

- 不同代币：367,373；三链七日覆盖：21/21。
- 最终验收：35/35 通过；固定种子原生 QA：191 个案例、14 个分组。
- 两次禁网复现：15 张处理表逐字节一致。
- 预期长表：6,156,902 行评估，其中 5,856,212 行有效。
- 直接币身份映射：0；28 条映射属于链、平台或共享经济背景。

## 常用入口

| 目的 | 位置 |
|---|---|
| 阅读详细实验报告 | [P3_详细实验报告.md](P3_详细实验报告.md) |
| 使用最终数据 | [processed/](runs/formal_20261008_15_v6/processed/) |
| 核对完成状态 | [最终验收](runs/formal_20261008_15_v6/reports/validation_results.json)、[当前指针](reports/current_formal_run.json) |
| 查表粒度、字段和哈希 | [数据字典](runs/formal_20261008_15_v6/configs/data_dictionary.csv)、[processed manifest](runs/formal_20261008_15_v6/provenance/processed_manifest.csv) |
| 查原始取证 | [raw/](runs/formal_20261008_15_v6/raw/)、[逐日回执与证据](runs/formal_20261008_15_v6/days/)、[请求账本](runs/formal_20261008_15_v6/provenance/requests.jsonl) |
| 查 QA 与复现 | [原生 QA](runs/formal_20261008_15_v6/reports/native_QA_receipt.json)、[禁网复现](runs/formal_20261008_15_v6/reports/offline_reproduction.json) |
| 查修复、准备与旧版本 | [archive/](archive/README.md) |
| 查本次目录整理 | [整理说明](../../整理记录/整理说明.md) |

## 目录结构

~~~text
p3/
├── P3_详细实验报告.md
├── README.md
├── code/                     当前运行代码，内容与 v6 代码锁一致
├── configs/                  运行配置、ABI/IDL 和上游输入锁
├── tests/                    隔离测试代码
├── reports/                  当前指针、最终代码测试、报告统计依据
├── runs/
│   └── formal_20261008_15_v6/ 唯一展开保留的正式运行
│       ├── processed/        最终 15 张表
│       ├── raw/ days/ rules/ 原始证据、每日位置和完整规则
│       ├── reports/          最终覆盖、审核、QA、复现与验收
│       ├── configs/          冻结协议和代码
│       ├── provenance/       账本、哈希及迁移证据
│       └── figures/ manuscript/
└── archive/                  旧版本独有证据、过程日志、准备和修复记录
~~~

v1—v5 的重复 raw 已逐文件哈希核对后引用 v6 保留副本；独有的失败、代码和取证记录已归档。旧派生表、旧派生表压缩包、重复规范化中间表及过期 ETA 已清理。档案清单说明每个旧文件是留存、归档还是作为可重建输出删除。

## 离线复现

使用固定 Python 3.14.2，保留整个 registry_polymarket 及上游旧数据，在完整副本中从 p3 执行：

~~~bash
/opt/homebrew/opt/python@3.14/bin/python3.14 code/p3.py \
  --config configs/protocol_formal_v6.json \
  reproduce --output runs/formal_20261008_15_v6
~~~

正式采集已经完成，30 分钟监测已删除。历史规则修订和 API scalar 构造仍未认证；价格状态保持 retrospective_demonstration_only。真实生命周期与共同 cutoff 属于后续 P5。
