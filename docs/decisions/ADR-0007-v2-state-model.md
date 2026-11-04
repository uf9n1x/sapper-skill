# ADR-0007: v2 状态模型与事件回放

- **状态**：Accepted
- **日期**：2026-11-03
- **关联**：T-030（P2 状态模型 v2）；升级方案 §6；interfaces.md §2/§4；open-questions Q4

## 背景

P1 的 Walking Skeleton 只覆盖 Hypothesis/Evidence/Verdict。T-030 要求引入
Fact / Intent / Run / Approval，冻结 schema 并导出，提供 v1→v2 迁移脚本，
且状态事件可回放。

## 决策

1. **单一 JSONL 权威账本不变**：v2 新记录（fact / intent / run / approval）与
   既有的 hypothesis / evidence / verdict 同住 `ledger.jsonl`，每行一条、
   `v: 2` 标记；不做第二真相源。
2. **Intent / Run 为追加事件模型**：created / claimed / completed / blocked /
   cancelled（Run 另有 failed / timed_out）逐条追加，当前状态由同一实体
   最新事件派生（`prism.py state`），事件历史保留；禁止手工改历史。
3. **Worker Result 全字段冻结（Q4 关闭）**：14 个顶层字段与 Pydantic 模型
   `WorkerResult` 一致；FactProposal 的 kind 枚举冻结为 8 类（asset / service /
   application / identity / credential_ref / access / vulnerability_lead / progress）。
4. **approval_key 派生而非申报**：`action_class|target_scope|effect` 由模型
   自动生成，提供不一致值直接拒绝——消除"申报键与内容不符"的整类错误。
5. **引用完整性在回放期强制**：evidence→hypothesis、hypothesis→fact、
   fact/intent→source、intent claimed→run、run→intent 悬空引用一律拒绝；
   重复 ID 拒绝（幂等入库属 T-031 ingest）。
6. **迁移语义**：v1 记录升级为 v2（新可选字段取默认），顺序与 ID 不变；
   artifacts 整体复制；迁移后立即回放并与 v1 派生状态做 H/E/V 语义等价对比，
   不等价即失败——迁移脚本自带验证，不靠人工抽查。
7. **schema 导出扩展**：`prism.py schema` 同时导出 Result 包与 7 类账本记录
   模型（`references/result-schema.{json,md}`，漂移守卫测试强制）。

## 后果

- `state.replay()` 是后续黑板渲染、next 排序（planner）、graph 投影的统一入口。
- 事件模型使 claim/lease（T-031）只需追加事件，不需要状态更新语句。
- v1 账本不可直接回放（报错并提示 migrate），避免双格式长期并存。
- 固定时间戳 + ID 不变保证迁移确定性：同一输入两次迁移输出逐字节一致。
