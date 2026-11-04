# 进度日志

> **追加式记录，禁止覆盖或改写历史条目。** 每完成一个任务或发生重要状态变化，就在文件末尾追加一条。

---

## 2026-11-03

- 完成项目初始化
  - 建立目录骨架
  - 清理初始化模板示例
  - 保留 `SKILL.md` 作为项目入口
- 完成参考资料纳管
  - 复制 sapper-v2 / nvwabase / dsh-pentest / dsh-redteam-model / pi / 旧 Skill / 旧设计文档
  - 记录各快照 commit 与用途
- 完成文档体系
  - README / Spec / Design / Engineering / Plans / State / ADR / 启动提示词
- 当前状态
  - 项目处于初始化完成、P0 未开始
  - 未实现任何功能代码
  - 下一个任务：T-010 P0 安全纠正
- 初始化验证
  - `quick_validate.py` 通过
  - 总文件数 6253
  - 文档文件数 15
  - 参考项目快照 7 个
- 完成版本管理初始化
  - `git init`（main 分支），全量基线提交（含 reference/ 只读快照，任何改写可在 diff 中现形）
- 完成 T-010 P0 安全纠正
  - Python 环境：uv 创建 `.venv`（Python 3.13.13），安装 pytest / pytest-cov
  - v1 基线：`scripts/case_ledger.py` 从旧 Skill 快照复制（快照未动，`cmp` 校验一致）
  - 回归测试 59 项锁定旧账本正确行为：哈希校验、路径逃逸拒绝、重复 ID/引用校验、
    confirmed 三角色门禁、provisional/killed 语义、损坏尾行修复、原子报告替换、黑板折叠
  - 安全纠正：根 `SKILL.md` 演进为正式 Skill 入口（ADR-0004），反向授权规则替换为
    “一次声明、战役常驻、动作组审批、越界默认不执行”；`tests/test_skill_authorization.py`
    9 项机读门禁防止反向规则回归
  - v1 fixture 冻结：`tests/fixtures/v1/`（20 条记录、6 证据、全部裁决状态、时间戳固定），
    作为 v1→v2 迁移（T-030）输入
  - 测试总计 77 项全部通过
  - open-questions 新增 Q8（最终打包名，P4 决定）
  - 下一个任务：T-011 P0 依赖与骨架冻结
- 完成 T-011 P0 依赖与骨架冻结
  - 依赖声明：`scripts/pyproject.toml`（12 主依赖固定兼容范围 + dev extra）
  - 锁定：`uv pip compile` 生成 `scripts/requirements.lock` 与 `scripts/requirements-dev.txt`（ADR-0005）
    - pydantic 2.14.2 / typer 0.27.3 / rich 14.3.4 / PyYAML 6.0.3 / filelock 3.32.7 /
      rank-bm25 0.2.2 / jieba 0.42.1 / rapidfuzz 3.14.6 / networkx 3.7 /
      jinja2 3.1.6 / pyvis 0.3.2 / python-frontmatter 1.3.0
  - 安装验证：全量装入 `.venv`，`tests/test_dependency_lock.py` 校验可导入性与版本一致性
  - 测试结构：`tests/README.md` 补全结构说明；根 `pytest.ini`（过滤 jieba 第三方 SyntaxWarning）
  - 靶场决策：首个授权靶场确认 DVWA（Q3 关闭；仅靶场自身可用容器，Skill 运行时不引入 Docker）
  - 测试总计 83 项全部通过（新增 6 项依赖冒烟）
  - P0 出口核对：现有正确行为有回归保障 ✓；合法授权任务不再重复询问（授权 Gate 已机读锁定）✓；
    越界/高影响边界可机读（授权纪律测试 + 语义测试锁定，scope-check 命令化在 P2 policy.py）✓
  - 下一个任务：T-020 P1 Walking Skeleton
- 完成 T-020 P1 Walking Skeleton
  - 协议模型：`scripts/prism/` 包（models.py 协议模型 / packets.py 角色装配 / cli.py Typer 命令）+ `scripts/prism.py` 入口
  - Result schema 导出：`prism.py schema` 命令生成 `references/result-schema.{json,md}`，
    漂移守卫测试（`tests/test_result_schema_docs.py`）防止模型与文档漂移
  - 命令面：`assemble / loop / report / pack / verify-pack / schema`（P1 范围：单目标顺序闭环 + 报告包校验）
  - playbooks：focused / reason / explore / verify / report 五个协议文档（`playbooks/`）
  - SKILL.md：新增主循环与 playbook 路由 + prism.py 命令面（授权 Gate 原样保留，授权测试全绿）
  - 测试总计 113 项全部通过（新增 28 项：模型契约 16 + 闭环 E2E 12）
  - 工程化：新增 `.ruff.toml`（typer B008 惯用法豁免），ruff check / format 全部通过
  - 下一个任务：T-021 P1 Host Adapter 首版
- 完成 T-021 P1 Host Adapter 首版
  - 首批宿主目标（用户确认）：dsh（DSH Desktop）/ omp / workbuddy（ADR-0006）
  - `references/hosts/`：README 契约与注册表 + generic / omp / workbuddy / dsh 四个 adapter；
    契约六节（子 Agent 生成 / pack→result 传递 / 权限映射 / 能力降级 / 会话与恢复 / 实测记录）
  - 实测（WorkBuddy 原生子 Agent，全部通过）：
    - Worker 子 Agent：读 worker-H1.md → 落盘复现 artifact + WorkerResult JSON（Pydantic 契约校验通过）
    - Verifier 子 Agent：独立比对两个 artifact SHA-256（均一致），正确识别缺 impact 与控制对照，给出 provisional（独立性纪律生效）
    - 报告门禁双向：provisional 拒绝（exit 1）→ 三角色 confirmed 后 PASS（6 records）
  - 实测（omp CLI v18.15.0）：`-p` 无头模式 PowerShell 下验证通过（bash 沙箱会 SIGTERM）；
    `task` 子 Agent / `--auto-approve` / `--restore` / `--max-cost` 确认可用，派发闭环留 P4
  - 纯净性机读：`tests/test_host_adapters.py`（8 项）——注册表完整、契约小节、
    Core 文件词边界扫描（omp/dsh/workbuddy/codex/deepseek 零出现）、实测记录诚实性
  - SKILL.md 增加 hosts 路由；`prism.py hosts` 命令列出 adapter
  - 勘误：T-020 提交信息中的 assemble/loop/report 命令未实现（实际命令面 schema/pack/verify-pack/hosts），CHANGELOG 已修正
  - 测试总计 121 项全部通过
  - **P1 全部完成**；下一个任务：T-030 P2 状态模型 v2
- 完成 T-030 P2 状态模型 v2
  - v2 记录模型（ADR-0007）：FactRecord / IntentRecord / RunRecord / ApprovalRecord
    + Hypothesis/Evidence/Verdict v2 扩展（linked_facts / run / verifier_run 等）
  - 事件模型：Intent/Run 逐条追加事件，状态由最新事件派生；Intent 事件
    created/claimed/completed/blocked/cancelled，Run 另有 failed/timed_out
  - WorkerResult 14 字段冻结（Q4 关闭）；FactProposal kind 枚举冻结 8 类
  - approval_key 派生式生成（class|scope|effect），不一致即拒绝
  - `state.py`：确定性回放（引用完整性校验、重复 ID 拒绝、findings 投影、
    v1 账本提示 migrate）；`prism.py state [--json]` 命令
  - `migration.py` + `prism.py migrate`：v1→v2（ID/顺序不变、artifacts 复制、
    回放等价校验）；冻结 fixture 迁移实测：20 记录全 v2、裁决状态一一对应
  - schema 导出扩展：Result 包 + 7 类记录模型；references/result-schema 重生成
  - 测试新增 30 项（记录模型 11 + 回放 9 + 迁移 6 + 模型既有调整），总计 151 项全绿
  - 下一个任务：T-031 P2 并发与恢复（FileLock、claim、lease、幂等 ingest、崩溃恢复）
- 完成 T-031 P2 并发与恢复
  - 入库顺序落地（ADR-0008）：FileLock(locks/ingest.lock) → 回放校验与幂等检查 →
    追加并 fsync JSONL；SQLite 派生索引延后到 P3（回放即投影，不改变顺序）
  - `prism.py claim`：intent claimed + run created（lease_expires_at）；
    重复 Run ID 拒绝；completed/cancelled Intent 不可 claim；`--now` 仅供测试
  - `prism.py ingest`：WorkerResult 校验 → artifact 存在性与 SHA-256 核验
    （任一失败整体不入账）→ 生成 facts/hypotheses/evidence 记录 → run 完成事件
    （幂等键落在此事件）；同键重放返回 duplicate 且账本逐字节不变；
    suggested_verdicts 不自动入账（confirmed 仍由 Verifier 驱动）
  - `prism.py recover`：过期 Lease 的 Run → 结果包已落盘建议 ingest，否则 re_claim
    （副作用重放安全性由 Agent 层判断）
  - `prism.py repair`：截断崩溃留下的不完整尾行（只动尾行）
  - RunRecord 新增 idempotency_key 字段（可选），schema 文档重生成
  - 测试新增 10 项（claim 3 + ingest 4 含双进程并发 + 恢复 3），总计 161 项全绿
  - 下一个任务：T-032 P2 工具输出消化（Nmap/Masscan/httpx/Nuclei parser）

## 2026-11-04 · T-032 P2 工具输出消化（P2 收官）

- 验收三条全部达成：
  - 原始日志保存为证据：harvest 只消费 case 内 artifact（相对路径防逃逸）、
    SHA-256 入 digest、原文绝不回显；harvest 全程不写账本（入库由主 Agent 决定）
  - 模型只接收结构化增量：digest 与账本既有 facts 按资产键做增量对比，
    已知资产只计数（duplicates）不回显；候选硬上限 200 条（omitted 计数），
    单次解析上限 2000；digest_text ≤ 40 行
  - 跨工具去重：identity.py 归一化（IPv4/IPv6 压缩、IDNA punycode、URL 规范化、
    host:port/proto 服务键）+ 别名归并（nmap hostname）→ 相同资产键确定性合并
    （merge_reason 可解释）；模糊相似（token_sort_ratio 70–88）只进 review_queue
    永不静默合并；输出按资产键排序（确定性）
- 安全红线落地：秘密三类模式脱敏（KV/Bearer/令牌前缀）；parser 纯文本解析，
  嵌入指令（XML 注释等）不进 digest；扫描器告警固定 requires_verification=True
  且 confidence ≤ 0.5（永不自动 confirmed）
- 交付：`scripts/prism/parsers.py`（registry 五类 parser）、
  `scripts/prism/identity.py`、`prism.py harvest [--list-formats]`、
  ADR-0009、测试新增 25 项（parser 8 + identity 6 + harvest CLI 8 + registry 3）
- 测试 186 项全绿；P2 阶段（T-030/031/032）全部完成
- 下一个任务：T-040 P3 Recall / KB（混合召回、离线 KB、经验晋升）

## 2026-11-04 · T-040 P3 Recall / KB（P3 首任务）

- 验收三条全部达成：
  - 召回可解释：`prism.py recall` 每条命中返回 score breakdown
    （bm25 0.6 / fuzzy 0.25 / target 0.1 / graph 0.3 分量）与 reasons；
    BM25（rank-bm25 + jieba 中文分词）+ RapidFuzz 模糊 + 结构化加权 +
    一跳图扩展（共享资产族，限量 5）；同分按 ID 排序，确定性可回放
  - 失败路径可召回：killed 假设 / blocked Intent 全部进语料并标注
    path=failure（不同 Worker 检索即知死路）；`prism.py doc <id>`
    按需读详情（artifact 文件内容或记录 JSON），Top-N 只给短摘要
  - KB 带来源与信任级别：frontmatter source / trust(official/community/
    unverified) / applies_to / last_verified；超 180 天强制 EXPIRED
    警告（--today 注入保证测试确定性）；非法 trust 拒绝加载
- 晋升门禁（prism.py kb-promote）：仅 latest verdict = confirmed；
  去目标化硬校验（案件 target/scope 抽取主机标识，文本含任一即拒绝并
  指出泄漏串）；新条目固定 trust=unverified 不虚标
- 交付：scripts/prism/recall.py、scripts/prism/knowledge.py、
  kb/README.md、ADR-0010、CLI 五命令（recall/doc/kb-list/kb-read/
  kb-promote）、测试新增 19 项
- SQLite 物化缓存继续延迟（ADR-0008 决策沿用，接口不变）
- 测试 205 项全绿；下一任务：T-041 P3 可视化（board/dashboard/graph）

## 2026-11-04 · T-041 P3 可视化（P3 收官）

- 验收三条全部达成：
  - 离线打开：`prism.py render` 生成 board.md / dashboard.html /
    attack-graph.html / attack-graph.mmd 到 `<case>/dashboard/`（可
    --out-dir）；PyVis cdn_resources=in_line 全量内联 vis-network，
    并剥离 pyvis 0.3.2 模板残留的 bootstrap CDN 外链；测试机读断言
    两个 HTML 无任何 src/href=http(s) 外链
  - 图与账本一致：节点/边全部由回放派生（asset/service/finding/
    intent→run/linked_facts）；资产族口径复用 recall._HOST_RE 保证
    图与召回同拓扑；confirmed 投影为 finding（mermaid classDef +
    PyVis 高亮）；killed 假设不进 findings
  - 删除派生物后可重建：board.md / attack-graph.mmd 确定性（同
    --now 逐字节一致）；删除 dashboard/ 后 render 完整重建；render
    只读账本（JSONL 逐字节不变断言）
- dashboard.html：Jinja2 内联 CSS + 原生 JS 关键词过滤（目标/状态/ID），
  明示"离线快照，重新 render 刷新"
- 实现修正：pyvis 拼写 in_line（非 inline）；linked_facts 边需
  fact_id→图节点映射（asset 节点为 A_<target>）
- 交付：scripts/prism/render.py、ADR-0011、CLI render 命令、
  测试新增 12 项
- 测试 217 项全绿；P3（T-040/041）全部完成
- 下一任务：T-050 P4 实战评测（授权靶场对比、多宿主实测、打包）

## 2026-11-04 · 命名决策：sapper-skill（Q8 关闭）

- 用户决策：Skill 最终名 **sapper-skill**（目录名与 name 一致），不改回
  pentest-redteam，不做旧 Skill 原地替换（ADR-0012）
- 变更：SKILL.md frontmatter `name: sapper-skill` + description 更新为
  "P0–P3 已交付 / P4 评测期"（不虚标口径同步守卫测试）；README / docs/README /
  technical-design 框图 / NEW_SESSION_PROMPT / project-state.yml /
  scripts/pyproject.toml description / conftest docstring 同步
- 开发目录暂保持 `prism-skill/`（避免中断会话），打包产物用 `sapper-skill/`
- 内部包 `scripts/prism/` 保持实现代号不变
- DVWA 靶场就绪确认：ssh bob → docker 容器 dvwa（0.0.0.0:8080→80/tcp），
  login.php 302 正常
- 测试 217 项全绿；ruff 全绿
- 下一任务：T-050 P4 实战评测

## 2026-11-04 · T-050 P4 实战评测（DVWA 对比基线）

- 靶场就绪：ssh bob（192.168.8.159）docker dvwa，8080→80；初始化踩坑记录：
  旧版 DVWA setup.php 带 Anti-CSRF user_token（单引号属性），login/security
  同样需要 token；security cookie 直接显式携带 security=low 更稳
- 协议（关闭 Q5/Q7）：docs/eval/T-050-protocol.md——同操作者/同工具/同探测
  目录/预算 ≤40 请求；注入同一份合成 nuclei 告警（1 真 2 假）专测告警处置
- 基线（旧纪律）：v1 账本自我裁决，REPORT gate PASS 但 6 confirmed 中含
  2 个假告警误报；12 请求 2 重复（16.7%）
- v2（sapper-skill）：I1(worker R1) 8 步探测 → 幂等 ingest（重放 duplicate，
  账本 md5 不变）→ harvest（requires_verification=true, confidence=0.5）
  → I2(verifier R2) 独立复核（SQLi union 重放复现凭据提取；xoops/
  phpLDAPadmin 0 特征命中 → killed）→ V1-V4 confirmed（verifier_run 溯源）
  → 门禁 PASS → render 四件套；11 请求 1 重复（9.1%）
- 结果：有效确认 4=4（持平）、误报 2→0、重复率 16.7%→9.1%，三条验收达成
- 诚实披露：单操作者非盲测；有效确认未提升因基线已能确认全部真实漏洞
- 改进项候选（转后续）：v2 案件 H/E/V 追加 CLI；harvest 同资产合并保留
  告警标题列表；v2 报告门禁下沉为正式命令
- 评测数据 workspace/t050/ 本地保留（git 忽略，凭据不落盘）
- 下一任务：T-051 多宿主验收（omp/dsh 实测 + 打包 sapper-skill/）

## 2026-11-04 · P4 增量：实时面板 serve + 工业风双语界面重设计（ADR-0013）

- 用户三项需求：①实时更新机制（启动可选、中途可开关）②视觉重设计（浅色）
  ③文案中文化/双语
- 答案①：原产物是离线快照（ADR-0011，不伪称实时）；新增 `prism.py serve`
  （scripts/prism/live.py）——本地 HTTP 托管 + 账本指纹轮询自动重渲染 +
  /api/state /api/version /api/live；启动交互询问（--live/--no-live 跳过），
  运行中页内按钮随时暂停/恢复；file:// 打开自动退化为离线快照（不产生
  控制台噪音）
- 实施②③：render.py 模板重写——工业实用浅色（#f2f0ea/#211e19/#c2451e，
  Bahnschrift+雅黑+Cascadia 本地栈，无 webfont）；蓝图网格底纹、四角标尺
  框、错峰入场、空态折叠、:focus-visible、reduced-motion 降级；
  data-zh/data-en 双语切换；board/mermaid 中英并列；状态标签中文优先
- 工程坑：ThreadingHTTPServer 必须 serve_forever 跑在线程内（否则 accept
  循环不运行、stop() 死锁）；pyvis JSON 中文 \u 转义影响断言形态；
  board.md 只含 runs/intents/findings（facts 断言应走 /api/state）
- 测试：test_live.py 11 项（API/实时/开关/双语/路径逃逸）；全量 228 项 +
  ruff 全绿；T-050 案件面板已用新版重渲染并浏览器 QA（DOM 断言 + 控制台
  零错误；渲染路径截图受限，用 evaluate_script 校验计算样式与节点数）
- 下一任务：T-051 多宿主验收

## 2026-11-04 · T-051 P4 多宿主验收（P4 收官）

- omp 宿主真闭环（workspace/t051/omp/case）：pack(H10) → claim R1 →
  omp -p 无头 Worker（brute 弱口令探测；发现任务写的 POST 实为 GET →
  deviations 如实记录 + 同 URL 补测，未扩大范围；25 请求 45 artifacts）→
  ingest（1 fact + 6 evidence）→ verify-pack → claim R2 → 无头 Verifier
  （SHA-256 逐条比对 + 独立重放；发现派发凭据失效 → 不迁就，改字典内
  候选独立复现且工件哈希与 Worker 一致，矛盾如实上报）→ ingest（8 evidence
  + confirmed 建议）→ 裁决 V10（confirmed + verifier_run=R2）→ 门禁 PASS
  → render 四件套
- 工程改进：pack/verify-pack v2 化（packets.py → state.replay；v1 需先
  migrate）；prism.py verify 报告门禁正式命令；test_walking_skeleton
  全链 v2 化；ingest --result 相对路径按 cwd 解析（跨目录调用传绝对路径）
- MCP 实测（用户启动 yakit/dudesuite 后）：yakit connected 55 工具
  （get_mitm_filter 只读调用成功）；dudesuite 单实例互斥——锁被 dsh 桌面
  宿主持有（[MCP][Startup] 检测到另一个 MCP 实例已运行），omp 拉起即退，
  约束「dudesuite 不能同挂 dsh 与 omp」写入 adapter 文档
- dsh 验收文档 docs/eval/T-051-dsh-acceptance.md：插件 0.1.0 已装双
  profile、结构完整、scope guard 在位；发现 preset 未挂载（cordis.patch.yml
  无 prism 引用）；交互实测协议 D1–D9 待用户回填（不阻塞双宿主门槛）
- 打包 scripts/pack_skill.py → dist/sapper-skill/ 32 文件；五重结构校验
  （frontmatter=目录名/资源引用/Core 无宿主名/命令面 18/schema 同步）+
  干净冒烟；dist 产物独立跑 omp 案件门禁 PASS
- 测试 230 passed（217→230），ruff 全绿；project-state → P4-complete
- P0–P4 全部完成；后续为增量维护

## 2026-11-04 · T-051 补测：dudesuite MCP 互斥闭环验证

- 用户在 dsh 侧断开 dudesuite MCP 后重测：stdio 探针 initialize 通过
  （DudeSuite 1.2.3，独立认证通过），13 工具；omp 无头真实调用
  query_ip_location(114.114.114.114) → 中国江苏南京 163ms，exit 0
- 互斥约束闭环验证：dsh 断开 ↔ omp 挂载，双向无半挂载残留；三处文档
  （omp.md / dsh.md / T-051-dsh-acceptance.md §4）同步回填
