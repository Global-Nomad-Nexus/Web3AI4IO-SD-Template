# 五面板定义

全部源表来自 P3 v6 正式数据；代码为 code/gallery.py，SVG 用标准库确定性生成，PNG 用固定 librsvg 渲染。图集不读取 tests 或 test_outputs。没有生命周期结局或删失样本参与此图。

| 面板 | 问题、来源与公式 | 单位、分母与范围 | 缺失与解释 |
|---|---|---|---|
| A | registry 的 chain_key、created_at_utc、token_id，按 UTC 日去重计数；与逐日 creation_coverage 对照 | token/日；三平台声明版本，共 367,373 币 | complete 仅针对声明地址/topic/layout；不推断全链发行或成功 |
| B | 21 个链日的创建覆盖；context_daily 中 matched_valid 行数/该链日评估行数 | 日格；下方分数是有效映射锚点/评估锚点，不是代币覆盖率 | C 表示声明创建范围完整；背景有效与创建完整分开。未知不得表示为 0 |
| C | pm_mapping 按四类关系统计独立 market、mapping 行；expectation_coverage 中每链有效 token 去重后跨链相加 | market、mapping、不同 token 三种单位；token 总分母 367,373 | 不同关系的 token 可重叠，不求和当总体；direct identity 为真实零。条形表示 token/总分母 |
| D | metadata_coverage 按 checkpoint、final_state 分组 | 每检查点 4,668 个计划；旧七日 Solana 队列，合计18,672 | observed、request_failed、parse_failed；最后一类含缺证据，不全是非法 JSON。元数据不可访问不是死亡 |
| E | 在 shared_economic_event 映射中选择有效 UTC 日初锚点最多、mapping_id 字典序最小的一条；保留同一个原生 outcome，展示 context_daily 的严格事前桶结束价格，下面按日堆叠三链创建数 | 上图 API scalar，0–1；下图 token/UTC日；均为10月8–14日 | 无有效价格则 NA 并断线，不插值；标记题目、关闭期限和未见窗内关闭/结算。历史规则和价格构造未认证，不能解释为正式事前特征或因果 |

每面板 CSV：figures/data/panel_A_activity.csv、panel_B_coverage.csv、panel_C_links.csv、panel_D_metadata.csv、panel_E_alignment.csv。E 的题目、原生 outcome、mapping 与时间限界见 figures/selection.json。三链真实预览见 figures/real_three_chain_preview.csv，其粒度仅为展示，每链一条，不能当作正式样本量。

作图尺寸 SVG 1800×1640；PNG 3600×3280。坐标、图例和限制已做视觉检查。图像使用英文标签以便后续稿件复用，定义与解释保存在本说明。SVG 不受字体栅格化字节差异影响，源表与 SVG 要求逐字节一致；PNG 在本次固定 librsvg 环境也逐字节比较。
