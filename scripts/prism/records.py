"""v2 直追加命令（T-052）：intent / hypothesis / evidence / verdict。

为什么存在：focused 单假设场景下完整 intent→claim→ingest 仪式过重，而宿主
一旦没有轻量正路就会回退 v1 遗留账本（nss28621 实测教训：整场走 case_ledger.py
v1 命令，v2 门禁形同虚设）。本模块提供与 v1 同名的命令面，但全部走 v2 schema：
- evidence 哈希由脚本计算，artifact 存在性与路径逃逸强制校验
- verdict status=confirmed 强制要求 verifier_run（账本中已完成的 Run）
  + observation/reproduction/impact 三角色闭环，写入时即拦截
- 全程 FileLock + 追加 fsync，与 ingest 相同的并发纪律；账本只追加，不改历史
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from filelock import FileLock

from prism import models, state
from prism.ingest import (
    _LOCK_RELATIVE,
    IngestError,
    _append,
    _next_id,
    _validated,
    now_z,
)


def ensure_case(case: Path) -> Path:
    """初始化案件目录（不存在则创建 ledger.jsonl 与标准子目录）。"""
    case = Path(case)
    case.mkdir(parents=True, exist_ok=True)
    (case / "artifacts").mkdir(exist_ok=True)
    (case / "results").mkdir(exist_ok=True)
    ledger = case / "ledger.jsonl"
    if not ledger.exists():
        ledger.touch()
    return case


def _replay_or_fail(case: Path) -> state.DerivedState:
    try:
        return state.replay(case)
    except state.ReplayError as exc:
        raise IngestError(f"case ledger replay failed: {exc}") from exc


_LOCAL_PATH_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")


def _reject_local_paths(fields: dict[str, object]) -> None:
    """自由文本不得含本机磁盘路径（防敏感路径经账本渲染进报告/图）。

    典型来源：Git Bash (MSYS) 会把以 / 开头的参数自动转成 Windows 路径
    （/view/<uuid> → C:/.../PortableGit/view/<uuid>）。仅写入时校验，
    历史账本回放不受影响。
    """
    for field, value in fields.items():
        if isinstance(value, str) and _LOCAL_PATH_RE.search(value):
            sample = value if len(value) <= 60 else value[:57] + "..."
            raise IngestError(
                f"{field} 含本机磁盘路径（{sample}），拒绝入账以防敏感路径泄露；"
                "Git Bash 环境调用请加 MSYS_NO_PATHCONV=1，或改用相对/URL 表述"
            )


def record_intent(
    case: Path,
    intent_id: str | None,
    title: str,
    objective: str | None = None,
    target: str | None = None,
    angle: str | None = None,
    priority: int = 3,
    timebox_minutes: int | None = None,
    now: str | None = None,
) -> dict:
    """追加 intent created 事件（案件不存在时自动初始化）。"""
    case = ensure_case(case)
    moment = now or now_z()
    _reject_local_paths(
        {"intent.title": title, "intent.objective": objective,
         "intent.target": target, "intent.angle": angle}
    )
    with FileLock(str(case / _LOCK_RELATIVE)):
        derived = _replay_or_fail(case)
        resolved_id = intent_id or _next_id(set(derived.intents), "I")
        if resolved_id in derived.intents:
            raise IngestError(f"intent {resolved_id} already exists")
        record = _validated(
            [
                {
                    "v": 2,
                    "type": "intent",
                    "id": resolved_id,
                    "at": moment,
                    "event": "created",
                    "title": title,
                    "objective": objective,
                    "target": target,
                    "angle": angle,
                    "priority": priority,
                    "timebox_minutes": timebox_minutes,
                }
            ]
        )
        _append(case, [r.model_dump() for r in record])
    return {"intent": resolved_id, "status": "ready"}


def record_hypothesis(
    case: Path,
    hypothesis_id: str | None,
    claim: str,
    scope: str,
    disprove_if: list[str],
    now: str | None = None,
) -> dict:
    """追加 hypothesis 记录（必须可证伪：disprove_if 至少一条）。"""
    case = Path(case)
    if not (case / "ledger.jsonl").is_file():
        raise IngestError("case has no ledger; create an intent first")
    moment = now or now_z()
    _reject_local_paths(
        {"hypothesis.claim": claim, "hypothesis.scope": scope,
         **{f"hypothesis.disprove_if[{i}]": item
            for i, item in enumerate(disprove_if) if isinstance(item, str)}}
    )
    with FileLock(str(case / _LOCK_RELATIVE)):
        derived = _replay_or_fail(case)
        resolved_id = hypothesis_id or _next_id(set(derived.hypotheses), "H")
        if resolved_id in derived.hypotheses:
            raise IngestError(f"hypothesis {resolved_id} already exists")
        record = _validated(
            [
                {
                    "v": 2,
                    "type": "hypothesis",
                    "id": resolved_id,
                    "at": moment,
                    "claim": claim,
                    "scope": scope,
                    "disprove_if": list(disprove_if),
                }
            ]
        )
        _append(case, [r.model_dump() for r in record])
    return {"hypothesis": resolved_id}


def record_evidence(
    case: Path,
    evidence_id: str | None,
    hypothesis: str,
    role: str,
    effect: str,
    artifact: str,
    summary: str,
    run: str | None = None,
    actor: str | None = None,
    observed_at: str | None = None,
    now: str | None = None,
) -> dict:
    """追加 evidence 记录：artifact 必须存在，SHA-256 由脚本计算。"""
    case = Path(case)
    if not (case / "ledger.jsonl").is_file():
        raise IngestError("case has no ledger; create an intent first")
    _reject_local_paths({"evidence.summary": summary})
    normalized = artifact.replace("\\", "/")
    artifact_path = case / normalized
    if (
        normalized.startswith("/")
        or not artifact_path.is_file()
        or any(part == ".." for part in normalized.split("/"))
    ):
        raise IngestError(f"artifact not found or invalid: {normalized}")
    digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    moment = now or now_z()
    with FileLock(str(case / _LOCK_RELATIVE)):
        derived = _replay_or_fail(case)
        if hypothesis not in derived.hypotheses:
            raise IngestError(f"unknown hypothesis: {hypothesis}")
        if run is not None and run not in derived.runs:
            raise IngestError(f"unknown run: {run}")
        resolved_id = evidence_id or _next_id(set(derived.evidence_by_id), "E")
        if resolved_id in derived.evidence_by_id:
            raise IngestError(f"evidence {resolved_id} already exists")
        record = _validated(
            [
                {
                    "v": 2,
                    "type": "evidence",
                    "id": resolved_id,
                    "at": moment,
                    "hypothesis": hypothesis,
                    "role": role,
                    "effect": effect,
                    "artifact": normalized,
                    "sha256": digest,
                    "summary": summary,
                    "run": run,
                    "actor": actor,
                    "observed_at": observed_at,
                }
            ]
        )
        _append(case, [r.model_dump() for r in record])
    return {"evidence": resolved_id, "sha256": digest}


def record_verdict(
    case: Path,
    verdict_id: str | None,
    hypothesis: str,
    status: str,
    evidence: list[str],
    reason: str,
    verifier_run: str | None = None,
    now: str | None = None,
) -> dict:
    """追加 verdict 记录；confirmed 写入时强制 Verifier 溯源 + 三角色闭环。"""
    case = Path(case)
    if not (case / "ledger.jsonl").is_file():
        raise IngestError("case has no ledger; create an intent first")
    if status not in models.VERDICT_STATUSES:
        raise IngestError(f"invalid status: {status}")
    _reject_local_paths({"verdict.reason": reason})
    moment = now or now_z()
    with FileLock(str(case / _LOCK_RELATIVE)):
        derived = _replay_or_fail(case)
        if hypothesis not in derived.hypotheses:
            raise IngestError(f"unknown hypothesis: {hypothesis}")
        if not evidence:
            raise IngestError("verdict requires at least one evidence id")
        for evidence_id in evidence:
            record = derived.evidence_by_id.get(evidence_id)
            if record is None:
                raise IngestError(f"unknown evidence: {evidence_id}")
            if record.hypothesis != hypothesis:
                raise IngestError(
                    f"evidence {evidence_id} belongs to {record.hypothesis}, "
                    f"not {hypothesis}"
                )
        if verifier_run is not None and verifier_run not in derived.runs:
            raise IngestError(f"unknown run: {verifier_run}")
        if status == "confirmed":
            if verifier_run is None:
                raise IngestError(
                    "confirmed verdict requires --verifier-run（独立 Verifier Run 溯源）"
                )
            roles = {
                rec.role
                for eid, rec in derived.evidence_by_id.items()
                if rec.hypothesis == hypothesis
            }
            missing = {"observation", "reproduction", "impact"} - roles
            if missing:
                raise IngestError(
                    f"confirmed verdict missing evidence roles: {sorted(missing)}"
                )
        resolved_id = verdict_id or _next_id(derived.verdict_ids, "V")
        record = _validated(
            [
                {
                    "v": 2,
                    "type": "verdict",
                    "id": resolved_id,
                    "at": moment,
                    "hypothesis": hypothesis,
                    "status": status,
                    "evidence": list(evidence),
                    "reason": reason,
                    "verifier_run": verifier_run,
                }
            ]
        )
        _append(case, [r.model_dump() for r in record])
    return {"verdict": resolved_id, "status": status}
