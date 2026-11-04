# ADR-0003：参考项目以只读快照纳管

- **状态**：已接受
- **日期**：2026-11-03

## 背景

项目设计大量依赖本地参考项目：

- sapper-v2
- nvwabase
- dsh-pentest
- dsh-redteam-model
- pi（历史路线）
- 旧 pentest-redteam Skill
- 旧 dsh-prism 文档

若只保留外部路径，会出现：

- 路径漂移
- 上游更新导致设计失真
- 新会话无法恢复参考上下文

## 决策

- 在 `reference/projects/` 下保存**只读快照**
- 每个快照记录：
  - 上游 URL
  - commit hash
  - 复制时间
  - 用途
- 快照不进入 import 路径，不参与构建
- 更新快照必须写 ADR，并记录新旧版本

## 后果

- 参考上下文可长期恢复
- 设计依据固定
- 不会误把参考代码当运行依赖
- 目录体积增大，但可控
