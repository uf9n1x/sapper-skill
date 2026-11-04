# ADR-0010: 混合召回与离线知识库

- **状态**：Accepted
- **日期**：2026-11-04
- **关联任务**：T-040（P3 Recall / KB）
- **关联决策**：ADR-0007（v2 状态模型）、ADR-0008（并发与恢复，SQLite 延迟）

## 背景

长战役中上下文压缩后无法重读全历史；不同 Worker 会重复踩已被证伪的
路径。升级方案 §8 要求混合、可解释召回，同时召回成功与失败路径；
离线 KB 带来源与信任级别；只有验证过的去目标化经验才能晋升。

## 决策

### 1. 召回索引为内存重建，SQLite 缓存继续延迟

每次 `recall` 调用从账本回放重建语料（案件规模可控，实测 < 200ms 量
级）。SQLite 物化缓存仍是可选优化（ADR-0008 延迟决策继续有效）——
待案件规模实测证明需要时引入，接口（`prism.py recall`）不变。

### 2. 打分：BM25 为主 + 模糊匹配 + 结构化加权 + 一跳图扩展

- BM25（rank-bm25，jieba 中文分词 + ASCII 词元）权重 0.6；
  RapidFuzz partial_ratio 模糊匹配（产品别名/近似指纹）权重 0.25；
- target/产品字段命中加权 0.10；总分为各分量之和，每条命中返回
  `breakdown` 与 `reasons`（**可解释**，验收 1）；
- 低于 0.05 的命中丢弃；同分按记录 ID 排序（确定性，可回放对比）。

### 3. 失败路径与成功路径并召

killed 假设 / blocked·cancelled Intent 全部进入语料，命中标注
`path=failure` 并携带最新状态（验收 2）——不同 Worker 检索即可看到
"此路已证伪 / 已受阻"，不必重读全历史。

### 4. 图扩展：一跳、共享资产族、限量 5 条

资产族 = 文本（target + claim/summary）中出现的全部主机/IP 标识的
交集。命中记录的一跳同族邻居以 `breakdown.graph=0.3` 与"图扩展"
原因加入，严格限量（防止大案件噪声）。详情按需 `prism.py doc <id>`
（有 artifact 返回文件内容，否则返回记录 JSON）。

### 5. KB：frontmatter 元数据 + 强制警告

- trust ∈ {official, community, unverified}，非法值拒绝加载；
- `last_verified` 超过 180 天强制 `EXPIRED` 警告（`kb-list` /
  `kb-read`，验收 3）；`--today` 可注入用于确定性测试；
- KB 与 techniques 分工：KB 管"产品/版本的可复用解法"，
  不重复维护同一内容。

### 6. 晋升门禁：confirmed + 去目标化硬校验

`kb-promote` 只接受 latest verdict = confirmed 的假设；晋升文本
（含 title/source note）出现案件内任何原始目标串（fact target /
hypothesis scope / intent target 中抽取的主机标识）直接拒绝并指出
泄漏串。新条目固定 `trust: unverified`——信任由后续验证提升。
跨案件召回的完整脱敏导入（显式只读引入历史 Engagement）在 P4
多宿主验收前保持延后。

## 影响

- 长上下文压缩后可用 `recall` + `doc` 恢复工作记忆，无需重读全历史
- 检索质量评估（recall@k、重复尝试率）待 P4 靶场对比时补测
- 语义向量检索仍不引入；BM25+模糊+图召回不足时再评估 FastEmbed
