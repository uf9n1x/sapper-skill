"""v1 → v2 账本迁移（T-030 验收：迁移脚本可用）。

语义（升级方案 §6：保留 Hypothesis/Evidence/Verdict，增加 Fact/Intent/Run）：
- v1 的 hypothesis / evidence / verdict 记录升级为 v:2（可选新字段取默认）
- 记录顺序与 ID 保持不变（审计连续性）
- artifacts 目录整体复制到输出案件
- 迁移后立即回放校验，与 v1 派生状态做语义等价对比
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import case_ledger as v1
from pydantic import TypeAdapter

from prism import models, state


def _upgraded(raw: dict) -> dict:
    """v1 记录 → v2 记录（补充新增可选字段的默认值）。"""
    upgraded = {**raw, "v": 2}
    kind = raw["type"]
    if kind == "hypothesis":
        upgraded.setdefault("linked_facts", [])
    elif kind == "evidence":
        upgraded.setdefault("run", None)
        upgraded.setdefault("actor", None)
        upgraded.setdefault("observed_at", None)
    elif kind == "verdict":
        upgraded.setdefault("verifier_run", None)
    return upgraded


def migrate_case(case: Path, out: Path) -> dict:
    """迁移 v1 案件到 v2；返回迁移报告（records / equivalent / out）。"""
    case, out = Path(case), Path(out)
    records_v1 = v1.verified(case)  # 校验 + 修复尾行后读取
    if not records_v1:
        raise state.ReplayError(f"v1 ledger empty or unreadable: {case}")
    if any(r.get("v") == 2 for r in records_v1):
        raise state.ReplayError(
            "input ledger already contains v2 records (already migrated)"
        )

    upgraded = [_upgraded(raw) for raw in records_v1]
    adapter = TypeAdapter(list[models.LedgerRecord])
    validated = adapter.validate_python(upgraded)

    out.mkdir(parents=True, exist_ok=False)
    (out / "ledger.jsonl").write_text(
        "".join(
            json.dumps(record.model_dump(), ensure_ascii=False) + "\n"
            for record in validated
        ),
        encoding="utf-8",
        newline="\n",
    )
    if (case / "artifacts").is_dir():
        shutil.copytree(case / "artifacts", out / "artifacts")

    # 回放校验 + 与 v1 派生状态语义等价对比
    derived = state.replay(out)
    equivalent = _equivalent(records_v1, derived)
    return {
        "records": len(validated),
        "out": str(out),
        "equivalent": equivalent,
        "counts": derived.counts,
    }


def _equivalent(records_v1: list[dict], derived: state.DerivedState) -> bool:
    """v1 派生状态与 v2 回放结果在 H/E/V 三类记录上等价。"""
    v1_hypotheses = {
        r["id"]: (r["claim"], tuple(r["disprove_if"]))
        for r in records_v1
        if r["type"] == "hypothesis"
    }
    v2_hypotheses = {
        h: (fields["claim"], tuple(fields["disprove_if"]))
        for h, fields in derived.hypotheses.items()
    }
    if v1_hypotheses != v2_hypotheses:
        return False

    v1_evidence = {
        r["id"]: (r["hypothesis"], r["role"], r["effect"], r["artifact"])
        for r in records_v1
        if r["type"] == "evidence"
    }
    v2_evidence = {
        e_id: (e.hypothesis, e.role, e.effect, e.artifact)
        for e_id, e in derived.evidence_by_id.items()
    }
    if v1_evidence != v2_evidence:
        return False

    # 最新裁决对比（同假设多条按账本顺序取最后）
    v1_latest: dict[str, dict] = {}
    for r in records_v1:
        if r["type"] == "verdict":
            v1_latest[r["hypothesis"]] = r
    v2_latest = {
        h: {"status": v["status"], "evidence": tuple(v["evidence"])}
        for h, v in derived.verdicts.items()
    }
    v1_latest_cmp = {
        h: {"status": v["status"], "evidence": tuple(v["evidence"])}
        for h, v in v1_latest.items()
    }
    return v1_latest_cmp == v2_latest


def migrate_command(case: str, out: str) -> dict:
    """CLI 包装：把 ReplayError 留给调用方转换为退出码。"""
    return migrate_case(Path(case), Path(out))
