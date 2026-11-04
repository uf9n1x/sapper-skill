"""v1→v2 迁移测试（T-030 验收：迁移脚本可用）。

输入：tests/fixtures/v1/case（冻结 fixture，20 条记录全状态覆盖）。
锁定：
- 迁移输出全部为 v:2 记录，记录数一致
- 语义等价：hypothesis / evidence / 最新 verdict 与 v1 派生状态一致
- artifacts 复制完整（哈希一致）
- 迁移可重放（幂等）：同一输入两次迁移输出一致
- 拒绝迁移已迁移（v2）账本
"""

from __future__ import annotations

import json
from pathlib import Path

from conftest import FIXTURE_V1_CASE, run_prism
from prism import migration, state


def migrate_fixture(tmp_path: Path) -> Path:
    out = tmp_path / "case-v2"
    result = run_prism("migrate", str(FIXTURE_V1_CASE), "--out", str(out))
    assert result.returncode == 0, result.stderr
    return out


class TestMigrate:
    def test_all_records_upgraded_to_v2(self, tmp_path: Path):
        out = migrate_fixture(tmp_path)
        lines = (out / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
        records = [json.loads(line) for line in lines]
        assert len(records) == 20
        assert all(r["v"] == 2 for r in records)

    def test_semantic_equivalence_with_v1(self, tmp_path: Path):
        out = migrate_fixture(tmp_path)
        derived = state.replay(out)
        # 假设与证据一一对应
        assert set(derived.hypotheses) == {"H1", "H2", "H3", "H4", "H5", "H6"}
        evidence_ids = {e.id for e in derived.evidence_by_id.values()}
        assert evidence_ids == {f"E{i}" for i in range(1, 10)}
        # 最新裁决状态一致（fixture 覆盖五种裁决状态；H5 保持 active 无裁决）
        latest = {h: v["status"] for h, v in derived.verdicts.items()}
        assert latest == {
            "H1": "confirmed",
            "H2": "killed",
            "H3": "provisional",
            "H4": "deferred",
            "H6": "inconclusive",
        }
        # confirmed findings 投影
        assert set(derived.findings) == {"H1"}

    def test_artifacts_copied_with_identical_hash(self, tmp_path: Path):
        out = migrate_fixture(tmp_path)
        source = FIXTURE_V1_CASE / "artifacts" / "nmap-192.0.2.10.txt"
        copied = out / "artifacts" / "nmap-192.0.2.10.txt"
        assert copied.is_file()
        import hashlib

        sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
        assert sha(source) == sha(copied)

    def test_migration_is_deterministic(self, tmp_path: Path):
        out1 = migrate_fixture(tmp_path)
        out2 = tmp_path / "again"
        result = run_prism("migrate", str(FIXTURE_V1_CASE), "--out", str(out2))
        assert result.returncode == 0
        assert (out1 / "ledger.jsonl").read_text(encoding="utf-8") == (
            out2 / "ledger.jsonl"
        ).read_text(encoding="utf-8")

    def test_rejects_already_migrated_input(self, tmp_path: Path):
        out = migrate_fixture(tmp_path)
        result = run_prism("migrate", str(out), "--out", str(tmp_path / "x"))
        assert result.returncode == 1
        assert "already" in result.stderr or "v2" in result.stderr

    def test_module_entry_matches_cli(self, tmp_path: Path):
        out = tmp_path / "direct"
        report = migration.migrate_case(FIXTURE_V1_CASE, out)
        assert report["records"] == 20
        assert report["equivalent"] is True
