# P2：已完成的三链共同整日试点

窗口为 [2026-10-08 00:00:00, 2026-10-09 00:00:00) UTC。声明平台范围内共 61,916 个不同代币：Solana 55,508、Base 197、BSC 6,211；最终 33 项验收通过。范围为 Pump.fun create/create_v2、六个固定 Clanker 工厂与 Four.meme V2。

## 阅读与使用

| 目的 | 入口 |
|---|---|
| 了解过程与结果 | [执行与验收报告](reports/P2_执行与验收报告.md) |
| 使用数据 | [processed/](processed/) |
| 核对验收 | [validation_results.json](reports/validation_results.json) |
| 核对复现 | [offline_reproduction.json](reports/offline_reproduction.json) |
| 核对原生 QA | [native_QA_receipt.json](reports/native_QA_receipt.json) |
| 查看完整阶段过程 | [P0—P2 详细报告](../P0-P2_工作内容与实验过程详记.md) |
| 查看来源切换与失败历史 | [archive/](archive/README.md) |

## 目录

- code/、configs/、tests/：采集、解码、构建、验证和固定配置。
- vendor/：固定 eth-abi 等依赖，P3 继续引用。
- raw/、data/：原始响应、查询与原生证据。
- processed/：已验收的九张处理表。
- reports/：最终验收、原生核验、覆盖及固定证据账本。
- provenance/：请求与文件哈希、原协议快照。
- figures/、manuscript/：阶段图表与方法记录。
- archive/：过程日志及早期来源探测记录。

## 离线复现

在保留整个 registry_polymarket 及旧输入的目录副本中，从 p2 执行：

~~~bash
/opt/homebrew/opt/python@3.14/bin/python3.14 code/reproduce_offline.py
~~~

P2 读取父目录 P0/P1 的固定市场数据，也被 P3 按哈希引用。目录整理保留了这些路径及输入字节；历史控制台日志和未被输入锁引用的早期探测已集中到 archive。

所有数量均限声明地址／事件范围。补录币没有历史元数据观察时保持 not_collected_historically_P2；共享背景不等于直接币身份概率。生命周期和共同 cutoff 未在 P2 接入。
