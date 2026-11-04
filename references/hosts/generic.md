# Generic Adapter（通用顺序模式）

> 适用：任何宿主，不假设原生子 Agent、不假设任何专有工具。
> 这是 T-021 验收基准模式，也是其他 adapter 的降级兜底。

## 子 Agent 生成

无原生子 Agent 时，**同一主 Agent 顺序分阶段扮演角色**：

1. Commander 阶段：`prism.py pack` 装配 Worker 包。
2. 角色切换声明：明确输出"——进入 Worker 角色（仅依据 worker-<H>.md）——"，
   之后只依据包内容行动，不引用包外的推理过程。
3. 执行完毕后写 `results/worker-<R>.json`，切回 Commander，校验入库。
4. Verifier 阶段同理：只依据 `verifier-<H>.md` 与 artifact 原文，重新计算
   SHA-256、独立重现，**不读自己之前作为 Worker 写下的叙事**
   （无法物理隔离时，至少做到：裁决理由只引用 artifact 与包内材料）。

顺序模式的独立性弱于真子 Agent，因此规则收紧：**顺序模式出具的 confirmed
必须在报告中标注 `verification_mode: sequential`**，供报告读者评估证据强度。

## pack → result 传递

- 读 `packets/worker-<H>.md`（路径来自 `prism.py pack --json`）。
- 结果写 `results/`：JSON 需通过 `prism.py schema`（`--format json`）契约；
  校验失败不得入库，按 `failed` 处理。

## 权限映射

- 动作组审批、越界默认不执行等 Core 纪律原样生效。
- 工具按**能力**描述（HTTP 客户端、文件读写、命令执行），由宿主任意具备该
  能力的机制承担；Core 不点名工具。

## 能力降级

| 缺失能力 | 降级方式 |
|---|---|
| 原生子 Agent | 顺序扮演（本文件），报告标注 `sequential` |
| 命令执行 | 无头解析类动作不可用；仅做文档/响应分析类假设，入 `blockers` |
| 网络工具 | 观察 / 复现不可执行；假设保持 active 或转 deferred，不虚报证据 |

## 会话与恢复

- 权威状态在案件目录（ledger.jsonl + artifacts + packets + results），
  会话记忆丢失不影响：接班后 `prism.py` + ledger 命令重建黑板即可。
- 接班顺序：读案件目录 → 重放黑板 → 从最后一条未闭环 Intent 继续。

## 实测记录

- 2026-11-03：端到端闭环测试通过（pack → worker → ingest → verdict → 门禁）
  （pack → Result 校验 → 入库 → verify-pack → confirmed → 报告门禁）；
  同日 WorkBuddy 实测中，impact 阶段以本模式顺序扮演完成，门禁先拒后放行为符合预期。
