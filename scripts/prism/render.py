"""离线面板渲染（T-041；P4 增量：双语界面 + 工业风浅色重设计 + 实时挂钩）。

设计依据（升级方案 §9 + ADR-0013）：
- 三层可见性中的第 3 层：离线自动重建面板——每次状态变化后运行
  `render`，生成 board.md / dashboard.html / attack-graph.{html,mmd}
- 静态资源全部内联（PyVis cdn_resources=inline + 内联过滤脚本），
  无 CDN、无服务、单文件离线打开；是"状态变化时更新、打开或刷新
  查看"，不伪称实时推送
- 实时能力由 `prism.py serve` 提供（ADR-0013）：同一份渲染产物 +
  /api/state 版本轮询，静态文件在离线打开时自动退化为快照模式
- 图与账本一致：全部节点/边由账本回放派生；confirmed 假设投影为
  finding；Intent→Run 诊断链如实呈现
- 派生物可删除重建：board/mmd 确定性输出（同 --now 逐字节一致），
  JSONL 审计权威只读不写
视觉（ADR-0013，工业实用 · 浅色）：
- 主色暖纸白 #f2f0ea / 表面 #fbfaf7 / 墨色 #211e19，单一强调色 #c2451e
- 字体本地栈：Bahnschrift（DIN 系展示/数字）+ Microsoft YaHei UI（正文）
  + Consolas/Cascadia Mono（ID），无任何外部资源
- 双语：HTML 端 data-zh/data-en 属性切换（默认中文），board/mmd 标签
  中英并列
"""

from __future__ import annotations

import html as html_mod
import re
from pathlib import Path

from jinja2 import Template
from pyvis.network import Network

from prism import state
from prism.recall import _HOST_RE  # 共享主机抽取规则（归一化口径一致）

_OUTPUTS = ("board.md", "dashboard.html", "attack-graph.html", "attack-graph.mmd")

_NODE_SAFE_RE = re.compile(r"[^A-Za-z0-9_]")
_COLOR_BY_TYPE = {
    "asset": "#46627f",
    "service": "#6a8f6b",
    "application": "#6a8f6b",
    "finding": "#c2451e",
    "hypothesis": "#8a7bb8",
    "intent": "#b98a2f",
    "run": "#4f8f9e",
}

# 状态中英对照（界面标签统一口径）
STATUS_ZH = {
    "confirmed": "已确认",
    "killed": "已证伪",
    "inconclusive": "未决",
    "deferred": "暂缓",
    "provisional": "暂定",
    "open": "未决",
    "created": "已创建",
    "claimed": "已认领",
    "in_progress": "执行中",
    "completed": "已完成",
    "done": "已完成",
    "failed": "失败",
    "blocked": "受阻",
    "cancelled": "已取消",
    "approved": "已批准",
    "ready": "就绪",
}


def status_label(status: str) -> str:
    """中文优先、英文兜底的状态标签。"""
    return f"{STATUS_ZH.get(status, status)} {status}"


class RenderError(ValueError):
    """渲染失败。"""


def _esc(text: str) -> str:
    return html_mod.escape(str(text), quote=True)


def _sanitize_node_id(raw: str) -> str:
    return _NODE_SAFE_RE.sub("_", raw)


def _family_hosts(text: str) -> set[str]:
    return {match.group(0).lower() for match in _HOST_RE.finditer(text)}


# ---------------------------------------------------------------------------
# 派生视图收集（全部来自账本回放，保证图与账本一致）
# ---------------------------------------------------------------------------


def _collect(derived: state.DerivedState) -> dict:
    facts = [derived.facts[fid] for fid in sorted(derived.facts)]
    assets = [f for f in facts if f.get("kind") == "asset"]
    services = [f for f in facts if f.get("kind") in ("service", "application")]
    hypotheses = []
    for hyp_id in sorted(derived.hypotheses):
        record = dict(derived.hypotheses[hyp_id])
        verdict = derived.verdicts.get(hyp_id) or {}
        record["status"] = str(verdict.get("status", "open"))
        record["is_finding"] = record["status"] == "confirmed"
        record["status_zh"] = STATUS_ZH.get(record["status"], record["status"])
        hypotheses.append(record)
    intents = []
    for intent_id in sorted(derived.intents):
        entry = derived.intents[intent_id]
        entry = dict(entry)
        entry["status_zh"] = STATUS_ZH.get(entry.get("status", ""), entry.get("status", ""))
        intents.append({"id": intent_id, **entry})
    runs = []
    for run_id in sorted(derived.runs):
        entry = derived.runs[run_id]
        entry = dict(entry)
        entry["status_zh"] = STATUS_ZH.get(entry.get("status", ""), entry.get("status", ""))
        runs.append({"id": run_id, **entry})
    approvals = []
    for aid in sorted(derived.approvals):
        entry = dict(derived.approvals[aid])
        entry["status_zh"] = STATUS_ZH.get(entry.get("status", ""), entry.get("status", ""))
        approvals.append(entry)
    return {
        "facts": facts,
        "assets": assets,
        "services": services,
        "hypotheses": hypotheses,
        "intents": intents,
        "runs": runs,
        "approvals": approvals,
        "findings": list(derived.findings),
        "counts": derived.counts,
    }


# ---------------------------------------------------------------------------
# board.md
# ---------------------------------------------------------------------------


def render_board(view: dict, now_iso: str) -> str:
    active_runs = [r for r in view["runs"] if r["status"] == "created"]
    ready_intents = [i for i in view["intents"] if i["status"] == "created"]
    blocked_intents = [
        i for i in view["intents"] if i["status"] in ("blocked", "cancelled")
    ]
    counts_line = (
        f"- 统计 Counts：findings={len(view['findings'])} "
        f"hypotheses={view['counts'].get('hypotheses', 0)} "
        f"intents={view['counts'].get('intents', 0)} "
        f"runs={view['counts'].get('runs', 0)} "
        f"facts={view['counts'].get('facts', 0)}"
    )
    lines = [
        "# prism board（战役黑板）",
        "",
        f"- **NOW**: {_esc(now_iso)}",
        counts_line,
        "",
        "## Active Runs（活动 Run）",
        "",
    ]
    if active_runs:
        for run in active_runs:
            lines.append(
                f"- `{run['id']}`（intent {run.get('intent', '-')}，"
                f"actor {run.get('actor', '-')}, lease {run.get('lease_expires_at', '-')})"
            )
    else:
        lines.append("-（无活动 Run）")
    lines += ["", "## Ready / Blocked Intents（就绪 / 受阻 Intent）", ""]
    if ready_intents or blocked_intents:
        for intent in ready_intents:
            lines.append(
                f"- READY `{intent['id']}` {_esc(intent.get('title', ''))}"
                f"（{STATUS_ZH.get('ready', '就绪')}）"
            )
        for intent in blocked_intents:
            lines.append(
                f"- BLOCKED `{intent['id']}` {_esc(intent.get('title', ''))}"
                f"—— {_esc(intent.get('reason', ''))}"
            )
    else:
        lines.append("-（无待办 / 受阻 Intent）")
    lines += ["", "## Findings（已确认发现）", ""]
    if view["findings"]:
        findings_by_id = {h["id"]: h for h in view["hypotheses"]}
        for finding in view["findings"]:
            hyp = findings_by_id.get(finding, {})
            lines.append(f"- `{finding}` {_esc(hyp.get('claim', ''))}")
    else:
        lines.append("-（暂无 confirmed Finding）")
    lines += [
        "",
        "## Cleanup（清理）",
        "",
        "-（无未完成清理项；cleanup 机器状态随报告门禁在 P4 落地）",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# attack-graph.mmd（Mermaid，宿主可直接渲染）
# ---------------------------------------------------------------------------


def render_mermaid(view: dict) -> str:
    lines = ["graph TD"]

    def asset_id(target: str) -> str:
        return "A_" + _sanitize_node_id(target)

    fact_node_ids: dict[str, str] = {}
    for fact in view["assets"]:
        fact_node_ids[fact["id"]] = asset_id(fact["target"])
    for fact in view["services"]:
        fact_node_ids[fact["id"]] = _sanitize_node_id(fact["id"])

    lines.append("  subgraph attack[攻击链 Attack Chain]")
    for fact in view["assets"]:
        lines.append(f'    {asset_id(fact["target"])}["资产 asset: {_esc(fact["target"])}"]')
    for fact in view["services"]:
        lines.append(
            f"    {_sanitize_node_id(fact['id'])}"
            f'["服务 service: {_esc(fact.get("title", fact["id"]))}"]'
        )
    for hyp in view["hypotheses"]:
        label = (
            f"{hyp['id']} {_esc(hyp.get('claim', ''))}"
            f"（{status_label(hyp['status'])}）"
        )
        lines.append(f'    {hyp["id"]}["{label}"]')
    lines.append("  end")
    lines.append("  subgraph diag[Fact→Intent→Run 诊断链 Diagnostics]")
    for intent in view["intents"]:
        lines.append(
            f'    {intent["id"]}["意图 intent {_esc(intent.get("title", ""))}'
            f'（{status_label(intent["status"])}）"]'
        )
    for run in view["runs"]:
        lines.append(
            f'    {run["id"]}["执行 run {run["id"]}'
            f'（{status_label(run["status"])}）"]'
        )
    lines.append("  end")

    # 服务 → 资产（host:port 解出 host）
    for fact in view["services"]:
        host = str(fact.get("target", "")).split(":")[0]
        host_key = _sanitize_node_id(host)
        if any(_sanitize_node_id(a["target"]) == host_key for a in view["assets"]):
            lines.append(f"    {_sanitize_node_id(fact['id'])} --> {asset_id(host)}")
    # 假设 → 其文本引用的资产/服务（资产族口径与 recall 一致）
    for hyp in view["hypotheses"]:
        hosts = _family_hosts(f"{hyp.get('claim', '')} {hyp.get('scope', '')}")
        edge_label = STATUS_ZH.get(hyp["status"], hyp["status"])
        for fact in view["services"]:
            if _family_hosts(str(fact.get("target", ""))) & hosts:
                lines.append(
                    f"    {hyp['id']} -.{_esc(edge_label)}.-> {_sanitize_node_id(fact['id'])}"
                )
        for fact in view["assets"]:
            if _family_hosts(str(fact.get("target", ""))) & hosts:
                lines.append(
                    f"    {hyp['id']} -.{_esc(edge_label)}.-> {asset_id(fact['target'])}"
                )
    # Intent → Run；Fact → Intent（linked_facts）
    for run in view["runs"]:
        intent = run.get("intent")
        if intent:
            lines.append(f"    {intent} --> {run['id']}")
    for intent in view["intents"]:
        for fact_id in intent.get("linked_facts", []) or []:
            node = fact_node_ids.get(fact_id)
            if node is not None:
                lines.append(f"    {node} --> {intent['id']}")
    # finding 高亮
    if view["findings"]:
        lines.append("  classDef finding fill:#c2451e,color:#fbfaf7")
        lines.append("  class " + ",".join(view["findings"]) + " finding")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# dashboard.html（Jinja2，内联样式与过滤脚本）
# ---------------------------------------------------------------------------

_DASHBOARD_TEMPLATE = Template(
    """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>sapper-skill 战役面板 Campaign Dashboard</title>
<style>
/* ============ 设计令牌（工业实用 · 浅色） ============ */
:root {
  --bg: #f2f0ea;            /* 暖纸白主色 */
  --surface: #fbfaf7;       /* 卡片表面 */
  --ink: #211e19;           /* 墨色正文（对比度 12.9:1） */
  --muted: #6f695e;         /* 次级文本（4.9:1） */
  --line: rgba(33, 30, 25, .14);
  --line-strong: rgba(33, 30, 25, .28);
  --accent: #c2451e;        /* 信号橙红：仅 finding 与关键动作 */
  --accent-soft: rgba(194, 69, 30, .09);
  --ok: #47714f;            /* killed/已完成 绿 */
  --warn: #a4740f;          /* 进行中 琥珀 */
  --info: #46627f;          /* 信息蓝 */
  --radius: 3px;
  --font-display: Bahnschrift, "Bahnschrift SemiBold", "Segoe UI", "Microsoft YaHei UI", sans-serif;
  --font-body: "Microsoft YaHei UI", "PingFang SC", "Segoe UI", sans-serif;
  --font-mono: "Cascadia Mono", Consolas, "Courier New", monospace;
  --ease-out: cubic-bezier(.16, 1, .3, 1);
  --dur-fast: 160ms; --dur-base: 320ms;
  --shadow-1: 0 2px 6px rgba(33, 30, 25, .07);
  --shadow-2: 0 8px 28px rgba(33, 30, 25, .10);
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font-family: var(--font-body); font-size: 14px; line-height: 1.7;
  letter-spacing: .01em;
}
/* 蓝图网格底纹 + 顶部暖晕（氛围层） */
body::before {
  content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 0;
  background:
    radial-gradient(56rem 30rem at 8% -6%, rgba(194, 69, 30, .05), transparent 60%),
    repeating-linear-gradient(0deg, transparent, transparent 31px, var(--line) 31px, var(--line) 32px),
    repeating-linear-gradient(90deg, transparent, transparent 31px, var(--line) 31px, var(--line) 32px);
  opacity: .35;
}
.wrap { position: relative; z-index: 1; max-width: 1180px; margin: 0 auto; padding: 28px 24px 72px; }

/* ============ 头部：四角标尺框 ============ */
header.masthead {
  position: relative; padding: 22px 26px 18px; background: var(--surface);
  border: 1px solid var(--line-strong); box-shadow: var(--shadow-2);
}
header.masthead::before, header.masthead::after,
.corner-b::before, .corner-b::after {
  content: ""; position: absolute; width: 14px; height: 14px;
  border-color: var(--ink); border-style: solid; border-width: 0;
}
header.masthead::before { top: -2px; left: -2px; border-top-width: 3px; border-left-width: 3px; }
header.masthead::after { top: -2px; right: -2px; border-top-width: 3px; border-right-width: 3px; }
.corner-b::before { bottom: -2px; left: -2px; border-bottom-width: 3px; border-left-width: 3px; }
.corner-b::after { bottom: -2px; right: -2px; border-bottom-width: 3px; border-right-width: 3px; }
h1 {
  margin: 0; font-family: var(--font-display); font-weight: 700;
  font-size: clamp(26px, 4vw, 40px); line-height: 1.05; letter-spacing: -.02em;
}
h1 .en { color: var(--muted); font-weight: 300; font-size: .48em; letter-spacing: .14em; text-transform: uppercase; display: block; margin-top: 4px; }
.masthead .rule { height: 3px; background: var(--ink); margin: 12px 0 10px; position: relative; }
.masthead .rule::after { content: ""; position: absolute; left: 0; top: 0; height: 3px; width: 88px; background: var(--accent); }
.masthead-meta { display: flex; flex-wrap: wrap; gap: 10px 22px; align-items: center; font-family: var(--font-mono); font-size: 12px; color: var(--muted); }
.masthead-meta b { color: var(--ink); font-weight: 600; }

/* ============ 状态徽标 / 实时指示 ============ */
.badge {
  display: inline-flex; align-items: center; gap: 6px;
  font-family: var(--font-mono); font-size: 11.5px; letter-spacing: .04em;
  padding: 2px 9px; border: 1px solid var(--line-strong); border-radius: 999px;
  background: var(--surface); white-space: nowrap;
}
.badge .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--muted); }
.badge.live .dot { background: var(--ok); animation: pulse 2s var(--ease-out) infinite; }
.badge.live { border-color: var(--ok); color: var(--ok); }
.badge.paused { border-color: var(--warn); color: var(--warn); }
.badge.offline .dot { background: var(--muted); }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .35; } }
#live-toggle {
  font: inherit; cursor: pointer; background: var(--surface); color: var(--ink);
  border: 1px solid var(--line-strong); border-radius: 999px; padding: 3px 12px;
  font-family: var(--font-mono); font-size: 11.5px;
  transition: background var(--dur-fast) ease-out, transform var(--dur-fast) ease-out;
}
#live-toggle:hover { background: var(--accent-soft); }
#live-toggle:active { transform: translateY(1px); }
#live-toggle:focus-visible, input:focus-visible, .lang:focus-visible {
  outline: 2px solid var(--accent); outline-offset: 2px;
}
#live-toggle[hidden], .lang[hidden] { display: none; }

/* ============ 计数条：等宽数字 ============ */
.stats {
  display: grid; grid-template-columns: repeat(5, 1fr); gap: 1px;
  background: var(--line-strong); border: 1px solid var(--line-strong);
  margin: 18px 0 0; box-shadow: var(--shadow-1);
}
.stat { background: var(--surface); padding: 14px 16px 10px; position: relative; }
.stat::before { content: ""; position: absolute; left: 0; top: 0; width: 3px; height: 100%; }
.stat.findings::before { background: var(--accent); }
.stat.hypotheses::before { background: #8a7bb8; }
.stat.intents::before { background: var(--warn); }
.stat.runs::before { background: var(--info); }
.stat.facts::before { background: var(--muted); }
.stat .num { font-family: var(--font-display); font-variant-numeric: tabular-nums; font-size: 34px; line-height: 1; font-weight: 700; }
.stat.findings .num { color: var(--accent); }
.stat .label { font-size: 12px; color: var(--muted); margin-top: 6px; letter-spacing: .08em; }

/* ============ 工具栏 ============ */
.toolbar {
  display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
  margin: 18px 0 6px; position: sticky; top: 0; z-index: 5;
  background: linear-gradient(var(--bg) 82%, transparent);
  padding: 8px 0;
}
#filter {
  flex: 1 1 260px; max-width: 420px; padding: 9px 12px;
  font: 13px var(--font-mono); color: var(--ink);
  background: var(--surface); border: 1px solid var(--line-strong); border-radius: var(--radius);
}
#filter::placeholder { color: var(--muted); }
.lang {
  font: 12px var(--font-mono); cursor: pointer; background: var(--surface);
  border: 1px solid var(--line-strong); border-radius: var(--radius); padding: 8px 12px;
  color: var(--ink); transition: background var(--dur-fast) ease-out;
}
.lang:hover { background: var(--accent-soft); }

/* ============ 分区与表格 ============ */
section { margin-top: 26px; }
section > h2 {
  display: flex; align-items: baseline; gap: 10px; margin: 0 0 10px;
  font-family: var(--font-display); font-size: 19px; font-weight: 700; letter-spacing: -.01em;
}
section > h2 .count {
  font-family: var(--font-mono); font-size: 12px; color: var(--muted); font-weight: 400;
}
section > h2 .count::before { content: "／"; margin-right: 2px; }
.tblwrap { background: var(--surface); border: 1px solid var(--line-strong); box-shadow: var(--shadow-1); overflow-x: auto; }
table { border-collapse: collapse; width: 100%; }
th, td { padding: 8px 14px; text-align: left; font-size: 13px; border-bottom: 1px solid var(--line); }
th {
  font-family: var(--font-mono); font-size: 11px; letter-spacing: .1em; text-transform: uppercase;
  color: var(--muted); background: rgba(33, 30, 25, .045); border-bottom: 2px solid var(--line-strong);
  white-space: nowrap;
}
tbody tr { transition: background var(--dur-fast) ease-out; }
tbody tr:hover { background: var(--accent-soft); }
tbody tr:last-child td { border-bottom: none; }
td.id, .mono { font-family: var(--font-mono); font-size: 12.5px; white-space: nowrap; }
td.status { white-space: nowrap; }
.st {
  display: inline-block; padding: 1px 8px; border-radius: 2px;
  font-family: var(--font-mono); font-size: 11px; letter-spacing: .03em;
  border: 1px solid var(--line-strong); background: var(--surface); color: var(--muted);
}
tr.finding td:first-child { box-shadow: inset 3px 0 0 var(--accent); background: var(--accent-soft); }
tr.finding .st { background: var(--accent); border-color: var(--accent); color: #fbfaf7; }
tr.killed .st { color: var(--ok); border-color: var(--ok); }
tr.in_progress .st, tr.claimed .st, tr.created.run-open .st { color: var(--warn); border-color: var(--warn); }
tr.blocked .st, tr.cancelled .st { color: #7a4fa0; border-color: #7a4fa0; }
.empty { padding: 18px 14px; color: var(--muted); font-size: 13px; }
section[data-empty="1"] .tblwrap { display: none; }
section[data-empty="1"] .empty { display: block; }
.empty { display: none; }

/* ============ 页脚 ============ */
footer { margin-top: 30px; color: var(--muted); font-size: 12px; font-family: var(--font-mono); }
footer a { color: var(--info); }

/* ============ 入场序列（错峰 80ms，降级守卫） ============ */
.reveal { opacity: 0; transform: translateY(14px); }
body.anim .reveal {
  transition: opacity var(--dur-base) var(--ease-out), transform var(--dur-base) var(--ease-out);
}
body.anim .reveal:nth-of-type(1) { transition-delay: 0ms; }
body.anim .reveal:nth-of-type(2) { transition-delay: 80ms; }
body.anim .reveal:nth-of-type(3) { transition-delay: 160ms; }
body.anim .reveal:nth-of-type(4) { transition-delay: 240ms; }
body.anim .reveal:nth-of-type(5) { transition-delay: 320ms; }
body.anim.loaded .reveal { opacity: 1; transform: none; }
@media (prefers-reduced-motion: reduce) {
  .reveal { opacity: 1 !important; transform: none !important; transition: none !important; }
  .badge.live .dot { animation: none; }
}
@media (max-width: 720px) {
  .stats { grid-template-columns: repeat(2, 1fr); }
  .wrap { padding: 16px 12px 56px; }
}
</style>
</head>
<body>
<div class="wrap">
  <header class="masthead reveal">
    <h1>战役面板<span class="en">sapper-skill · Campaign Dashboard</span></h1>
    <div class="rule"></div>
    <div class="masthead-meta">
      <span>NOW <b>{{ now }}</b></span>
      <span class="badge offline" id="live-badge" data-zh-live="实时监听" data-en-live="LIVE"><span class="dot"></span><span id="live-text" data-zh="离线快照 Offline snapshot">离线快照 Offline snapshot</span></span>
      <button id="live-toggle" hidden data-zh-pause="暂停实时" data-en-pause="Pause live" data-zh-resume="恢复实时" data-en-resume="Resume live">暂停实时</button>
      <button class="lang" id="lang-toggle" data-zh="EN" data-en="中">EN</button>
    </div>
  </header>

  <div class="stats reveal" role="group">
    <div class="stat findings"><div class="num">{{ counts.findings }}</div><div class="label" data-zh="已确认发现 Findings" data-en="Findings">已确认发现 Findings</div></div>
    <div class="stat hypotheses"><div class="num">{{ counts.hypotheses }}</div><div class="label" data-zh="假设 Hypotheses" data-en="Hypotheses">假设 Hypotheses</div></div>
    <div class="stat intents"><div class="num">{{ counts.intents }}</div><div class="label" data-zh="意图 Intents" data-en="Intents">意图 Intents</div></div>
    <div class="stat runs"><div class="num">{{ counts.runs }}</div><div class="label" data-zh="执行 Runs" data-en="Runs">执行 Runs</div></div>
    <div class="stat facts"><div class="num">{{ counts.facts }}</div><div class="label" data-zh="事实 Facts" data-en="Facts">事实 Facts</div></div>
  </div>

  <div class="toolbar reveal">
    <input id="filter" type="text" placeholder="过滤 Filter：目标 / 状态 / ID 关键词" oninput="filterTables()">
  </div>

  <section class="reveal" id="sec-findings">
    <h2 data-zh="发现 Findings（已确认 confirmed）" data-en="Findings (confirmed)">发现 Findings（已确认 confirmed）<span class="count">{{ counts.findings }}</span></h2>
    <div class="tblwrap"><table id="tbl-findings">
      <thead><tr><th>ID</th><th data-zh="声明 claim" data-en="Claim">声明 claim</th><th data-zh="状态 status" data-en="Status">状态 status</th></tr></thead>
      <tbody>
      {% for h in hypotheses %}{% if h.is_finding %}
      <tr class="finding"><td class="id">{{ h.id }}</td><td>{{ h.claim }}</td><td class="status"><span class="st">{{ h.status }} {{ h.status_zh }}</span></td></tr>
      {% endif %}{% endfor %}
      </tbody>
    </table></div>
    <p class="empty" data-zh="暂无已确认发现。" data-en="No confirmed findings.">暂无已确认发现。</p>
  </section>

  <section class="reveal" id="sec-hypotheses">
    <h2 data-zh="假设 Hypotheses" data-en="Hypotheses">假设 Hypotheses<span class="count">{{ counts.hypotheses }}</span></h2>
    <div class="tblwrap"><table id="tbl-hypotheses">
      <thead><tr><th>ID</th><th data-zh="声明 claim" data-en="Claim">声明 claim</th><th data-zh="范围 scope" data-en="Scope">范围 scope</th><th data-zh="状态 status" data-en="Status">状态 status</th></tr></thead>
      <tbody>
      {% for h in hypotheses %}
      <tr class="{{ h.status }}"><td class="id">{{ h.id }}</td><td>{{ h.claim }}</td><td>{{ h.scope }}</td><td class="status"><span class="st">{{ h.status }} {{ h.status_zh }}</span></td></tr>
      {% endfor %}
      </tbody>
    </table></div>
    <p class="empty" data-zh="暂无假设。" data-en="No hypotheses.">暂无假设。</p>
  </section>

  <section class="reveal" id="sec-intents">
    <h2 data-zh="意图与执行 Intents / Runs" data-en="Intents / Runs">意图与执行 Intents / Runs<span class="count">{{ counts.intents + counts.runs }}</span></h2>
    <div class="tblwrap"><table id="tbl-intents">
      <thead><tr><th>ID</th><th data-zh="标题 title" data-en="Title">标题 title</th><th data-zh="状态 status" data-en="Status">状态 status</th><th data-zh="目标 target" data-en="Target">目标 target</th></tr></thead>
      <tbody>
      {% for i in intents %}
      <tr class="{{ i.status }}"><td class="id">{{ i.id }}</td><td>{{ i.title }}</td><td class="status"><span class="st">{{ i.status }} {{ i.status_zh }}</span></td><td class="mono">{{ i.target }}</td></tr>
      {% endfor %}
      {% for r in runs %}
      <tr class="{{ r.status }} run-open"><td class="id">{{ r.id }}</td><td data-zh="执行 run（意图 intent {{ r.intent }}）" data-en="run (intent {{ r.intent }})">执行 run（意图 intent {{ r.intent }}）</td><td class="status"><span class="st">{{ r.status }} {{ r.status_zh }}</span></td><td class="mono">{{ r.result_ref }}</td></tr>
      {% endfor %}
      </tbody>
    </table></div>
    <p class="empty" data-zh="暂无意图 / 执行记录。" data-en="No intents / runs.">暂无意图 / 执行记录。</p>
  </section>

  <section class="reveal" id="sec-approvals">
    <h2 data-zh="审批 Approvals" data-en="Approvals">审批 Approvals<span class="count">{{ approvals | length }}</span></h2>
    <div class="tblwrap"><table id="tbl-approvals">
      <thead><tr><th>ID</th><th data-zh="动作类别 action_class" data-en="Action class">动作类别 action_class</th><th data-zh="目标范围 target_scope" data-en="Target scope">目标范围 target_scope</th><th data-zh="影响 effect" data-en="Effect">影响 effect</th><th data-zh="状态 status" data-en="Status">状态 status</th><th data-zh="批准人 decided_by" data-en="Decided by">批准人 decided_by</th></tr></thead>
      <tbody>
      {% for a in approvals %}
      <tr><td class="id">{{ a.id }}</td><td class="mono">{{ a.action_class }}</td><td>{{ a.target_scope }}</td><td class="mono">{{ a.effect }}</td><td class="status"><span class="st">{{ a.status }} {{ a.status_zh }}</span></td><td>{{ a.decided_by }}</td></tr>
      {% endfor %}
      </tbody>
    </table></div>
    <p class="empty" data-zh="暂无审批记录。" data-en="No approvals.">暂无审批记录。</p>
  </section>

  <footer class="reveal">
    攻击图 Attack graph：<a href="attack-graph.html">attack-graph.html</a> ·
    <a href="attack-graph.mmd">attack-graph.mmd</a> ·
    <span data-zh="账本审计权威：../ledger.jsonl（只读）" data-en="Ledger authority: ../ledger.jsonl (read-only)">账本审计权威：../ledger.jsonl（只读）</span>
  </footer>
</div>

<script>
/* ---------- 入场序列 ---------- */
document.body.classList.add('anim');
requestAnimationFrame(function () {
  requestAnimationFrame(function () { document.body.classList.add('loaded'); });
});

/* ---------- 中英切换（data-zh / data-en 双语） ---------- */
var LANG = 'zh';
function applyLang() {
  var nodes = document.querySelectorAll('[data-zh]');
  for (var i = 0; i < nodes.length; i++) {
    var v = nodes[i].getAttribute(LANG === 'zh' ? 'data-zh' : 'data-en');
    if (v !== null) nodes[i].textContent = v;
  }
  document.documentElement.lang = LANG === 'zh' ? 'zh-CN' : 'en';
}
document.getElementById('lang-toggle').addEventListener('click', function () {
  LANG = LANG === 'zh' ? 'en' : 'zh';
  this.textContent = LANG === 'zh' ? 'EN' : '中';
  applyLang(); updateLiveUi();
});

/* ---------- 过滤（空分区折叠 + 空态提示） ---------- */
function filterTables() {
  var q = document.getElementById('filter').value.toLowerCase();
  var sections = document.querySelectorAll('section');
  for (var s = 0; s < sections.length; s++) {
    var rows = sections[s].querySelectorAll('tbody tr');
    var visible = 0;
    for (var i = 0; i < rows.length; i++) {
      var hit = rows[i].textContent.toLowerCase().indexOf(q) >= 0;
      rows[i].style.display = hit ? '' : 'none';
      if (hit) visible++;
    }
    sections[s].setAttribute('data-empty', rows.length === 0 || visible === 0 ? '1' : '0');
  }
}
filterTables();

/* ---------- 实时挂钩（serve 模式下生效；离线自动退化） ---------- */
var LIVE = { on: false, known: null, timer: null };
function updateLiveUi() {
  var badge = document.getElementById('live-badge');
  var text = document.getElementById('live-text');
  var btn = document.getElementById('live-toggle');
  badge.classList.remove('live', 'paused', 'offline');
  if (!LIVE.served) {
    badge.classList.add('offline');
    text.textContent = LANG === 'zh' ? '离线快照 Offline snapshot' : 'Offline snapshot';
    return;
  }
  btn.hidden = false;
  if (LIVE.on) {
    badge.classList.add('live');
    text.textContent = LANG === 'zh' ? '实时监听 Live' : 'LIVE';
    btn.textContent = LANG === 'zh' ? '暂停实时' : 'Pause live';
  } else {
    badge.classList.add('paused');
    text.textContent = LANG === 'zh' ? '已暂停 Paused' : 'Paused';
    btn.textContent = LANG === 'zh' ? '恢复实时' : 'Resume live';
  }
}
function postLive(enabled) {
  fetch('api/live', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled: enabled })
  }).catch(function () {});
}
document.getElementById('live-toggle').addEventListener('click', function () {
  postLive(!LIVE.on); LIVE.on = !LIVE.on; updateLiveUi();
});
function pollVersion() {
  fetch('api/version').then(function (r) { return r.json(); }).then(function (v) {
    LIVE.served = true; LIVE.on = v.live_enabled;
    if (LIVE.known === null) LIVE.known = v.ledger_sha256;
    if (LIVE.known !== v.ledger_sha256) { location.reload(); return; }
    updateLiveUi();
  }).catch(function () {
    if (!LIVE.served) {
      // file:// 打开：API 永远不可达，停止轮询（避免控制台噪音），保持离线快照
      clearInterval(LIVE.timer);
      LIVE.on = false; updateLiveUi();
      return;
    }
    LIVE.on = false; updateLiveUi(); /* serve 模式瞬时失败：保持轮询 */
  });
}
if (location.protocol === 'file:') {
  /* file:// 打开：API 不可达，直接保持离线快照，不产生轮询请求 */
  updateLiveUi();
} else {
  pollVersion();
  LIVE.timer = setInterval(pollVersion, 2000);
}
</script>
</body>
</html>
"""
)


def render_dashboard(view: dict, now_iso: str) -> str:
    return _DASHBOARD_TEMPLATE.render(
        now=now_iso,
        counts=view["counts"],
        hypotheses=view["hypotheses"],
        intents=view["intents"],
        runs=view["runs"],
        approvals=view["approvals"],
    )


# ---------------------------------------------------------------------------
# attack-graph.html（PyVis，cdn_resources=inline 完全离线）
# ---------------------------------------------------------------------------


def render_attack_graph(view: dict, out_html: Path) -> None:
    net = Network(
        height="calc(100vh - 84px)",
        width="100%",
        bgcolor="#f7f5f0",
        font_color="#211e19",
        directed=True,
        cdn_resources="in_line",  # 硬要求：静态资源内联，无 CDN（pyvis 拼写）
    )
    node_specs: list[tuple[str, str, str]] = []  # (id, label, type)

    def add_node(node_id: str, label: str, type_: str) -> None:
        node_specs.append((node_id, label, type_))

    asset_ids: dict[str, str] = {}
    fact_node_ids: dict[str, str] = {}  # fact 记录 ID → 图节点 ID
    for fact in view["assets"]:
        node_id = "A_" + _sanitize_node_id(fact["target"])
        asset_ids[_sanitize_node_id(fact["target"])] = node_id
        fact_node_ids[fact["id"]] = node_id
        add_node(node_id, f"资产 asset: {fact['target']}", "asset")
    service_ids: dict[str, str] = {}
    for fact in view["services"]:
        service_ids[fact["id"]] = fact["id"]
        fact_node_ids[fact["id"]] = fact["id"]
        add_node(fact["id"], f"服务 service: {fact.get('title', fact['id'])}", "service")
    for hyp in view["hypotheses"]:
        add_node(
            hyp["id"],
            f"{hyp['id']} {hyp.get('claim', '')[:40]}"
            + ("★发现 finding" if hyp["is_finding"] else f"（{status_label(hyp['status'])}）"),
            "finding" if hyp["is_finding"] else "hypothesis",
        )
    for intent in view["intents"]:
        add_node(
            intent["id"],
            f"意图 intent: {intent.get('title', intent['id'])}",
            "intent",
        )
    for run in view["runs"]:
        add_node(
            run["id"],
            f"执行 run {run['id']}（{status_label(run['status'])}）",
            "run",
        )

    # 大图降噪：只保留与 findings/活动 intent 相关的假设子集之外全部保留
    # （当前规模直接全量；节点 > 500 时按 finding/一跳过滤，见 ADR-0011）
    if len(node_specs) > 500:
        keep = set(view["findings"])
        node_specs = [
            spec for spec in node_specs if spec[2] != "hypothesis" or spec[0] in keep
        ]

    for node_id, label, type_ in node_specs:
        net.add_node(
            node_id,
            label=label,
            color=_COLOR_BY_TYPE.get(type_, "#cccccc"),
            title=label,
        )

    edges: list[tuple[str, str, str]] = []
    for fact in view["services"]:
        host = _sanitize_node_id(str(fact.get("target", "")).split(":")[0])
        if host in asset_ids:
            edges.append((fact["id"], asset_ids[host], "部署 deploy"))
    for hyp in view["hypotheses"]:
        hosts = _family_hosts(f"{hyp.get('claim', '')} {hyp.get('scope', '')}")
        for fact in view["services"]:
            if _family_hosts(str(fact.get("target", ""))) & hosts:
                edges.append((hyp["id"], fact["id"], STATUS_ZH.get(hyp["status"], hyp["status"])))
        for fact in view["assets"]:
            if _family_hosts(str(fact.get("target", ""))) & hosts:
                edges.append(
                    (
                        hyp["id"],
                        asset_ids[_sanitize_node_id(fact["target"])],
                        STATUS_ZH.get(hyp["status"], hyp["status"]),
                    )
                )
    for run in view["runs"]:
        if run.get("intent"):
            edges.append((run["intent"], run["id"], "执行 run"))
    for intent in view["intents"]:
        for fact_id in intent.get("linked_facts", []) or []:
            node = fact_node_ids.get(fact_id)
            if node is not None:
                edges.append((node, intent["id"], "引用 uses"))

    for source, target, label in edges:
        net.add_edge(
            source, target, title=label, label=label if label != "部署 deploy" else ""
        )

    out_html.parent.mkdir(parents=True, exist_ok=True)
    net.write_html(str(out_html), notebook=False)
    _strip_external_refs(out_html)
    _inject_graph_header(out_html)


_EXTERNAL_TAG_RE = re.compile(
    r"<link\b[^>]*bootstrap[^>]*>|<script\b[^>]*bootstrap[^>]*>\s*</script>",
    re.IGNORECASE | re.DOTALL,
)


def _strip_external_refs(html_path: Path) -> None:
    """剥离 pyvis 模板注入的 bootstrap CDN 引用。

    pyvis 0.3.2 即使 cdn_resources=in_line 也会注入未使用的 bootstrap
    外链（纯装饰用途）；vis-network 本体已内联，删除这些标签可保证
    单文件离线打开，功能不受影响。
    """
    html = html_path.read_text(encoding="utf-8")
    cleaned = _EXTERNAL_TAG_RE.sub("", html)
    if cleaned != html:
        html_path.write_text(cleaned, encoding="utf-8", newline="\n")


# attack-graph.html 注入的头部状态条与实时挂钩（相对路径 api/，离线自动退化）
_GRAPH_HEADER_HTML = """<style>
:root { --ink: #211e19; --muted: #6f695e; --surface: #fbfaf7; --line: rgba(33,30,25,.28);
        --accent: #c2451e; --ok: #47714f; --bg: #f2f0ea; }
body { margin: 0; background: var(--bg); font-family: "Microsoft YaHei UI", "PingFang SC", sans-serif; }
#graph-bar { position: fixed; top: 0; left: 0; right: 0; z-index: 10; height: 56px;
  display: flex; align-items: center; gap: 18px; padding: 0 18px;
  background: var(--surface); border-bottom: 2px solid var(--ink); box-shadow: 0 8px 28px rgba(33,30,25,.10); }
#graph-bar .brand { font-family: Bahnschrift, "Segoe UI", sans-serif; font-weight: 700;
  font-size: 17px; letter-spacing: -.01em; color: var(--ink); }
#graph-bar .brand em { font-style: normal; color: var(--accent); }
#graph-bar .sub { color: var(--muted); font-size: 12px; }
.badge { display: inline-flex; align-items: center; gap: 6px; font-family: Consolas, monospace;
  font-size: 11.5px; padding: 2px 9px; border: 1px solid var(--line); border-radius: 999px;
  background: var(--surface); color: var(--muted); }
.badge .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--muted); }
.badge.live { color: var(--ok); border-color: var(--ok); }
.badge.live .dot { background: var(--ok); animation: gpulse 2s cubic-bezier(.16,1,.3,1) infinite; }
@keyframes gpulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }
@media (prefers-reduced-motion: reduce) { .badge.live .dot { animation: none; } }
#vis-wrap { padding: 68px 10px 10px; }
</style>
<div id="graph-bar">
  <span class="brand">攻击图 <em>Attack Graph</em></span>
  <span class="sub">sapper-skill · 节点/边由账本回放派生</span>
  <span class="badge" id="graph-live"><span class="dot"></span><span id="graph-live-text">离线快照 Offline snapshot</span></span>
</div>
<div id="vis-wrap">
</div>
<script>
(function () {
  var wrap = document.getElementById('vis-wrap');
  var bar = document.getElementById('graph-bar');
  var children = Array.prototype.slice.call(document.body.children);
  for (var i = 0; i < children.length; i++) {
    var el = children[i];
    if (el !== bar && el.tagName !== 'SCRIPT' && el.id !== 'vis-wrap' && el.tagName !== 'STYLE') {
      wrap.appendChild(el);
    }
  }
  var known = null;
  var served = false;
  var timer = null;
  function poll() {
    fetch('api/version').then(function (r) { return r.json(); }).then(function (v) {
      served = true;
      var badge = document.getElementById('graph-live');
      if (known === null) known = v.ledger_sha256;
      if (known !== v.ledger_sha256) { location.reload(); return; }
      badge.classList.add('live');
      document.getElementById('graph-live-text').textContent = '实时监听 LIVE';
    }).catch(function () {
      if (!served) { clearInterval(timer); } /* serve 模式瞬时失败：停止轮询保持快照 */
    });
  }
  if (location.protocol !== 'file:') {
    poll();
    timer = setInterval(poll, 2000);
  }
})();
</script>
"""


def _inject_graph_header(html_path: Path) -> None:
    """注入头部状态条与实时轮询（serve 模式生效，离线自动退化）。"""
    html = html_path.read_text(encoding="utf-8")
    if "graph-bar" in html:
        return
    html = html.replace("<body>", "<body>" + _GRAPH_HEADER_HTML, 1)
    html_path.write_text(html, encoding="utf-8", newline="\n")


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def render_all(case_path: Path, out_dir: Path | None, now_iso: str) -> dict:
    derived = state.replay(case_path)
    view = _collect(derived)
    target_dir = out_dir or (case_path / "dashboard")
    target_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "board.md": render_board(view, now_iso),
        "dashboard.html": render_dashboard(view, now_iso),
        "attack-graph.mmd": render_mermaid(view),
    }
    for name, content in outputs.items():
        (target_dir / name).write_text(content, encoding="utf-8", newline="\n")
    render_attack_graph(view, target_dir / "attack-graph.html")
    return {
        "out_dir": str(target_dir),
        "files": list(outputs) + ["attack-graph.html"],
        "now": now_iso,
    }
