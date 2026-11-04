# ADR-0002：采用 Spec 驱动与状态恢复体系

- **状态**：已接受
- **日期**：2026-11-03

## 背景

项目跨多个会话、多个阶段、多个参考项目演进。若没有统一事实源，容易出现：

- 重复开发
- 需求与实现脱节
- 上下文丢失
- 文档互相矛盾
- 新会话不知道当前进度

## 决策

建立以下分层事实源：

| 层 | 文件 |
|---|---|
| 需求 | `docs/spec/requirements.md` |
| 设计 | `docs/design/technical-design.md` |
| 任务 | `state/TASKS.md` |
| 进度 | `state/PROGRESS.md` |
| 变更 | `state/CHANGELOG.md` |
| 决策 | `docs/decisions/ADR-*.md` |
| 恢复入口 | `NEW_SESSION_PROMPT.md` |

并规定：

1. 任何实现前，需求先落文档
2. 任何设计变更，先写 ADR
3. 任何任务状态变化，同步 `TASKS.md` 与 `PROGRESS.md`
4. 新会话必须先读全部文档再开发
5. 未确认事项只放 `open-questions.md`，不臆造

## 后果

- 文档成为强制流程，不是事后补写
- 每次开发都可恢复
- 任务不会凭记忆重复
- 需求漂移可追踪
