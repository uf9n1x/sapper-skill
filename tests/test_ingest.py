"""P2 并发与恢复测试（T-031）。

锁定三条验收：
1. 并发结果不丢——两个进程同时 ingest，全部记录落账且回放通过
2. 重放不重复——同一结果包重复 ingest 幂等（账本逐字节不变）
3. 中断后可恢复——损坏尾行可修复；过期 lease 可恢复决策
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from conftest import PROJECT_ROOT, run_prism
from prism import state

NOW = "2026-01-01T00:00:00Z"


def seed_case(case: Path) -> str:
    """v2 案件：审批 + 事实 + 假设 + Intent（待 claim）。返回 Intent ID。"""
    case.mkdir(parents=True)
    (case / "artifacts").mkdir()
    (case / "results").mkdir()
    records = [
        {
            "v": 2,
            "type": "approval",
            "id": "A1",
            "at": NOW,
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
            "at": NOW,
            "kind": "service",
            "target": "192.0.2.10:80",
            "title": "example-httpd",
            "summary": "80 端口 HTTP",
        },
        {
            "v": 2,
            "type": "hypothesis",
            "id": "H1",
            "at": NOW,
            "claim": "192.0.2.10 /admin 存在未授权访问",
            "scope": "192.0.2.10 web",
            "disprove_if": ["控制请求返回 401"],
            "linked_facts": [],
        },
        {
            "v": 2,
            "type": "intent",
            "id": "I1",
            "at": NOW,
            "event": "created",
            "title": "验证 /admin",
            "objective": "确认未授权访问",
            "angle": "web-direct",
            "target": "192.0.2.10:80",
        },
    ]
    (case / "ledger.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
        encoding="utf-8",
        newline="\n",
    )
    return "I1"


def make_result(path: Path, run_id: str, key: str, artifact: str, digest: str) -> Path:
    result = {
        "schema_version": 2,
        "run_id": run_id,
        "intent_id": "I1",
        "idempotency_key": key,
        "status": "needs_verification",
        "summary": "观察到 /admin 无认证可达",
        "evidence": [
            {
                "hypothesis": "H1",
                "role": "observation",
                "effect": "supports",
                "artifact": artifact,
                "sha256": digest,
                "summary": "GET /admin 200",
            }
        ],
    }
    path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return path


class TestClaim:
    def test_claim_creates_lease_and_run(self, tmp_path: Path):
        case = tmp_path / "case"
        seed_case(case)
        result = run_prism(
            "claim",
            str(case),
            "--intent",
            "I1",
            "--run",
            "R1",
            "--actor",
            "worker",
            "--lease-minutes",
            "30",
        )
        assert result.returncode == 0, result.stderr
        derived = state.replay(case)
        assert derived.intents["I1"]["status"] == "in_progress"
        assert derived.runs["R1"]["status"] == "running"
        assert derived.runs["R1"]["lease_expires_at"] is not None

    def test_double_claim_same_run_rejected(self, tmp_path: Path):
        case = tmp_path / "case"
        seed_case(case)
        args = (
            "claim",
            str(case),
            "--intent",
            "I1",
            "--run",
            "R1",
            "--actor",
            "worker",
        )
        assert run_prism(*args).returncode == 0
        again = run_prism(*args)
        assert again.returncode == 1
        assert "R1" in again.stderr

    def test_claim_completed_intent_rejected(self, tmp_path: Path):
        case = tmp_path / "case"
        seed_case(case)
        records = (case / "ledger.jsonl").read_text(encoding="utf-8")
        records += (
            json.dumps(
                {
                    "v": 2,
                    "type": "intent",
                    "id": "I1",
                    "at": "2026-01-01T01:00:00Z",
                    "event": "completed",
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        (case / "ledger.jsonl").write_text(records, encoding="utf-8", newline="\n")
        result = run_prism(
            "claim", str(case), "--intent", "I1", "--run", "R1", "--actor", "worker"
        )
        assert result.returncode == 1


class TestIngest:
    def test_happy_path_appends_evidence_and_completes_run(self, tmp_path: Path):
        case = tmp_path / "case"
        seed_case(case)
        artifact = case / "artifacts" / "obs.txt"
        artifact.write_text("observation payload", encoding="utf-8")
        result_file = make_result(
            case / "results" / "R1.json", "R1", "idem-1", "artifacts/obs.txt", None
        )
        # sha256 留空 → 入库方计算
        import hashlib

        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        result_file = make_result(
            case / "results" / "R1.json",
            "R1",
            "idem-1",
            "artifacts/obs.txt",
            digest,
        )
        run_prism(
            "claim", str(case), "--intent", "I1", "--run", "R1", "--actor", "worker"
        )
        result = run_prism("ingest", str(case), "--result", str(result_file))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["ingested"]["evidence"] == 1
        derived = state.replay(case)
        assert derived.runs["R1"]["status"] == "completed"
        assert any(e.id == "E1" for e in derived.evidence_by_id.values())

    def test_missing_artifact_rejected_without_mutation(self, tmp_path: Path):
        case = tmp_path / "case"
        seed_case(case)
        before = (case / "ledger.jsonl").read_text(encoding="utf-8")
        result_file = make_result(
            case / "results" / "R1.json",
            "R1",
            "idem-1",
            "artifacts/ghost.txt",
            "a" * 64,
        )
        result = run_prism("ingest", str(case), "--result", str(result_file))
        assert result.returncode == 1
        assert (case / "ledger.jsonl").read_text(encoding="utf-8") == before

    def test_duplicate_idempotency_key_noop(self, tmp_path: Path):
        case = tmp_path / "case"
        seed_case(case)
        artifact = case / "artifacts" / "obs.txt"
        artifact.write_text("payload", encoding="utf-8")
        import hashlib

        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        result_file = make_result(
            case / "results" / "R1.json",
            "R1",
            "idem-1",
            "artifacts/obs.txt",
            digest,
        )
        run_prism(
            "claim", str(case), "--intent", "I1", "--run", "R1", "--actor", "worker"
        )
        first = run_prism("ingest", str(case), "--result", str(result_file))
        assert first.returncode == 0
        ledger_after_first = (case / "ledger.jsonl").read_text(encoding="utf-8")
        second = run_prism("ingest", str(case), "--result", str(result_file))
        assert second.returncode == 0
        assert json.loads(second.stdout)["status"] == "duplicate"
        assert (case / "ledger.jsonl").read_text(encoding="utf-8") == ledger_after_first

    def test_concurrent_ingests_both_survive(self, tmp_path: Path):
        """验收 1：并发结果不丢。两个进程同时入库，全部落账。"""
        case = tmp_path / "case"
        seed_case(case)
        import hashlib

        results = []
        for index in (1, 2):
            artifact = case / "artifacts" / f"obs{index}.txt"
            artifact.write_text(f"payload {index}", encoding="utf-8")
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            results.append(
                make_result(
                    case / "results" / f"R{index}.json",
                    f"R{index}",
                    f"idem-{index}",
                    f"artifacts/obs{index}.txt",
                    digest,
                )
            )

        outputs: list[subprocess.CompletedProcess] = [None, None]

        def launch(index: int):
            outputs[index] = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(PROJECT_ROOT / "scripts" / "prism.py"),
                    "ingest",
                    str(case),
                    "--result",
                    str(results[index]),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                cwd=str(PROJECT_ROOT),
                check=False,
            )

        threads = [threading.Thread(target=launch, args=(i,)) for i in (0, 1)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        for index, output in enumerate(outputs):
            assert output.returncode == 0, f"ingest {index}: {output.stderr}"
        derived = state.replay(case)
        evidence_ids = set(derived.evidence_by_id)
        assert "E1" in evidence_ids and "E2" in evidence_ids
        assert derived.runs["R1"]["status"] == "completed"
        assert derived.runs["R2"]["status"] == "completed"


class TestRecovery:
    def test_partial_tail_detected_and_repaired(self, tmp_path: Path):
        """验收 3：中断后可恢复（崩溃留下的半行可修复）。"""
        case = tmp_path / "case"
        seed_case(case)
        with open(case / "ledger.jsonl", "a", encoding="utf-8") as handle:
            handle.write('{"v":2,"type":"fact","id":"F2","at":"2026-01-01T00')  # 半行
        with pytest.raises(state.ReplayError):
            state.replay(case)
        result = run_prism("repair", str(case))
        assert result.returncode == 0, result.stderr
        derived = state.replay(case)
        assert "F2" not in derived.facts
        assert derived.counts["hypotheses"] == 1  # 完整记录未受损

    def test_expired_lease_recovery_decision(self, tmp_path: Path):
        case = tmp_path / "case"
        seed_case(case)
        # 过期 lease 的 claim（lease 已在 2026-01-02 到期）
        result = run_prism(
            "claim",
            str(case),
            "--intent",
            "I1",
            "--run",
            "R1",
            "--actor",
            "worker",
            "--lease-minutes",
            "1",
            "--now",
            "2026-01-01T00:00:00Z",
        )
        assert result.returncode == 0
        # 无结果包：建议 re-claim
        report = json.loads(run_prism("recover", str(case), "--json").stdout)
        assert report["actions"][0]["action"] == "re_claim"
        # 结果包落盘：建议 ingest
        make_result(
            case / "results" / "R1.json",
            "R1",
            "idem-1",
            "artifacts/x.txt",
            "a" * 64,
        )
        report = json.loads(run_prism("recover", str(case), "--json").stdout)
        assert report["actions"][0]["action"] == "ingest"

    def test_active_lease_not_reported(self, tmp_path: Path):
        case = tmp_path / "case"
        seed_case(case)
        run_prism(
            "claim",
            str(case),
            "--intent",
            "I1",
            "--run",
            "R1",
            "--actor",
            "worker",
            "--lease-minutes",
            "60",
        )
        report = json.loads(run_prism("recover", str(case), "--json").stdout)
        assert report["actions"] == []
