"""prism CLI（P1 命令面：schema / pack / verify-pack）。

约定（interfaces.md §1）：
- 结果写 stdout，诊断写 stderr（ERROR 前缀）
- 稳定退出码：0 成功 / 1 业务错误
- 不实现 Agent 自动循环，不做隐式联网安装
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

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


@app.command()
def serve(
    case: str = typer.Argument(help="v2 案件目录（含 ledger.jsonl）"),
    host: str = typer.Option("127.0.0.1", "--host", help="监听地址（默认仅本机）"),
    port: int = typer.Option(8765, "--port", min=1, help="监听端口（0 = 随机）"),
    interval: float = typer.Option(
        2.0, "--interval", min=0.2, help="账本轮询间隔（秒）"
    ),
    live: bool | None = typer.Option(
        None,
        "--live/--no-live",
        help="实时可视化开关；缺省时交互式询问，非交互默认开启",
    ),
) -> None:
    """实时面板：托管 dashboard 产物 + 账本监听自动重渲染（ADR-0013）。

    - /dashboard/dashboard.html 全局状态页；/api/state、/api/version 供
      前端轮询；/api/live 随时切换实时开关
    - 账本变化自动重新 render；Ctrl-C 退出
    - 硬约束不变：JSONL 只读，默认绑定 127.0.0.1
    """
    from prism import live as live_module

    case_path = Path(case).expanduser().resolve()
    if not (case_path / "ledger.jsonl").is_file():
        _fail(f"案件目录缺少 ledger.jsonl: {case_path}")
        return
    enabled = live_module.prompt_live_enabled(live)
    server = live_module.LivePanelServer(
        case_path, host=host, port=port, interval=interval, live_enabled=enabled
    )
    server.start()
    typer.echo(
        json.dumps(
            {
                "url": f"http://{host if host != '0.0.0.0' else '127.0.0.1'}:{server.port}/dashboard/dashboard.html",
                "api": f"http://127.0.0.1:{server.port}/api/state",
                "live_enabled": server.live_enabled,
                "interval_s": server.interval,
            },
            ensure_ascii=False,
        )
    )
    server.serve_forever()


if __name__ == "__main__":
    app()
