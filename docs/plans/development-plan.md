# 开发计划

> 本文件只回答**“什么时候做什么”**。任务细节见 `task-breakdown.md`，需求见 `../spec/requirements.md`。

## 总体节奏

```text
P0 基线与安全纠正
  → P1 宿主原生 Walking Skeleton
  → P2 v2 实战状态与安全并发
  → P3 Recall / KB / 输入包 / 可视化
  → P4 实战质量与多宿主验收
```

## P0：基线与安全纠正

**目标**：把现有 Skill 的正确行为锁住，修正授权反向规则，建立可回归的基线。

- 修正 `SKILL.md:20` 的反向授权表述
- 为现有 ledger 的哈希、路径、报告门禁、断尾修复和黑板建立测试
- 冻结 v1 fixture，准备 v1→v2 迁移
- 补齐 `agent_created` 和通用 frontmatter
- 从实际 SKILL 重新生成 README

**出口**：

- 现有正确行为有回归保障
- 合法授权任务不再被重复询问
- 越界 / 高影响边界可机读

## P1：宿主原生 Walking Skeleton

**目标**：打通一次最小闭环，验证架构方向。

- 精简 SKILL，新增 reason / explore / verify playbooks
- 以 Pydantic 定义 Result 并自动导出 JSON Schema
- 用现有账本完成单目标顺序闭环：主 Agent → Worker → Verifier → 报告
- 实现 `pack / verify-pack`
- 在一个有子 Agent 的宿主和 generic 顺序模式各跑一次相同授权实验

**出口**：

- 无独立 Runtime、无 Docker、无 hook
- 能产出可追溯 Finding
- 核心流程无宿主专有工具名

## P2：v2 实战状态与安全并发

**目标**：让状态模型能承载真实多目标、多 Worker、可恢复的实战。

- 增加 Fact / Intent / Run、三层文档、claim / lease、结果 ingest、FileLock 和幂等
- 增加 snapshot、可重建 SQLite 索引、故障注入和确定性 `next / paths / diff`
- 实现工具能力矩阵、首批 `harvest` parser、资产归一化和跨工具去重
- 完成 v1 迁移、崩溃恢复、重复返回、多 Worker 并发测试
- 增加 evidence provenance、副作用重放级别、Cleanup 机器状态和高影响 approval key

**出口**：

- 多个 Worker 不丢更新、不重复入账
- 中断后可解释恢复
- Verifier 不同意则不会 confirmed

## P3：Recall / KB / 输入包 / 最小面板

**目标**：让长任务能“记得住、找得到、看得清”。

- 实现 BM25 + 模糊匹配 + 图扩展的 recall / doc
- 实现带来源和信任级别的离线 KB
- 实现 targets / docs / tools / skills 清单处理
- 自动生成 board、Finding / Evidence 报告和可筛选的 PyVis 离线交互 dashboard / attack graph
- 加入跨资产同族经验召回、失败路径召回与停滞换角度策略

**出口**：

- 长上下文压缩后无需重读全历史
- 用户随时能看懂当前执行状态和攻击链

## P4：实战质量与多宿主验收

**目标**：用真实授权环境证明“更强”，而不是“功能更多”。

- 审核 techniques 的适用条件、风险、证据和来源
- 完成 Codex、DSH adapter 的实测文档；不支持能力明确降级
- 在授权本地靶场 / 模拟多目标环境对比旧版 Skill
- 回放典型成功、误报、停滞、恢复和提示注入案例
- 运行 Skill 结构校验与 `package_skill.py`
- 检查资源引用、渐进披露、私有分发包和全新环境安装

**出口**：

- 同一 Core 在两个宿主无需修改即可运行
- 结果质量、恢复、证据和成本指标可复现

## 当前状态

- **P0 尚未开始**
- 项目已完成初始化、参考资料纳管和文档建设
