"""状态事件回放测试（T-030 验收：状态事件可回放）。

锁定：
- 回放确定性：同一账本两次回放结果一致
- Intent / Run 最新事件派生当前状态
- 引用完整性：悬空引用被拒绝
- findings 投影：confirmed 假设
- v1 账本不可直接回放（提示 migrate）
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import FIXTURE_V1_CASE
from prism import state


def write_ledger(case: Path, records: list[dict]) -> Path:
    case.mkdir(parents=True, exist_ok=True)
    path = case / "ledger.jsonl"
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
        encoding="utf-8",
        newline="\n",
    )
    return path


def v2_campaign() -> list[dict]:
    """一个小型 v2 战役：假设 → Intent → Run → 证据 → 裁决 → 审批。"""
    return [
        {
            "v": 2,
            "type": "approval",
            "id": "A1",
            "at": "2026-01-01T00:00:00Z",
            "action_class": "probe",
            "target_scope": "192.0.2.10",
            "effect": "reversible",
            "status": "approved",
            "decided_by": "user",
        },
        {
            "v": 2,
            "type": "fact",
            "id": "F1",
            "at": "2026-01-01T00:00:01Z",
            "kind": "service",
            "target": "192.0.2.10:80",
            "title": "example-httpd 2.4",
            "summary": "80 端口 HTTP 服务",
            "source_evidence": [],
        },
        {
            "v": 2,
            "type": "hypothesis",
            "id": "H1",
            "at": "2026-01-01T00:00:02Z",
            "claim": "192.0.2.10 /admin 存在未授权访问",
            "scope": "192.0.2.10 web",
            "disprove_if": ["控制请求返回 401"],
            "linked_facts": ["F1"],
        },
        {
            "v": 2,
            "type": "intent",
            "id": "I1",
            "at": "2026-01-01T00:00:03Z",
            "event": "created",
            "title": "验证 /admin",
            "objective": "确认未授权访问",
            "angle": "web-direct",
            "target": "192.0.2.10:80",
            "linked_facts": ["F1"],
        },
        {
            "v": 2,
            "type": "run",
            "id": "R1",
            "at": "2026-01-01T00:01:00Z",
            "event": "created",
            "intent": "I1",
            "actor": "worker",
        },
        {
            "v": 2,
            "type": "intent",
            "id": "I1",
            "at": "2026-01-01T00:01:01Z",
            "event": "claimed",
            "run": "R1",
        },
        {
            "v": 2,
            "type": "evidence",
            "id": "E1",
            "at": "2026-01-01T00:02:00Z",
            "hypothesis": "H1",
            "role": "observation",
            "effect": "supports",
            "artifact": "artifacts/obs.txt",
            "sha256": "a" * 64,
            "summary": "GET /admin 200",
            "run": "R1",
        },
        {
            "v": 2,
            "type": "run",
            "id": "R1",
            "at": "2026-01-01T00:02:30Z",
            "event": "completed",
            "result_ref": "results/R1.json",
        },
        {
            "v": 2,
            "type": "intent",
            "id": "I1",
            "at": "2026-01-01T00:03:00Z",
            "event": "completed",
        },
        {
            "v": 2,
            "type": "verdict",
            "id": "V1",
            "at": "2026-01-01T00:04:00Z",
            "hypothesis": "H1",
            "status": "confirmed",
            "evidence": ["E1"],
            "reason": "Verifier 复核通过",
            "verifier_run": "R1",
        },
    ]


class TestReplay:
    def test_replay_derives_latest_event_states(self, tmp_path: Path):
        case = tmp_path / "case"
        write_ledger(case, v2_campaign())
        derived = state.replay(case)
        assert derived.intents["I1"]["status"] == "completed"
        assert derived.runs["R1"]["status"] == "completed"
        assert derived.runs["R1"]["result_ref"] == "results/R1.json"
        assert derived.findings == ["H1"]

    def test_replay_is_deterministic(self, tmp_path: Path):
        case = tmp_path / "case"
        write_ledger(case, v2_campaign())
        first = state.replay(case).to_json()
        second = state.replay(case).to_json()
        assert first == second

    def test_intent_status_history_preserved(self, tmp_path: Path):
        case = tmp_path / "case"
        write_ledger(case, v2_campaign())
        derived = state.replay(case)
        assert derived.intents["I1"]["history"] == [
            "created",
            "claimed",
            "completed",
        ]

    def test_duplicate_id_rejected(self, tmp_path: Path):
        records = v2_campaign()
        records.append(dict(records[1]))  # 重复 Fact F1
        case = tmp_path / "case"
        write_ledger(case, records)
        with pytest.raises(state.ReplayError, match="duplicate"):
            state.replay(case)

    def test_dangling_evidence_reference_rejected(self, tmp_path: Path):
        records = v2_campaign()
        records.append(
            {
                "v": 2,
                "type": "evidence",
                "id": "E9",
                "at": "2026-01-01T00:05:00Z",
                "hypothesis": "H_MISSING",
                "role": "observation",
                "effect": "supports",
                "artifact": "artifacts/x.txt",
                "sha256": "b" * 64,
                "summary": "悬空引用",
            }
        )
        case = tmp_path / "case"
        write_ledger(case, records)
        with pytest.raises(state.ReplayError, match="H_MISSING"):
            state.replay(case)

    def test_dangling_linked_fact_rejected(self, tmp_path: Path):
        records = v2_campaign()
        for record in records:
            if record["type"] == "hypothesis":
                record["linked_facts"] = ["F_MISSING"]
        case = tmp_path / "case"
        write_ledger(case, records)
        with pytest.raises(state.ReplayError, match="F_MISSING"):
            state.replay(case)

    def test_v1_ledger_requires_migration(self):
        with pytest.raises(state.ReplayError, match="migrate"):
            state.replay(FIXTURE_V1_CASE)

    def test_malformed_json_line_rejected(self, tmp_path: Path):
        case = tmp_path / "case"
        case.mkdir(parents=True)
        (case / "ledger.jsonl").write_text(
            "{not json}\n", encoding="utf-8", newline="\n"
        )
        with pytest.raises(state.ReplayError, match="line 1"):
            state.replay(case)


class TestStateCommand:
    def test_state_json_output(self, tmp_path: Path):
        case = tmp_path / "case"
        write_ledger(case, v2_campaign())
        from conftest import run_prism

        result = run_prism("state", str(case), "--json")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["counts"]["facts"] == 1
        assert payload["counts"]["findings"] == 1
        assert payload["intents"][0]["id"] == "I1"
        assert payload["intents"][0]["status"] == "completed"
