# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **T-051 P4 多宿主验收（P4 收官）**：
  - omp 宿主真实施役闭环（`workspace/t051/omp/case`）：pack → claim →
    omp 无头 Worker（brute 弱口令探测，25 请求 45 artifacts）→ ingest →
    verify-pack → 无头 Verifier（SHA-256 逐条比对 + 独立重放）→ 裁决
    confirmed（verifier_run 溯源）→ `prism.py verify` 门禁 PASS。
    Worker deviations 纪律与 Verifier 独立性（凭据失效不迁就、改用字典内
    候选独立复现）均实测验证。
  - `pack` / `verify-pack` v2 化（`scripts/prism/packets.py` 切换到
    `state.replay`；v1 案件先 `migrate`），消除 T-050 记录的改进项
  - **`prism.py verify <case>` 报告门禁正式命令**（v2 口径：confirmed
    三角色闭环 + verifier_run 溯源 + 无未闭环 provisional），T-050 的
    手工 gate_check 下沉为 Core
  - `scripts/pack_skill.py` 打包器：`dist/sapper-skill/`（32 文件）+
    五重结构校验（frontmatter=目录名 / 资源引用 / Core 无宿主专有名 /
    命令面 18 命令 / schema 同步）+ 临时目录干净冒烟
  - yakit / dudesuite MCP 实测：yakit connected（55 工具，只读调用成功）；
    dudesuite 单实例互斥被 dsh 宿主持有致 omp 无法挂载（约束已写入
    omp/dsh adapter 文档）；dsh 宿主 MCP 生态运行中
  - `docs/eval/T-051-dsh-acceptance.md`：dsh 验收文档（自动验证 8 项 +
    交互实测协议 D1–D9 待用户回填；发现 preset 未挂载）
  - 测试基线 217 → **230**（test_walking_skeleton 全链 v2 化 + verify 门禁
    用例）；230 passed，ruff 全绿
  - `project-state.yml`：P4-complete / delivered

- **实时面板服务与双语界面（ADR-0013，用户 P4 增量需求）**：
  - `prism.py serve`（新增 `scripts/prism/live.py`）：本地 HTTP 托管
    dashboard 产物 + `/api/state` `/api/version` `/api/live`；监听线程
    轮询账本指纹，变化自动重渲染；交互式启动询问是否开启实时，运行中
    可随时暂停/恢复（页内按钮或 POST /api/live），Ctrl-C 退出
  - `dashboard.html` / `attack-graph.html` 重设计：工业实用浅色主题
    （暖纸白 #f2f0ea / 墨色 #211e19 / 信号橙红 #c2451e 强调）、本地字体栈
    （Bahnschrift + 微软雅黑 / Cascadia Mono）、蓝图网格底纹 + 四角标尺框、
    错峰入场序列与 prefers-reduced-motion 降级、空态折叠与悬停反馈
  - 双语：data-zh/data-en 中英切换（默认中文）；board.md / mermaid 标签
    中英并列；状态标签中文优先（已确认/已证伪/执行中…）
  - 离线退化：file:// 打开自动停止轮询、显示"离线快照"，保持单文件
    离线语义（测试锁定无任何 http(s) 外链）
  - `tests/test_live.py` 11 项（API/实时监听/开关/双语/路径逃逸防护）；
    测试增至 228 项
- **T-050 P4 实战评测（DVWA 对比基线）**：协议 `docs/eval/T-050-protocol.md`
  （关闭 Q5/Q7）+ 报告 `docs/eval/T-050-report.md`。三条验收全部达成：
  有效确认 4=4、误报 2→0（Scanner 假告警 Verifier 分诊 killed）、
  重复调用率 16.7%→9.1%。v2 控制面端到端实测：claim/lease、幂等 ingest
  （重放账本逐字节不变）、state 回放、recall 可解释召回、render 四件套、
  报告门禁 PASS（含 verifier_run 溯源校验）。评测数据本地保留
  （workspace/t050/，不入 git）
- **命名决策（ADR-0012）**：Skill 最终名 `sapper-skill`（用户决策 2026-11-04，
  open-questions Q8 关闭）。frontmatter `name`、README / docs / NEW_SESSION_PROMPT /
  project-state.yml 同步改名；开发目录暂为 `prism-skill/`，最终打包目录
  `sapper-skill/`；内部包 `scripts/prism/` 保持实现代号不变。授权守卫测试
  name 断言与 description 不虚标关键词（开发中|基线|建设|评测）同步更新
- 项目初始化
  - 目录骨架
  - Skill 入口
  - 参考资料快照
  - Spec / Design / Engineering / Plans / State / ADR 文档体系
  - 新会话启动提示词
  - Skill 结构校验通过
- 版本管理：git 仓库初始化（main 分支），全量基线提交
- v1 账本基线（T-010）：`scripts/case_ledger.py`（迁移期兼容，行为冻结）
- 回归测试套件（T-010）：77 项 pytest，覆盖哈希/路径/引用校验、报告门禁、
  尾行修复、原子报告、黑板折叠与授权纪律机读门禁
- v1 冻结 fixture（T-010）：`tests/fixtures/v1/`，覆盖全部记录类型与裁决状态
- 依赖锁定（T-011）：`scripts/pyproject.toml` + `requirements.lock` + `requirements-dev.txt`，
  12 个主依赖与开发依赖全量锁定并验证可复现（ADR-0005）
- 依赖冒烟测试（T-011）：`tests/test_dependency_lock.py`，导入与版本一致性校验
- 测试配置（T-011）：根 `pytest.ini`，`tests/README.md` 结构说明
- prism v2 控制面骨架（T-020）：`scripts/prism/`（models / packets / cli）+ `scripts/prism.py`，
  提供 `schema / pack / verify-pack / hosts` 命令（单目标顺序闭环）
- 协议模型与 schema 导出（T-020）：Pydantic WorkerResult / VerifierResult / Finding / FinalReport，
  `references/result-schema.{json,md}` 自动生成并带漂移守卫测试（P1 骨架版，冻结属 T-030）
- playbooks（T-020）：focused / reason / explore / verify / report 五个协议文档
- Walking Skeleton 测试（T-020）：模型契约 + 单目标闭环 E2E + schema 漂移守卫，共 28 项
- Host adapter 体系（T-021）：`references/hosts/`（契约 + 注册表 + generic / omp /
  workbuddy / dsh 四个 adapter，ADR-0006）；SKILL.md hosts 路由；`prism.py hosts` 命令
- 宿主实测（T-021）：WorkBuddy 原生子 Agent 协议闭环（Worker + 独立 Verifier，
  SHA-256 独立比对，报告门禁先拒后放）；omp 无头 CLI 冒烟（v18.15.0，PowerShell）
- Host adapter 契约测试（T-021）：`tests/test_host_adapters.py`，注册表完整性 +
  契约小节 + Core 纯净性词边界扫描 + 实测记录诚实性，共 8 项
- v2 状态模型（T-030）：`scripts/prism/models.py` 冻结 7 类账本记录
  （fact / intent / run / approval / hypothesis / evidence / verdict），
  Intent/Run 为追加事件模型；approval_key 派生式生成（ADR-0007）
- 状态回放（T-030）：`scripts/prism/state.py` + `prism.py state [--json]`，
  确定性回放、引用完整性校验、findings 投影
- v1→v2 迁移（T-030）：`prism.py migrate`，回放等价校验 + artifacts 复制，
  冻结 fixture 实测通过；schema 导出扩展至记录模型并重生成 references 文档
- 并发入库与恢复（T-031）：`prism.py claim / ingest / recover / repair`——
  FileLock + 锁内重放 + fsync 追加；幂等键记录于 run 完成事件，同键重放
  账本不变（ADR-0008）；双进程并发实测不丢记录
- 工具输出消化（T-032）：`prism.py harvest` 五类 parser registry
  （nmap-xml / masscan-json / httpx-jsonl / nuclei-jsonl / generic-json）+
  `scripts/prism/identity.py` 资产归一化（IP/IDNA/URL/服务键）与跨工具
  确定性去重（别名归并、模糊相似审查队列、秘密脱敏、digest 硬上限，
  ADR-0009）；P2 阶段完成
- Recall / KB（T-040）：`prism.py recall`（BM25+jieba+RapidFuzz+一跳图扩展，
  可解释 breakdown，失败路径并召）、`prism.py doc`（按需读详情）、
  `kb-list / kb-read / kb-promote`（离线 KB 信任级别、过期警告、
  confirmed + 去目标化晋升门禁，ADR-0010）
- 可视化（T-041）：`prism.py render` 生成 board.md / dashboard.html /
  attack-graph.html / attack-graph.mmd——静态资源全内联（无 CDN）、
  回放派生保证图与账本一致、派生物可删除重建（ADR-0011）；P3 阶段完成

### Changed

- **[安全]** 授权规则纠正（T-010）：根 `SKILL.md` 从“项目骨架说明”演进为正式
  Skill 入口；旧版反向授权表述（“超出范围或存在歧义的操作直接做”）替换为
  “一次声明、战役常驻、高影响动作组审批、越界与歧义默认不执行”（ADR-0004）
