# 验收标准（Acceptance Criteria）

> 状态：**总体口径已确认，具体量化指标待 P0 基线后确定**。

## 1. 总体验收原则

- **Spec 驱动**：任何功能必须在 `requirements.md` 中有对应条目
- **可测试**：每条验收标准必须能转化为测试或可执行检查
- **可恢复**：中断后能从状态文档和账本完整恢复
- **不虚标**：未实现的能力不得在文档或 Skill 描述中宣称

## 2. 初始化阶段验收（当前阶段）

- [x] 项目目录结构建立
- [x] 参考项目快照纳入统一管理
- [x] README / Spec / Design / Plan / State 文档建立
- [x] 新会话启动提示词可用
- [x] 明确当前不含功能实现

## 3. 功能阶段验收口径

### A. 授权与安全

- 一次授权声明可跨会话恢复
- 同一 approval key 不重复询问
- 不同目标、影响或过期审批不能复用
- 越界或歧义目标默认不执行
- 目标文本中的指令不改变 Scope

### B. 状态与并发

- 多 Worker 并发结果不丢记录
- 同一结果重放不重复入账
- 非法路径、哈希、schema 被拒绝
- claim 后崩溃、结果已写但未 ingest、Verifier 中断均可恢复
- 任何 confirmed 都有 observation/reproduction/impact、有效 artifact 和 Verifier provenance

### C. 上下文与召回

- 千级节点时 context 可按目标/状态过滤
- 召回只返回短摘要，详情按需读取
- Worker pack 不含无关目标
- Verifier pack 不含 Worker 成功叙事
- 包大小超预算时确定性裁剪并报告省略项

### D. 工具与数据

- 同一资产经多个 parser 输入只形成一个规范实体
- 低置信匹配不静默合并
- scanner warning 不能自动 confirmed
- dashboard 离线打开，图与账本一致
- 删除 SQLite / snapshot 后可从 JSONL 完整重建
- 秘密不出现在摘要中

### E. 报告

- 全部 confirmed 三角色闭环
- 全部 Cleanup 项已确认
- Inconclusive / ruled-out / deferred 有明确披露
- 证据索引完整可追溯

## 4. 量化指标（TBD）

以下指标需在 P0 建立基线后确定：

- 有效确认数
- 误报数
- 重复工具调用率
- 首次有效 Finding 所需步骤
- 停滞后换角度成功率
- 跨资产经验复用次数
- 人工纠偏次数
- 上下文压缩 / 新会话恢复成功率
- 模型 token / 费用
- 报告追溯完整度
