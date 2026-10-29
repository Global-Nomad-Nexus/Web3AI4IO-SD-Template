Pump.fun 七日纳入 + 72 小时复访数据包（2026-10-21）

本目录只整理 2026-10-08 00:00 UTC 至 2026-10-15 00:00 UTC
七个完整 UTC 日的采集，以及每个事件的 T0/T24/T48/T72 四轮观察。
窗口含起点、不含终点。T0 按首次解码时间，其他观察点按区块时间计算。

当前结果
  4,668 个创建事件、4,668 个 mint、18,672 条计划与覆盖记录。
  成功解析 16,736 条，请求失败 1,924 条，记为解析失败 12 条。
  133,888 条字段记录。全部计划均有终态，进程为 finished。
  校验仍为 INCOMPLETE：4 笔链上交易在重试后仍未取回。
  现有名单不保证覆盖这一周链上的全部创建。

WORK_PROGRESS_REPORT.md / WORK_PROGRESS_REPORT.pdf
  本轮的工作说明、时间规则、统计、数据来源、质量问题与待办。

code-7day-72h/
  采集器、配置、离线样例、测试、Slurm 脚本和四张统计图。
  使用说明见该目录 README.md。

data/7day-72h-20261008-release/
  六张 CSV：launch_events、observation_plan、request_attempts、
  response_snapshots、field_observations、coverage_ledger。
  同时保留原始 release_manifest.json 与 validation_results.json。

data/7day-72h-20261008-protocol/
  冻结协议、来源登记、RPC 选择、网关预检、数据处理规则、
  输入清单、进度和结束状态。实采文件保留原字节。

paper/README.md
  本轮论文准备事项、现有图表位置；当前不提供完整投稿稿。

精简包不包含
  第三方原始响应正文 response_bodies.jsonl；
  与 CSV 重复的 request_attempts.jsonl；
  完整 run 目录、集群日志、虚拟环境和补录中间目录。
  原始 manifest 仍列出省略的 JSONL 文件，这不是文件损坏。

复现边界
  离线 fixture 只验证流程，其样例日期不属于实采事件。
  实采表可用于分析和关联检查，但没有原始响应正文，不能仅凭
  此包重新解析历史正文或重新验证响应正文的 SHA-256。
  对网络来源的再次请求属于新的观察，不能保证返回历史字节。
