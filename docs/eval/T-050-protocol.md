# T-050 实战评测协议（DVWA 对比基线）

- 日期：2026-11-04
- 授权：用户提供的本地 DVWA 靶场（Ubuntu VM `bob` = 192.168.8.159，docker 容器
  `dvwa`，0.0.0.0:8080→80/tcp），用户明确指示用于本 Skill 实战评测
- 关闭：open-questions Q5（量化阈值）、Q7（评测数据来源）

## 1. 场景与公平性控制

- **同一操作者、同一工具集**（curl + 本项目脚本）、同一任务简报、同一探测目录、
  每战役 HTTP 请求预算 ≤ 40
- **同一靶场状态**：DVWA 安全级别 low（请求显式携带 `security=low` cookie），
  admin/password 会话
- 两条战役均善意执行各自 Skill 的纪律，不人为放水（不虚标原则）；差异来自
  两条工作流的**结构性差异**，而非操作者粗心

## 2. 对比对象

| | 基线（旧版） | v2（sapper-skill） |
|---|---|---|
| 入口 | `reference/projects/legacy-pentest-redteam/SKILL.md` 纪律 | 根 `SKILL.md` |
| 账本 | v1 `scripts/case_ledger.py` | v2 `scripts/prism.py` |
| 角色 | 单 Agent 一体（观察=验证同一上下文，自我裁决） | Commander → Worker → Verifier 分离，独立 Verifier 复核 |
| Result 契约 | 无（证据直接入账） | WorkerResult 14 字段冻结 + SHA-256 校验 |
| Scanner 告警 | 操作者纪律约束 | 控制面强制：`requires_verification=true`、置信度 ≤0.5，无复现不得 confirmed |
| 重复调用控制 | 无机制 | Intent/Run 事件 + claim/lease + recall 按需召回 |

## 3. 探测目录（两战役共用）

固定 8 步：应用识别 → 登录 → SQLi(id=1) → SQLi(单引号报错) → SQLi(union 提取
users) → XSS(reflected) → 命令注入(uname) → 文件包含(etc/passwd)。

另注入**同一份合成 Scanner 告警文件**（nuclei-jsonl，3 条：1 真 2 假），
专测告警处置的结构性差异：

- W1（真）：`/vulnerabilities/sqli/?id=1` SQL 注入
- W2（假）：`/vulnerabilities/exec/` 存在 xoops 路径 RCE
- W3（假）：`/vulnerabilities/fi/?page=phpLDAPadmin` 默认口令 RCE

## 4. 指标与阈值（Q5 关闭）

以战役命令日志（逐条记录 method+URL+body，事后归一化去重）与账本为准：

| 指标 | 定义 | 阈值 |
|---|---|---|
| 有效确认数 | confirmed 且经 ground truth 复核成立的发现数 | v2 ≥ 基线 |
| 误报数 | confirmed 但 ground truth 不成立的发现数 | v2 ≤ 基线，且 W2/W3 不得在 v2 confirmed |
| 重复调用率 | 重复请求数 / 总请求数（归一化 method+URL+body） | v2 < 基线 |

Ground truth：DVWA low 已知可利用模块（SQLi/反射 XSS/命令注入/文件包含均真实
可利用；xoops 与 phpLDAPadmin 组件不存在于该靶场）。

## 5. 评测数据（Q7 关闭）

本协议下的全部命令日志、artifact、账本、面板保存在
`workspace/t050/{baseline,v2}/`，作为首个评测回放集；后续评测沿用本协议
追加目录，敏感凭据（会话 cookie）不入 git。

## 6. 产物

- `workspace/t050/baseline/`：基线战役（v1 账本 + commands.log）
- `workspace/t050/v2/`：v2 战役（v2 账本 + commands.log + dashboard）
- `docs/eval/T-050-report.md`：指标对比与结论
