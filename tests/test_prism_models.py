"""v2 控制面协议模型测试（T-020，P1 骨架版）。

锁定 WorkerResult 契约方向（interfaces.md §3）：
- 14 个顶层字段、status 枚举、证据角色/效果、裁决状态枚举
- idempotency_key 必填（Worker 不写账本，幂等键由主 Agent 下发）
- schema 导出完整（JSON Schema + 字段文档，防三处漂移）

字段冻结版属 T-030（open-questions Q4）；本文件锁定的是 P1 骨架行为。
"""

from __future__ import annotations

import json

import pytest
from prism import models
from pydantic import ValidationError

RESULT_TOP_LEVEL_FIELDS = {
    "schema_version",
    "run_id",
    "intent_id",
    "idempotency_key",
    "status",
    "summary",
    "facts",
    "hypotheses",
    "evidence",
    "suggested_verdicts",
    "next_intents",
    "deviations",
    "cleanup",
    "blockers",
}


def minimal_result(**overrides) -> dict:
    payload = {
        "schema_version": 2,
        "run_id": "R001",
        "idempotency_key": "idem-R001-001",
        "status": "done",
        "summary": "最小合法结果",
    }
    payload.update(overrides)
    return payload


class TestWorkerResultContract:
    def test_minimal_result_valid(self):
        result = models.WorkerResult.model_validate(minimal_result())
        assert result.status == "done"
        assert result.facts == []
        assert result.schema_version == 2

    def test_all_top_level_fields_present_in_schema(self):
        schema = models.WorkerResult.model_json_schema()
        assert set(schema["properties"]) == RESULT_TOP_LEVEL_FIELDS
        for field in ("run_id", "idempotency_key", "status", "summary"):
            assert field in schema["required"]

    def test_missing_idempotency_key_rejected(self):
        payload = minimal_result()
        del payload["idempotency_key"]
        with pytest.raises(ValidationError):
            models.WorkerResult.model_validate(payload)

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError):
            models.WorkerResult.model_validate(minimal_result(status="maybe"))

    def test_status_enum_values(self):
        assert set(models.ResultStatus) == {
            "done",
            "blocked",
            "failed",
            "needs_verification",
        }

    def test_wrong_schema_version_rejected(self):
        with pytest.raises(ValidationError):
            models.WorkerResult.model_validate(minimal_result(schema_version=1))

    def test_intent_id_optional_in_p1(self):
        result = models.WorkerResult.model_validate(minimal_result())
        assert result.intent_id is None


class TestResultSubmodels:
    def test_evidence_proposal_valid(self):
        proposal = models.EvidenceProposal(
            hypothesis="H1",
            role="observation",
            effect="supports",
            artifact="artifacts/resp.txt",
            summary="GET /admin 200",
        )
        assert proposal.sha256 is None  # None → ingest 侧计算并校验

    def test_evidence_proposal_bad_role_rejected(self):
        with pytest.raises(ValidationError):
            models.EvidenceProposal(
                hypothesis="H1",
                role="smell",
                effect="supports",
                artifact="artifacts/resp.txt",
                summary="s",
            )

    def test_evidence_proposal_bad_effect_rejected(self):
        with pytest.raises(ValidationError):
            models.EvidenceProposal(
                hypothesis="H1",
                role="observation",
                effect="maybe",
                artifact="artifacts/resp.txt",
                summary="s",
            )

    def test_evidence_proposal_absolute_artifact_rejected(self):
        with pytest.raises(ValidationError):
            models.EvidenceProposal(
                hypothesis="H1",
                role="observation",
                effect="supports",
                artifact="C:/abs/path.txt",
                summary="s",
            )

    def test_evidence_proposal_artifact_must_be_posix_relative(self):
        proposal = models.EvidenceProposal(
            hypothesis="H1",
            role="observation",
            effect="supports",
            artifact="artifacts\\resp.txt",
            summary="s",
        )
        assert "\\" not in proposal.artifact

    def test_suggested_verdict_bad_status_rejected(self):
        with pytest.raises(ValidationError):
            models.SuggestedVerdict(
                hypothesis="H1",
                status="maybe",
                evidence=["E1"],
                reason="r",
            )

    def test_suggested_verdict_statuses_align_with_v1(self):
        assert set(models.VERDICT_STATUSES) == {
            "confirmed",
            "killed",
            "inconclusive",
            "deferred",
            "provisional",
        }

    def test_full_result_roundtrip(self):
        payload = minimal_result(
            hypotheses=[
                {
                    "claim": "目标存在未授权访问",
                    "scope": "192.0.2.10 web",
                    "disprove_if": ["控制请求返回 401"],
                }
            ],
            evidence=[
                {
                    "hypothesis": "H001",
                    "role": "observation",
                    "effect": "supports",
                    "artifact": "artifacts/a.txt",
                    "summary": "observed",
                }
            ],
            suggested_verdicts=[
                {
                    "hypothesis": "H001",
                    "status": "provisional",
                    "evidence": ["E001"],
                    "reason": "待验证影响",
                }
            ],
            next_intents=[
                {"title": "补影响评估", "objective": "评估影响", "angle": "impact"}
            ],
            cleanup=[{"action": "清理测试账号", "note": "创建过临时文件"}],
            deviations=["工具降级为 curl"],
            blockers=[],
        )
        result = models.WorkerResult.model_validate(payload)
        dumped = result.model_dump_json()
        assert json.loads(dumped)["status"] == "done"


class TestSchemaExport:
    def test_export_json_schema_roundtrip(self):
        schema = models.export_json_schema()
        assert schema["$defs"]["ResultStatus"]["enum"] == [
            "done",
            "blocked",
            "failed",
            "needs_verification",
        ]
        assert schema["$defs"]["WorkerResult"]["properties"]["status"]["$ref"].endswith(
            "ResultStatus"
        )

    def test_export_markdown_documents_all_fields(self):
        markdown = models.export_markdown()
        for field in RESULT_TOP_LEVEL_FIELDS:
            assert field in markdown
        assert "idempotency_key" in markdown
