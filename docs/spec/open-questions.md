# 待确认事项（Open Questions）

> 本文件只记录**尚未决定**的问题。已决定的内容请写入 `requirements.md` 或 `design/technical-design.md`。

## Q1. 首批宿主优先级

**问题**：首批要正式适配哪些宿主？

- 候选：Codex、DSH、WorkBuddy、其他
- 当前状态：**TBD**
- 影响：决定 host adapter 的开发顺序和测试矩阵

## Q2. Python 依赖锁定

**问题**：最终锁定的主依赖版本与可选 extras 清单？

- 当前状态：**已锁定（T-011，见 ADR-0005 与 `scripts/requirements.lock`）**
- 遗留：离线分发/私有权验签方案在 P4 打包时再定
- 影响：~~决定 `requirements.lock` 和离线安装方案~~ 已落地

## Q3. 首个实战靶场

**问题**：P1 / P2 阶段用什么靶场做垂直切片验证？

- 当前状态：**已确认：DVWA（T-011，用户决策 2026-11-03）**
- 约束：仅靶场自身部署可用容器，Skill 运行时不引入 Docker（与"非目标"不冲突）
- 影响：~~决定第一个端到端验收场景~~ P1 闭环与 P2 并发/恢复验收均以 DVWA 为默认场景

## Q4. Worker Result Schema 冻结版

**问题**：Result 包的完整字段、必填/可选、版本迁移策略？

- 当前状态：**已关闭（T-030，2026-11-03）**——14 个顶层字段随
  `scripts/prism/models.py::WorkerResult` 冻结并导出（ADR-0007）；
  后续变更走"改模型 → 重生成 → 漂移守卫测试通过"流程
- 影响：ingest（T-031）与 host adapter 的稳定性基准已确定

## Q5. 量化验收目标

**问题**：有效确认数、误报率、token 费用等指标的具体阈值？

- 当前状态：**已关闭（T-050，2026-11-04）**——首轮阈值见
  `docs/eval/T-050-protocol.md` §4：有效确认数 v2 ≥ 基线；误报数 v2 ≤ 基线且
  合成假告警不得在 v2 confirmed；重复调用率 v2 < 基线。后续评测按同口径追加
- 影响：~~决定是否进入下一阶段~~ 已落地为首轮对比评测口径

## Q6. 外部 Skill / MCP 清单

**问题**：首批需要显式支持哪些外部 Skill 或 MCP 工具？

- 当前状态：**TBD**
- 影响：决定 `tools.yml` 和 capability matrix 的初始内容

## Q7. 评测回放集来源

**问题**：授权实验回放集从哪里来，如何脱敏？

- 当前状态：**已关闭（T-050，2026-11-04）**——首个回放集为本地 DVWA 对比战役
  （`workspace/t050/`，协议见 `docs/eval/T-050-protocol.md`）；靶场为隔离实验
  环境，会话 cookie 等凭据不入 git
- 影响：~~决定 P4 的对比评测可信度~~ 已落地

## Q8. 最终打包目录名与 Skill name

**问题**：P4 多宿主验收时，Skill 打包目录名与 frontmatter `name` 是保持 `prism-skill` 还是改为 `pentest-redteam`（升级方案 §14 要求目录名与 name 一致为 pentest-redteam，便于直接替换旧 Skill）？

- 当前状态：**已关闭（用户决策 2026-11-04，ADR-0012）**——最终名为 **`sapper-skill`**（目录名与 name 一致），不改回 `pentest-redteam`；开发目录暂为 `prism-skill/`，打包产物用 `sapper-skill/`
- 影响：~~决定 P4 打包配置、触发评测与旧 Skill 替换路径~~ 已落地；本项目为独立新 Skill，不做旧 Skill 原地替换
