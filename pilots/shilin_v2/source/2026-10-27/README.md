# 2026-10-27 项目目录

这是三链 Token 创建 Registry、Polymarket 预期背景及旧元数据审计的工作目录。P0—P3 已完成各自范围的验收；最新正式数据是 P3 v6。P4 的非文章交付已完成最终包独立离线验收，真实生命周期仍留给 P5。

## 从这里阅读

| 目的 | 文件／目录 |
|---|---|
| 看总体方案 | [执行路径](执行路径.md)、[任务解读](Shilin_任务解读与实施建议.md) |
| 看 P0—P2 的过程、来源和结果 | [P0—P2 详细报告](registry_polymarket/P0-P2_工作内容与实验过程详记.md) |
| 看 P3 的过程、方法、来源与结果 | [P3 详细报告](registry_polymarket/p3/P3_详细实验报告.md) |
| 看 P4 非文章完成与验收 | [P4 完成报告](registry_polymarket/p4/reports/P4_完成与验收报告.md)、[P4 入口](registry_polymarket/p4/README.md) |
| 取最终交付包 | [P4 个人交付包](registry_polymarket/p4/delivery/P4_个人交付包_20261029.tar.gz) |
| 使用最新正式数据 | [P3 v6 processed](registry_polymarket/p3/runs/formal_20261008_15_v6/processed/) |
| 核对最终验收 | [P3 最终验收](registry_polymarket/p3/runs/formal_20261008_15_v6/reports/validation_results.json) |
| 找阶段代码与原始证据 | [阶段目录导航](registry_polymarket/README.md) |
| 看本次删除、归档及校验记录 | [整理说明](整理记录/整理说明.md)、[逐项清单](整理记录/20261029_整理清单.json) |

## 结构

~~~text
2026-10-27/
├── README.md                      本导航
├── 执行路径.md                    总体方案
├── Shilin_任务解读与实施建议.md     任务解释
├── registry_polymarket/
│   ├── README.md                  各阶段入口
│   ├── P0-P2_工作内容与实验过程详记.md
│   ├── code/ configs/ processed/ raw/ reports/ ...   P0/P1 成果与证据
│   ├── archive/                   P0/P1 过程日志
│   ├── p2/                        已完成的单日试点
│   ├── p3/                        已完成的正式一周数据
│   └── p4/                        非文章交付、接口、图集及最终包验收
└── 整理记录/                       本次清理的文件级审计
~~~

P0/P1 的基础目录、p2 和 P3 v6 的数据路径保持原位，因为后续阶段通过相对路径和哈希锁引用它们。旧失败与独有取证记录归档；重复副本、可重新生成的旧派生结果、缓存和过期进度已清理。真实生命周期与联合 cutoff 仍属于后续 P5。
