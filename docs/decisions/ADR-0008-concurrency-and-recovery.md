# ADR-0008: 并发入库、Claim/Lease 与崩溃恢复

- **状态**：Accepted
- **日期**：2026-11-04
- **关联**：T-031（P2 并发与恢复）；升级方案 §6/§7.3；ADR-0007（事件模型）

## 背景

v1 账本"读全量→校验→追加"没有锁、claim 或幂等键，多 Worker 同时回传可能
丢更新或重复入账。T-031 验收：并发结果不丢、重放不重复、中断后可恢复。

## 决策

1. **入库顺序**（升级方案 §6 的落地版）：
   `FileLock(locks/ingest.lock) → 回放校验与幂等检查 → 追加并 fsync JSONL`。
   SQLite 派生索引**本阶段不引入**——回放即投影，索引属 P3 召回/图性能优化；
   届时按"事务更新 SQLite → 提交后重建投影"补齐，不改变本顺序。
2. **幂等键落在 run 完成事件**：`RunRecord.idempotency_key` 记录于
   `event=completed`；同键重放直接返回原 Run（`status: duplicate`），
   账本逐字节不变。ID 分配（H/E/F 递增）在锁内重读状态后进行，
   并发进程串行化后天然不冲突。
3. **claim 带 Lease**：`prism.py claim` 追加 intent claimed + run created
   （`lease_expires_at`）；同一 Run ID 重复 claim 拒绝；completed/cancelled
   的 Intent 不可 claim。`--now` 覆盖时间仅供测试。
4. **恢复是建议而非自动执行**：`prism.py recover` 只列出过期 Lease 的 Run
   与决策依据（结果包已落盘 → `ingest`；未落盘 → `re_claim`）；副作用动作
   的重放安全性（reversible / unknown / irreversible）由 Agent 层判断，
   `unknown` 不得自动重放。
5. **崩溃修复只截尾**：`prism.py repair` 截断账本末尾无法解析的半行
   （崩溃窗口只有一行），完整记录永不触碰；追加前每行先整体校验
   （Pydantic），无效记录整体拒绝、不部分入账。
6. **suggested_verdicts 不自动入账**：ingest 只落 facts/hypotheses/evidence
   与 run 完成事件；裁决仍由 Verifier 结果驱动（与 P1 纪律一致）。

## 后果

- 并发安全性由文件锁 + 锁内重放保证，Windows/POSIX 通用（filelock）。
- 主 Agent 仍是正常情况的唯一入库者；锁只是异常与并发兜底（设计 §7.1）。
- 快照（snapshot + 增量重放）延后到黑板分页/性能需要时（P3），回放已确定性。
