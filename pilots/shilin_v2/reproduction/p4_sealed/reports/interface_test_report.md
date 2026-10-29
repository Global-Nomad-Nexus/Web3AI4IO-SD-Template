# P4 生命周期接口测试报告

## Material Passport

Origin Skill: academic-research-suite / experiment-agent；Mode: reproducibility validation；日期：2026-10-29；Verification Status: VERIFIED for synthetic interface behavior only。

接口 `shilin_lifecycle_adapter_v1`，确认状态 unconfirmed_by_claire。合成测试 51 项，失败 0，实际CLI退出码 0；状态 passed。逐案例与命令产物见 test_outputs/final_interface/interface_test_results.json、unittest.log、positive_cli。

边界包含：Base/BSC同地址分链、Solana大小写、EVM规范化、旧object_id显式crosswalk、歧义及冲突身份拒绝；重复事件审计和冲突全隔离、一币多事件、母表无丢币、缺记录未知；创建/首次观测/事件/获取时钟分离、creator角色冲突；覆盖完整、相邻拼接、覆盖缺口、晚起观察、partial与source_missing、矛盾覆盖隔离、目标层不同；cutoff前后及恰好边界；行政右删失/失访/未知/已观测事件；缺口后首次发生不认证；inactivity和reactivation均保留；真实模式拒绝synthetic行；未来桶/当前报价/结算支付拒绝、合法历史API标量保留限制。

本报告证明样例上的程序行为，不证明真实生命周期已取得或随访完整。真实状态 awaiting_integration；共同cutoff=null；无真实outcome_followup表。合成输入和结果位于tests/fixtures与test_outputs，正式15表和五面板不读取它们。最终包会重新运行相同测试，报告单独保存，不与真实数据35项检查或P3原生QA案例数相加。
