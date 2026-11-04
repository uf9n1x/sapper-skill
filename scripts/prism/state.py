"""状态事件回放（T-030 验收：状态事件可回放）。

原则（升级方案 §6）：
- ledger.jsonl 是唯一权威账本；黑板 / 图 / findings 全部是派生物
- Intent / Run 为追加事件模型，当前状态由同一实体最新事件派生
- 引用完整性在回放时强制校验（悬空引用直接拒绝）
- 重复 ID 拒绝（幂等入库属 T-031 ingest，这里只做回放期守护）
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from prism import models

_LEDGER_ADAPTER: TypeAdapter = TypeAdapter(models.LedgerRecord)

_INTENT_STATUS_BY_EVENT = {
    "created": "ready",
    "claimed": "in_progress",
    "completed": "completed",
    "blocked": "blocked",
    "cancelled": "cancelled",
}

_RUN_STATUS_BY_EVENT = {
    "created": "running",
    "completed": "completed",
    "failed": "failed",
    "timed_out": "timed_out",
    "cancelled": "cancelled",
}


class ReplayError(Exception):
    """回放失败（格式、引用或重复问题）；消息面向 Agent 展示。"""


@dataclass
class DerivedState:
    """回放产物：全部派生状态，可整体序列化对比。"""

    facts: dict = field(default_factory=dict)
    intents: dict = field(default_factory=dict)
    runs: dict = field(default_factory=dict)
    approvals: dict = field(default_factory=dict)
    hypotheses: dict = field(default_factory=dict)
    evidence_by_id: dict = field(default_factory=dict)
    verdicts: dict = field(default_factory=dict)  # 假设 -> 最新裁决信息
    findings: list = field(default_factory=list)
    counts: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(self._payload(), ensure_ascii=False, sort_keys=True)

    def _payload(self) -> dict:
        return {
            "counts": self.counts,
            "facts": self.facts,
            "intents": self.intents,
            "runs": self.runs,
            "approvals": self.approvals,
            "hypotheses": self.hypotheses,
            "evidence_by_id": {
                k: v.model_dump() for k, v in self.evidence_by_id.items()
            },
            "verdicts": self.verdicts,
            "findings": self.findings,
        }


def load_records(case: Path) -> list:
    """读取并校验 v2 账本；v1 账本提示迁移。"""
    path = Path(case) / "ledger.jsonl"
    if not path.is_file():
        raise ReplayError(f"ledger not found: {path}")
    records: list = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReplayError(f"line {lineno}: malformed JSON: {exc}") from exc
        version = raw.get("v")
        if version == 1:
            raise ReplayError(
                f"line {lineno}: v1 record (type={raw.get('type')}) — "
                "run 'prism.py migrate' first"
            )
        try:
            records.append(_LEDGER_ADAPTER.validate_python(raw))
        except ValidationError as exc:
            raise ReplayError(f"line {lineno}: {exc.errors()[0]['msg']}") from exc
    return records


def replay(case: Path) -> DerivedState:
    """从账本事件重建全部派生状态（纯函数：不修改案件目录）。"""
    records = load_records(Path(case))
    derived = DerivedState()

    seen_ids: set[tuple[str, str]] = set()
    for record in records:
        kind = record.type
        unique_by_id = kind in ("fact", "approval", "hypothesis", "evidence", "verdict")
        if unique_by_id:
            key = (kind, record.id)
            if key in seen_ids:
                raise ReplayError(f"duplicate {kind} id: {record.id}")
            seen_ids.add(key)

    # --- 实体聚合 ---
    for record in records:
        if record.type == "fact":
            derived.facts[record.id] = record.model_dump()
        elif record.type == "approval":
            derived.approvals[record.id] = record.model_dump()
        elif record.type == "hypothesis":
            derived.hypotheses[record.id] = record.model_dump()
        elif record.type == "evidence":
            derived.evidence_by_id[record.id] = record
        elif record.type == "verdict":
            # 最新裁决覆盖（同假设多条裁决按账本顺序取最后）
            derived.verdicts[record.hypothesis] = record.model_dump()

    # --- Intent / Run：最新事件派生当前状态，保留事件历史；字段展平到顶层 ---
    for record in records:
        if record.type == "intent":
            entry = derived.intents.setdefault(record.id, {"history": []})
            entry["history"].append(record.event)
            if record.event == "created":
                entry.update(record.model_dump())
            else:
                for attr in ("run", "reason"):
                    value = getattr(record, attr)
                    if value is not None:
                        entry[attr] = value
            entry["status"] = _INTENT_STATUS_BY_EVENT[record.event]
        elif record.type == "run":
            entry = derived.runs.setdefault(record.id, {"history": []})
            entry["history"].append(record.event)
            if record.event == "created":
                entry.update(record.model_dump())
            else:
                for attr in ("result_ref", "error", "usage", "idempotency_key"):
                    value = getattr(record, attr)
                    if value is not None:
                        entry[attr] = value
            entry["status"] = _RUN_STATUS_BY_EVENT[record.event]

    # --- 引用完整性 ---
    for evidence_id, evidence in derived.evidence_by_id.items():
        if evidence.hypothesis not in derived.hypotheses:
            raise ReplayError(
                f"evidence {evidence_id} references unknown hypothesis "
                f"{evidence.hypothesis}"
            )
    for hypothesis_id, hypothesis in derived.hypotheses.items():
        for fact_id in hypothesis.get("linked_facts", []):
            if fact_id not in derived.facts:
                raise ReplayError(
                    f"hypothesis {hypothesis_id} references unknown fact {fact_id}"
                )
    for fact_id, fact in derived.facts.items():
        for evidence_id in fact.get("source_evidence", []):
            if evidence_id not in derived.evidence_by_id:
                raise ReplayError(
                    f"fact {fact_id} references unknown evidence {evidence_id}"
                )
    for intent_id, intent in derived.intents.items():
        for fact_id in intent.get("linked_facts", []):
            if fact_id not in derived.facts:
                raise ReplayError(
                    f"intent {intent_id} references unknown fact {fact_id}"
                )
        if "claimed" in intent["history"]:
            run_id = intent.get("run")
            if run_id is None or run_id not in derived.runs:
                raise ReplayError(f"intent {intent_id} claims unknown run {run_id!r}")
    for run_id, run in derived.runs.items():
        intent_id = run.get("intent")
        if intent_id is not None and intent_id not in derived.intents:
            raise ReplayError(f"run {run_id} references unknown intent {intent_id}")

    # --- findings 投影：最新裁决为 confirmed 的假设 ---
    derived.findings = sorted(
        hypothesis_id
        for hypothesis_id, verdict in derived.verdicts.items()
        if verdict["status"] == "confirmed"
    )

    derived.counts = {
        "facts": len(derived.facts),
        "intents": len(derived.intents),
        "runs": len(derived.runs),
        "approvals": len(derived.approvals),
        "hypotheses": len(derived.hypotheses),
        "evidence": len(derived.evidence_by_id),
        "verdicts": len(derived.verdicts),
        "findings": len(derived.findings),
    }
    return derived


def state_summary(case: Path) -> dict:
    """`prism.py state --json` 的紧凑输出。"""
    derived = replay(case)
    return {
        "counts": derived.counts,
        "findings": derived.findings,
        "intents": [
            {"id": intent_id, "status": intent["status"]}
            for intent_id, intent in sorted(derived.intents.items())
        ],
        "runs": [
            {
                "id": run_id,
                "status": run["status"],
                "intent": run.get("intent"),
            }
            for run_id, run in sorted(derived.runs.items())
        ],
        "approvals": [
            {
                "id": approval_id,
                "status": approval["status"],
                "approval_key": approval["approval_key"],
            }
            for approval_id, approval in sorted(derived.approvals.items())
        ],
    }
