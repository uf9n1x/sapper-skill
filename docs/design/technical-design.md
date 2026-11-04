# 技术设计总览

> 详细设计见同目录 `PENTEST_SKILL_UPGRADE_PLAN.md`；本文只固化**已确认的架构决策**与当前实现状态。

## 1. 总体架构

```text
┌─────────────────────────── 宿主 Agent 层 ───────────────────────────┐
│ Commander（主 Agent）：规划 / 派单 / 纠偏 / 汇报                     │
│ Worker / Verifier（原生子 Agent）：可并行，顺序降级可用              │
│ 宿主工具：Shell、MCP、其他 Skills、文件与网络能力                    │
└────────────────────────────────┬───────────────────────────────────┘
                                 │
┌────────────────────────────────▼───────────────────────────────────┐
│ sapper-skill（本项目）                                                │
│ 1. Skill 指令层：方法论、路由、角色协议、授权纪律                    │
│ 2. Python 控制面：状态、锁、召回、图、报告、面板、工具解析           │
│ 3. 输入层：engagement.yml / scope.yml / targets / docs / tools      │
└─────────────────────────────────────────────────────────────────────┘
```

## 2. 关键设计决策

| 决策 | 内容 | 状态 |
|---|---|---|
| 宿主职责 | 模型、子 Agent、MCP、交互、实时执行 | 已确认 |
| Skill 职责 | 方法论、工作流、状态协议、证据纪律 | 已确认 |
| Python 职责 | 确定性状态、锁、召回、图、报告、面板 | 已确认 |
| 存储 | JSONL 权威账本 + 可重建 SQLite 索引 | 已确认 |
| 并发 | Worker 不写账本，主 Agent 统一 ingest | 已确认 |
| 授权 | 一次声明、战役常驻、高影响动作组审批 | 已确认 |
| 图 | NetworkX 派生投影，不是第二真相源 | 已确认 |
| 可视化 | 离线交互 HTML，无常驻服务 | 已确认 |

## 3. 模块边界

### 3.1 Skill 指令层

- `SKILL.md`：触发条件、路由、硬约束
- `playbooks/`：Commander / Worker / Verifier / Report 协议
- `techniques/`：领域战术资料，按需加载
- `references/`：渐进披露文档

### 3.2 Python 控制面

- `store.py`：JSONL、快照、SQLite、迁移
- `ingest.py`：FileLock、claim、幂等入库
- `policy.py`：Scope、常驻授权、高影响审批
- `recall.py`：混合召回
- `knowledge.py`：离线 KB、信任级别、经验晋升
- `planner.py`：候选排序、阻塞/停滞分析
- `packets.py`：角色上下文包装配
- `graph.py`：关系、路径、影响面分析
- `projection.py`：Board、报告、时间线
- `render.py`：Jinja2/PyVis 离线面板
- `workspace.py`：输入清单索引
- `parsers.py`：工具输出解析
- `identity.py`：资产归一化与去重
- `capabilities.py`：MCP/工具/Skills 能力矩阵
- `doctor.py`：依赖、工具、存储诊断

### 3.3 输入层

```text
my-engagement/
  engagement.yml
  scope.yml
  inputs/
    targets.csv
    docs/
    tools.yml
    skills.yml
  case/
    ledger.jsonl
    snapshots/
    index.sqlite
    artifacts/
    results/
    packets/
    board.md
    dashboard.html
    attack-graph.html
    attack-graph.mmd
    reports/
```

## 4. 当前实现状态

- P0 完成：授权纠正、v1 账本基线与回归测试、依赖锁定（ADR-0004/0005）
- P1 完成：prism 控制面骨架（pack/verify-pack/schema/hosts）、五 playbooks、
  host adapter 体系（generic/omp/workbuddy/dsh，WorkBuddy 原生子 Agent 实测闭环，ADR-0006）
- P2 完成：v2 状态模型与事件回放（Fact/Intent/Run/Approval、
  `state` 回放、`migrate` 迁移，ADR-0007）；并发与恢复（claim/lease、
  FileLock + fsync 幂等 ingest、recover/repair，ADR-0008）；工具输出消化
  （五类 parser registry、identity 归一化与去重、`harvest`，ADR-0009）
- P3 进行中：Recall/KB 完成（BM25+模糊+图扩展可解释召回、失败路径并召、
  离线 KB 信任级别与过期警告、confirmed+去目标化晋升门禁，ADR-0010）；
  可视化（T-041）未开始

## 5. 明确不做

- 不实现模型 API
- 不实现自主 `while` 推理循环
- 不实现子 Agent 进程管理
- 不实现目标 Shell/Exploit 执行
- 不实现 MCP Server
- 不实现常驻 HTTP 服务
