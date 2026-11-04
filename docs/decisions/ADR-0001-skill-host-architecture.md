# ADR-0001：采用 Skill + 宿主原生 Agent + Python 控制面

- **状态**：已接受
- **日期**：2026-11-03

## 背景

此前依次评估过三条路线：

1. 自研独立 Agent Runtime
2. fork Pi Coding Agent
3. 整体二开 sapper-v2

三者都能实现目标，但都会重复解决宿主已经解决的问题，并带来跨宿主行为分叉、部署臃肿或维护成本过高的问题。

## 决策

采用：

```text
通用 Agent Skill
  + 宿主原生主/子 Agent
  + Python 确定性控制面
```

- 宿主负责：模型、子 Agent、MCP、工具、交互、会话
- Skill 负责：方法论、工作流、状态协议、证据纪律
- Python 负责：状态、锁、召回、图、报告、面板、工具解析

## 理由

1. Codex、DSH 等宿主已具备子 Agent 与工具能力
2. sapper-v2 的价值在智能机制，不在 Docker/tmux 外壳
3. 自研 Runtime 只会重复宿主工作
4. Python 能把最易错的部分做成确定性工程

## 后果

- 不再维护独立 TypeScript Agent Core
- 不 fork Pi、不整体二开 sapper-v2
- 参考项目只作设计输入，不作为运行依赖
