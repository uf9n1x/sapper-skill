"""v1 账本 CLI 端到端回归测试。

锁定 CLI 层行为：稳定退出码（0 成功 / 1 失败）、诊断写 stderr、
结果写 stdout、追加输出黑板 delta、原子报告替换与损坏尾行修复。
"""

from __future__ import annotations

import json
from pathlib import Path

from conftest import make_artifact, run_cli


class TestHappyPath:
    def test_full_confirmed_lifecycle(self, tmp_path: Path):
        case = tmp_path / "case"
        art = make_artifact(case, "resp.txt", "reserved-range observation payload")

        assert (
            run_cli(
                "hypothesis",
                str(case),
                "--id",
                "H1",
                "--claim",
                "目标存在未授权访问",
                "--scope",
                "192.0.2.10 web",
                "--disprove-if",
                "访问返回403",
            ).returncode
            == 0
        )
        for evidence_id, role in (
            ("E1", "observation"),
            ("E2", "reproduction"),
            ("E3", "impact"),
        ):
            result = run_cli(
                "evidence",
                str(case),
                "--id",
                evidence_id,
                "--hypothesis",
                "H1",
                "--role",
                role,
                "--effect",
                "supports",
                "--artifact",
                art,
                "--summary",
                f"{role} summary",
            )
            assert result.returncode == 0, result.stderr
            assert f"证据 {evidence_id} 已添加" in result.stdout

        verdict = run_cli(
            "verdict",
            str(case),
            "--id",
            "V1",
            "--hypothesis",
            "H1",
            "--status",
            "confirmed",
            "--evidence",
            "E1",
            "E2",
            "E3",
            "--reason",
            "三角色闭环",
        )
        assert verdict.returncode == 0
        assert "裁决 V1 已添加" in verdict.stdout

        verify = run_cli("verify", str(case))
        assert verify.returncode == 0
        assert "Integrity: PASS (5 records)" in verify.stdout

        report = run_cli("verify", str(case), "--report")
        assert report.returncode == 0
        assert "REPORT gate: PASS" in report.stdout

    def test_case_directory_auto_created(self, tmp_path: Path):
        case = tmp_path / "nested" / "case"
        result = run_cli(
            "hypothesis",
            str(case),
            "--id",
            "H1",
            "--claim",
            "c",
            "--scope",
            "s",
            "--disprove-if",
            "d",
        )
        assert result.returncode == 0
        assert (case / "ledger.jsonl").exists()
        assert (case / "artifacts").is_dir()
        assert (case / "evidence-validation.md").exists()

    def test_context_plain_outputs_blackboard(self, tmp_path: Path):
        case = tmp_path / "case"
        run_cli(
            "hypothesis",
            str(case),
            "--id",
            "H1",
            "--claim",
            "c",
            "--scope",
            "s",
            "--disprove-if",
            "d",
        )
        result = run_cli("context", str(case), "--plain")
        assert result.returncode == 0
        assert "[案件黑板 v1]" in result.stdout
        assert "完整性：通过" in result.stdout

    def test_context_hook_json_mode(self, tmp_path: Path):
        case = tmp_path / "case"
        run_cli(
            "hypothesis",
            str(case),
            "--id",
            "H1",
            "--claim",
            "c",
            "--scope",
            "s",
            "--disprove-if",
            "d",
        )
        result = run_cli("context", str(case))
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"

    def test_render_prints_report_path(self, tmp_path: Path):
        case = tmp_path / "case"
        run_cli(
            "hypothesis",
            str(case),
            "--id",
            "H1",
            "--claim",
            "c",
            "--scope",
            "s",
            "--disprove-if",
            "d",
        )
        result = run_cli("render", str(case))
        assert result.returncode == 0
        assert str(case / "evidence-validation.md") in result.stdout
        report_text = (case / "evidence-validation.md").read_text(encoding="utf-8")
        assert "BLACKBOARD:BEGIN" in report_text
        assert "## Detailed Evidence Chains" in report_text

    def test_error_context_reports_integrity_failure(self, tmp_path: Path):
        case = tmp_path / "case"
        run_cli(
            "hypothesis",
            str(case),
            "--id",
            "H1",
            "--claim",
            "c",
            "--scope",
            "s",
            "--disprove-if",
            "d",
        )
        ledger = case / "ledger.jsonl"
        ledger.write_bytes(ledger.read_bytes() + b'{"broken"\n')
        result = run_cli("context", str(case), "--plain")
        assert result.returncode == 0
        assert "完整性：失败" in result.stdout


class TestCliRejections:
    def test_missing_artifact_rejected(self, tmp_path: Path):
        case = tmp_path / "case"
        run_cli(
            "hypothesis",
            str(case),
            "--id",
            "H1",
            "--claim",
            "c",
            "--scope",
            "s",
            "--disprove-if",
            "d",
        )
        result = run_cli(
            "evidence",
            str(case),
            "--id",
            "E1",
            "--hypothesis",
            "H1",
            "--role",
            "observation",
            "--effect",
            "supports",
            "--artifact",
            "artifacts/missing.txt",
            "--summary",
            "s",
        )
        assert result.returncode == 1
        assert result.stderr.startswith("ERROR:")
        assert "does not exist" in result.stderr

    def test_absolute_artifact_path_rejected(self, tmp_path: Path):
        case = tmp_path / "case"
        make_artifact(case, "a.txt", "a")
        run_cli(
            "hypothesis",
            str(case),
            "--id",
            "H1",
            "--claim",
            "c",
            "--scope",
            "s",
            "--disprove-if",
            "d",
        )
        absolute = str(case / "artifacts" / "a.txt")
        result = run_cli(
            "evidence",
            str(case),
            "--id",
            "E1",
            "--hypothesis",
            "H1",
            "--role",
            "observation",
            "--effect",
            "supports",
            "--artifact",
            absolute,
            "--summary",
            "s",
        )
        assert result.returncode == 1
        assert "must be relative" in result.stderr

    def test_wrong_sha256_rejected(self, tmp_path: Path):
        case = tmp_path / "case"
        art = make_artifact(case, "a.txt", "content")
        run_cli(
            "hypothesis",
            str(case),
            "--id",
            "H1",
            "--claim",
            "c",
            "--scope",
            "s",
            "--disprove-if",
            "d",
        )
        result = run_cli(
            "evidence",
            str(case),
            "--id",
            "E1",
            "--hypothesis",
            "H1",
            "--role",
            "observation",
            "--effect",
            "supports",
            "--artifact",
            art,
            "--sha256",
            "0" * 64,
            "--summary",
            "s",
        )
        assert result.returncode == 1
        assert "SHA-256 mismatch" in result.stderr

    def test_confirmed_missing_role_rejected(self, tmp_path: Path):
        case = tmp_path / "case"
        art = make_artifact(case, "a.txt", "content")
        run_cli(
            "hypothesis",
            str(case),
            "--id",
            "H1",
            "--claim",
            "c",
            "--scope",
            "s",
            "--disprove-if",
            "d",
        )
        run_cli(
            "evidence",
            str(case),
            "--id",
            "E1",
            "--hypothesis",
            "H1",
            "--role",
            "observation",
            "--effect",
            "supports",
            "--artifact",
            art,
            "--summary",
            "s",
        )
        result = run_cli(
            "verdict",
            str(case),
            "--id",
            "V1",
            "--hypothesis",
            "H1",
            "--status",
            "confirmed",
            "--evidence",
            "E1",
            "--reason",
            "r",
        )
        assert result.returncode == 1
        assert "missing roles" in result.stderr

    def test_duplicate_id_rejected(self, tmp_path: Path):
        case = tmp_path / "case"
        for _ in range(2):
            run_cli(
                "hypothesis",
                str(case),
                "--id",
                "H1",
                "--claim",
                "c",
                "--scope",
                "s",
                "--disprove-if",
                "d",
            )
        ledger = case / "ledger.jsonl"
        assert len(ledger.read_text(encoding="utf-8").splitlines()) == 1

    def test_report_gate_blocks_open_provisional(self, tmp_path: Path):
        case = tmp_path / "case"
        art = make_artifact(case, "a.txt", "content")
        run_cli(
            "hypothesis",
            str(case),
            "--id",
            "H1",
            "--claim",
            "c",
            "--scope",
            "s",
            "--disprove-if",
            "d",
        )
        for evidence_id, role in (("E1", "observation"), ("E2", "reproduction")):
            run_cli(
                "evidence",
                str(case),
                "--id",
                evidence_id,
                "--hypothesis",
                "H1",
                "--role",
                role,
                "--effect",
                "supports",
                "--artifact",
                art,
                "--summary",
                "s",
            )
        run_cli(
            "verdict",
            str(case),
            "--id",
            "V1",
            "--hypothesis",
            "H1",
            "--status",
            "provisional",
            "--evidence",
            "E1",
            "E2",
            "--reason",
            "r",
        )
        result = run_cli("verify", str(case), "--report")
        assert result.returncode == 1
        assert "REPORT gate 未通过" in result.stderr
        plain = run_cli("verify", str(case))
        assert plain.returncode == 0


class TestRepairTail:
    def _seeded_case(self, tmp_path: Path) -> Path:
        case = tmp_path / "case"
        art = make_artifact(case, "a.txt", "content")
        run_cli(
            "hypothesis",
            str(case),
            "--id",
            "H1",
            "--claim",
            "c",
            "--scope",
            "s",
            "--disprove-if",
            "d",
        )
        run_cli(
            "evidence",
            str(case),
            "--id",
            "E1",
            "--hypothesis",
            "H1",
            "--role",
            "observation",
            "--effect",
            "supports",
            "--artifact",
            art,
            "--summary",
            "s",
        )
        return case

    def test_damaged_tail_detected_then_repaired(self, tmp_path: Path):
        case = self._seeded_case(tmp_path)
        ledger = case / "ledger.jsonl"
        ledger.write_bytes(ledger.read_bytes() + b'{"half-written')

        broken = run_cli("verify", str(case))
        assert broken.returncode == 1
        assert "invalid JSON" in broken.stderr

        repaired = run_cli("verify", str(case), "--repair-tail")
        assert repaired.returncode == 0, repaired.stderr
        assert "Tail repaired" in repaired.stdout

        backups = list(case.glob("ledger.jsonl.bak-*"))
        assert len(backups) == 1
        assert b'{"half-written' in backups[0].read_bytes()

        after = run_cli("verify", str(case))
        assert after.returncode == 0
        assert "Integrity: PASS (2 records)" in after.stdout
        assert (case / "evidence-validation.md").exists()

    def test_repair_refuses_mid_ledger_damage(self, tmp_path: Path):
        case = self._seeded_case(tmp_path)
        run_cli(
            "hypothesis",
            str(case),
            "--id",
            "H2",
            "--claim",
            "c2",
            "--scope",
            "s",
            "--disprove-if",
            "d",
        )
        ledger = case / "ledger.jsonl"
        lines = ledger.read_text(encoding="utf-8").splitlines(keepends=True)
        lines[0] = "{corrupted\n"
        ledger.write_text("".join(lines), encoding="utf-8")
        result = run_cli("verify", str(case), "--repair-tail")
        assert result.returncode == 1
        assert "not confined to the final line" in result.stderr

    def test_repair_refuses_healthy_ledger(self, tmp_path: Path):
        case = self._seeded_case(tmp_path)
        result = run_cli("verify", str(case), "--repair-tail")
        assert result.returncode == 1
        assert "not damaged" in result.stderr


class TestAtomicReportWrite:
    def test_no_temp_files_after_appends(self, tmp_path: Path):
        case = tmp_path / "case"
        art = make_artifact(case, "a.txt", "content")
        run_cli(
            "hypothesis",
            str(case),
            "--id",
            "H1",
            "--claim",
            "c",
            "--scope",
            "s",
            "--disprove-if",
            "d",
        )
        run_cli(
            "evidence",
            str(case),
            "--id",
            "E1",
            "--hypothesis",
            "H1",
            "--role",
            "observation",
            "--effect",
            "supports",
            "--artifact",
            art,
            "--summary",
            "s",
        )
        leftovers = [p.name for p in case.iterdir() if p.name.endswith(".tmp")]
        assert leftovers == []

    def test_render_is_idempotent(self, tmp_path: Path):
        case = tmp_path / "case"
        run_cli(
            "hypothesis",
            str(case),
            "--id",
            "H1",
            "--claim",
            "c",
            "--scope",
            "s",
            "--disprove-if",
            "d",
        )
        first = run_cli("render", str(case))
        report = case / "evidence-validation.md"
        before = report.read_text(encoding="utf-8")
        run_cli("render", str(case))
        assert report.read_text(encoding="utf-8") == before
        leftovers = [p.name for p in case.iterdir() if p.name.endswith(".tmp")]
        assert leftovers == []
        assert first.returncode == 0
