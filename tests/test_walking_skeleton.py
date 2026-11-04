"""Walking Skeleton 端到端测试（T-020，T-051 起 v2 化）。

验证单目标顺序闭环：Commander(reason) → pack → Worker Result →
ingest 入账 → verify-pack → Verifier Result → confirmed 裁决 → 报告门禁。

约束锁定（升级方案 §7）：
- Worker pack 不含无关目标
- Verifier pack 不含 Worker 成功叙事（裁决理由/建议/叙事性 summary）
- Worker 建议不直接成为 confirmed，confirmed 由 Verifier 结果驱动
- 账本为 v2 事件模型；主 Agent 是唯一入库者
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from conftest import make_artifact, run_prism
from prism import models

NOW = "2026-01-01T00:00:00Z"


def _sha(case: Path, rel: str) -> str:
    return hashlib.sha256((case / rel).read_bytes()).hexdigest()


def _append(case: Path, records: list[dict]) -> None:
    for rec in records:
        model = {
            "approval": models.ApprovalRecord,
            "hypothesis": models.HypothesisRecord,
            "evidence": models.EvidenceRecord,
            "verdict": models.VerdictRecord,
            "intent": models.IntentRecord,
            "fact": models.FactRecord,
        }[rec["type"]]
        model.model_validate(rec)
    with open(case / "ledger.jsonl", "a", encoding="utf-8", newline="\n") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def seeded_case(tmp_path: Path) -> Path:
    """两假设案件：H1 待验证（含一条观察证据），H2 为无关目标。"""
    case = tmp_path / "case"
    (case / "artifacts").mkdir(parents=True)
    (case / "results").mkdir(parents=True)
    (case / "packets").mkdir(parents=True)
    rel = make_artifact(case, "obs.txt", "observation payload reserved-range")
    _append(case, [
        {"v": 2, "type": "approval", "id": "A1", "at": NOW, "action_class": "probe",
         "target_scope": "192.0.2.10 web", "effect": "reversible",
         "status": "approved", "decided_by": "user"},
        {"v": 2, "type": "hypothesis", "id": "H1", "at": NOW,
         "claim": "192.0.2.10 存在未授权访问", "scope": "192.0.2.10 web",
         "disprove_if": ["控制请求返回 401"]},
        {"v": 2, "type": "evidence", "id": "E1", "at": NOW, "hypothesis": "H1",
         "role": "observation", "effect": "supports", "artifact": rel,
         "sha256": _sha(case, rel), "summary": "首轮观察：GET / 200"},
        {"v": 2, "type": "hypothesis", "id": "H2", "at": NOW,
         "claim": "无关目标假设仅用于隔离校验", "scope": "10.9.9.9 db",
         "disprove_if": ["x"]},
    ])
    return case


class TestPack:
    def test_worker_pack_written_and_routed(self, tmp_path: Path):
        case = seeded_case(tmp_path)
        result = run_prism("pack", str(case), "--hypothesis", "H1")
        assert result.returncode == 0, result.stderr
        pack_path = case / "packets" / "worker-H1.md"
        assert pack_path.is_file()
        content = pack_path.read_text(encoding="utf-8")
        assert "192.0.2.10 存在未授权访问" in content
        assert "192.0.2.10 web" in content
        assert "E1" in content
        assert "reproduction" in content and "impact" in content  # 缺失角色提示

    def test_worker_pack_excludes_unrelated_targets(self, tmp_path: Path):
        case = seeded_case(tmp_path)
        run_prism("pack", str(case), "--hypothesis", "H1")
        content = (case / "packets" / "worker-H1.md").read_text(encoding="utf-8")
        assert "无关目标假设" not in content
        assert "10.9.9.9" not in content

    def test_worker_pack_references_result_schema(self, tmp_path: Path):
        case = seeded_case(tmp_path)
        run_prism("pack", str(case), "--hypothesis", "H1")
        content = (case / "packets" / "worker-H1.md").read_text(encoding="utf-8")
        assert "WorkerResult" in content
        assert "idempotency_key" in content

    def test_pack_json_output(self, tmp_path: Path):
        case = seeded_case(tmp_path)
        result = run_prism("pack", str(case), "--hypothesis", "H1", "--json")
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["hypothesis"] == "H1"
        assert payload["pack_path"].endswith("worker-H1.md")

    def test_pack_unknown_hypothesis_fails(self, tmp_path: Path):
        case = seeded_case(tmp_path)
        result = run_prism("pack", str(case), "--hypothesis", "H9")
        assert result.returncode == 1
        assert "ERROR" in result.stderr


class TestVerifyPack:
    def test_verifier_pack_contains_claim_and_evidence_only(self, tmp_path: Path):
        case = seeded_case(tmp_path)
        result = run_prism("verify-pack", str(case), "--hypothesis", "H1")
        assert result.returncode == 0, result.stderr
        pack_path = case / "packets" / "verifier-H1.md"
        assert pack_path.is_file()
        content = pack_path.read_text(encoding="utf-8")
        assert "192.0.2.10 存在未授权访问" in content
        assert "E1" in content
        assert "SHA-256" in content
        assert "证伪条件" in content

    def test_verifier_pack_excludes_worker_narrative(self, tmp_path: Path):
        """已有裁决理由与 Worker 叙事不得进入 Verifier 包。"""
        case = seeded_case(tmp_path)
        marker = "WorkerSuccessNarrativeMarker不应出现在验证包"
        rel2 = make_artifact(case, "repro.txt", "repro payload")
        _append(case, [
            {"v": 2, "type": "evidence", "id": "E2", "at": NOW, "hypothesis": "H1",
             "role": "reproduction", "effect": "supports", "artifact": rel2,
             "sha256": _sha(case, rel2), "summary": marker},
            {"v": 2, "type": "verdict", "id": "V0", "at": NOW, "hypothesis": "H1",
             "status": "provisional", "evidence": ["E1"], "reason": "WorkerNarrativeReason不得泄露"},
        ])
        run_prism("verify-pack", str(case), "--hypothesis", "H1")
        content = (case / "packets" / "verifier-H1.md").read_text(encoding="utf-8")
        assert marker not in content
        assert "WorkerNarrativeReason" not in content

    def test_verify_pack_excludes_unrelated_targets(self, tmp_path: Path):
        case = seeded_case(tmp_path)
        run_prism("verify-pack", str(case), "--hypothesis", "H1")
        content = (case / "packets" / "verifier-H1.md").read_text(encoding="utf-8")
        assert "10.9.9.9" not in content


class TestSchemaCommand:
    def test_schema_json_output_is_valid_json_schema(self):
        result = run_prism("schema", "--format", "json")
        assert result.returncode == 0
        schema = json.loads(result.stdout)
        assert schema["$defs"]["ResultStatus"]["enum"]
        assert "WorkerResult" in schema["$defs"]

    def test_schema_markdown_output_documents_fields(self):
        result = run_prism("schema", "--format", "markdown")
        assert result.returncode == 0
        assert "idempotency_key" in result.stdout
        assert "suggested_verdicts" in result.stdout


class TestVerifyGate:
    def test_gate_fails_on_unproven_confirmed(self, tmp_path: Path):
        """confirmed 缺 verifier_run 溯源 → 门禁拒绝。"""
        case = seeded_case(tmp_path)
        _append(case, [
            {"v": 2, "type": "verdict", "id": "V1", "at": NOW, "hypothesis": "H1",
             "status": "confirmed", "evidence": ["E1"], "reason": "r"},
        ])
        result = run_prism("verify", str(case))
        assert result.returncode == 1
        assert "REPORT gate: FAIL" in result.stdout
        assert "verifier_run" in result.stdout

    def test_gate_passes_on_closed_loop(self, tmp_path: Path):
        case = seeded_case(tmp_path)
        rel_repro = make_artifact(case, "repro.txt", "repro")
        rel_impact = make_artifact(case, "impact.txt", "impact")
        _append(case, [
            {"v": 2, "type": "evidence", "id": "E2", "at": NOW, "hypothesis": "H1",
             "role": "reproduction", "effect": "supports", "artifact": rel_repro,
             "sha256": _sha(case, rel_repro), "summary": "复现"},
            {"v": 2, "type": "evidence", "id": "E3", "at": NOW, "hypothesis": "H1",
             "role": "impact", "effect": "supports", "artifact": rel_impact,
             "sha256": _sha(case, rel_impact), "summary": "影响"},
            {"v": 2, "type": "verdict", "id": "V1", "at": NOW, "hypothesis": "H1",
             "status": "confirmed", "evidence": ["E1", "E2", "E3"],
             "reason": "Verifier 独立复核通过", "verifier_run": "R2"},
        ])
        result = run_prism("verify", str(case))
        assert result.returncode == 0, result.stdout + result.stderr
        assert "REPORT gate: PASS" in result.stdout


class TestSingleTargetClosedLoop:
    def test_commander_to_report_produces_traceable_finding(self, tmp_path: Path):
        case = tmp_path / "case"
        (case / "artifacts").mkdir(parents=True)
        (case / "results").mkdir(parents=True)
        rel_obs = make_artifact(case, "obs.txt", "observation payload")
        rel_repro = make_artifact(case, "repro.txt", "reproduction payload")
        rel_impact = make_artifact(case, "impact.txt", "impact payload")

        # 1. Commander：reason 产生假设与执行意图，入账（v2）
        _append(case, [
            {"v": 2, "type": "approval", "id": "A1", "at": NOW,
             "action_class": "probe", "target_scope": "192.0.2.10 web",
             "effect": "reversible", "status": "approved", "decided_by": "user"},
            {"v": 2, "type": "hypothesis", "id": "H1", "at": NOW,
             "claim": "192.0.2.10 /admin 存在未授权访问", "scope": "192.0.2.10 web",
             "disprove_if": ["控制请求返回 401"]},
            {"v": 2, "type": "intent", "id": "I1", "at": NOW, "event": "created",
             "title": "探测 /admin", "objective": "对 H1 采集证据",
             "angle": "web-direct", "target": "192.0.2.10"},
        ])

        # 2. 主 Agent 装配 Worker 包（pack）
        packed = run_prism("pack", str(case), "--hypothesis", "H1")
        assert packed.returncode == 0, packed.stderr

        # 3. Worker 返回 Result（不写账本，只给结构化结果）
        worker_result = models.WorkerResult.model_validate(
            {
                "schema_version": 2,
                "run_id": "R001",
                "intent_id": "I1",
                "idempotency_key": "idem-R001-001",
                "status": "needs_verification",
                "summary": "观察到 /admin 无认证可达，已固定证据",
                "evidence": [
                    {
                        "hypothesis": "H1",
                        "role": "observation",
                        "effect": "supports",
                        "artifact": rel_obs,
                        "sha256": _sha(case, rel_obs),
                        "summary": "GET /admin 200",
                    },
                    {
                        "hypothesis": "H1",
                        "role": "reproduction",
                        "effect": "supports",
                        "artifact": rel_repro,
                        "sha256": _sha(case, rel_repro),
                        "summary": "复现：3/3 次无认证可达",
                    },
                ],
            }
        )

        # 4. 主 Agent 是唯一入库者：claim → ingest（建议不直接 confirmed）
        claimed = run_prism("claim", str(case), "--intent", "I1",
                            "--run", "R001", "--actor", "worker")
        assert claimed.returncode == 0, claimed.stdout + claimed.stderr
        result_path = case / "results" / "worker-R001.json"
        result_path.write_text(
            json.dumps(worker_result.model_dump(), ensure_ascii=False),
            encoding="utf-8",
        )
        ingested = run_prism("ingest", str(case), "--result", str(result_path))
        assert ingested.returncode == 0, ingested.stdout + ingested.stderr

        # 5. 独立 Verifier：只读 verify-pack（不含 Worker 叙事）
        verifier_pack = run_prism("verify-pack", str(case), "--hypothesis", "H1")
        assert verifier_pack.returncode == 0, verifier_pack.stderr

        # 6. Verifier 结果驱动裁决：impact 证据 + confirmed（verifier_run 溯源）
        _append(case, [
            {"v": 2, "type": "evidence", "id": "E3", "at": NOW, "hypothesis": "H1",
             "role": "impact", "effect": "supports", "artifact": rel_impact,
             "sha256": _sha(case, rel_impact), "summary": "可列用户，未尝试写入",
             "run": "R002", "actor": "verifier"},
            {"v": 2, "type": "verdict", "id": "V1", "at": NOW, "hypothesis": "H1",
             "status": "confirmed", "evidence": ["E1", "E2", "E3"],
             "reason": "Verifier 独立复核通过", "verifier_run": "R002"},
        ])

        # 7. 报告门禁通过，Finding 可回溯
        report = run_prism("verify", str(case))
        assert report.returncode == 0, report.stdout + report.stderr
        assert "REPORT gate: PASS" in report.stdout

        ledger_lines = (case / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
        records = [json.loads(line) for line in ledger_lines]
        verdicts = [r for r in records if r["type"] == "verdict"]
        assert verdicts[0]["status"] == "confirmed"
        assert verdicts[0]["verifier_run"] == "R002"
        # 证据链完整：observation → reproduction → impact 全部在账
        roles = {r["role"] for r in records if r["type"] == "evidence"}
        assert roles == {"observation", "reproduction", "impact"}
