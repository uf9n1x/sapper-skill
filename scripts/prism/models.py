"""协议与账本记录模型（v2 冻结版，T-030）。

两层协议：
1. WorkerResult：Worker/Verifier 返回的结构化结果包（Q4 已冻结，14 个顶层字段）
2. LedgerRecord：v2 账本 JSONL 的记录模型（fact / intent / run / approval +
   hypothesis / evidence / verdict），Intent 与 Run 为追加事件模型——当前状态由
   同一实体最新事件派生（见 state.py），禁止手工改历史。

协议文档（references/result-schema.md、result-schema.json）由本模块
自动生成，禁止手工编辑，防止"模型 / 文档 / Schema"三处漂移。
"""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import Annotated, Literal

import pydantic
from pydantic import BaseModel, Field, field_validator

RESULT_SCHEMA_VERSION = 2

# 与 v1 账本（scripts/case_ledger.py）保持一致的语义集合
VERDICT_STATUSES = ("confirmed", "killed", "inconclusive", "deferred", "provisional")
EVIDENCE_ROLES = ("observation", "reproduction", "impact", "refutation")
EVIDENCE_EFFECTS = ("supports", "refutes", "context")

_RESULT_ID_PATTERN = r"^R[A-Za-z0-9._-]{0,63}$"
_INTENT_ID_PATTERN = r"^I[A-Za-z0-9._-]{0,63}$"
_FACT_ID_PATTERN = r"^F[A-Za-z0-9._-]{0,63}$"
_APPROVAL_ID_PATTERN = r"^A[A-Za-z0-9._-]{0,63}$"
_HYPOTHESIS_ID_PATTERN = r"^H[A-Za-z0-9._-]{0,63}$"
_RECORD_ID_PATTERN = r"^[EV][A-Za-z0-9._-]{0,63}$"
_AT_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
_SHA256_PATTERN = r"^[0-9a-f]{64}$"

FACT_KINDS = (
    "asset",
    "service",
    "application",
    "identity",
    "credential_ref",
    "access",
    "vulnerability_lead",
    "progress",
)
INTENT_EVENTS = ("created", "claimed", "completed", "blocked", "cancelled")
RUN_EVENTS = ("created", "completed", "failed", "timed_out", "cancelled")


class ResultStatus(str, Enum):
    """Worker/Verifier 执行结果状态。"""

    done = "done"
    blocked = "blocked"
    failed = "failed"
    needs_verification = "needs_verification"


class EvidenceProposal(BaseModel):
    """证据提案：Worker 只提案，入库方校验 artifact 存在性、路径与哈希。"""

    hypothesis: str = Field(description="所属假设 ID")
    role: Literal["observation", "reproduction", "impact", "refutation"] = Field(
        description="证据角色：观察 / 复现 / 影响 / 反证"
    )
    effect: Literal["supports", "refutes", "context"] = Field(
        description="证据效果：支持 / 反驳 / 上下文"
    )
    artifact: str = Field(description="case/artifacts/ 内的相对路径（POSIX 风格）")
    sha256: str | None = Field(
        default=None, description="留空时由入库方计算并校验（SHA-256）"
    )
    summary: str = Field(description="一句话摘要（不含秘密原文）")

    @field_validator("artifact")
    @classmethod
    def _artifact_must_be_relative_posix(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
            raise ValueError("artifact 必须是 case 内相对路径")
        if any(part == ".." for part in normalized.split("/")):
            raise ValueError("artifact 路径不得包含 ..")
        return normalized


class HypothesisProposal(BaseModel):
    """假设提案：确认后由入库方写入账本成为可攻击假设。"""

    claim: str = Field(description="可证伪的攻击假设", max_length=240)
    scope: str = Field(description="目标范围", max_length=160)
    disprove_if: list[str] = Field(
        description="证伪条件（至少一条）", min_length=1, max_length=10
    )


class SuggestedVerdict(BaseModel):
    """裁决建议：仅是建议，confirmed 必须由 Verifier 结果驱动（P2 加 provenance 硬校验）。"""

    hypothesis: str = Field(description="目标假设 ID")
    status: Literal[
        "confirmed", "killed", "inconclusive", "deferred", "provisional"
    ] = Field(description="建议的裁决状态")
    evidence: list[str] = Field(description="引用的证据 ID", min_length=1)
    reason: str = Field(description="裁决理由", max_length=500)


class FactProposal(BaseModel):
    """事实提案：Worker 报告的新事实，入库后成为 FactRecord。"""

    kind: Literal[
        "asset",
        "service",
        "application",
        "identity",
        "credential_ref",
        "access",
        "vulnerability_lead",
        "progress",
    ] = Field(description="事实类别（枚举已冻结）")
    target: str = Field(description="归属目标标识")
    title: str = Field(description="短标题")
    summary: str = Field(description="一句话摘要")


class NextIntent(BaseModel):
    """下一步工作建议：入库后由 Commander 转正为 Intent 记录。"""

    title: str = Field(description="短标题")
    objective: str = Field(description="目标")
    angle: str = Field(description="切入角度（同一目标允许多角度）")


class CleanupItem(BaseModel):
    """清理项：报告门禁要求全部处理完（状态由账本 cleanup 记录跟踪）。"""

    action: str = Field(description="需要执行的清理动作")
    note: str = Field(default="", description="补充说明（可逆性 / 影响面）")


class WorkerResult(BaseModel):
    """Worker / Verifier 返回的结构化结果包（不直接写账本）。"""

    schema_version: Literal[2] = Field(
        default=RESULT_SCHEMA_VERSION, description="协议版本（当前为 2）"
    )
    run_id: str = Field(
        description="本次 Run 的 ID（R 前缀）", pattern=_RESULT_ID_PATTERN
    )
    intent_id: str | None = Field(
        default=None,
        description="所属 Intent ID（P1 可空；Intent 记录在 T-030 落地）",
        pattern=_INTENT_ID_PATTERN,
    )
    idempotency_key: str = Field(
        description="幂等键：由主 Agent 生成并随任务下发；同一键重试不重复入账"
    )
    status: ResultStatus = Field(description="执行结果状态")
    summary: str = Field(description="本次增量结果摘要", max_length=500)
    facts: list[FactProposal] = Field(default=[], description="新事实提案（P1 占位）")
    hypotheses: list[HypothesisProposal] = Field(default=[], description="新假设提案")
    evidence: list[EvidenceProposal] = Field(
        default=[], description="证据提案（artifact 相对路径 + 摘要）"
    )
    suggested_verdicts: list[SuggestedVerdict] = Field(
        default=[], description="裁决建议（不直接成为 confirmed）"
    )
    next_intents: list[NextIntent] = Field(
        default=[], description="下一步工作建议（不含 Worker 叙事展开）"
    )
    deviations: list[str] = Field(
        default=[], description="偏离任务边界的记录（含原因）"
    )
    cleanup: list[CleanupItem] = Field(default=[], description="需要清理的事项")
    blockers: list[str] = Field(default=[], description="阻塞项与缺失信息")


# ---------------------------------------------------------------------------
# v2 账本记录模型（JSONL 每行一条；Intent / Run 为追加事件模型）
# ---------------------------------------------------------------------------


class FactRecord(BaseModel):
    """已观察事实：资产 / 服务 / 身份 / 凭据引用 / 访问 / 漏洞线索 / 进展。"""

    v: Literal[2] = Field(default=2, description="账本 schema 版本")
    type: Literal["fact"] = "fact"
    id: str = Field(pattern=_FACT_ID_PATTERN, description="事实 ID（F 前缀）")
    at: str = Field(pattern=_AT_PATTERN)
    kind: Literal[
        "asset",
        "service",
        "application",
        "identity",
        "credential_ref",
        "access",
        "vulnerability_lead",
        "progress",
    ] = Field(description="事实类别（枚举冻结）")
    target: str = Field(description="归属目标标识", max_length=200)
    title: str = Field(max_length=200)
    summary: str = Field(max_length=500)
    doc_path: str | None = Field(
        default=None, description="长文所在 artifacts/ 相对路径（账本只存引用）"
    )
    data: dict[str, str | int | float | bool] = Field(
        default={}, description="小型结构化载荷（不含秘密原文）"
    )
    relations: list[dict[str, str]] = Field(
        default=[], description='关系边：{"relation": "...", "target": "<记录 ID>"}'
    )
    source_evidence: list[str] = Field(default=[], description="来源证据 ID（E 前缀）")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class IntentRecord(BaseModel):
    """Intent 追加事件：created / claimed / completed / blocked / cancelled。"""

    v: Literal[2] = Field(default=2, description="账本 schema 版本")
    type: Literal["intent"] = "intent"
    id: str = Field(pattern=_INTENT_ID_PATTERN, description="Intent ID（I 前缀）")
    at: str = Field(pattern=_AT_PATTERN)
    event: Literal["created", "claimed", "completed", "blocked", "cancelled"] = Field(
        description="事件类型"
    )
    title: str | None = Field(default=None, max_length=200)
    objective: str | None = Field(default=None, max_length=500)
    angle: str | None = Field(
        default=None, description="切入角度（同一目标允许多角度）", max_length=80
    )
    target: str | None = Field(default=None, max_length=200)
    linked_facts: list[str] = Field(default=[])
    priority: int = Field(default=3, ge=1, le=5)
    timebox_minutes: int | None = Field(default=None, ge=1)
    depends_on: list[str] = Field(default=[])
    run: str | None = Field(default=None, pattern=_RESULT_ID_PATTERN)
    reason: str | None = Field(default=None, max_length=500)

    @pydantic.model_validator(mode="after")
    def _validate_event_fields(self) -> IntentRecord:
        if self.event == "created":
            missing = [
                name
                for name in ("title", "objective", "angle", "target")
                if getattr(self, name) is None
            ]
            if missing:
                raise ValueError(f"event=created 时必填: {', '.join(missing)}")
        if self.event == "claimed" and self.run is None:
            raise ValueError("event=claimed 时 run 必填")
        return self


class RunRecord(BaseModel):
    """Run 追加事件：一次宿主 Worker/Verifier 执行的生命周期。"""

    v: Literal[2] = Field(default=2, description="账本 schema 版本")
    type: Literal["run"] = "run"
    id: str = Field(pattern=_RESULT_ID_PATTERN, description="Run ID（R 前缀）")
    at: str = Field(pattern=_AT_PATTERN)
    event: Literal["created", "completed", "failed", "timed_out", "cancelled"] = Field(
        description="事件类型"
    )
    intent: str | None = Field(default=None, pattern=_INTENT_ID_PATTERN)
    actor: str | None = Field(
        default=None, description="执行角色标签（worker / verifier）"
    )
    host_task_id: str | None = Field(default=None)
    lease_expires_at: str | None = Field(default=None, pattern=_AT_PATTERN)
    result_ref: str | None = Field(
        default=None, description="结果包相对路径（results/<run>.json）"
    )
    idempotency_key: str | None = Field(
        default=None,
        max_length=128,
        description="幂等键（入库时记录在 run 完成事件上；同键重试不重复入账）",
    )
    usage: dict[str, int | float] | None = Field(default=None)
    error: str | None = Field(default=None, max_length=500)

    @pydantic.model_validator(mode="after")
    def _validate_event_fields(self) -> RunRecord:
        if self.event == "created":
            missing = [
                name for name in ("intent", "actor") if getattr(self, name) is None
            ]
            if missing:
                raise ValueError(f"event=created 时必填: {', '.join(missing)}")
        if self.event == "completed" and self.result_ref is None:
            raise ValueError("event=completed 时 result_ref 必填")
        return self


class ApprovalRecord(BaseModel):
    """高影响动作组审批：approval_key = action_class + target_scope + effect。"""

    v: Literal[2] = Field(default=2, description="账本 schema 版本")
    type: Literal["approval"] = "approval"
    id: str = Field(pattern=_APPROVAL_ID_PATTERN, description="审批 ID（A 前缀）")
    at: str = Field(pattern=_AT_PATTERN)
    action_class: str = Field(max_length=80)
    target_scope: str = Field(max_length=200)
    effect: str = Field(max_length=80)
    approval_key: str = Field(
        default="", description="缺省时按三段组合自动生成：class|scope|effect"
    )
    status: Literal["approved", "revoked"] = Field(description="审批状态")
    decided_by: str = Field(max_length=80)
    expires_at: str | None = Field(default=None, pattern=_AT_PATTERN)
    note: str = Field(default="", max_length=500)

    @pydantic.model_validator(mode="before")
    @classmethod
    def _derive_key(cls, data: dict) -> dict:
        if isinstance(data, dict) and not data.get("approval_key"):
            data["approval_key"] = (
                f"{data.get('action_class')}|{data.get('target_scope')}"
                f"|{data.get('effect')}"
            )
        return data

    @pydantic.model_validator(mode="after")
    def _key_must_match(self) -> ApprovalRecord:
        expected = f"{self.action_class}|{self.target_scope}|{self.effect}"
        if self.approval_key != expected:
            raise ValueError(f"approval_key 必须为 {expected!r}")
        return self


class HypothesisRecord(BaseModel):
    """假设（v2）：可证伪攻击假设，confirmed 后投影为 Finding。"""

    v: Literal[2] = Field(default=2, description="账本 schema 版本")
    type: Literal["hypothesis"] = "hypothesis"
    id: str = Field(pattern=_HYPOTHESIS_ID_PATTERN)
    at: str = Field(pattern=_AT_PATTERN)
    claim: str = Field(max_length=500)
    scope: str = Field(max_length=200)
    disprove_if: list[str] = Field(min_length=1, max_length=10)
    linked_facts: list[str] = Field(default=[])


class EvidenceRecord(BaseModel):
    """证据（v2）：可校验的原始观察或复现材料。"""

    v: Literal[2] = Field(default=2, description="账本 schema 版本")
    type: Literal["evidence"] = "evidence"
    id: str = Field(pattern=_RECORD_ID_PATTERN)
    at: str = Field(pattern=_AT_PATTERN)
    hypothesis: str = Field(pattern=_HYPOTHESIS_ID_PATTERN)
    role: Literal["observation", "reproduction", "impact", "refutation"]
    effect: Literal["supports", "refutes", "context"]
    artifact: str = Field(description="case/artifacts/ 内相对路径（POSIX）")
    sha256: str = Field(pattern=_SHA256_PATTERN)
    summary: str = Field(max_length=300)
    run: str | None = Field(default=None, pattern=_RESULT_ID_PATTERN)
    actor: str | None = Field(default=None, max_length=80)
    observed_at: str | None = Field(default=None, pattern=_AT_PATTERN)

    @field_validator("artifact")
    @classmethod
    def _artifact_must_be_relative_posix(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
            raise ValueError("artifact 必须是 case 内相对路径")
        if any(part == ".." for part in normalized.split("/")):
            raise ValueError("artifact 路径不得包含 ..")
        return normalized


class VerdictRecord(BaseModel):
    """裁决（v2）：对假设的裁决；Verifier provenance 由 verifier_run 记录。"""

    v: Literal[2] = Field(default=2, description="账本 schema 版本")
    type: Literal["verdict"] = "verdict"
    id: str = Field(pattern=_RECORD_ID_PATTERN)
    at: str = Field(pattern=_AT_PATTERN)
    hypothesis: str = Field(pattern=_HYPOTHESIS_ID_PATTERN)
    status: Literal["confirmed", "killed", "inconclusive", "deferred", "provisional"]
    evidence: list[str] = Field(min_length=1)
    reason: str = Field(max_length=500)
    verifier_run: str | None = Field(default=None, pattern=_RESULT_ID_PATTERN)


LedgerRecord = Annotated[
    FactRecord
    | IntentRecord
    | RunRecord
    | ApprovalRecord
    | HypothesisRecord
    | EvidenceRecord
    | VerdictRecord,
    Field(discriminator="type"),
]


def export_json_schema() -> dict:
    """导出全部协议模型（Result 包 + v2 账本记录）的 JSON Schema。"""
    exported = [
        (WorkerResult, "validation"),
        (FactRecord, "validation"),
        (IntentRecord, "validation"),
        (RunRecord, "validation"),
        (ApprovalRecord, "validation"),
        (HypothesisRecord, "validation"),
        (EvidenceRecord, "validation"),
        (VerdictRecord, "validation"),
    ]
    _, definitions = pydantic.json_schema.models_json_schema(
        exported, ref_template="#/$defs/{model}"
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "prism 协议与账本记录 schema（v2 冻结版，T-030）",
        "description": (
            "由 scripts/prism/models.py 自动生成，禁止手工编辑；"
            "字段变更须走 models.py 并重新生成（漂移守卫测试强制）。"
        ),
        "$defs": definitions["$defs"],
    }


def _render_type(spec: dict) -> str:
    if "enum" in spec:
        return " / ".join(f"`{value}`" for value in spec["enum"])
    if "$ref" in spec:
        return spec["$ref"].split("/")[-1]
    if "anyOf" in spec:
        return " / ".join(_render_type(part) for part in spec["anyOf"])
    if spec.get("type") == "array":
        return f"list[{_render_type(spec.get('items', {}))}]"
    if spec.get("type") == "string":
        return (
            "string"
            if "pattern" not in spec
            else f"string (pattern `{spec['pattern']}`)"
        )
    return spec.get("type", json.dumps(spec, ensure_ascii=False))


def export_markdown() -> str:
    """从 Pydantic 模型生成字段文档（references/result-schema.md 的内容源）。"""
    schema = export_json_schema()
    lines = [
        "# prism 协议与账本记录 schema（v2 冻结版，T-030）",
        "",
        (
            "> 本文档由 `scripts/prism/models.py` 自动生成（`python -X utf8 scripts/prism.py"
            " schema --format markdown`），**禁止手工编辑**。"
        ),
        (
            "> Worker 不直接写账本，只返回 WorkerResult；`suggested_verdicts` 不直接成为"
            " confirmed，必须由 Verifier 结果驱动。Intent / Run 为追加事件模型，"
            "当前状态由最新事件派生（`prism.py state`）。"
        ),
        "",
    ]
    # WorkerResult 与账本记录在前，子模型随后
    priority = [
        "WorkerResult",
        "FactRecord",
        "IntentRecord",
        "RunRecord",
        "ApprovalRecord",
        "HypothesisRecord",
        "EvidenceRecord",
        "VerdictRecord",
    ]
    ordered = [k for k in priority if k in schema["$defs"]] + [
        k for k in schema["$defs"] if k not in priority
    ]
    for name in ordered:
        model_schema = schema["$defs"][name]
        lines += [f"## {name}", ""]
        if description := model_schema.get("description"):
            lines += [description, ""]
        required = set(model_schema.get("required", []))
        lines += ["| 字段 | 类型 | 必填 | 默认 | 说明 |", "|---|---|---|---|---|"]
        for field, spec in model_schema.get("properties", {}).items():
            flag = "是" if field in required else "否"
            default = spec.get("default", "—")
            default_text = (
                "—" if default == "—" else json.dumps(default, ensure_ascii=False)
            )
            lines.append(
                f"| `{field}` | {_render_type(spec)} | {flag} | {default_text} "
                f"| {spec.get('description', '')} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
