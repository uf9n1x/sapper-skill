# ADR-0009: 工具输出消化（harvest）与资产归一化

- **状态**：Accepted
- **日期**：2026-11-04
- **关联任务**：T-032（P2 工具输出消化）
- **关联决策**：ADR-0007（v2 状态模型）、ADR-0008（并发与恢复）

## 背景

大型实战中模型反复阅读原始扫描日志（Nmap/Masscan/httpx/Nuclei 输出）会
撑爆上下文且效率低下。升级方案 §5 要求 Python 消化工具输出：原始日志只
存 artifact，模型只接收结构化增量；同一资产经多个工具输入应归并为一个
规范实体。

## 决策

### 1. harvest 是只读操作，入库仍由主 Agent 决定

`prism.py harvest` 读取 case 内 artifact（相对路径防逃逸）、计算 SHA-256、
解析出候选事实、与账本既有事实做增量对比后输出 digest JSON。**全程不写
账本**——候选是否入库由主 Agent 按授权范围与战役焦点决定，保持"主 Agent
是唯一入库者"的既有纪律。

### 2. parser 是纯文本解析，registry 可扩展

- 首批五类：`nmap-xml`、`masscan-json`、`httpx-jsonl`、`nuclei-jsonl`、
  `generic-json`（浅层启发式，置信度 0.6 上限）
- `PARSERS` dict 即扩展点；BloodHound 等大数据后续做独立 parser，
  不全量注入模型
- 非结构化内容（如 XML 注释）不进入 digest——嵌入输出中的指令式文本
  只会被当作数据处理或直接忽略，永远不会被执行

### 3. 秘密默认脱敏

parser 输出的全部字符串字段经过键值（password/token/api_key/secret/
authorization）、Bearer、常见令牌前缀（sk-/ghp-/akia- 等）三类模式脱敏。
完整原文只在 artifact 中，受案件权限控制。

### 4. 扫描器告警永不自动成为 confirmed Finding

Nuclei 等扫描告警解析为 `vulnerability_lead` 候选，固定携带
`requires_verification=true` 且置信度上限 0.5（按严重度 0.30–0.50）。
这与"confirmed 必须由 Verifier 驱动"（ADR-0007/0008）一脉相承。

### 5. 跨工具去重：确定性规则合并，模糊相似只进审查队列

- **确定性合并**：目标归一化（IPv4/IPv6 压缩小写、IDNA punycode、URL
  规范化去默认端口/query）产生资产键；`host:port/proto` 服务形态绑定
  主机键；parser 报告的 hostname 别名（如 nmap PTR）生成 primary↔alias
  表，别名归并到同一键。相同键才合并，`merge_reason` 说明依据。
- **模糊相似（rapidfuzz token_sort_ratio）只用于发现疑似重复**：
  70 ≤ score < 88 进入 review_queue（附分数与理由），永不静默合并；
  < 70 视为无关。跨键即使高相似也不合并——保守优先。
- 合并与审查输出按资产键排序，与输入顺序无关（确定性，可回放对比）。

### 6. digest 有硬上限，防上下文爆炸

digest 候选上限 200 条（`limits.max_candidates`），超出部分只计数
（`counts.omitted`）；单次解析总量上限 2000。digest_text 短摘要 ≤ 40 行。

## 影响

- 模型上下文只接收新增/变化候选（验收 2），大扫描不再重复进入上下文
- 账本 facts 与 digest 的增量对比基于资产键，事实记录新增字段无需变更
- SQLite 派生索引（P3）落地后，增量对比可从图/索引读取，接口不变
