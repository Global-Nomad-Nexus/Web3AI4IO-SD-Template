# P4 个人交付候选（不含文章修改）

本目录完成生命周期接口适配、隔离测试、正式个人数据总审计、五面板图集及最终封装包的离线验收。数据基线是 P3 v6，创建窗口 `[2026-10-08, 2026-10-15)` UTC；不改动 P0–P3 原文件或文章。真实生命周期状态保持 `awaiting_integration`，共同 cutoff 为空。

## 优先阅读

- `reports/P4_完成与验收报告.md`：最终结果、证据及限制。
- `reports/final_acceptance/acceptance.json`：独立目录实际验收结果。
- `delivery/p4_personal_candidate_20261029/`：封装后交付目录；`inputs.tar.gz` 是独立输入胶囊，`data/*.csv.gz` 是正式 15 表。
- `figures/shilin_gallery.svg` 与 `.png`：真实五面板；`figures/data/` 为全部源表。
- `docs/interface_contract.md`、`configs/adapter_config.json`、`configs/lifecycle_schema.json`：接口和字段映射。
- `test_outputs/final_interface/`：合成接口测试、逐案例结果、CLI 运行产物。
- `handoff_to_claire.md` 与 `joint_revision_checklist.md`：本地交接材料，尚未发送。
- `docs/data_card.md`、`configs/source_rights.csv`、`configs/croissant.json`、`configs/rai_metadata.json`：数据与来源说明。

## 从最终包独立离线重建

需要 macOS arm64、Python **3.14.2**（原 P3 ABI 依赖已随胶囊封装）。接口程序和 SVG 生成只需标准库；PNG 使用 `rsvg-convert 2.63.2`。不自动联网安装依赖。

在 `delivery/p4_personal_candidate_20261029` 目录运行（相对路径可随包整体搬移）：

```bash
/opt/homebrew/opt/python@3.14/bin/python3.14 -B code/accept_delivery.py \
  --release . --output /private/tmp/p4_independent_acceptance_new
```

输出目录必须是**尚不存在的新目录**，可自定义。程序验证封装文件集与哈希、解压全部输入、从原生规范化证据重建创建表及派生表，重跑真实数据验证、图表和接口测试。工作进程通过 Python audit hook 限制读取到胶囊及解释器安装目录，并拒绝 socket 网络；会用实际负对照验证禁网与文件隔离。验收后删除该次可重建的大表，保留日志、哈希、测试和数字审计；`--keep-workspace` 可保留完整输出，需约 8–10 GB 空闲空间。

原始 NDJSON 是从冻结原始响应生成并保留的原生交易/日志证据。本次重建从该冻结规范化层开始；胶囊同时带回查所需原始响应。市场六表作为固定输入逐字节保留，本次不重新查询或重新解释可变历史 API。旧元数据只可回放六表摘要，不能复原缺失的历史 HTTP 正文。

## 接口单独使用

```bash
python3 -B code/lifecycle_adapter.py --registry registry.csv \
  --config configs/adapter_config.json --events ecosystem_events.csv \
  --coverage observation_coverage.csv --crosswalk identity_crosswalk.csv \
  --mode real --output adapter_output_new
```

`--events`、`--coverage`、`--crosswalk` 可省略。真实模式拒绝 synthetic 标记；错误行进入带文件/行号/原因的 quarantine，并返回非零退出码。现阶段真实模式只供字段兼容与身份连接，`joint_definitions_confirmed=false` 时拒绝生成真实结局。P5 确认协议、逐目标覆盖和 cutoff 后再版本化接入。

```bash
python3 -B code/run_interface_tests.py --output test_outputs/new_interface_run
```

## 交付边界

本包为**本地审阅候选**，没有公开上传或联系 Claire。来源可公开读取的实采证据与第三方再分发许可分别记录，未知许可不升级为允许；不对第三方材料套统一许可证。Croissant/RAI 以本地描述文件交付，官方 validator 和发布平台验收尚未运行，不声称认证合规。既有 P3 正文只读快照及数字核对随包保留，本次不完成文章写作。
