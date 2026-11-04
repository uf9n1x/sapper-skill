# 需求规格（Requirements Specification）

> 状态：**已确认方向，待细化条目**。本文只记录已明确的需求；未确认内容一律标记 `TBD`。

## 1. 项目目标

构建一个面向授权渗透测试与红蓝对抗的通用 Skill：

- 由宿主 Agent 提供模型、子 Agent、MCP、工具与交互能力
- Skill 提供实战方法论、工作流、状态协议、证据纪律与知识复用
- Python 控制面负责确定性、可重复、易出错的状态与数据工作
- 最终目标是**实战效果优先**，而不是堆叠工程复杂度

## 2. 适用范围

- 明确授权的攻防演练、红蓝对抗、靶场实战、大型内网渗透
- 单目标漏洞验证与多目标资产评估
- 需要 evidence chain、可追溯报告和长周期恢复的实战任务

## 3. 非目标（Out of Scope）

- 不开发独立 Agent Runtime
- 不 fork Pi、不整体二开 sapper-v2
- 不引入 Docker、外部数据库、常驻服务
- 不做通用 C2、自动化攻击执行器或无关领域的泛化工具
- 不支持黑灰产或其他未获授权目标

## 4. 核心能力需求

### R1. 授权与范围管理

- 一次授权声明，战役内常驻，不重复打扰用户
- 目标、动作、时间窗口和数据处置边界可机读
- 高影响动作按 `动作类别 + 目标范围 + 影响类型` 分组审批，同组只确认一次
- 越界或未覆盖目标默认不执行

### R2. 事实 / 假设 / 意图 / 执行状态

- 类型化 Fact：资产、服务、应用、身份、凭据引用、访问、漏洞线索、目标进展
- Hypothesis：可证伪的攻击假设，确认后成为 Finding
- Intent：带边界、角度、预算和依赖的工作单元
- Run：一次宿主 Worker/Verifier 执行的记录，含 Lease、结果和恢复状态
- Evidence：带角色、效果、来源、actor、run 和哈希的原始观察或复现材料

### R3. 证据链与报告

- Confirmed 必须可回溯到 `observation → reproduction → impact`
- 报告门禁机器校验证据角色、哈希、引用、Verifier provenance、Cleanup 与未决项
- 报告支持 Finding、攻击路径、证据索引、清理确认和 deferred work

### R4. 宿主原生协作

- 主 Agent 作为 Commander，负责规划、派单、纠偏和汇报
- 原生子 Agent 作为 Worker / Verifier，可并行
- 不支持子 Agent 的宿主，按同一协议顺序降级
- Worker 不直接写账本，只返回结构化 Result 和 artifacts

### R5. 经验召回与知识复用

- 混合召回：文本相关度 + 产品/版本 + 技术族 + 图邻近 + 验证状态 + 失败路径
- 输出 Top-N 短摘要及 `has_doc`，按需读取详情
- 跨资产、同产品/版本、技术族经验复用
- 原始目标输出不自动污染通用 KB

### R6. 可视化与执行现场

- 宿主原生实时执行流为主入口
- 每次状态变化输出简短 delta
- 离线自动重建：`board.md`、`dashboard.html`、`attack-graph.html/mmd`
- 无常驻服务、无 CDN 依赖

### R7. 工具输出消化

- 支持 Nmap XML、Masscan JSON、httpx/Nuclei JSONL 等解析
- 原始日志保存为哈希证据，模型只接收结构化增量
- 跨工具资产归一化、去重与关联
- Scanner warning 不能直接成为 confirmed Finding

## 5. 用户与使用场景

- 单人授权渗透 / 红队评估
- 靶场实战与验证
- 多目标大型内网评估
- 需要可审计报告和恢复的长期任务

## 6. 关键约束

| 约束 | 内容 |
|---|---|
| 形态 | Agent Skill + Python 控制面 |
| 运行时 | 宿主提供 Agent 能力；Python 只做确定性工作 |
| 存储 | JSONL 权威账本 + 可重建 SQLite 派生索引 |
| 安全 | 授权内自动，高影响确认，越界默认拒绝 |
| 兼容 | 通用 Core 不绑定宿主；宿主差异只在 adapter |

## 7. 待确认事项

见 `docs/spec/open-questions.md`。以下为当前已知待定项：

- 具体支持的首批宿主清单与优先级
- Python 依赖的最终锁定版本
- 首个实战靶场与验收场景
- Worker Result 的完整字段冻结版
- 评测基准的量化目标
