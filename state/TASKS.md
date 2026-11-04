# 任务状态

> 本文件是**唯一任务状态事实源**。任何状态变化必须同步追加 `PROGRESS.md`。

## 当前阶段

- **P0 完成**
- 下一个任务：`T-050 P4 实战评测`

## 任务总览

| ID | 任务 | 状态 | 依赖 |
|---|---|---|---|
| T-000 | 项目初始化 | done | - |
| T-001 | 参考资料纳管 | done | T-000 |
| T-002 | 文档体系建立 | done | T-000 |
| T-010 | P0 安全纠正 | done | - |
| T-011 | P0 依赖与骨架冻结 | done | T-010 |
| T-020 | P1 Walking Skeleton | done | T-010 |
| T-021 | P1 Host Adapter 首版 | done | T-020 |
| T-030 | P2 状态模型 v2 | done | T-020 |
| T-031 | P2 并发与恢复 | done | T-030 |
| T-032 | P2 工具输出消化 | done | T-030 |
| T-040 | P3 Recall / KB | done | T-030 |
| T-041 | P3 可视化 | done | T-030 |
| T-050 | P4 实战评测 | pending | T-031, T-040, T-041 |
| T-051 | P4 多宿主验收 | pending | T-050 |

## 详细任务定义

详见 `../docs/plans/task-breakdown.md`。

## 阻塞

- 当前无阻塞

## 待确认

见 `../docs/spec/open-questions.md`。
