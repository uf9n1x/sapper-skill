"""prism CLI（P1 命令面：schema / pack / verify-pack）。

约定（interfaces.md §1）：
- 结果写 stdout，诊断写 stderr（ERROR 前缀）
- 稳定退出码：0 成功 / 1 业务错误
- 不实现 Agent 自动循环，不做隐式联网安装
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import sysconfig
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

import typer

from prism import identity, migration, models, packets, parsers, records
from prism import ingest as ingest_module
from prism import knowledge as knowledge_module
from prism import recall as recall_module
from prism import render as render_module
from prism import state as state_store
from prism.packets import LedgerError

app = typer.Typer(
    help="prism 控制面（P1 骨架：schema / pack / verify-pack）。",
    no_args_is_help=True,
    add_completion=False,
)


def _fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise typer.Exit(1)


@app.command()
def schema(
    format: str = typer.Option(
        "markdown", "--format", help="输出格式：json / markdown"
    ),
    out: Path | None = typer.Option(None, "--out", help="写入文件而不是 stdout"),
) -> None:
    """导出 WorkerResult 协议的 JSON Schema 或字段文档。"""
    if format == "json":
        text = json.dumps(models.export_json_schema(), ensure_ascii=False, indent=2)
    elif format == "markdown":
        text = models.export_markdown()
    else:
        _fail(f"unknown format: {format}（可选 json / markdown）")
        return
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            text if text.endswith("\n") else text + "\n", encoding="utf-8", newline="\n"
        )
        typer.echo(str(out))
    else:
        typer.echo(text)


def _write_pack(
    case: str, hypothesis: str, builder, filename: str, json_output: bool
) -> None:
    case_path = Path(case).expanduser().resolve()
    try:
        content = builder(case_path, hypothesis)
    except LedgerError as exc:
        _fail(str(exc))
        return
    pack_path = case_path / "packets" / filename.format(hypothesis=hypothesis)
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    pack_path.write_text(content, encoding="utf-8", newline="\n")
    if json_output:
        typer.echo(
            json.dumps(
                {"hypothesis": hypothesis, "pack_path": str(pack_path)},
                ensure_ascii=False,
            )
        )
    else:
        typer.echo(str(pack_path))


@app.command()
def pack(
    case: str = typer.Argument(help="案件目录（含 ledger.jsonl）"),
    hypothesis: str = typer.Option(..., "--hypothesis", help="目标假设 ID"),
    json_output: bool = typer.Option(False, "--json", help="机器可读输出"),
) -> None:
    """装配 Worker 上下文包（最小上下文，不含无关目标）。"""
    _write_pack(
        case,
        hypothesis,
        packets.build_worker_pack,
        "worker-{hypothesis}.md",
        json_output,
    )


@app.command("verify-pack")
def verify_pack(
    case: str = typer.Argument(help="案件目录（含 ledger.jsonl）"),
    hypothesis: str = typer.Option(..., "--hypothesis", help="待验假设 ID"),
    json_output: bool = typer.Option(False, "--json", help="机器可读输出"),
) -> None:
    """装配 Verifier 上下文包（排除 Worker 推理叙事）。"""
    _write_pack(
        case,
        hypothesis,
        packets.build_verifier_pack,
        "verifier-{hypothesis}.md",
        json_output,
    )


def _echo_record(payload: dict) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False))


@app.command()
def intent(
    case: str = typer.Argument(help="案件目录（不存在时自动初始化）"),
    id: str | None = typer.Option(None, "--id", help="Intent ID（缺省自动分配）"),
    title: str = typer.Option(..., "--title", help="一句话任务标题"),
    objective: str = typer.Option(..., "--objective", help="任务目标"),
    target: str = typer.Option(..., "--target", help="目标范围"),
    angle: str = typer.Option(..., "--angle", help="切入角度"),
    priority: int = typer.Option(3, "--priority", min=1, max=5),
    timebox: int | None = typer.Option(None, "--timebox-minutes", min=1),
) -> None:
    """创建 Intent（案件不存在时自动初始化目录与账本）。"""
    try:
        _echo_record(
            records.record_intent(
                Path(case).expanduser().resolve(),
                id,
                title,
                objective=objective,
                target=target,
                angle=angle,
                priority=priority,
                timebox_minutes=timebox,
            )
        )
    except (ingest_module.IngestError, state_store.ReplayError) as exc:
        _fail(str(exc))


@app.command()
def hypothesis(
    case: str = typer.Argument(help="案件目录（含 ledger.jsonl）"),
    id: str | None = typer.Option(None, "--id", help="假设 ID（缺省自动分配）"),
    claim: str = typer.Option(..., "--claim", help="可证伪的攻击假设"),
    scope: str = typer.Option(..., "--scope", help="目标/范围"),
    disprove_if: list[str] = typer.Option(
        ..., "--disprove-if", help="证伪条件（至少一条，可重复）"
    ),
) -> None:
    """追加 hypothesis 记录（v2）。"""
    try:
        _echo_record(
            records.record_hypothesis(
                Path(case).expanduser().resolve(),
                id,
                claim,
                scope,
                list(disprove_if),
            )
        )
    except (ingest_module.IngestError, state_store.ReplayError) as exc:
        _fail(str(exc))


@app.command()
def evidence(
    case: str = typer.Argument(help="案件目录（含 ledger.jsonl）"),
    id: str | None = typer.Option(None, "--id", help="证据 ID（缺省自动分配）"),
    hypothesis: str = typer.Option(..., "--hypothesis", help="所属假设 ID"),
    role: str = typer.Option(
        ..., "--role", help="observation|reproduction|impact|refutation"
    ),
    effect: str = typer.Option(..., "--effect", help="supports|refutes|context"),
    artifact: str = typer.Option(..., "--artifact", help="case 内相对路径"),
    summary: str = typer.Option(..., "--summary", help="一句话摘要（不含秘密原文）"),
    run: str | None = typer.Option(None, "--run", help="关联 Run ID"),
    actor: str | None = typer.Option(None, "--actor", help="采集者"),
) -> None:
    """追加 evidence 记录（v2）：SHA-256 由脚本计算，artifact 必须存在。"""
    try:
        _echo_record(
            records.record_evidence(
                Path(case).expanduser().resolve(),
                id,
                hypothesis,
                role,
                effect,
                artifact,
                summary,
                run=run,
                actor=actor,
            )
        )
    except (ingest_module.IngestError, state_store.ReplayError) as exc:
        _fail(str(exc))


@app.command()
def verdict(
    case: str = typer.Argument(help="案件目录（含 ledger.jsonl）"),
    id: str | None = typer.Option(None, "--id", help="裁决 ID（缺省自动分配）"),
    hypothesis: str = typer.Option(..., "--hypothesis", help="目标假设 ID"),
    status: str = typer.Option(
        ...,
        "--status",
        help="confirmed|killed|inconclusive|deferred|provisional",
    ),
    evidence: list[str] = typer.Option(..., "--evidence", help="证据 ID（可重复）"),
    reason: str = typer.Option(..., "--reason", help="裁决理由（≤500 字）"),
    verifier_run: str | None = typer.Option(
        None, "--verifier-run", help="独立 Verifier Run ID（confirmed 必填）"
    ),
) -> None:
    """追加 verdict 记录（v2）：confirmed 强制 verifier_run 溯源 + 三角色闭环。"""
    try:
        _echo_record(
            records.record_verdict(
                Path(case).expanduser().resolve(),
                id,
                hypothesis,
                status,
                list(evidence),
                reason,
                verifier_run=verifier_run,
            )
        )
    except (ingest_module.IngestError, state_store.ReplayError) as exc:
        _fail(str(exc))


@app.command()
def verify(
    case: str = typer.Argument(help="v2 案件目录（含 ledger.jsonl）"),
) -> None:
    """报告门禁（v2）：confirmed 三角色闭环 + verifier 溯源 + 无未闭环 provisional。

    通过输出 `REPORT gate: PASS`；任何缺口输出明细并退出码 1。
    """
    case_path = Path(case).expanduser().resolve()
    try:
        derived = state_store.replay(case_path)
    except state_store.ReplayError as exc:
        _fail(str(exc))
        return

    roles_by_hypothesis: dict[str, set[str]] = {}
    for record in derived.evidence_by_id.values():
        roles_by_hypothesis.setdefault(record.hypothesis, set()).add(record.role)

    gaps: list[str] = []
    for hyp_id, verdict in derived.verdicts.items():
        status = verdict.get("status")
        if status == "provisional":
            gaps.append(f"{hyp_id}: provisional 未闭环")
        elif status == "confirmed":
            roles = roles_by_hypothesis.get(hyp_id, set())
            missing = {"observation", "reproduction", "impact"} - roles
            if missing:
                gaps.append(f"{hyp_id}: confirmed 缺证据角色 {sorted(missing)}")
            if not verdict.get("verifier_run"):
                gaps.append(f"{hyp_id}: confirmed 缺 verifier_run 溯源")

    typer.echo("REPORT gate: " + ("PASS" if not gaps else "FAIL"))
    for gap in gaps:
        typer.echo(f" - {gap}")
    if gaps:
        raise typer.Exit(1)


@app.command()
def migrate(
    case: str = typer.Argument(help="v1 案件目录（含 ledger.jsonl）"),
    out: str = typer.Option(..., "--out", help="输出 v2 案件目录（必须不存在）"),
) -> None:
    """把 v1 账本迁移为 v2（含回放等价性校验与 artifacts 复制）。"""
    try:
        report = migration.migrate_case(Path(case), Path(out))
    except state_store.ReplayError as exc:
        _fail(f"migrate failed: {exc}")
        return
    typer.echo(json.dumps(report, ensure_ascii=False))


@app.command()
def state(
    case: str = typer.Argument(help="v2 案件目录（含 ledger.jsonl）"),
    json_output: bool = typer.Option(False, "--json", help="机器可读输出"),
) -> None:
    """回放账本事件，输出当前派生状态（Intent/Run 状态、findings）。"""
    try:
        if json_output:
            typer.echo(
                json.dumps(state_store.state_summary(Path(case)), ensure_ascii=False)
            )
        else:
            derived = state_store.replay(Path(case))
            counts = derived.counts
            typer.echo(
                f"facts={counts['facts']} intents={counts['intents']} "
                f"runs={counts['runs']} hypotheses={counts['hypotheses']} "
                f"evidence={counts['evidence']} findings={counts['findings']}"
            )
            for intent_id, intent in sorted(derived.intents.items()):
                typer.echo(f"intent {intent_id}: {intent['status']}")
            for run_id, run in sorted(derived.runs.items()):
                typer.echo(f"run {run_id}: {run['status']}")
            for finding in derived.findings:
                typer.echo(f"finding {finding}")
    except state_store.ReplayError as exc:
        _fail(str(exc))
        return


@app.command()
def claim(
    case: str = typer.Argument(help="v2 案件目录"),
    intent: str = typer.Option(..., "--intent", help="Intent ID"),
    run: str = typer.Option(..., "--run", help="新 Run ID（R 前缀）"),
    actor: str = typer.Option(..., "--actor", help="执行角色（worker/verifier）"),
    lease_minutes: int = typer.Option(30, "--lease-minutes", min=1),
    now: str | None = typer.Option(None, "--now", help="覆盖当前时间（测试用）"),
) -> None:
    """认领 Intent：追加 claimed 事件并创建带 Lease 的 Run。"""
    try:
        report = ingest_module.claim(Path(case), intent, run, actor, lease_minutes, now)
    except (ingest_module.IngestError, state_store.ReplayError) as exc:
        _fail(str(exc))
        return
    typer.echo(json.dumps(report, ensure_ascii=False))


@app.command()
def ingest(
    case: str = typer.Argument(help="v2 案件目录"),
    result: str = typer.Option(
        ..., "--result", help="结果包路径（results/<run>.json）"
    ),
) -> None:
    """幂等入库结果包：校验 artifact/哈希 → 追加记录 → run 完成。

    suggested_verdicts 不会自动入账为 verdict（confirmed 必须由 Verifier 驱动）。
    """
    try:
        report = ingest_module.ingest(Path(case), Path(result))
    except (ingest_module.IngestError, state_store.ReplayError) as exc:
        _fail(str(exc))
        return
    typer.echo(json.dumps(report, ensure_ascii=False))


@app.command()
def recover(
    case: str = typer.Argument(help="v2 案件目录"),
    json_output: bool = typer.Option(False, "--json", help="机器可读输出"),
    now: str | None = typer.Option(None, "--now", help="覆盖当前时间（测试用）"),
) -> None:
    """检查过期 Lease 的 Run 并给出恢复建议（ingest 或 re_claim）。"""
    try:
        report = ingest_module.recover(Path(case), now)
    except state_store.ReplayError as exc:
        _fail(str(exc))
        return
    if json_output:
        typer.echo(json.dumps(report, ensure_ascii=False))
    else:
        if not report["actions"]:
            typer.echo("无过期 Lease 的 Run")
        for action in report["actions"]:
            typer.echo(
                f"run {action['run_id']} (intent {action['intent']}) "
                f"lease 过期 → 建议 {action['action']}"
            )


@app.command()
def repair(
    case: str = typer.Argument(help="案件目录"),
) -> None:
    """修复崩溃留下的不完整账本尾行（截断半行，完整记录不受影响）。"""
    report = ingest_module.repair_tail(Path(case))
    if report["repaired"]:
        typer.echo(f"已截断不完整尾行（{report['removed_bytes']} 字节）")
    else:
        typer.echo("账本完整，无需修复")


_HARVEST_MAX_CANDIDATES = 200
_HARVEST_DIGEST_TEXT_LINES = 40


def _validate_artifact_path(case_path: Path, artifact: str) -> Path:
    """artifact 必须是 case 内 POSIX 相对路径（防逃逸），并真实存在。"""
    normalized = artifact.replace("\\", "/")
    lowered = normalized.lower()
    if (
        normalized.startswith("/")
        or re.match(r"^[a-z]:", lowered)
        or any(part == ".." for part in normalized.split("/"))
    ):
        _fail(f"artifact 必须是 case 内相对路径（POSIX，不含 ..）: {artifact}")
        raise typer.Exit(1)
    path = case_path / normalized
    if not path.is_file():
        _fail(f"artifact not found（不存在）: {normalized}")
        raise typer.Exit(1)
    return path


@app.command()
def harvest(
    case: str = typer.Argument(help="v2 案件目录（含 ledger.jsonl）"),
    artifact: str = typer.Option(..., "--artifact", help="原始工具输出相对路径"),
    format: str = typer.Option(
        ..., "--format", help="parser 格式（见 --list-formats）"
    ),
    list_formats: bool = typer.Option(False, "--list-formats", help="列出可用格式"),
    json_output: bool = typer.Option(False, "--json", help="机器可读输出（默认）"),
) -> None:
    """消化工具输出：原始日志存证（SHA-256）+ 结构化增量 digest。

    harvest 是只读操作：不写账本；入库仍由主 Agent 决定（suggested
    facts 需走账本追加）。digest 只含账本中尚不存在的新增候选，已知
    事实只计数不重复回显。
    """
    if list_formats:
        typer.echo("\n".join(sorted(parsers.PARSERS)))
        return
    case_path = Path(case).expanduser().resolve()
    artifact_path = _validate_artifact_path(case_path, artifact)
    try:
        parsed = parsers.parse(format, artifact_path.read_text(encoding="utf-8"))
    except parsers.ParseError as exc:
        _fail(str(exc))
        return
    sha256 = hashlib.sha256(artifact_path.read_bytes()).hexdigest()

    # 别名归并表（parser 报告的 hostname 等价关系）
    alias_to_primary = identity._alias_to_primary(parsed.aliases)
    try:
        merged, review = identity.merge(parsed.candidates, parsed.aliases)
    except identity.IdentityError as exc:
        _fail(str(exc))
        return

    # 与既有账本事实做增量对比：已知资产不重复回显
    existing_keys: set[str] = set()
    try:
        derived = state_store.replay(case_path)
    except state_store.ReplayError as exc:
        _fail(f"case ledger replay failed: {exc}")
        return
    for record in derived.facts.values():
        probe = identity.Candidate(
            kind=str(record.get("kind", "")),
            target=str(record.get("target", "")),
            title=str(record.get("title", "")),
            summary="",
        )
        try:
            existing_keys.add(identity.asset_key(probe, alias_to_primary))
        except identity.IdentityError:
            continue

    fresh = [c for c in merged if c.asset_key not in existing_keys]
    duplicates = len(merged) - len(fresh)
    omitted = max(0, len(fresh) - _HARVEST_MAX_CANDIDATES)
    digest_candidates = fresh[:_HARVEST_MAX_CANDIDATES]

    lines = [f"[{parsed.format}] {parsed.tool}: 新增 {len(fresh)} 条候选"]
    lines.extend(parsed.notes)
    for candidate in digest_candidates[:_HARVEST_DIGEST_TEXT_LINES]:
        sources = ",".join(candidate.sources) or candidate.source
        flag = " ⚠需验证" if candidate.requires_verification else ""
        lines.append(
            f"• [{candidate.kind}] {candidate.target} — {candidate.title}"
            f"（{sources}）{flag}"
        )
    if omitted:
        lines.append(f"… 其余 {omitted} 条候选已省略（上限 {_HARVEST_MAX_CANDIDATES}）")

    typer.echo(
        json.dumps(
            {
                "artifact": artifact.replace("\\", "/"),
                "sha256": sha256,
                "format": parsed.format,
                "tool": parsed.tool,
                "counts": {
                    "total": len(parsed.candidates),
                    "merged": len(merged),
                    "new": len(fresh),
                    "duplicates": duplicates,
                    "review_queue": len(review),
                    "omitted": omitted,
                },
                "limits": {"max_candidates": _HARVEST_MAX_CANDIDATES},
                "candidates": [c.model_dump() for c in digest_candidates],
                "review_queue": [r.model_dump() for r in review],
                "aliases": parsed.aliases,
                "digest_text": "\n".join(lines),
            },
            ensure_ascii=False,
        )
    )


@app.command()
def hosts(
    json_output: bool = typer.Option(False, "--json", help="机器可读输出"),
) -> None:
    """列出可用的宿主 adapter（references/hosts/，渐进披露入口）。"""
    hosts_dir = Path(__file__).resolve().parents[2] / "references" / "hosts"
    adapters = sorted(p.name for p in hosts_dir.glob("*.md") if p.name != "README.md")
    if not adapters:
        _fail(f"no host adapters found in {hosts_dir}")
        return
    if json_output:
        typer.echo(
            json.dumps(
                {"adapters": [{"host": a.removesuffix(".md")} for a in adapters]},
                ensure_ascii=False,
            )
        )
    else:
        for name in adapters:
            typer.echo(name.removesuffix(".md"))


@app.command()
def recall(
    case: str = typer.Argument(help="v2 案件目录"),
    query: str = typer.Option(..., "--query", help="查询串（中英文混合）"),
    top: int = typer.Option(5, "--top", min=1, help="返回命中数上限"),
) -> None:
    """混合可解释召回：BM25 + 模糊 + 结构化加权 + 一跳图扩展。

    成功路径与失败路径（killed/blocked）同时可召回并标注，避免重复走死路。
    """
    try:
        payload = recall_module.recall(Path(case), query, top=top)
    except (recall_module.RecallError, state_store.ReplayError) as exc:
        _fail(str(exc))
        return
    typer.echo(json.dumps(payload, ensure_ascii=False))


@app.command()
def doc(
    case: str = typer.Argument(help="v2 案件目录"),
    id: str = typer.Option(..., "--id", help="记录 ID（F/H/I/E 前缀）"),
) -> None:
    """按需读详情：有 doc_path/artifact 返回文件内容，否则返回记录 JSON。"""
    try:
        typer.echo(recall_module.doc_detail(Path(case), id))
    except (recall_module.RecallError, state_store.ReplayError) as exc:
        _fail(str(exc))
        return


@app.command("kb-list")
def kb_list(
    dir: Path = typer.Option(
        Path(__file__).resolve().parents[2] / "kb", "--dir", help="KB 目录"
    ),
    today: str | None = typer.Option(None, "--today", help="覆盖今天日期（测试用）"),
) -> None:
    """列出 KB 条目（来源 / 信任级别 / 适用版本 / 过期警告）。"""
    try:
        entries = knowledge_module.load_kb(dir)
    except knowledge_module.KBError as exc:
        _fail(str(exc))
        return
    today_date = None
    if today:
        import datetime as _dt

        try:
            today_date = _dt.date.fromisoformat(today)
        except ValueError:
            _fail(f"非法日期: {today}")
            return
    if not entries:
        typer.echo("（KB 为空）")
        return
    for entry in entries:
        meta = entry["meta"]
        expired = (
            " [EXPIRED]" if knowledge_module.is_expired(entry, today=today_date) else ""
        )
        typer.echo(
            f"{entry['id']}  trust={meta.get('trust', '')}  "
            f"applies_to={meta.get('applies_to', '')}  "
            f"verified={meta.get('last_verified', '')}{expired}  "
            f"source={meta.get('source', '')}"
        )


@app.command("kb-read")
def kb_read(
    id: str = typer.Argument(help="KB 条目 ID（文件名去 .md）"),
    dir: Path = typer.Option(
        Path(__file__).resolve().parents[2] / "kb", "--dir", help="KB 目录"
    ),
    today: str | None = typer.Option(None, "--today", help="覆盖今天日期（测试用）"),
) -> None:
    """读取 KB 条目全文（含过期与未验证强制警告）。"""
    today_date = None
    if today:
        import datetime as _dt

        try:
            today_date = _dt.date.fromisoformat(today)
        except ValueError:
            _fail(f"非法日期: {today}")
            return
    try:
        entries = knowledge_module.load_kb(dir)
    except knowledge_module.KBError as exc:
        _fail(str(exc))
        return
    for entry in entries:
        if entry["id"] == id:
            typer.echo(knowledge_module.render_entry_text(entry, today=today_date))
            return
    _fail(f"KB 条目不存在: {id}")


@app.command("kb-promote")
def kb_promote(
    case: str = typer.Argument(help="v2 案件目录"),
    hypothesis: str = typer.Option(..., "--hypothesis", help="已 confirmed 的假设 ID"),
    file: Path = typer.Option(..., "--file", help="去目标化后的经验文本（Markdown）"),
    dir: Path = typer.Option(
        Path(__file__).resolve().parents[2] / "kb", "--dir", help="KB 目录"
    ),
    source_note: str = typer.Option("", "--source-note", help="来源说明"),
) -> None:
    """经验晋升门禁：confirmed + 去目标化硬校验，新条目 trust=unverified。"""
    try:
        path = knowledge_module.promote(
            Path(case), hypothesis, file, dir, source_note=source_note
        )
    except (knowledge_module.KBError, state_store.ReplayError) as exc:
        _fail(str(exc))
        return
    typer.echo(json.dumps({"path": str(path)}, ensure_ascii=False))


@app.command()
def render(
    case: str = typer.Argument(help="v2 案件目录"),
    out_dir: Path | None = typer.Option(
        None, "--out-dir", help="输出目录（默认 <case>/dashboard）"
    ),
    now: str | None = typer.Option(
        None, "--now", help="NOW 时间戳覆盖（测试/确定性用）"
    ),
) -> None:
    """离线重建面板：board.md / dashboard.html / attack-graph.{html,mmd}。

    只读账本（审计权威），派生物可随时删除重建；静态资源内联，无 CDN。
    需要实时查看时改用 `serve`（账本变化自动重渲染）。
    """
    if now is None:
        import datetime as _dt

        now = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        report = render_module.render_all(Path(case), out_dir, now)
    except (state_store.ReplayError, render_module.RenderError) as exc:
        _fail(str(exc))
        return
    typer.echo(json.dumps(report, ensure_ascii=False))


_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1"}
# token 会出现在 URL、Set-Cookie 与子进程命令行里，限定为 URL/Cookie 安全字符集
_TOKEN_RE = re.compile(r"^[A-Za-z0-9._~-]{1,128}$")


def _now() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pid_alive(pid: object) -> bool:
    """Windows 不能用 os.kill(pid, 0) 探测（会真的终止进程），需查退出码。"""
    try:
        value = int(pid)
    except (TypeError, ValueError):
        return False
    if value <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [
            wintypes.DWORD, wintypes.BOOL, wintypes.DWORD,
        ]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.OpenProcess(0x1000, False, value)  # QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(value, 0)
    except OSError:
        return False
    return True


def _daemon_python() -> str:
    """返回「无控制台、且不会再 spawn 一次」的真实解释器。

    uv/venv 在 Windows 上的 python.exe / pythonw.exe 是 redirector：它会
    CreateProcess 拉起真正的解释器（实测 Popen PID ≠ 子进程 os.getpid()）。
    孙进程不继承 CREATE_NO_WINDOW，于是每次启动都弹出命令行黑窗口。
    这里直接定位 sys.base_prefix 下的 pythonw.exe（GUI 子系统二进制），
    由 _daemon_env() 通过 PYTHONHOME / PYTHONPATH 挂回 venv 的依赖目录。
    """
    if os.name == "nt":
        base_exe = Path(getattr(sys, "_base_executable", "") or sys.executable)
        pythonw = base_exe.with_name("pythonw.exe")
        if pythonw.is_file():
            return str(pythonw)
        if Path(sys.executable).name == "pythonw.exe":
            return sys.executable
    return sys.executable


def _daemon_env() -> dict:
    """真实解释器不认识 venv：显式指定标准库位置与 site-packages。"""
    env = dict(os.environ)
    if os.name == "nt" and _daemon_python() != sys.executable:
        env["PYTHONHOME"] = sys.base_prefix
        paths = sysconfig.get_paths()
        candidates = [
            paths.get("purelib", ""),
            paths.get("platlib", ""),
            env.get("PYTHONPATH", ""),
        ]
        env["PYTHONPATH"] = os.pathsep.join(
            dict.fromkeys(p for p in candidates if p)
        )
    return env


def _daemon_popen_kwargs() -> dict:
    """脱离父控制台/会话：不会弹出命令行黑窗口，父进程退出不影响服务。"""
    if os.name == "nt":
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0  # SW_HIDE（回退到 redirector 时也尽量隐藏）
        return {
            "creationflags": (
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
            ),
            "startupinfo": startup,
            "close_fds": True,
        }
    return {"start_new_session": True, "close_fds": True}


def _validate_token(token: str | None) -> str | None:
    """仅接受 URL / Cookie / 命令行均安全的字符集，避免注入与编码歧义。"""
    if token is None:
        return None
    if not _TOKEN_RE.fullmatch(token):
        _fail("--token 只允许 A-Z a-z 0-9 . _ ~ -（1–128 位）")
    return token


def _probe_serve(state: dict) -> bool:
    """确认该 PID/端口上确实是本 Skill 的实时服务（防 PID 复用误杀）。

    uv 在 Windows 上用启动器 exe 拉起真正的解释器，二者 PID 不同，
    因此身份确认靠「服务自己的版本端点」而不是父进程 PID。
    """
    url = state.get("version")
    if not url and state.get("api"):
        url = state["api"].replace("/api/state", "/api/version")
    if not url:
        return False
    try:
        with urllib.request.urlopen(url, timeout=1.5) as resp:
            if resp.status != 200:
                return False
            payload = json.loads(resp.read().decode("utf-8"))
    except (OSError, urllib.error.HTTPError, ValueError):
        return False
    return "ledger_sha256" in payload and "rendered_sha256" in payload


def _kill_pid(pid: object) -> None:
    if not _pid_alive(pid):
        return
    try:
        os.kill(int(pid), signal.SIGTERM)
    except OSError:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(int(pid)), "/F", "/T"],
                capture_output=True, check=False,
            )


def _cleanup_failed_spawn(case_path: Path, proc, log: Path, reason: str) -> None:
    """启动失败/超时：连启动器与真实服务进程一起清理，绝不留孤儿 daemon。"""
    from prism import live as live_module

    state = live_module.read_serve_state(case_path)
    if state:
        _kill_pid(state.get("pid"))
    if proc.poll() is None:
        try:
            proc.terminate()
        except OSError:
            try:
                proc.kill()
            except OSError:
                pass
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
    live_module.remove_serve_state(case_path)
    _fail(f"后台服务启动失败（{reason}），已清理残留进程；日志：{log}")


def _wait_for_state(case_path: Path, proc, log: Path, timeout: float = 20.0) -> dict:
    from prism import live as live_module

    deadline = time.time() + timeout
    while time.time() < deadline:
        state = live_module.read_serve_state(case_path)
        if state and state.get("port") and _pid_alive(state.get("pid")) and _probe_serve(state):
            return state
        if proc.poll() is not None and not state:
            _cleanup_failed_spawn(case_path, proc, log, f"退出码 {proc.returncode}")
        time.sleep(0.1)
    _cleanup_failed_spawn(case_path, proc, log, "超时")
    return {}


@app.command()
def serve(
    case: str = typer.Argument(help="v2 案件目录（含 ledger.jsonl）"),
    host: str = typer.Option("127.0.0.1", "--host", help="监听地址（默认仅本机）"),
    port: int = typer.Option(8765, "--port", min=0, help="监听端口（0 = 随机）"),
    interval: float = typer.Option(
        2.0, "--interval", min=0.2, help="账本轮询间隔（秒）"
    ),
    live: bool | None = typer.Option(
        None,
        "--live/--no-live",
        help="实时可视化开关；前台模式缺省时交互式询问",
    ),
    token: str | None = typer.Option(
        None, "--token", help="访问令牌；绑定到非本机地址时必填"
    ),
    detach: bool = typer.Option(
        True,
        "--detach/--foreground",
        help="默认后台守护（无控制台窗口，命令立即返回）；--foreground 阻塞驻留",
    ),
) -> None:
    """实时面板：托管 dashboard 产物 + 账本监听自动重渲染（ADR-0013）。

    - 默认 **后台守护**：不弹控制台黑窗口，关闭启动它的终端/会话不影响面板；
      重复调用返回既有服务；用 `serve-stop <case>` 停止
    - /api/state、/api/version 只读，/api/live 为 POST 写开关；
      /dashboard/api/* 是旧页面缓存的兼容入口
    - 账本变化自动重新 render；Ctrl-C 仅对 --foreground 有效
    - 硬约束：JSONL 只读，默认绑定 127.0.0.1；非本机绑定强制 --token
    """
    from prism import live as live_module

    case_path = Path(case).expanduser().resolve()
    if not (case_path / "ledger.jsonl").is_file():
        _fail(f"案件目录缺少 ledger.jsonl: {case_path}")
        return
    if host not in _LOOPBACK_HOSTS and not token:
        _fail(
            "非本机绑定会暴露账本投影与可写实时开关：必须提供 --token "
            "（首次访问 URL 会带 ?token=... 并下发 Cookie）"
        )
        return
    token = _validate_token(token)

    if detach:
        enabled = live if live is not None else True
        existing = live_module.read_serve_state(case_path)
        if existing and _pid_alive(existing.get("pid")) and _probe_serve(existing):
            mismatched = []
            if existing.get("host") != host:
                mismatched.append("--host")
            if port and existing.get("port") != port:
                mismatched.append("--port")
            if (existing.get("token") or "") != (token or ""):
                mismatched.append("--token")
            if bool(existing.get("live_enabled")) != enabled:
                mismatched.append("--live")
            if mismatched:
                _fail(
                    "已有实时服务参数不同（" + "、".join(mismatched) +
                    "）：请先 `serve-stop`，再按新参数启动"
                )
            typer.echo(json.dumps({**existing, "reused": True}, ensure_ascii=False))
            return
        if existing and _pid_alive(existing.get("pid")):
            _fail(
                "状态文件中的进程仍在，但不是本 Skill 的实时面板（端口无响应）："
                "可能为 PID 复用，请人工核对后删除 serve.json"
            )
        live_module.remove_serve_state(case_path)  # 清掉残留的过期状态文件
        prism_script = Path(__file__).resolve().parents[1] / "prism.py"
        cmd = [
            _daemon_python(), "-X", "utf8", str(prism_script),
            "serve", str(case_path), "--foreground",
            "--host", host, "--port", str(port), "--interval", str(interval),
            "--live" if enabled else "--no-live",
        ]
        if token:
            cmd += ["--token", token]
        log = case_path / "serve.log"
        with log.open("ab") as logfh:
            logfh.write(f"\n=== daemon spawn {_now()} ===\n".encode())
            logfh.flush()
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=logfh,
                stderr=subprocess.STDOUT,
                cwd=str(case_path),
                env=_daemon_env(),
                **_daemon_popen_kwargs(),
            )
        state = _wait_for_state(case_path, proc, log)
        typer.echo(
            json.dumps(
                {
                    "url": state["url"],
                    "api": state["api"],
                    "pid": state["pid"],
                    "port": state["port"],
                    "live_enabled": state["live_enabled"],
                    "detached": True,
                    "reused": False,
                    "state_file": str(live_module.serve_state_path(case_path)),
                    "log": str(log),
                    "stop": f"python -X utf8 {prism_script} serve-stop {case_path}",
                },
                ensure_ascii=False,
            )
        )
        return

    enabled = live_module.prompt_live_enabled(live)
    server = live_module.LivePanelServer(
        case_path, host=host, port=port, interval=interval,
        live_enabled=enabled, token=token,
    )
    server.start()
    if host == "0.0.0.0":
        display_host = "127.0.0.1"
    elif ":" in host and not host.startswith("["):
        display_host = f"[{host}]"  # IPv6 地址需要方括号
    else:
        display_host = host
    base = f"http://{display_host}:{server.port}"
    token_query = f"?token={quote(token, safe='')}" if token else ""
    state = {
        "pid": os.getpid(),
        "host": host,
        "port": server.port,
        "token": token or "",
        "url": f"{base}/dashboard/dashboard.html{token_query}",
        "api": f"{base}/api/state{token_query}",
        "version": f"{base}/api/version{token_query}",
        "live_enabled": server.live_enabled,
        "interval_s": server.interval,
        "started_at": _now(),
    }
    live_module.write_serve_state(case_path, state)
    typer.echo(json.dumps({**state, "detached": False}, ensure_ascii=False))
    try:
        server.serve_forever()
    finally:
        live_module.remove_serve_state(case_path)


@app.command("serve-stop")
def serve_stop(case: str = typer.Argument(help="v2 案件目录")) -> None:
    """停止该案件的后台实时面板（幂等；无运行实例时返回 stopped=false）。"""
    from prism import live as live_module

    case_path = Path(case).expanduser().resolve()
    state = live_module.read_serve_state(case_path)
    if not state:
        typer.echo(
            json.dumps(
                {"stopped": False, "reason": "no active serve"}, ensure_ascii=False
            )
        )
        return
    pid = state.get("pid")
    # 进程已退出：清掉残留状态即可（绝不按 PID 盲杀，避免 PID 复用误伤）
    if not _pid_alive(pid):
        live_module.remove_serve_state(case_path)
        typer.echo(json.dumps(
            {"stopped": True, "pid": pid, "terminated": False,
             "reason": "stale state cleared"}, ensure_ascii=False,
        ))
        return
    # 进程存活但不是我们的面板：保留状态供人工核对，不误杀
    if not _probe_serve(state):
        typer.echo(json.dumps(
            {"stopped": False, "pid": pid,
             "reason": "进程存活但面板不响应，状态文件保留以便重试"},
            ensure_ascii=False,
        ))
        return
    try:
        # Windows 上 os.kill 是 TerminateProcess（硬杀），前台 finally 不会执行
        os.kill(int(pid), signal.SIGTERM)
    except OSError:
        fallback = subprocess.run(
            ["taskkill", "/PID", str(pid), "/F", "/T"],
            capture_output=True, check=False,
        ) if os.name == "nt" else None
        if fallback is None or fallback.returncode != 0:
            typer.echo(json.dumps(
                {"stopped": False, "pid": pid,
                 "reason": "无法终止进程，状态文件保留以便重试"},
                ensure_ascii=False,
            ))
            return
    deadline = time.time() + 5
    while time.time() < deadline and _pid_alive(pid):
        time.sleep(0.1)
    live_module.remove_serve_state(case_path)
    typer.echo(json.dumps(
        {"stopped": True, "pid": pid, "terminated": True}, ensure_ascii=False,
    ))


if __name__ == "__main__":
    app()
