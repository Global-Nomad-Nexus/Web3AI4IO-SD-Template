# 元数据与许可验收范围

configs/table_schema.json描述真实15表、251列、主键和文本精度；data_dictionary.csv保留P3冻结版本。configs/lifecycle_schema.json描述canonical事件/覆盖行形状；实际适配器还验证主外键、UTC、原生位置、角色、事件先后与覆盖关系。两类schema不能互相代替。

Croissant/RAI文件针对本地候选数据；本轮比照MLCommons公开规范制作，检查JSON可解析、15个recordSet、251字段、字段来源指向、压缩与未压缩文件hash、来源/许可表列和RAI限制/用途说明。这是局部结构和引用验收，官方mlcroissant validator未运行，不声称符合全部发布平台要求。发布许可证、持久URL和引用将在P5权利审核及外部发布时补齐；不虚构DOI。

来源表中的公开获取结论只指冻结请求所用公开路径。terms_checked_at为空表示未审阅，不是通过审核；raw_redistribution_status=unknown_not_authorized_for_public_release。既有P3许可未核定的限制继续保留。该本地材料包不自动授予第三方规则、描述、图像或响应的再分发权利。

参考：[Croissant1.1](https://docs.mlcommons.org/croissant/docs/croissant-spec-1.1.html)、[CroissantRAI](https://docs.mlcommons.org/croissant/docs/croissant-rai-spec.html)，核对日期2026-10-29。
