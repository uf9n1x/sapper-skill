# 接口与协议约定

> 状态：**Result 包与 v2 账本记录 schema 已冻结并导出（T-030，ADR-0007）**。
> 所有 schema 以 `scripts/prism/models.py` 的 Pydantic 导出为准，本文不重复字段细节，避免文档漂移。

## 1. CLI 接口原则

- 唯一入口：`scripts/prism.py`
- 输出：`--json` 机器可读，默认 Rich 人类可读
- 退出码：稳定且可测试
- 诊断：写 stderr
- 结果：写 stdout

## 2. 核心命令面（规划）

```text
prism.py init / doctor / capabilities / context / handoff / next / paths
prism.py pack / verify-pack / claim / approve / ingest / harvest / diff
prism.py recall / doc / kb-list / kb-read / kb-promote
prism.py scope-check / verify / render / report / migrate
```

| 命令 | 用途 | 状态 |
|---|---|---|
| `init` | 初始化 engagement | 规划中 |
| `doctor` | 依赖与存储诊断 | 规划中 |
| `capabilities` | 工具/Skill/MCP 能力矩阵 | 规划中 |
| `context` | 当前黑板与状态 | 规划中 |
| `handoff` | 会话恢复摘要 | 规划中 |
| `next` | 候选 Intent 排序 | 规划中 |
| `paths` | 攻击路径与缺失边 | 规划中 |
| `pack` | Worker 上下文包 | 规划中 |
| `verify-pack` | Verifier 上下文包 | 规划中 |
| `claim` | 认领 Intent，创建 Run | ✅ 首版完成（T-031，含 Lease） |
| `approve` | 记录高影响审批 | 规划中（approval 记录模型已冻结，T-030） |
| `ingest` | 幂等入库结果 | ✅ 首版完成（T-031，FileLock + fsync + 幂等键） |
| `harvest` | 工具输出解析 | ✅ 首版完成（T-032：五类 parser registry + 增量 digest + 归一化去重） |
| `diff` | 状态变化增量 | 规划中 |
| `recall` | 混合经验召回 | ✅ 首版完成（T-040：BM25+模糊+图扩展，可解释，失败路径并召） |
| `doc` | 按需读取详情 | ✅ 首版完成（T-040：artifact 内容或记录 JSON） |
| `kb-list` | 离线 KB 列表 | ✅ 首版完成（T-040：来源/信任/过期警告） |
| `kb-read` | KB 条目详情 | ✅ 首版完成（T-040：含强制警告） |
| `kb-promote` | 经验晋升门禁 | ✅ 首版完成（T-040：confirmed + 去目标化硬校验） |
| `index-inputs` | 输入清单索引 | 规划中 |
| `scope-check` | 授权预检 | 规划中 |
| `verify` | 账本一致性校验 | 规划中 |
| `render` | 生成 board/dashboard/graph | ✅ 首版完成（T-041：四产物离线单文件，回放派生，可重建） |
| `report` | 生成报告 | 规划中 |
| `migrate` | schema 迁移 | ✅ 首版完成（T-030：v1→v2 + 回放等价校验） |
| `state` | 回放派生状态 | ✅ 首版完成（T-030） |

## 3. Worker Result 包（方向）

```json
{
  "schema_version": 2,
  "run_id": "R...",
  "intent_id": "I...",
  "idempotency_key": "由主 Agent 生成并随任务下发",
  "status": "done | blocked | failed | needs_verification",
  "summary": "本次增量结果",
  "facts": [],
  "hypotheses": [],
  "evidence": [],
  "suggested_verdicts": [],
  "next_intents": [],
  "deviations": [],
  "cleanup": [],
  "blockers": []
}
```

约束：

- Worker 不直接修改 ledger
- `suggested_verdicts` 不直接成为 confirmed
- 同一 `idempotency_key` 重试返回原结果，不重复入账
- schema 以 Pydantic 导出为准

## 4. 审批键

```text
approval_key = action_class + target_scope + effect
```

- 同一战役、同一动作类别和范围只确认一次
- `scope-check` 返回 `allow / confirm / deny`
- 主 Agent 不得把 `confirm` 当 `allow`

## 5. 存储接口

| 层 | 职责 |
|---|---|
| `ledger.jsonl` | 唯一权威账本，追加式 |
| `snapshots/` | 可重建状态快照 |
| `index.sqlite` | 派生查询/召回缓存，可删除重建 |
| `artifacts/` | 原始证据、日志、长文档 |
| `results/` | 各 Run 原始结构化返回 |
| `packets/` | 自动装配的角色上下文包 |
| `reports/` | 生成报告 |

## 6. 兼容性

- 通用 Core 不出现宿主专有工具名
- 宿主差异只放 `references/hosts/`
- `case_ledger.py` 作为迁移期兼容 wrapper，最终可移除
