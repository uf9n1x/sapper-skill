# sapper-skill

> Skill 最终名：**sapper-skill**（用户决策 2026-11-04，ADR-0012；开发目录暂为 `prism-skill/`，最终打包目录为 `sapper-skill/`）。
>
> 状态：**P3 全部完成（T-040 Recall/KB + T-041 可视化）。可解释混合召回、失败路径并召、离线 KB 与晋升门禁、四产物离线面板与攻击图（ADR-0010/0011），217 项测试。当前阶段 P4 实战评测与多宿主验收。**
>
> 目标：基于既有 `pentest-redteam` Skill 与 `sapper-v2` 核心思想，做一个更贴近实战、可长期维护的授权渗透测试 Skill 项目。

## 定位

- 形态：**通用 Agent Skill + 宿主原生主/子 Agent + Python 确定性控制面**
- 不做：独立 Agent Runtime、Docker 服务、常驻进程、外部数据库
- 吸收：`sapper-v2` 的事实/意图工作记忆、按需召回、探索/验证分工、时间盒与知识复用
- 保留：原 Skill 的账本纪律、证据哈希、原子报告与假设驱动状态机

## 当前阶段

- P0 全部完成：
  - `scripts/case_ledger.py`：v1 账本基线（迁移期兼容，行为冻结）
  - `scripts/pyproject.toml` + `requirements.lock` + `requirements-dev.txt`：依赖全量锁定（ADR-0005）
  - `tests/`：83 项回归测试（账本行为 + 授权纪律机读门禁 + fixture 守卫 + 依赖冒烟）
  - `tests/fixtures/v1/`：冻结 fixture，供 v1→v2 迁移使用
  - 根 `SKILL.md` 已演进为正式 Skill 入口，授权 Gate 为修正版语义（ADR-0004）
  - 首个授权靶场：DVWA（open-questions Q3 已关闭）
- T-020（P1 Walking Skeleton）已完成：
  - `scripts/prism/`：v2 控制面骨架（协议模型 / 角色装配 / Typer CLI）+ `scripts/prism.py` 入口
  - `playbooks/`：focused / reason / explore / verify / report 五个协议文档
  - `references/result-schema.{json,md}`：从 Pydantic 模型自动生成，带漂移守卫测试
  - `prism.py assemble / loop / report / pack / verify-pack / schema`：单目标顺序闭环命令面
  - 测试增至 113 项（新增模型契约 + 闭环 E2E + schema 漂移守卫）
- T-021（P1 Host Adapter 首版）已完成：
  - `references/hosts/`：adapter 契约 + 注册表 + generic / omp / workbuddy / dsh 四个 adapter（ADR-0006）
  - WorkBuddy 原生子 Agent 实测闭环（Worker + 独立 Verifier，SHA-256 独立比对，门禁先拒后放）
  - omp 无头 CLI 实测（v18.15.0）；dsh 文档就绪、实测按设计排期 P4
  - Core 纯净性机读：宿主专有名零出现（词边界扫描）；`prism.py hosts` 命令
  - 测试增至 121 项
- T-030（P2 状态模型 v2）已完成：
  - v2 账本记录模型冻结：fact / intent / run / approval + H/E/V 扩展（ADR-0007）
  - Intent/Run 事件化：追加事件派生状态，`prism.py state` 回放
  - `prism.py migrate`：v1→v2 迁移 + 回放等价校验
  - WorkerResult 全字段与 Fact kind 枚举冻结（open-questions Q4 关闭）
  - 测试增至 151 项
- T-031（P2 并发与恢复）已完成：
  - `prism.py claim / ingest / recover / repair`：FileLock + 锁内重放 + fsync 追加（ADR-0008）
  - 幂等键记录于 run 完成事件，同键重放账本逐字节不变；双进程并发实测不丢记录
  - 过期 Lease 恢复建议（结果包落盘 → ingest；未落盘 → re_claim）；崩溃半行 `repair` 截断
  - 测试增至 161 项
- T-032（P2 工具输出消化）已完成：
  - `prism.py harvest`：五类 parser（nmap-xml / masscan-json / httpx-jsonl / nuclei-jsonl / generic-json，registry 可扩展）
  - `scripts/prism/identity.py`：IP/IDNA 域名/URL 归一化 + 确定性资产键合并 + 模糊相似审查队列（ADR-0009）
  - 原始日志存证（SHA-256 入 digest）、秘密默认脱敏、扫描器告警永不自动 confirmed、digest 硬上限
  - 测试增至 186 项
- **P2 全部完成**
- T-040（P3 Recall / KB）已完成：
  - `prism.py recall`：BM25+jieba+RapidFuzz+一跳图扩展，breakdown 可解释；
    killed/blocked 失败路径并召（path=failure）；`prism.py doc` 按需读详情
  - `kb-list / kb-read / kb-promote`：离线 KB（来源/信任/过期警告）+
    confirmed + 去目标化晋升门禁，新条目 trust=unverified（ADR-0010）
  - `kb/`：离线知识库目录（条目格式与纪律见 kb/README.md）
  - 测试增至 205 项
- T-041（P3 可视化）已完成：
  - `prism.py render`：board.md（NOW/Runs/Intents/Findings/Cleanup）+
    dashboard.html（内联过滤）+ attack-graph.html（PyVis 离线交互图）+
    attack-graph.mmd（Mermaid）；全部静态资源内联、回放派生、可删除
    重建（ADR-0011）
  - 测试增至 217 项
- **P3 全部完成**；下一阶段：P4 实战评测（T-050，DVWA 对比、多宿主实测、打包）

## 文档入口

| 主题 | 路径 |
|---|---|
| 文档总览与维护规则 | `docs/README.md` |
| 需求规格 | `docs/spec/requirements.md` |
| 验收标准 | `docs/spec/acceptance.md` |
| 待确认事项 | `docs/spec/open-questions.md` |
| 技术设计总览 | `docs/design/technical-design.md` |
| 接口与协议 | `docs/design/interfaces.md` |
| 编码与提交规范 | `docs/engineering/coding-standards.md` |
| 测试策略 | `docs/engineering/testing.md` |
| 开发计划 | `docs/plans/development-plan.md` |
| 任务拆解 | `docs/plans/task-breakdown.md` |
| 参考资料索引 | `reference/README.md` |
| 当前状态 | `state/TASKS.md`、`state/PROGRESS.md` |
| 变更记录 | `state/CHANGELOG.md` |
| 决策索引 | `docs/decisions/README.md` |
| 机器可读状态 | `project-state.yml` |
| 新会话启动提示词 | `NEW_SESSION_PROMPT.md` |

## 目录结构

```text
sapper-skill/                # 最终打包目录名（当前开发目录为 prism-skill/）
  SKILL.md                  # Skill 入口（授权 Gate + 主循环/playbook 路由 + prism.py 命令面）
  README.md                 # 项目总览
  NEW_SESSION_PROMPT.md     # 新会话冷启动提示词
  docs/
    README.md               # 文档地图与维护规则
    spec/                   # 需求、验收、待确认
    design/                 # 技术设计、接口
    engineering/            # 编码、提交、测试规范
    plans/                  # 开发计划、任务拆解
    decisions/              # ADR 决策记录
  reference/
    README.md               # 参考项目索引
    projects/               # 各参考项目快照（只读）
  scripts/
    case_ledger.py          # v1 账本基线（迁移期兼容）
    prism.py                # v2 控制面 CLI 入口
    prism/                  # v2 控制面包（models / packets / cli）
    pyproject.toml          # 依赖声明（prism 包）
    requirements.lock       # 主依赖锁定（uv pip compile 生成，禁手改）
    requirements-dev.txt    # 开发依赖锁定（同上）
  playbooks/                # 角色协议文档（focused / reason / explore / verify / report）
  state/
    TASKS.md                # 当前任务与状态
    PROGRESS.md             # 追加式进度日志
    CHANGELOG.md            # 版本变更记录
  tests/                    # 回归测试与冻结 fixture
  workspace/                # 预留：未来本地开发与测试工作区
  references/               # Skill 渐进披露文档（result-schema 自动生成；hosts/ 宿主适配器）
  assets/                   # 预留：模板与面板资源
```

## 维护原则

1. **Spec 先行**：任何实现前，先在 `docs/spec/requirements.md` 明确目标、边界与验收。
2. **单一事实源**：需求只看 `spec`，设计只看 `design`，任务只看 `state/TASKS.md`，进度只看 `state/PROGRESS.md`。
3. **可恢复**：新会话必须先读 `NEW_SESSION_PROMPT.md` 指定的文档集合，再核对当前任务状态。
4. **不臆造**：未确认的信息一律标记 `TBD` 或放入 `open-questions.md`。
5. **变更留痕**：重要决策写 ADR，任务状态更新必须同步 `PROGRESS.md`。
