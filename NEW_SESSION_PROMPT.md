# 新会话启动提示词

> 使用方式：将以下整段内容复制给新会话的智能体，作为第一条消息。

---

你是 `sapper-skill` 项目的开发助手（Skill 最终名 sapper-skill，开发目录仍为 prism-skill，见 ADR-0012）。请严格按以下顺序恢复上下文，不要跳步、不要凭记忆猜测：

1. 读取 `README.md`
2. 读取 `docs/README.md`
3. 读取 `docs/spec/requirements.md`
4. 读取 `docs/spec/acceptance.md`
5. 读取 `docs/spec/open-questions.md`
6. 读取 `docs/design/technical-design.md`
7. 读取 `docs/design/PENTEST_SKILL_UPGRADE_PLAN.md`
8. 读取 `docs/design/interfaces.md`
9. 读取 `docs/engineering/coding-standards.md`
10. 读取 `docs/engineering/testing.md`
11. 读取 `docs/plans/development-plan.md`
12. 读取 `docs/plans/task-breakdown.md`
13. 读取 `reference/README.md`
14. 读取 `state/TASKS.md`
15. 读取 `state/PROGRESS.md`
16. 读取 `state/CHANGELOG.md`
17. 读取 `project-state.yml`

完成阅读后，请先做三件事，再开始任何开发：

1. **核对当前状态**：报告当前阶段、已完成任务、下一个应执行的任务 ID。
2. **确认无冲突**：检查 `TASKS.md`、`PROGRESS.md`、`development-plan.md` 是否一致；若不一致，先指出冲突并停下询问，不要自行猜测。
3. **确认边界**：复述当前不允许做的事（不实现 Runtime、不执行攻击、不支持黑灰产等）。

然后按以下规则工作：

- 严格依据 `docs/spec/requirements.md` 和 `docs/plans/task-breakdown.md` 实施
- 每完成一个任务，立即更新：
  - `state/TASKS.md` 的任务状态
  - `state/PROGRESS.md` 的追加记录
  - 如涉及对外行为，`state/CHANGELOG.md`
- 任何需求或设计变更，先更新对应文档，再写代码
- 任何不确定项，写入 `docs/spec/open-questions.md`，不要臆造
- 不要重复开发已完成的任务
- 不要删除或改写 `reference/projects/` 下的快照
- 不要在未读完全部文档前开始写代码
