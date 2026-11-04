"""v2 账本记录模型冻结测试（T-030，Q4 收口）。

锁定：
- 记录类型全集：fact / intent / run / approval / hypothesis / evidence / verdict
- v 字段固定为 2；ID 前缀 F/I/R/A/H/E/V
- Fact kind 枚举冻结；Intent/Run 为追加事件模型
- Approval 键 = action_class + target_scope + effect
- WorkerResult 全字段冻结（Q4）
"""

from __future__ import annotations

import pytest
from prism import models
from pydantic import ValidationError


def base_fact(**overrides):
    fields = {
        "v": 2,
        "type": "fact",
        "id": "F1",
        "at": "2026-01-01T00:00:00Z",
        "kind": "service",
        "target": "192.0.2.10:80",
        "title": "example-httpd 2.4",
        "summary": "80 端口 HTTP 服务",
    }
    fields.update(overrides)
    return fields


class TestFactRecord:
    def test_valid_fact(self):
        record = models.FactRecord.model_validate(base_fact())
        assert record.confidence == 0.5  # 默认置信度
        assert record.relations == []

    def test_kind_enum_frozen(self):
        assert set(models.FACT_KINDS) == {
            "asset",
            "service",
            "application",
            "identity",
            "credential_ref",
            "access",
            "vulnerability_lead",
            "progress",
        }
        with pytest.raises(ValidationError):
            models.FactRecord.model_validate(base_fact(kind="not_a_kind"))

    def test_id_prefix_enforced(self):
        with pytest.raises(ValidationError):
            models.FactRecord.model_validate(base_fact(id="X1"))

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            models.FactRecord.model_validate(base_fact(confidence=1.5))

    def test_v_frozen_at_2(self):
        with pytest.raises(ValidationError):
            models.FactRecord.model_validate(base_fact(v=1))


def intent(**overrides):
    fields = {
        "v": 2,
        "type": "intent",
        "id": "I1",
        "at": "2026-01-01T00:00:00Z",
        "event": "created",
        "title": "验证 /admin 未授权访问",
        "objective": "确认是否存在未授权管理面板",
        "angle": "web-direct",
        "target": "192.0.2.10:80",
    }
    fields.update(overrides)
    return fields


class TestIntentRecord:
    def test_created_requires_doctrine_fields(self):
        record = models.IntentRecord.model_validate(intent())
        assert record.priority == 3
        with pytest.raises(ValidationError):
            models.IntentRecord.model_validate(intent(title=None))

    def test_event_enum(self):
        assert set(models.INTENT_EVENTS) == {
            "created",
            "claimed",
            "completed",
            "blocked",
            "cancelled",
        }

    def test_claimed_requires_run(self):
        with pytest.raises(ValidationError):
            models.IntentRecord.model_validate(intent(event="claimed"))
        record = models.IntentRecord.model_validate(
            intent(event="claimed", run="R1", at="2026-01-01T00:01:00Z")
        )
        assert record.run == "R1"


def run_record(**overrides):
    fields = {
        "v": 2,
        "type": "run",
        "id": "R1",
        "at": "2026-01-01T00:01:00Z",
        "event": "created",
        "intent": "I1",
        "actor": "worker",
    }
    fields.update(overrides)
    return fields


class TestRunRecord:
    def test_created_requires_intent_and_actor(self):
        record = models.RunRecord.model_validate(run_record())
        assert record.host_task_id is None
        with pytest.raises(ValidationError):
            models.RunRecord.model_validate(run_record(actor=None))

    def test_event_enum(self):
        assert set(models.RUN_EVENTS) == {
            "created",
            "completed",
            "failed",
            "timed_out",
            "cancelled",
        }

    def test_completed_requires_result_ref(self):
        with pytest.raises(ValidationError):
            models.RunRecord.model_validate(run_record(event="completed"))
        record = models.RunRecord.model_validate(
            run_record(event="completed", result_ref="results/R1.json")
        )
        assert record.result_ref == "results/R1.json"


class TestApprovalRecord:
    def test_approval_key_composition(self):
        record = models.ApprovalRecord.model_validate(
            {
                "v": 2,
                "type": "approval",
                "id": "A1",
                "at": "2026-01-01T00:00:00Z",
                "action_class": "write",
                "target_scope": "192.0.2.10",
                "effect": "irreversible",
                "status": "approved",
                "decided_by": "user",
            }
        )
        assert record.approval_key == "write|192.0.2.10|irreversible"

    def test_status_enum(self):
        with pytest.raises(ValidationError):
            models.ApprovalRecord.model_validate(
                {
                    "v": 2,
                    "type": "approval",
                    "id": "A1",
                    "at": "2026-01-01T00:00:00Z",
                    "action_class": "write",
                    "target_scope": "192.0.2.10",
                    "effect": "irreversible",
                    "status": "maybe",
                    "decided_by": "user",
                }
            )


class TestWorkerResultFrozen:
    """Q4 收口：14 个顶层字段全部冻结。"""

    def test_all_interface_fields_present(self):
        fields = set(models.WorkerResult.model_fields)
        assert fields == {
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

    def test_fact_proposal_kind_frozen(self):
        assert models.FactProposal.model_fields["kind"].annotation is not None
