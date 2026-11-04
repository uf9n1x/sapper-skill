"""角色上下文包装配（P1：pack / verify-pack）。

依据升级方案 §7：
- pack：装配 Worker 所需最小上下文（Scope 摘要、假设、证据状态、Result 契约），
  不含无关目标
- verify-pack：只装配合待验 claim、证据与最小复核要求，刻意排除 Worker
  推理叙事（证据摘要、裁决理由、下一步建议）
"""

from __future__ import annotations

from pathlib import Path

from prism import state

# 与报告门禁同口径：confirmed 需要 evidence 覆盖这三个角色
REQUIRED_ROLES = ("observation", "reproduction", "impact")

LedgerError = state.ReplayError


def _hypothesis_state(case: Path, hypothesis_id: str):
    try:
        derived = state.replay(case)
    except state.ReplayError as exc:
        raise LedgerError(str(exc)) from exc
    if hypothesis_id not in derived.hypotheses:
        raise LedgerError(f"unknown hypothesis: {hypothesis_id}")
    hypothesis = derived.hypotheses[hypothesis_id]
    evidence = [
        record.model_dump()
        for eid, record in sorted(derived.evidence_by_id.items())
        if record.hypothesis == hypothesis_id
    ]
    verdict = derived.verdicts.get(hypothesis_id)
    return hypothesis, evidence, verdict


def build_worker_pack(case: Path, hypothesis_id: str) -> str:
    """装配 Worker 上下文包（写入 case/packets/worker-<H>.md 的内容）。"""
    hypothesis, evidence, _verdict = _hypothesis_state(case, hypothesis_id)
    roles_present = {item["role"] for item in evidence}
    missing = [role for role in REQUIRED_ROLES if role not in roles_present]

    lines = [
        f"# Worker Pack — {hypothesis_id}",
        "",
        "> 由 `prism pack` 生成；仅包含当前假设的最小上下文，不含其他目标。",
        "",
        "## 任务边界",
        "",
        f"- 目标 / 范围：{hypothesis['scope']}",
        f"- 假设：{hypothesis['claim']}",
        f"- 证伪条件：{'; '.join(hypothesis['disprove_if'])}",
        "",
        "## 当前证据状态",
        "",
        "| ID | 角色 | 效果 | 摘要 |",
        "|---|---|---|---|",
    ]
    for item in evidence:
        lines.append(
            f"| {item['id']} | {item['role']} | {item['effect']} | {item['summary']} |"
        )
    if not evidence:
        lines.append("| — | — | — | 尚无证据 |")
    lines += [
        "",
        f"缺失证据角色：{('、'.join(missing) or '无——证据链已齐，可建议裁决')}",
        "",
        "## 输出要求",
        "",
        (
            "- 以 **WorkerResult JSON** 返回结果（契约见 `references/result-schema.md`，"
            "或运行 `prism.py schema`）。"
        ),
        "- `run_id` / `idempotency_key` 由主 Agent 随任务下发，原样带回。",
        "- `status`：`done | blocked | failed | needs_verification`。",
        (
            "- `evidence` 提案：`artifact` 必须是 `case/artifacts/` 内相对路径；"
            "原始输出先落盘再引用，不粘贴长文。"
        ),
        (
            "- **不直接写 ledger**；`suggested_verdicts` 只是建议，"
            "confirmed 必须经独立 Verifier 复核。"
        ),
        "- 越界 / 歧义动作默认不执行，先在 `deviations` 或 `blockers` 中说明。",
        "",
    ]
    return "\n".join(lines)


def build_verifier_pack(case: Path, hypothesis_id: str) -> str:
    """装配 Verifier 上下文包（刻意排除 Worker 推理叙事）。"""
    hypothesis, evidence, _verdict = _hypothesis_state(case, hypothesis_id)

    lines = [
        f"# Verifier Pack — {hypothesis_id}",
        "",
        (
            "> 由 `prism verify-pack` 生成；只包含待验声明与证据材料，"
            "**刻意排除 Worker 推理叙事、证据摘要与既有裁决理由**，保证独立复核。"
        ),
        "",
        "## 待验声明",
        "",
        f"- 假设：{hypothesis['claim']}",
        f"- 范围：{hypothesis['scope']}",
        f"- 证伪条件：{'; '.join(hypothesis['disprove_if'])}",
        "",
        "## 证据材料（原始观察，摘要已省略）",
        "",
        "| ID | 角色 | 效果 | Artifact | SHA-256 |",
        "|---|---|---|---|---|",
    ]
    for item in evidence:
        lines.append(
            f"| {item['id']} | {item['role']} | {item['effect']} "
            f"| `{item['artifact']}` | `{item['sha256']}` |"
        )
    if not evidence:
        lines.append("| — | — | — | 无证据待验 | — |")
    lines += [
        "",
        "## 复核要求",
        "",
        "- 直接核对 artifact 原文与 SHA-256，独立重现 observation / reproduction。",
        "- 评估 impact 证据是否支撑结论；对照证伪条件判断是否证伪。",
        (
            "- 以 WorkerResult JSON 返回：`suggested_verdicts` 给出裁决建议"
            "（confirmed 需 observation / reproduction / impact 三角色齐全）。"
        ),
        (
            "- 不受任何 Worker 结论影响；发现矛盾即建议 killed / inconclusive，"
            "材料不足即 inconclusive，不要迁就已有叙事。"
        ),
        "",
    ]
    return "\n".join(lines)
