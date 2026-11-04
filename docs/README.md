# sapper-skill 文档总览

> 本目录是项目的**唯一文档事实源**。所有开发、测试、恢复和交接都以这里的文档为准。

## 阅读顺序

1. `README.md`（项目根）
2. `docs/spec/requirements.md`
3. `docs/design/technical-design.md`
4. `docs/plans/development-plan.md`
5. `docs/plans/task-breakdown.md`
6. `state/TASKS.md`
7. `state/PROGRESS.md`
8. `state/CHANGELOG.md`
9. `NEW_SESSION_PROMPT.md`

## 文档职责边界

| 目录 | 只负责 | 不负责 |
|---|---|---|
| `spec/` | 做什么、为什么、验收标准 | 怎么实现 |
| `design/` | 架构、模块、接口、数据模型 | 任务排期 |
| `engineering/` | 编码、提交、测试、协作规范 | 产品目标 |
| `plans/` | 阶段计划、任务拆解、里程碑 | 需求定义 |
| `state/` | 当前任务状态、进度、变更 | 设计理由 |
| `decisions/` | 关键技术/产品决策记录 | 日常任务 |

## 快速入口

- 需求：`spec/requirements.md`
- 设计：`design/technical-design.md`
- 计划：`plans/development-plan.md`
- 任务：`../state/TASKS.md`
- 进度：`../state/PROGRESS.md`
- 决策：`decisions/README.md`

## 维护规则

- **需求变更**：先改 `spec/requirements.md`，再评估 `design`、`plans` 和 `tasks`。
- **设计变更**：先写 ADR，再改 `design/technical-design.md` 或 `design/interfaces.md`。
- **任务状态**：只改 `state/TASKS.md`，并在 `state/PROGRESS.md` 追加一条记录。
- **版本变化**：`state/CHANGELOG.md` 记录对外可见变化，不重复任务流水。
- **不确定项**：一律进入 `docs/spec/open-questions.md`，不要在正文里隐式假设。

## 当前状态

- 项目处于**初始化阶段**
- 只完成了文档体系、目录骨架和参考资料纳管
- 尚未开始任何功能实现、接口落地或测试编写
