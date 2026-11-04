"""冻结 v1 fixture 守卫测试（T-010）。

fixture 是 v1 账本行为的黄金样本，也是 v1→v2 迁移（T-030）的输入。
本文件锁定其完整性、内容清单与门禁行为；fixture 本体禁止改写。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from conftest import FIXTURE_V1_CASE, run_cli

EXPECTED_STATUSES = {
    "H1": "confirmed",
    "H2": "killed",
    "H3": "provisional",
    "H4": "deferred",
    "H5": "active",
    "H6": "inconclusive",
}
EXPECTED_RECORD_COUNT = 20
EXPECTED_ARTIFACT_COUNT = 6


def _records() -> list[dict]:
    import json

    ledger = FIXTURE_V1_CASE / "ledger.jsonl"
    text = ledger.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


class TestFixtureIntegrity:
    def test_ledger_exists_with_frozen_record_count(self):
        records = _records()
        assert len(records) == EXPECTED_RECORD_COUNT

    def test_record_type_inventory(self):
        records = _records()
        by_type: dict[str, int] = {}
        for record in records:
            by_type[record["type"]] = by_type.get(record["type"], 0) + 1
        assert by_type == {"hypothesis": 6, "evidence": 9, "verdict": 5}

    def test_artifact_inventory(self):
        artifacts = list((FIXTURE_V1_CASE / "artifacts").glob("*.txt"))
        assert len(artifacts) == EXPECTED_ARTIFACT_COUNT

    def test_all_timestamps_frozen(self):
        for record in _records():
            assert record["at"].startswith("2026-01-01T00:")

    def test_no_real_target_data(self):
        """安全编码底线：fixture 只允许保留地址与占位域名。"""
        text = (FIXTURE_V1_CASE / "ledger.jsonl").read_text(encoding="utf-8")
        for artifact in (FIXTURE_V1_CASE / "artifacts").glob("*.txt"):
            text += artifact.read_text(encoding="utf-8")
        assert "192.0.2." in text or "example.com" in text
        banned = ["10.0.", "172.16.", "192.168.", ".qq.com", ".baidu.com", ".aliyun"]
        for marker in banned:
            assert marker not in text, f"疑似真实/内网目标数据泄漏：{marker}"

    def test_derived_statuses_match_expectation(self):
        records = _records()
        hypotheses = {r["id"] for r in records if r["type"] == "hypothesis"}
        verdicts = {}
        for record in records:
            if record["type"] == "verdict":
                verdicts[record["hypothesis"]] = record["status"]
        assert hypotheses == set(EXPECTED_STATUSES)
        for hypothesis_id, expected in EXPECTED_STATUSES.items():
            actual = verdicts.get(hypothesis_id, "active")
            assert actual == expected, f"{hypothesis_id} 应为 {expected}，实际 {actual}"


class TestFixtureBehavior:
    def test_verify_passes_on_copy(self, tmp_path: Path):
        case = tmp_path / "case"
        shutil.copytree(FIXTURE_V1_CASE, case)
        result = run_cli("verify", str(case))
        assert result.returncode == 0
        assert f"Integrity: PASS ({EXPECTED_RECORD_COUNT} records)" in result.stdout

    def test_report_gate_blocked_by_open_provisional(self, tmp_path: Path):
        case = tmp_path / "case"
        shutil.copytree(FIXTURE_V1_CASE, case)
        result = run_cli("verify", str(case), "--report")
        assert result.returncode == 1
        assert "REPORT gate 未通过" in result.stderr
        assert "H3" in result.stderr

    def test_frozen_report_is_golden_render(self, tmp_path: Path):
        case = tmp_path / "case"
        shutil.copytree(FIXTURE_V1_CASE, case)
        frozen = (FIXTURE_V1_CASE / "evidence-validation.md").read_text(
            encoding="utf-8"
        )
        run_cli("render", str(case))
        regenerated = (case / "evidence-validation.md").read_text(encoding="utf-8")
        assert regenerated == frozen
