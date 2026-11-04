"""v1 账本单元级回归测试。

锁定 docs/design/PENTEST_SKILL_UPGRADE_PLAN.md §2.1 列出的既有正确行为：
- 证据路径逃逸检查、SHA-256、UTF-8 严格读取、重复 ID 和引用校验
- observation / reproduction / impact 证据角色与 confirmed 门禁
- provisional / confirmed / killed / inconclusive / deferred 裁决语义
- 黑板折叠策略与溢出保护
"""

from __future__ import annotations

import json

import pytest
from conftest import make_artifact


def hypothesis(
    record_id, claim="claim", scope="scope", disprove=None, at="2026-01-01T00:00:00Z"
):
    return {
        "v": 1,
        "type": "hypothesis",
        "id": record_id,
        "at": at,
        "claim": claim,
        "scope": scope,
        "disprove_if": disprove if disprove is not None else ["condition"],
    }


def evidence(
    record_id, hypothesis_id, role, effect, artifact, sha256, summary="summary"
):
    return {
        "v": 1,
        "type": "evidence",
        "id": record_id,
        "at": "2026-01-01T00:00:01Z",
        "hypothesis": hypothesis_id,
        "role": role,
        "effect": effect,
        "artifact": artifact,
        "sha256": sha256,
        "summary": summary,
    }


def verdict(record_id, hypothesis_id, status, evidence_ids, reason="reason"):
    return {
        "v": 1,
        "type": "verdict",
        "id": record_id,
        "at": "2026-01-01T00:00:02Z",
        "hypothesis": hypothesis_id,
        "status": status,
        "evidence": evidence_ids,
        "reason": reason,
    }


@pytest.fixture()
def complete_case(ledger_module, case_dir):
    """含一条已确认假设（三角色证据齐全）的案件，且已落盘到 ledger.jsonl。"""
    art = make_artifact(case_dir, "http.txt", "HTTP/1.1 200 OK reserved-range target")
    digest = ledger_module.digest(case_dir / art)
    records = [
        hypothesis("H1", claim="目标存在未授权访问", scope="192.0.2.10 web"),
        evidence("E1", "H1", "observation", "supports", art, digest),
        evidence("E2", "H1", "reproduction", "supports", art, digest),
        evidence("E3", "H1", "impact", "supports", art, digest),
        verdict("V1", "H1", "confirmed", ["E1", "E2", "E3"]),
    ]
    ledger = case_dir / "ledger.jsonl"
    ledger.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )
    return case_dir, records


class TestResolveArtifact:
    def test_absolute_path_rejected(self, ledger_module, case_dir):
        with pytest.raises(ledger_module.LedgerError, match="must be relative"):
            ledger_module.resolve_artifact(
                case_dir, str(case_dir / "artifacts" / "a.txt")
            )

    def test_path_escape_rejected(self, ledger_module, case_dir):
        with pytest.raises(ledger_module.LedgerError, match="escapes"):
            ledger_module.resolve_artifact(case_dir, "../outside.txt")

    def test_missing_artifact_rejected(self, ledger_module, case_dir):
        with pytest.raises(ledger_module.LedgerError, match="does not exist"):
            ledger_module.resolve_artifact(case_dir, "artifacts/nope.txt")

    def test_valid_relative_path_resolved(self, ledger_module, case_dir):
        relative = make_artifact(case_dir, "ok.txt", "ok")
        resolved = ledger_module.resolve_artifact(case_dir, relative)
        assert resolved == (case_dir / relative).resolve()


class TestIdAndTextValidation:
    def test_invalid_id_pattern(self, ledger_module):
        with pytest.raises(ledger_module.LedgerError, match="invalid id"):
            ledger_module.check_id("1bad", "H")

    def test_wrong_prefix(self, ledger_module):
        with pytest.raises(ledger_module.LedgerError, match="must start with"):
            ledger_module.check_id("E1", "H")

    def test_empty_text_rejected(self, ledger_module):
        with pytest.raises(ledger_module.LedgerError, match="must not be empty"):
            ledger_module.validate_short_text("   ", "claim")

    def test_over_limit_text_rejected(self, ledger_module):
        with pytest.raises(ledger_module.LedgerError, match="exceeds"):
            ledger_module.validate_short_text("x" * 241, "claim")

    def test_whitespace_collapsed(self, ledger_module):
        assert ledger_module.validate_short_text(" a \n b ", "claim") == "a b"


class TestLedgerStructure:
    def test_schema_version_mismatch_rejected(self, ledger_module, case_dir):
        bad = hypothesis("H1")
        bad["v"] = 2
        with pytest.raises(ledger_module.LedgerError, match="v must be"):
            ledger_module.validate(case_dir, [bad])

    def test_unknown_type_rejected(self, ledger_module, case_dir):
        bad = hypothesis("H1")
        bad["type"] = "fact"
        with pytest.raises(ledger_module.LedgerError, match="unknown record type"):
            ledger_module.validate(case_dir, [bad])

    def test_duplicate_id_rejected(self, ledger_module, case_dir):
        with pytest.raises(ledger_module.LedgerError, match="duplicate id"):
            ledger_module.validate(case_dir, [hypothesis("H1"), hypothesis("H1")])

    def test_blank_line_rejected(self, ledger_module, case_dir, tmp_path):
        ledger = tmp_path / "bad.jsonl"
        ledger.write_text("\n", encoding="utf-8")
        with pytest.raises(ledger_module.LedgerError, match="blank lines"):
            ledger_module.read_records(ledger)

    def test_invalid_json_rejected(self, ledger_module, tmp_path):
        ledger = tmp_path / "bad.jsonl"
        ledger.write_text("{not json}\n", encoding="utf-8")
        with pytest.raises(ledger_module.LedgerError, match="invalid JSON"):
            ledger_module.read_records(ledger)

    def test_invalid_utf8_rejected_with_offset(self, ledger_module, tmp_path):
        ledger = tmp_path / "bad.jsonl"
        ledger.write_bytes(b'{"a": "\xff\xfe"}\n')
        with pytest.raises(ledger_module.LedgerError, match="not valid UTF-8"):
            ledger_module.read_records(ledger)

    def test_non_object_record_rejected(self, ledger_module, tmp_path):
        ledger = tmp_path / "bad.jsonl"
        ledger.write_text("[1, 2]\n", encoding="utf-8")
        with pytest.raises(ledger_module.LedgerError, match="JSON object"):
            ledger_module.read_records(ledger)

    def test_evidence_before_hypothesis_rejected(self, ledger_module, case_dir):
        art = make_artifact(case_dir, "a.txt", "a")
        record = evidence("E1", "H9", "observation", "supports", art, "0" * 64)
        with pytest.raises(ledger_module.LedgerError, match="missing prior hypothesis"):
            ledger_module.validate(case_dir, [record])

    def test_verdict_reusing_other_hypothesis_evidence_rejected(
        self, ledger_module, case_dir
    ):
        art = make_artifact(case_dir, "a.txt", "a")
        digest = ledger_module.digest(case_dir / art)
        records = [
            hypothesis("H1"),
            hypothesis("H2"),
            evidence("E1", "H1", "observation", "supports", art, digest),
        ]
        with pytest.raises(
            ledger_module.LedgerError, match="belongs to another hypothesis"
        ):
            ledger_module.validate(
                case_dir, [*records, verdict("V1", "H2", "confirmed", ["E1"])]
            )


class TestEvidenceIntegrity:
    def test_sha256_mismatch_rejected(self, ledger_module, case_dir):
        art = make_artifact(case_dir, "a.txt", "content")
        records = [
            hypothesis("H1"),
            evidence("E1", "H1", "observation", "supports", art, "0" * 64),
        ]
        with pytest.raises(ledger_module.LedgerError, match="SHA-256 mismatch"):
            ledger_module.validate(case_dir, records)

    def test_invalid_role_rejected(self, ledger_module, case_dir):
        art = make_artifact(case_dir, "a.txt", "content")
        digest = ledger_module.digest(case_dir / art)
        record = evidence("E1", "H1", "smell", "supports", art, digest)
        with pytest.raises(ledger_module.LedgerError, match="invalid evidence role"):
            ledger_module.validate(case_dir, [hypothesis("H1"), record])

    def test_invalid_effect_rejected(self, ledger_module, case_dir):
        art = make_artifact(case_dir, "a.txt", "content")
        digest = ledger_module.digest(case_dir / art)
        record = evidence("E1", "H1", "observation", "maybe", art, digest)
        with pytest.raises(ledger_module.LedgerError, match="invalid evidence effect"):
            ledger_module.validate(case_dir, [hypothesis("H1"), record])

    def test_valid_complete_case_passes(self, ledger_module, complete_case):
        case_dir, records = complete_case
        all_ids = ledger_module.validate(case_dir, records)
        assert set(all_ids) == {"H1", "E1", "E2", "E3", "V1"}


class TestVerdictSemantics:
    def _with_evidence(self, ledger_module, case_dir, roles):
        art = make_artifact(case_dir, "a.txt", "content")
        digest = ledger_module.digest(case_dir / art)
        records = [hypothesis("H1")]
        ids = []
        for index, role in enumerate(roles, 1):
            record_id = f"E{index}"
            ids.append(record_id)
            records.append(evidence(record_id, "H1", role, "supports", art, digest))
        return records, ids

    def test_confirmed_requires_all_three_roles(self, ledger_module, case_dir):
        records, ids = self._with_evidence(
            ledger_module, case_dir, ["observation", "reproduction"]
        )
        with pytest.raises(
            ledger_module.LedgerError, match="confirmed verdict missing roles: impact"
        ):
            ledger_module.validate(
                case_dir, [*records, verdict("V1", "H1", "confirmed", ids)]
            )

    def test_provisional_requires_observation_and_reproduction(
        self, ledger_module, case_dir
    ):
        records, ids = self._with_evidence(ledger_module, case_dir, ["observation"])
        with pytest.raises(
            ledger_module.LedgerError,
            match="provisional verdict missing roles: reproduction",
        ):
            ledger_module.validate(
                case_dir, [*records, verdict("V1", "H1", "provisional", ids)]
            )

    def test_killed_requires_refutation(self, ledger_module, case_dir):
        records, ids = self._with_evidence(ledger_module, case_dir, ["observation"])
        with pytest.raises(ledger_module.LedgerError, match="killed verdict requires"):
            ledger_module.validate(
                case_dir, [*records, verdict("V1", "H1", "killed", ids)]
            )

    def test_killed_accepts_refutation_role(self, ledger_module, case_dir):
        records, ids = self._with_evidence(ledger_module, case_dir, ["observation"])
        art = make_artifact(case_dir, "b.txt", "other")
        digest = ledger_module.digest(case_dir / art)
        records.append(evidence("E9", "H1", "refutation", "context", art, digest))
        ledger_module.validate(
            case_dir, [*records, verdict("V1", "H1", "killed", [*ids, "E9"])]
        )

    def test_killed_accepts_refutes_effect(self, ledger_module, case_dir):
        records, ids = self._with_evidence(ledger_module, case_dir, ["observation"])
        art = make_artifact(case_dir, "b.txt", "other")
        digest = ledger_module.digest(case_dir / art)
        records.append(evidence("E9", "H1", "observation", "refutes", art, digest))
        ledger_module.validate(
            case_dir, [*records, verdict("V1", "H1", "killed", [*ids, "E9"])]
        )

    def test_verdict_without_evidence_rejected(self, ledger_module, case_dir):
        with pytest.raises(ledger_module.LedgerError, match="must reference evidence"):
            ledger_module.validate(
                case_dir, [hypothesis("H1"), verdict("V1", "H1", "confirmed", [])]
            )

    def test_unknown_status_rejected(self, ledger_module, case_dir):
        records, ids = self._with_evidence(ledger_module, case_dir, ["observation"])
        with pytest.raises(ledger_module.LedgerError, match="invalid verdict status"):
            ledger_module.validate(
                case_dir, [*records, verdict("V1", "H1", "maybe", ids)]
            )


class TestReportGate:
    def test_open_provisional_blocks_report(self, ledger_module, complete_case):
        case_dir, records = complete_case
        records.append(hypothesis("H2", claim="另一假设", scope="s"))
        art = make_artifact(case_dir, "b.txt", "b")
        digest = ledger_module.digest(case_dir / art)
        records.append(evidence("E4", "H2", "observation", "supports", art, digest))
        records.append(evidence("E5", "H2", "reproduction", "supports", art, digest))
        records.append(verdict("V2", "H2", "provisional", ["E4", "E5"]))
        with pytest.raises(ledger_module.LedgerError, match="REPORT gate 未通过"):
            ledger_module.report_gate(records)

    def test_closed_confirmed_passes_report_gate(self, ledger_module, complete_case):
        _, records = complete_case
        ledger_module.report_gate(records)


class TestBlackboard:
    def test_sections_present(self, ledger_module, complete_case):
        _, records = complete_case
        board = ledger_module.render_blackboard(records)
        for section in ("[案件黑板 v1]", "已确认事实", "活跃假设", "暂缓假设", "错误"):
            assert section in board
        assert "H1" in board

    def test_active_shows_missing_roles(self, ledger_module, case_dir):
        art = make_artifact(case_dir, "a.txt", "a")
        digest = ledger_module.digest(case_dir / art)
        records = [
            hypothesis("H1"),
            evidence("E1", "H1", "observation", "supports", art, digest),
        ]
        board = ledger_module.render_blackboard(records)
        assert "缺失：复现、影响" in board

    def test_deferred_collapsed_when_board_overflows(self, ledger_module, case_dir):
        art = make_artifact(case_dir, "a.txt", "a")
        digest = ledger_module.digest(case_dir / art)
        records = []
        # 25 条暂缓假设（各含 1 条证据与 deferred 裁决），全量展开会超过上限
        for index in range(1, 26):
            hid = f"H{index:03d}"
            eid = f"E{index:03d}"
            records.append(hypothesis(hid, claim="长假设" * 50, scope="范围" * 30))
            records.append(evidence(eid, hid, "observation", "supports", art, digest))
            records.append(verdict(f"V{index:03d}", hid, "deferred", [eid]))
        # 15 条活跃假设，把全量黑板推过 8000 字符
        for index in range(26, 41):
            records.append(
                hypothesis(f"H{index:03d}", claim="长假设" * 50, scope="范围" * 30)
            )
        board = ledger_module.render_blackboard(records)
        assert "已折叠：暂缓假设 25 条" in board
        assert len(board) <= ledger_module.BOARD_LIMIT

    def test_overflow_raises_after_full_collapse(self, ledger_module, case_dir):
        records = [
            hypothesis(f"H{index}", claim="长假设" * 40, scope="范围" * 30)
            for index in range(1, 61)
        ]
        with pytest.raises(ledger_module.LedgerError, match="黑板溢出"):
            ledger_module.render_blackboard(records)

    def test_error_board_reports_integrity_failure(self, ledger_module):
        board = ledger_module.error_board(
            ledger_module.LedgerError("line 3: invalid JSON: x")
        )
        assert "完整性：失败" in board
        assert "invalid JSON" in board


class TestDelta:
    def test_hypothesis_delta(self, ledger_module, complete_case):
        _, records = complete_case
        record = hypothesis("H9", claim="新假设", scope="s")
        message = ledger_module.delta(record, [*records, record])
        assert "假设 H9 已添加" in message
        assert "活跃" in message

    def test_evidence_delta_reports_missing_roles(self, ledger_module, complete_case):
        _, records = complete_case
        art = make_artifact(complete_case[0], "c.txt", "c")
        record = evidence("E9", "H1", "impact", "supports", art, "0" * 64)
        message = ledger_module.delta(record, [*records, record])
        assert "证据 E9 已添加" in message

    def test_verdict_delta_reports_status(self, ledger_module, complete_case):
        _, records = complete_case
        record = verdict("V9", "H1", "killed", ["E1"])
        message = ledger_module.delta(record, [*records, record])
        assert "裁决 V9 已添加" in message
        assert "已证伪" in message


class TestAppendDurability:
    def test_append_writes_jsonl_line_and_report(self, ledger_module, complete_case):
        case_dir, records = complete_case
        record = hypothesis("H2", claim="追加", scope="s")
        ledger_module.append(case_dir, record)
        lines = (case_dir / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == len(records) + 1
        assert json.loads(lines[-1])["id"] == "H2"
        assert (case_dir / "evidence-validation.md").exists()

    def test_append_rejects_invalid_record_without_mutating_ledger(
        self, ledger_module, complete_case
    ):
        case_dir, _records = complete_case
        before = (case_dir / "ledger.jsonl").read_text(encoding="utf-8")
        with pytest.raises(ledger_module.LedgerError):
            ledger_module.append(case_dir, hypothesis("H1"))
        assert (case_dir / "ledger.jsonl").read_text(encoding="utf-8") == before

    def test_no_temp_files_left_behind(self, ledger_module, complete_case):
        case_dir, _ = complete_case
        ledger_module.append(case_dir, hypothesis("H3", claim="原子", scope="s"))
        leftovers = [p.name for p in case_dir.iterdir() if p.name.endswith(".tmp")]
        assert leftovers == []
