"""并发入库、claim/lease 与崩溃恢复（T-031）。

入库顺序（升级方案 §6）：
    获取文件锁 → 校验结果与幂等键 → 追加并 fsync JSONL →（SQLite 索引属派生缓存，
    本阶段未引入）→ 提交后可重放；任何一步崩溃都能从 JSONL 重放修复。

幂等：幂等键记录在 run 完成事件上；同一键重试返回原 Run，不重复入账。
claim：附带 Lease（lease_expires_at）；过期 Run 由 `recover` 给出恢复建议
（结果包已落盘 → ingest；未落盘 → re_claim）。副作用动作的重放安全性由
Agent 层判断，本模块只提供确定性事实。
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from filelock import FileLock
from pydantic import TypeAdapter, ValidationError

from prism import models, state

_LEDGER_ADAPTER = TypeAdapter(list[models.LedgerRecord])
_LOCK_RELATIVE = Path("locks") / "ingest.lock"


class IngestError(Exception):
    """入库 / claim 失败；消息面向 Agent 展示。"""


def now_z() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_z(timestamp: str) -> datetime:
    return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _next_id(existing: set[str], prefix: str) -> str:
    index = 1
    while f"{prefix}{index}" in existing:
        index += 1
    return f"{prefix}{index}"


def _append(case: Path, records: list[dict]) -> None:
    """追加记录并 fsync（调用方必须已持锁）。"""
    path = case / "ledger.jsonl"
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.writelines(
            json.dumps(record, ensure_ascii=False) + "\n" for record in records
        )
        handle.flush()
        os.fsync(handle.fileno())


def _validated(records: list[dict]) -> list[models.LedgerRecord]:
    try:
        return _LEDGER_ADAPTER.validate_python(records)
    except ValidationError as exc:
        raise IngestError(f"record invalid: {exc.errors()[0]['msg']}") from exc


def _check_artifact(case: Path, proposal) -> str:
    """校验 artifact 存在并返回实际 SHA-256（提案哈希不一致即拒绝）。"""
    artifact_path = case / proposal.artifact
    if not artifact_path.is_file():
        raise IngestError(f"artifact not found: {proposal.artifact}")
    digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    if proposal.sha256 and proposal.sha256 != digest:
        raise IngestError(
            f"artifact sha256 mismatch for {proposal.artifact}: "
            f"declared {proposal.sha256}, actual {digest}"
        )
    return digest


def claim(
    case: Path,
    intent_id: str,
    run_id: str,
    actor: str,
    lease_minutes: int = 30,
    now_override: str | None = None,
) -> dict:
    """认领 Intent：追加 intent claimed + run created（含 Lease）。"""
    case = Path(case)
    if now_override is not None:
        moment = now_override
    else:
        moment = now_z()
    lease_expires_at = (_parse_z(moment) + timedelta(minutes=lease_minutes)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    with FileLock(str(case / _LOCK_RELATIVE)):
        derived = state.replay(case)
        if intent_id not in derived.intents:
            raise IngestError(f"unknown intent: {intent_id}")
        intent_status = derived.intents[intent_id]["status"]
        if intent_status in ("completed", "cancelled"):
            raise IngestError(f"intent {intent_id} is {intent_status}; cannot claim")
        if run_id in derived.runs:
            raise IngestError(f"run {run_id} already exists")
        records = _validated(
            [
                {
                    "v": 2,
                    "type": "intent",
                    "id": intent_id,
                    "at": moment,
                    "event": "claimed",
                    "run": run_id,
                },
                {
                    "v": 2,
                    "type": "run",
                    "id": run_id,
                    "at": moment,
                    "event": "created",
                    "intent": intent_id,
                    "actor": actor,
                    "lease_expires_at": lease_expires_at,
                },
            ]
        )
        _append(case, [r.model_dump() for r in records])
    return {
        "intent": intent_id,
        "run": run_id,
        "lease_expires_at": lease_expires_at,
        "status": "claimed",
    }


def ingest(case: Path, result_path: Path) -> dict:
    """幂等入库：校验结果包 → 追加 facts/hypotheses/evidence + run 完成。"""
    case = Path(case)
    result_path = Path(result_path)
    try:
        raw = json.loads(result_path.read_text(encoding="utf-8"))
        result = models.WorkerResult.model_validate(raw)
    except json.JSONDecodeError as exc:
        raise IngestError(f"result packet malformed: {exc}") from exc
    except ValidationError as exc:
        raise IngestError(f"result packet invalid: {exc.errors()[0]['msg']}") from exc

    with FileLock(str(case / _LOCK_RELATIVE)):
        derived = state.replay(case)

        # 幂等检查：同键已入库 → 返回原 Run
        for run_id, run in derived.runs.items():
            if run.get("idempotency_key") == result.idempotency_key:
                return {
                    "status": "duplicate",
                    "run_id": run_id,
                    "idempotency_key": result.idempotency_key,
                }

        run_id = result.run_id
        if run_id in derived.runs:
            if derived.runs[run_id]["status"] != "running":
                raise IngestError(f"run {run_id} is already completed")
            run_exists = True
        else:
            run_exists = False

        moment = now_z()
        records: list[dict] = []
        if not run_exists:
            if result.intent_id is None:
                raise IngestError("result has no intent_id and run was never claimed")
            records += [
                {
                    "v": 2,
                    "type": "intent",
                    "id": result.intent_id,
                    "at": moment,
                    "event": "claimed",
                    "run": run_id,
                },
                {
                    "v": 2,
                    "type": "run",
                    "id": run_id,
                    "at": moment,
                    "event": "created",
                    "intent": result.intent_id,
                    "actor": "worker",
                },
            ]

        # 证据先全部校验（任一失败则整体不入账）
        prepared_evidence: list[tuple[Any, str]] = []
        for proposal in result.evidence:
            digest = _check_artifact(case, proposal)
            prepared_evidence.append((proposal, digest))

        evidence_ids = set(derived.evidence_by_id)
        hypothesis_ids = set(derived.hypotheses)
        fact_ids = set(derived.facts)

        for proposal in result.hypotheses:
            hypothesis_id = _next_id(hypothesis_ids, "H")
            hypothesis_ids.add(hypothesis_id)
            records.append(
                {
                    "v": 2,
                    "type": "hypothesis",
                    "id": hypothesis_id,
                    "at": moment,
                    "claim": proposal.claim,
                    "scope": proposal.scope,
                    "disprove_if": list(proposal.disprove_if),
                    "linked_facts": [],
                }
            )
        for proposal in result.facts:
            fact_id = _next_id(fact_ids, "F")
            fact_ids.add(fact_id)
            records.append(
                {
                    "v": 2,
                    "type": "fact",
                    "id": fact_id,
                    "at": moment,
                    "kind": proposal.kind,
                    "target": proposal.target,
                    "title": proposal.title,
                    "summary": proposal.summary,
                }
            )
        for proposal, digest in prepared_evidence:
            evidence_id = _next_id(evidence_ids, "E")
            evidence_ids.add(evidence_id)
            records.append(
                {
                    "v": 2,
                    "type": "evidence",
                    "id": evidence_id,
                    "at": moment,
                    "hypothesis": proposal.hypothesis,
                    "role": proposal.role,
                    "effect": proposal.effect,
                    "artifact": proposal.artifact,
                    "sha256": digest,
                    "summary": proposal.summary,
                    "run": run_id,
                }
            )
        try:
            result_ref = str(result_path.relative_to(case)).replace("\\", "/")
        except ValueError:
            result_ref = result_path.name
        records.append(
            {
                "v": 2,
                "type": "run",
                "id": run_id,
                "at": moment,
                "event": "completed",
                "result_ref": result_ref,
                "idempotency_key": result.idempotency_key,
            }
        )

        validated = _validated(records)
        _append(case, [r.model_dump() for r in validated])

    return {
        "status": "ingested",
        "run_id": run_id,
        "idempotency_key": result.idempotency_key,
        "ingested": {
            "facts": len(result.facts),
            "hypotheses": len(result.hypotheses),
            "evidence": len(result.evidence),
        },
        "suggested_verdicts_pending": len(result.suggested_verdicts),
    }


def recover(case: Path, now: str | None = None) -> dict:
    """过期 lease 的恢复决策：结果包已落盘 → ingest；否则 re_claim。"""
    case = Path(case)
    moment = now or now_z()
    derived = state.replay(case)
    actions: list[dict] = []
    for run_id, run in sorted(derived.runs.items()):
        if run["status"] != "running":
            continue
        lease = run.get("lease_expires_at")
        if lease is not None and lease >= moment:
            continue  # lease 仍有效
        result_packet = case / "results" / f"{run_id}.json"
        actions.append(
            {
                "run_id": run_id,
                "intent": run.get("intent"),
                "actor": run.get("actor"),
                "lease_expires_at": lease,
                "result_packet_present": result_packet.is_file(),
                "action": "ingest" if result_packet.is_file() else "re_claim",
            }
        )
    return {"checked_at": moment, "actions": actions}


def repair_tail(case: Path) -> dict:
    """修复崩溃留下的不完整尾行：截断最后一个无法解析的尾行。"""
    case = Path(case)
    path = case / "ledger.jsonl"
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    removed_bytes = 0
    while lines:
        last = lines[-1]
        try:
            json.loads(last)
            break
        except json.JSONDecodeError:
            lines.pop()
            removed_bytes += len(last.encode("utf-8"))
    if removed_bytes == 0:
        return {"repaired": False, "removed_bytes": 0}
    path.write_text("".join(lines), encoding="utf-8", newline="")
    return {"repaired": True, "removed_bytes": removed_bytes}
