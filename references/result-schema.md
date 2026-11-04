# prism 协议与账本记录 schema（v2 冻结版，T-030）

> 本文档由 `scripts/prism/models.py` 自动生成（`python -X utf8 scripts/prism.py schema --format markdown`），**禁止手工编辑**。
> Worker 不直接写账本，只返回 WorkerResult；`suggested_verdicts` 不直接成为 confirmed，必须由 Verifier 结果驱动。Intent / Run 为追加事件模型，当前状态由最新事件派生（`prism.py state`）。

## WorkerResult

Worker / Verifier 返回的结构化结果包（不直接写账本）。

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `schema_version` | integer | 否 | 2 | 协议版本（当前为 2） |
| `run_id` | string (pattern `^R[A-Za-z0-9._-]{0,63}$`) | 是 | — | 本次 Run 的 ID（R 前缀） |
| `intent_id` | string (pattern `^I[A-Za-z0-9._-]{0,63}$`) / null | 否 | null | 所属 Intent ID（P1 可空；Intent 记录在 T-030 落地） |
| `idempotency_key` | string | 是 | — | 幂等键：由主 Agent 生成并随任务下发；同一键重试不重复入账 |
| `status` | ResultStatus | 是 | — | 执行结果状态 |
| `summary` | string | 是 | — | 本次增量结果摘要 |
| `facts` | list[FactProposal] | 否 | [] | 新事实提案（P1 占位） |
| `hypotheses` | list[HypothesisProposal] | 否 | [] | 新假设提案 |
| `evidence` | list[EvidenceProposal] | 否 | [] | 证据提案（artifact 相对路径 + 摘要） |
| `suggested_verdicts` | list[SuggestedVerdict] | 否 | [] | 裁决建议（不直接成为 confirmed） |
| `next_intents` | list[NextIntent] | 否 | [] | 下一步工作建议（不含 Worker 叙事展开） |
| `deviations` | list[string] | 否 | [] | 偏离任务边界的记录（含原因） |
| `cleanup` | list[CleanupItem] | 否 | [] | 需要清理的事项 |
| `blockers` | list[string] | 否 | [] | 阻塞项与缺失信息 |

## FactRecord

已观察事实：资产 / 服务 / 身份 / 凭据引用 / 访问 / 漏洞线索 / 进展。

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `v` | integer | 否 | 2 | 账本 schema 版本 |
| `type` | string | 否 | "fact" |  |
| `id` | string (pattern `^F[A-Za-z0-9._-]{0,63}$`) | 是 | — | 事实 ID（F 前缀） |
| `at` | string (pattern `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`) | 是 | — |  |
| `kind` | `asset` / `service` / `application` / `identity` / `credential_ref` / `access` / `vulnerability_lead` / `progress` | 是 | — | 事实类别（枚举冻结） |
| `target` | string | 是 | — | 归属目标标识 |
| `title` | string | 是 | — |  |
| `summary` | string | 是 | — |  |
| `doc_path` | string / null | 否 | null | 长文所在 artifacts/ 相对路径（账本只存引用） |
| `data` | object | 否 | {} | 小型结构化载荷（不含秘密原文） |
| `relations` | list[object] | 否 | [] | 关系边：{"relation": "...", "target": "<记录 ID>"} |
| `source_evidence` | list[string] | 否 | [] | 来源证据 ID（E 前缀） |
| `confidence` | number | 否 | 0.5 |  |

## IntentRecord

Intent 追加事件：created / claimed / completed / blocked / cancelled。

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `v` | integer | 否 | 2 | 账本 schema 版本 |
| `type` | string | 否 | "intent" |  |
| `id` | string (pattern `^I[A-Za-z0-9._-]{0,63}$`) | 是 | — | Intent ID（I 前缀） |
| `at` | string (pattern `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`) | 是 | — |  |
| `event` | `created` / `claimed` / `completed` / `blocked` / `cancelled` | 是 | — | 事件类型 |
| `title` | string / null | 否 | null |  |
| `objective` | string / null | 否 | null |  |
| `angle` | string / null | 否 | null | 切入角度（同一目标允许多角度） |
| `target` | string / null | 否 | null |  |
| `linked_facts` | list[string] | 否 | [] |  |
| `priority` | integer | 否 | 3 |  |
| `timebox_minutes` | integer / null | 否 | null |  |
| `depends_on` | list[string] | 否 | [] |  |
| `run` | string (pattern `^R[A-Za-z0-9._-]{0,63}$`) / null | 否 | null |  |
| `reason` | string / null | 否 | null |  |

## RunRecord

Run 追加事件：一次宿主 Worker/Verifier 执行的生命周期。

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `v` | integer | 否 | 2 | 账本 schema 版本 |
| `type` | string | 否 | "run" |  |
| `id` | string (pattern `^R[A-Za-z0-9._-]{0,63}$`) | 是 | — | Run ID（R 前缀） |
| `at` | string (pattern `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`) | 是 | — |  |
| `event` | `created` / `completed` / `failed` / `timed_out` / `cancelled` | 是 | — | 事件类型 |
| `intent` | string (pattern `^I[A-Za-z0-9._-]{0,63}$`) / null | 否 | null |  |
| `actor` | string / null | 否 | null | 执行角色标签（worker / verifier） |
| `host_task_id` | string / null | 否 | null |  |
| `lease_expires_at` | string (pattern `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`) / null | 否 | null |  |
| `result_ref` | string / null | 否 | null | 结果包相对路径（results/<run>.json） |
| `idempotency_key` | string / null | 否 | null | 幂等键（入库时记录在 run 完成事件上；同键重试不重复入账） |
| `usage` | object / null | 否 | null |  |
| `error` | string / null | 否 | null |  |

## ApprovalRecord

高影响动作组审批：approval_key = action_class + target_scope + effect。

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `v` | integer | 否 | 2 | 账本 schema 版本 |
| `type` | string | 否 | "approval" |  |
| `id` | string (pattern `^A[A-Za-z0-9._-]{0,63}$`) | 是 | — | 审批 ID（A 前缀） |
| `at` | string (pattern `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`) | 是 | — |  |
| `action_class` | string | 是 | — |  |
| `target_scope` | string | 是 | — |  |
| `effect` | string | 是 | — |  |
| `approval_key` | string | 否 | "" | 缺省时按三段组合自动生成：class|scope|effect |
| `status` | `approved` / `revoked` | 是 | — | 审批状态 |
| `decided_by` | string | 是 | — |  |
| `expires_at` | string (pattern `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`) / null | 否 | null |  |
| `note` | string | 否 | "" |  |

## HypothesisRecord

假设（v2）：可证伪攻击假设，confirmed 后投影为 Finding。

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `v` | integer | 否 | 2 | 账本 schema 版本 |
| `type` | string | 否 | "hypothesis" |  |
| `id` | string (pattern `^H[A-Za-z0-9._-]{0,63}$`) | 是 | — |  |
| `at` | string (pattern `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`) | 是 | — |  |
| `claim` | string | 是 | — |  |
| `scope` | string | 是 | — |  |
| `disprove_if` | list[string] | 是 | — |  |
| `linked_facts` | list[string] | 否 | [] |  |

## EvidenceRecord

证据（v2）：可校验的原始观察或复现材料。

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `v` | integer | 否 | 2 | 账本 schema 版本 |
| `type` | string | 否 | "evidence" |  |
| `id` | string (pattern `^[EV][A-Za-z0-9._-]{0,63}$`) | 是 | — |  |
| `at` | string (pattern `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`) | 是 | — |  |
| `hypothesis` | string (pattern `^H[A-Za-z0-9._-]{0,63}$`) | 是 | — |  |
| `role` | `observation` / `reproduction` / `impact` / `refutation` | 是 | — |  |
| `effect` | `supports` / `refutes` / `context` | 是 | — |  |
| `artifact` | string | 是 | — | case/artifacts/ 内相对路径（POSIX） |
| `sha256` | string (pattern `^[0-9a-f]{64}$`) | 是 | — |  |
| `summary` | string | 是 | — |  |
| `run` | string (pattern `^R[A-Za-z0-9._-]{0,63}$`) / null | 否 | null |  |
| `actor` | string / null | 否 | null |  |
| `observed_at` | string (pattern `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`) / null | 否 | null |  |

## VerdictRecord

裁决（v2）：对假设的裁决；Verifier provenance 由 verifier_run 记录。

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `v` | integer | 否 | 2 | 账本 schema 版本 |
| `type` | string | 否 | "verdict" |  |
| `id` | string (pattern `^[EV][A-Za-z0-9._-]{0,63}$`) | 是 | — |  |
| `at` | string (pattern `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`) | 是 | — |  |
| `hypothesis` | string (pattern `^H[A-Za-z0-9._-]{0,63}$`) | 是 | — |  |
| `status` | `confirmed` / `killed` / `inconclusive` / `deferred` / `provisional` | 是 | — |  |
| `evidence` | list[string] | 是 | — |  |
| `reason` | string | 是 | — |  |
| `verifier_run` | string (pattern `^R[A-Za-z0-9._-]{0,63}$`) / null | 否 | null |  |

## CleanupItem

清理项：报告门禁要求全部处理完（状态由账本 cleanup 记录跟踪）。

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `action` | string | 是 | — | 需要执行的清理动作 |
| `note` | string | 否 | "" | 补充说明（可逆性 / 影响面） |

## EvidenceProposal

证据提案：Worker 只提案，入库方校验 artifact 存在性、路径与哈希。

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `hypothesis` | string | 是 | — | 所属假设 ID |
| `role` | `observation` / `reproduction` / `impact` / `refutation` | 是 | — | 证据角色：观察 / 复现 / 影响 / 反证 |
| `effect` | `supports` / `refutes` / `context` | 是 | — | 证据效果：支持 / 反驳 / 上下文 |
| `artifact` | string | 是 | — | case/artifacts/ 内的相对路径（POSIX 风格） |
| `sha256` | string / null | 否 | null | 留空时由入库方计算并校验（SHA-256） |
| `summary` | string | 是 | — | 一句话摘要（不含秘密原文） |

## FactProposal

事实提案：Worker 报告的新事实，入库后成为 FactRecord。

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `kind` | `asset` / `service` / `application` / `identity` / `credential_ref` / `access` / `vulnerability_lead` / `progress` | 是 | — | 事实类别（枚举已冻结） |
| `target` | string | 是 | — | 归属目标标识 |
| `title` | string | 是 | — | 短标题 |
| `summary` | string | 是 | — | 一句话摘要 |

## HypothesisProposal

假设提案：确认后由入库方写入账本成为可攻击假设。

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `claim` | string | 是 | — | 可证伪的攻击假设 |
| `scope` | string | 是 | — | 目标范围 |
| `disprove_if` | list[string] | 是 | — | 证伪条件（至少一条） |

## NextIntent

下一步工作建议：入库后由 Commander 转正为 Intent 记录。

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `title` | string | 是 | — | 短标题 |
| `objective` | string | 是 | — | 目标 |
| `angle` | string | 是 | — | 切入角度（同一目标允许多角度） |

## ResultStatus

Worker/Verifier 执行结果状态。

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|

## SuggestedVerdict

裁决建议：仅是建议，confirmed 必须由 Verifier 结果驱动（P2 加 provenance 硬校验）。

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `hypothesis` | string | 是 | — | 目标假设 ID |
| `status` | `confirmed` / `killed` / `inconclusive` / `deferred` / `provisional` | 是 | — | 建议的裁决状态 |
| `evidence` | list[string] | 是 | — | 引用的证据 ID |
| `reason` | string | 是 | — | 裁决理由 |
