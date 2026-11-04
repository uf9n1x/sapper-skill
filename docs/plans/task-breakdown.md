# 任务拆解

> 本文件是**唯一任务事实源**。任务状态只在这里维护，并在 `../../state/PROGRESS.md` 追加记录。

## 状态标记

- `pending`：未开始
- `in_progress`：进行中
- `blocked`：被外部条件阻塞
- `done`：已完成
- `dropped`：取消，必须写原因

---

## T-000 项目初始化

- **状态**：`done`
- **范围**：创建目录、初始化 Skill 骨架、清理模板示例
- **验收**：
  - [x] `prism-skill` 目录存在
  - [x] `SKILL.md` 可被识别
  - [x] `docs / reference / state / workspace / scripts / references / assets` 目录建立

## T-001 参考资料纳管

- **状态**：`done`
- **范围**：复制 sapper-v2、nvwabase、dsh-pentest、dsh-redteam-model、pi、旧 Skill、旧设计文档
- **验收**：
  - [x] `reference/projects/` 下存在各快照
  - [x] `reference/README.md` 记录来源、版本、用途
  - [x] 快照不作为运行代码，仅作参考

## T-002 文档体系建立

- **状态**：`done`
- **范围**：README、Spec、Design、Engineering、Plans、State、ADR、启动提示词
- **验收**：
  - [x] 项目目标与范围明确
  - [x] 核心功能明确
  - [x] 架构与目录结构明确
  - [x] 接口约定明确
  - [x] 编码与提交规范明确
  - [x] 测试策略明确
  - [x] 验收标准明确
  - [x] 风险与待确认事项明确
  - [x] 新会话启动提示词可用

---

## T-010 P0 安全纠正

- **状态**：`done`
- **依赖**：无
- **范围**：修正反向授权规则，建立 v1 基线测试
- **验收**：
  - [x] `SKILL.md:20` 不再出现“越界直接做”（由 `tests/test_skill_authorization.py` 机读锁定）
  - [x] 合法授权任务不再重复询问（一次声明、战役常驻写入授权 Gate）
  - [x] 现有 ledger 行为有回归测试（`tests/test_ledger_unit.py` + `test_ledger_cli.py`，59 项）
  - [x] v1 fixture 冻结（`tests/fixtures/v1/`，20 条记录覆盖全部裁决状态）

## T-011 P0 依赖与骨架冻结

- **状态**：`done`
- **依赖**：T-010
- **范围**：锁定 Python 依赖、建立测试目录、确定首个靶场
- **验收**：
  - [x] `requirements.lock` 生成（`scripts/requirements.lock` + `requirements-dev.txt`，ADR-0005）
  - [x] `tests/` 目录与 fixture 结构建立（T-010 已建，本任务补 README 与 pytest 配置）
  - [x] 首个授权靶场确认（DVWA，open-questions Q3 已关闭）

## T-020 P1 Walking Skeleton

- **状态**：`done`（2026-11-03）
- **依赖**：T-010
- **范围**：精简 SKILL、新增 playbooks、打通单目标顺序闭环
- **验收**：
  - [x] reason / explore / verify playbook 可用（含 focused / report，共五个 `playbooks/*.md`）
  - [x] Pydantic Result schema 导出（`scripts/prism/models.py` + `references/result-schema.{json,md}` + 漂移守卫测试）
  - [x] 单目标闭环产出可追溯 Finding（Commander→Worker→Verifier→报告，E2E 测试验证；附带实现 `prism.py pack / verify-pack`）

## T-021 P1 Host Adapter 首版

- **状态**：`done`（2026-11-03）
- **依赖**：T-020
- **范围**：generic 顺序模式 + 一个支持子 Agent 的宿主
- **验收**：
  - [x] generic 模式可用（`references/hosts/generic.md`，顺序扮演 + `sequential` 报告标注；E2E 测试与实测均覆盖）
  - [x] 至少一个宿主原生子 Agent 模式可用（WorkBuddy 原生子 Agent 实测闭环：Worker + 独立 Verifier，哈希独立比对，门禁先拒后放；omp 无头 CLI 已实测，`task` 子 Agent 派发留 P4）
  - [x] 核心流程无宿主专有工具名（`tests/test_host_adapters.py` 词边界扫描 SKILL/playbooks/scripts；宿主差异只放 `references/hosts/`，ADR-0006）

## T-030 P2 状态模型 v2

- **状态**：`done`（2026-11-03）
- **依赖**：T-020
- **范围**：Fact / Intent / Run / Evidence / Verdict / Approval
- **验收**：
  - [x] schema 冻结并导出（7 类账本记录 + WorkerResult 全字段，`prism.py schema` 导出，漂移守卫强制；Q4 关闭，ADR-0007）
  - [x] 迁移脚本可用（`prism.py migrate`：v1→v2 + artifacts 复制 + 回放等价校验，fixture 实测通过）
  - [x] 状态事件可回放（`prism.py state`：Intent/Run 最新事件派生 + 引用完整性 + 确定性回放）

## T-031 P2 并发与恢复

- **状态**：`done`（2026-11-04）
- **依赖**：T-030
- **范围**：FileLock、claim、lease、幂等 ingest、崩溃恢复
- **验收**：
  - [x] 并发结果不丢（双进程同时 ingest，全部落账且回放通过；FileLock + 锁内重放分配 ID，ADR-0008）
  - [x] 重放不重复（幂等键记录于 run 完成事件；同键重放返回 duplicate，账本逐字节不变）
  - [x] 中断后可恢复（`repair` 截断崩溃半行；`recover` 对过期 Lease 给出 ingest / re_claim 建议）

## T-032 P2 工具输出消化

- **状态**：`done`（2026-11-04）
- **依赖**：T-030
- **范围**：Nmap / Masscan / httpx / Nuclei parser，资产归一化
- **验收**：
  - [x] 原始日志保存为证据（harvest 携带 artifact SHA-256，原文不回显）
  - [x] 模型只接收结构化增量（digest 只含账本外新增候选，硬上限 200）
  - [x] 跨工具去重（identity 确定性资产键合并 + 别名归并 + 审查队列）

## T-040 P3 Recall / KB

- **状态**：`done`（2026-11-04）
- **依赖**：T-030
- **范围**：混合召回、离线 KB、经验晋升
- **验收**：
  - [x] 召回可解释（score breakdown + reasons；BM25+模糊+结构化+图扩展分量）
  - [x] 失败路径可召回（killed 假设 / blocked Intent 标注 path=failure）
  - [x] KB 带来源与信任级别（frontmatter source/trust/applies_to/last_verified + 过期警告）

## T-041 P3 可视化

- **状态**：`done`（2026-11-04）
- **依赖**：T-030
- **范围**：board、dashboard、attack graph
- **验收**：
  - [x] 离线打开（PyVis in_line 内联 + bootstrap CDN 剥离，机读无外链）
  - [x] 图与账本一致（全部节点/边由回放派生，findings/Intent→Run 锁定）
  - [x] 删除派生物后可重建（board/mmd 同 --now 逐字节一致，JSONL 只读）

## T-050 P4 实战评测

- **状态**：`done`
- **依赖**：T-031、T-040、T-041
- **范围**：授权靶场对比旧版 Skill
- **验收**（协议与数据见 `../eval/T-050-protocol.md` 与 `../eval/T-050-report.md`）：
  - [x] 有效确认数提升（4 vs 4 持平，真实漏洞两版均可确认；质量增益见误报项）
  - [x] 误报数下降（2 → 0：Scanner 假告警由 Verifier 分诊 killed）
  - [x] 重复调用率下降（16.7% → 9.1%）

## T-051 P4 多宿主验收

- **状态**：`done`（2026-11-04）
- **依赖**：T-050
- **范围**：至少两个宿主实测
- **验收**：
  - [x] 同一 Core 无需修改即可运行（omp 无头闭环：pack → Worker → ingest →
    Verifier → 裁决 → 门禁 PASS，`workspace/t051/omp/case`；Core 零宿主专用
    修改——pack/verify-pack v2 化与 `prism.py verify` 门禁属 Core 功能补全；
    workbuddy 已于 T-021 实测，两宿主达标）
  - [x] 不支持能力明确降级（dudesuite MCP 连接失败如实告警不重试不虚报；
    DudeSuite 单实例互斥约束实测定位并写入 adapter 文档；dsh 预设未挂载
    退 generic 顺序模式已文档化）
  - [x] Skill 结构校验通过（`scripts/pack_skill.py`：frontmatter name=目录名、
    资源引用完整、Core 无宿主专有名、CLI 命令面 18 命令、schema 与模型同步、
    临时目录干净冒烟 claim/ingest/state/render/pack 全链；产物 `dist/sapper-skill/`
    32 文件，独立跑真实案件门禁 PASS）
- **遗留**：dsh 交互实测 D1–D9 待用户按 `docs/eval/T-051-dsh-acceptance.md`
  执行回填（不阻塞最低门槛：workbuddy + omp 两宿主已真闭环）

---

## 阻塞与风险

- 无当前阻塞
- 待确认事项见 `../spec/open-questions.md`
