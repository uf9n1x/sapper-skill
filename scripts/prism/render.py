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
import os
import re
from pathlib import Path

from jinja2 import Template
from pyvis.network import Network

from prism import state
from prism.recall import _HOST_RE  # 共享主机抽取规则（归一化口径一致）

_OUTPUTS = ("board.md", "dashboard.html", "attack-graph.html", "attack-graph.mmd")

_NODE_SAFE_RE = re.compile(r"[^A-Za-z0-9_]")

# 共享实时控制器：dashboard 与 attack-graph 注入同一份实现，避免两页对
# 错误响应行为不一致。SAPPER_LIVE_START / SAPPER_LIVE_END 两个标记供
# tests/js/live_contract.js 在 Node vm 中真实执行（桩 DOM/fetch/location）。
_LIVE_JS = r"""
/* SAPPER_LIVE_START */
var SapperLang = (function () {
  'use strict';
  var KEY = 'sapper.lang';
  function current() {
    try { return localStorage.getItem(KEY) === 'en' ? 'en' : 'zh'; } catch (e) { return 'zh'; }
  }
  function apply() {
    var lang = current();
    var nodes = document.querySelectorAll('[data-zh]');
    for (var i = 0; i < nodes.length; i++) {
      var value = nodes[i].getAttribute(lang === 'zh' ? 'data-zh' : 'data-en');
      if (value === null) continue;
      /* 只替换首个文本节点，保留标题里的 count 等子元素（M6） */
      var first = nodes[i].firstChild;
      if (first && first.nodeType === 3) {
        first.nodeValue = value;
      } else if (document.createTextNode && nodes[i].insertBefore) {
        nodes[i].insertBefore(document.createTextNode(value), first);
      } else {
        nodes[i].textContent = value;
      }
    }
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
    var toggles = document.querySelectorAll('[data-lang-toggle]');
    for (var j = 0; j < toggles.length; j++) {
      toggles[j].textContent = lang === 'zh' ? 'EN' : '中';
    }
    return lang;
  }
  function toggle() {
    try { localStorage.setItem(KEY, current() === 'zh' ? 'en' : 'zh'); } catch (e) {}
    apply();
    if (typeof SapperLive !== 'undefined' && SapperLive.updateUi) SapperLive.updateUi();
  }
  function bind() {
    var toggles = document.querySelectorAll('[data-lang-toggle]');
    for (var i = 0; i < toggles.length; i++) {
      toggles[i].addEventListener('click', toggle);
    }
    apply();
  }
  return { current: current, apply: apply, toggle: toggle, bind: bind };
})();

var SapperLive = (function () {
  'use strict';
  var S = {
    on: false, served: false, known: null, status: 'offline', busy: false, timer: null
  };
  var opts = {};
  var LABELS = {
    offline: ['Offline snapshot', '离线快照 Offline snapshot'],
    live: ['LIVE', '实时监听 Live'],
    paused: ['Paused', '已暂停 Paused'],
    disconnected: ['Disconnected', '连接断开 Disconnected'],
    error: ['Service error', '服务异常 Error']
  };
  function el(id) { return id ? document.getElementById(id) : null; }
  function tr(en, zh) { return SapperLang.current() === 'en' ? en : zh; }
  function setStatus(status) {
    S.status = status;
    var badge = el(opts.badgeId);
    if (badge) {
      badge.className = 'badge' +
        (status === 'live' ? ' live' : status === 'paused' ? ' paused' :
         status === 'offline' ? ' offline' : ' error');
    }
    var label = el(opts.textId);
    if (label) {
      var pair = LABELS[status] || LABELS.offline;
      label.textContent = tr(pair[0], pair[1]);
    }
    var btn = el(opts.toggleId);
    if (btn) {
      btn.hidden = status === 'offline';
      btn.disabled = !S.served || S.busy || status === 'disconnected' || status === 'error';
      btn.textContent = tr(S.on ? 'Pause live' : 'Resume live',
                           S.on ? '暂停实时' : '恢复实时');
    }
  }
  function updateUi() { setStatus(S.status); }
  function validVersion(v) {
    return v && typeof v.rendered_sha256 === 'string' && v.rendered_sha256.length > 0 &&
      typeof v.ledger_sha256 === 'string' && v.ledger_sha256.length > 0 &&
      typeof v.live_enabled === 'boolean';
  }
  function poll() {
    /* 相对页面目录的上一级：/dashboard/x.html → /api/*（反向代理子路径同样成立） */
    return fetch('../api/version').then(function (r) {
      if (!r.ok) { S.served = false; setStatus('error'); return; }
      return r.json().then(function (v) {
        /* 500/半行/脏响应都没有完整版本字段，绝不当作版本变化 */
        if (!validVersion(v)) { S.served = false; setStatus('error'); return; }
        S.served = true;
        S.on = v.live_enabled;
        /* 暂停态：账本在变，但服务端不重渲染 → 不 reload 到旧 HTML */
        if (v.live_enabled === false) {
          S.known = v.rendered_sha256;
          setStatus('paused');
          return;
        }
        setStatus('live');
        if (S.known === null) { S.known = v.rendered_sha256; return; }
        /* 只比较「已渲染」版本：HTML 真正更新后才刷新，杜绝竞态 */
        if (S.known !== v.rendered_sha256) {
          if (opts.saveState) opts.saveState();
          location.reload();
        }
      });
    }).catch(function () {
      S.served = false;
      setStatus('disconnected');  /* 保持定时器，服务端回来后自动恢复 */
    });
  }
  function postLive(enabled) {
    if (S.busy) return Promise.resolve();
    S.busy = true;
    setStatus(S.status);
    return fetch('../api/live', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: enabled })
    }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function (v) {
      if (typeof v.live_enabled !== 'boolean') throw new Error('bad payload');
      S.busy = false;
      S.on = v.live_enabled;       /* 只在服务端确认后翻转，不乐观更新 */
      setStatus(S.on ? 'live' : 'paused');
    }).catch(function () {
      S.busy = false;
      S.served = false;
      setStatus('error');          /* 失败显式报错，不静默吞掉 */
    });
  }
  function start(config) {
    opts = config || {};
    if (opts.restoreState) opts.restoreState();
    if (location.protocol === 'file:') { setStatus('offline'); return S; }
    var btn = el(opts.toggleId);
    if (btn) btn.addEventListener('click', function () { postLive(!S.on); });
    poll();
    S.timer = setInterval(poll, 2000);
    return S;
  }
  return { state: S, start: start, poll: poll, postLive: postLive, updateUi: updateUi };
})();
/* SAPPER_LIVE_END */
"""
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
    "running": "执行中",
    "completed": "已完成",
    "done": "已完成",
    "failed": "失败",
    "blocked": "受阻",
    "cancelled": "已取消",
    "approved": "已批准",
    "ready": "就绪",
}

# 证据角色中英对照（攻击链步骤口径）
ROLE_ZH = {
    "observation": "观察",
    "reproduction": "复现",
    "impact": "影响",
    "refutation": "反证",
}

# 证据角色 → 节点标记色（攻击链左轨；与关系图 _COLOR_BY_TYPE 同族）
_ROLE_COLOR = {
    "observation": "#46627f",
    "reproduction": "#8a5f00",
    "impact": "#c2451e",
    "refutation": "#47714f",
}


def status_label(status: str) -> str:
    """中文优先、英文兜底的状态标签。"""
    return f"{STATUS_ZH.get(status, status)} {status}"


class RenderError(ValueError):
    """渲染失败。"""


def _esc(text: str) -> str:
    return html_mod.escape(str(text), quote=True)


def _atomic_write_text(path: Path, content: str) -> None:
    """先写临时文件再原子替换：serve 并发读静态文件时不会读到半截 HTML。"""
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(content, encoding="utf-8", newline="\n")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


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
        # 攻击链视图所需的裁决明细（终结节点 + 溯源 + 理由）
        record["verdict_reason"] = str(verdict.get("reason", ""))
        record["verifier_run"] = str(verdict.get("verifier_run") or "")
        record["verdict_evidence"] = list(verdict.get("evidence", []))
        hypotheses.append(record)
    # 证据按账本顺序（追加序 = 推演序），并标注所属 Run 的执行者阶段
    run_actor: dict[str, str] = {}
    for run_id, run in derived.runs.items():
        run_actor[run_id] = str(run.get("actor") or "")
    evidence: list[dict] = []
    for ev in derived.evidence_by_id.values():
        item = ev.model_dump()
        run_id = str(item.get("run") or "")
        actor = run_actor.get(run_id, "")
        item["stage_actor"] = actor or "commander"
        item["stage_key"] = f"{actor or 'commander'}:{run_id or '-'}"
        item["role_zh"] = ROLE_ZH.get(item["role"], item["role"])
        evidence.append(item)
    intents = []
    for intent_id in sorted(derived.intents):
        entry = derived.intents[intent_id]
        entry = dict(entry)
        entry["status_zh"] = STATUS_ZH.get(
            entry.get("status", ""), entry.get("status", "")
        )
        intents.append({"id": intent_id, **entry})
    runs = []
    for run_id in sorted(derived.runs):
        entry = derived.runs[run_id]
        entry = dict(entry)
        entry["status_zh"] = STATUS_ZH.get(
            entry.get("status", ""), entry.get("status", "")
        )
        runs.append({"id": run_id, **entry})
    approvals = []
    for aid in sorted(derived.approvals):
        entry = dict(derived.approvals[aid])
        entry["status_zh"] = STATUS_ZH.get(
            entry.get("status", ""), entry.get("status", "")
        )
        approvals.append(entry)
    return {
        "facts": facts,
        "assets": assets,
        "services": services,
        "hypotheses": hypotheses,
        "evidence": evidence,
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
        (
            "- 产物导航 Outputs："
            "[dashboard.html](dashboard.html) · "
            "[attack-graph.html](attack-graph.html) · "
            "[attack-graph.mmd](attack-graph.mmd)"
        ),
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
        "-（无未完成清理项）",
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
        lines.append(
            f'    {asset_id(fact["target"])}["资产 asset: {_esc(fact["target"])}"]'
        )
    for fact in view["services"]:
        lines.append(
            f"    {_sanitize_node_id(fact['id'])}"
            f'["服务 service: {_esc(fact.get("title", fact["id"]))}"]'
        )
    for hyp in view["hypotheses"]:
        label = (
            f"{hyp['id']} {_esc(hyp.get('claim', ''))}（{status_label(hyp['status'])}）"
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
            f'    {run["id"]}["执行 run {run["id"]}（{status_label(run["status"])}）"]'
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
    # 四产物导航闭环：Mermaid 注释不影响渲染
    lines.append("  %% 面板 dashboard.html · 黑板 board.md · 本文件 attack-graph.mmd")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# kill chain（攻击链推演视图：证据按账本顺序 = 攻击叙事时间线）
# ---------------------------------------------------------------------------

_STAGE_LABEL = {
    "worker": ("攻击执行阶段 WORKER", "Worker stage"),
    "verifier": ("独立验证阶段 VERIFIER", "Verifier stage"),
    "commander": ("指挥观察阶段 COMMANDER", "Commander stage"),
}

_TERMINAL = {
    "confirmed": ("★", "FINDING 已达成", "Finding confirmed"),
    "killed": ("✖", "KILLED 已证伪", "Hypothesis killed"),
    "provisional": ("◐", "PROVISIONAL 暂定", "Provisional"),
    "inconclusive": ("○", "INCONCLUSIVE 未决", "Inconclusive"),
    "deferred": ("○", "DEFERRED 暂缓", "Deferred"),
    "open": ("○", "OPEN 推进中", "In progress"),
}


def _chain_sha(sha: str) -> str:
    return f"{sha[:6]}…{sha[-4:]}" if len(sha) >= 12 else sha


def render_kill_chain(view: dict) -> str:
    """把每个假设的证据序列渲染为垂直攻击链推演轨。

    顺序即账本追加序 = 实际推演序；按 Run 的 actor 分阶段（Worker/Verifier），
    终结节点是裁决（confirmed = 高亮 FINDING 封印卡）。全部内容转义，
    标签走 data-zh/data-en 双语。
    """
    by_hyp: dict[str, list[dict]] = {}
    for ev in view["evidence"]:
        by_hyp.setdefault(ev["hypothesis"], []).append(ev)

    parts: list[str] = []
    if not view["hypotheses"]:
        parts.append(
            '<p class="chain-empty" data-zh="账本中尚无假设：先用 prism.py hypothesis 建账，'
            '攻击链会随证据追加自动生长。" data-en="No hypotheses in the ledger yet: create one '
            'with prism.py hypothesis; the kill chain grows as evidence lands.">'
            "账本中尚无假设：先用 prism.py hypothesis 建账，攻击链会随证据追加自动生长。</p>"
        )
        return "\n".join(parts)

    for hyp in view["hypotheses"]:
        hyp_id = hyp["id"]
        steps = by_hyp.get(hyp_id, [])
        status = hyp["status"]
        term_symbol, term_zh, term_en = _TERMINAL.get(status, _TERMINAL["open"])
        parts.append(f'<section class="chain" id="chain-{_esc(hyp_id)}">')

        # -- 链头：假设声明 + 状态 + 溯源 -----------------------------------
        verifier_chip = (
            f'<span class="chip chip-verifier" title="verifier_run">'
            f'<span data-zh="验证溯源" data-en="verifier run">验证溯源</span>'
            f" {_esc(hyp['verifier_run'])}</span>"
            if hyp["verifier_run"]
            else ""
        )
        parts.append(
            f'<header class="chain-head">'
            f'<div class="chain-head-row"><span class="chain-id">{_esc(hyp_id)}</span>'
            f'<span class="st st-{_esc(status)}">{_esc(status)} {_esc(hyp["status_zh"])}</span>'
            f"{verifier_chip}</div>"
            f'<h3 class="chain-claim">{_esc(hyp.get("claim", ""))}</h3>'
            f'<div class="chain-scope mono">{_esc(hyp.get("scope", ""))}</div>'
            f"</header>"
        )

        # -- 推演轨 ----------------------------------------------------------
        if not steps:
            parts.append(
                '<p class="chain-empty" data-zh="该假设暂无证据步骤。" '
                'data-en="No evidence steps for this hypothesis yet.">'
                "该假设暂无证据步骤。</p></section>"
            )
            continue
        parts.append('<ol class="chain-steps">')
        index = 0
        seen_stage: str | None = None
        for ev in steps:
            stage = ev["stage_key"]
            if stage != seen_stage:
                seen_stage = stage
                actor = ev["stage_actor"]
                stage_zh, stage_en = _STAGE_LABEL.get(
                    actor, (f"阶段 {actor.upper()}", f"{actor.upper()} stage")
                )
                parts.append(
                    f'<li class="stage" style="--i:{index}">'
                    f'<span class="stage-run mono">{_esc(ev.get("run") or "-")}</span>'
                    f'<span class="stage-name" data-zh="{_esc(stage_zh)}" '
                    f'data-en="{_esc(stage_en)}">{_esc(stage_zh)}</span></li>'
                )
                index += 1
            color = _ROLE_COLOR.get(ev["role"], "#6f695e")
            effect_badge = (
                '<span class="chip chip-refutes" data-zh="反证 refutes" data-en="refutes">'
                "反证 refutes</span>"
                if ev["effect"] == "refutes"
                else ""
            )
            parts.append(
                f'<li class="step" style="--rc:{color};--i:{index}">'
                f'<div class="marker" aria-hidden="true">{index:02d}</div>'
                f'<div class="step-card">'
                f'<div class="step-top">'
                f'<span class="eid mono">{_esc(ev["id"])}</span>'
                f'<span class="role" data-zh="{_esc(ev["role"])} {_esc(ev["role_zh"])}" '
                f'data-en="{_esc(ev["role"])}">{_esc(ev["role"])} {_esc(ev["role_zh"])}</span>'
                f"{effect_badge}"
                f'<span class="chip chip-run mono">{_esc(ev.get("run") or "-")}</span>'
                f'<time class="mono">{_esc(ev.get("at", ""))}</time>'
                f"</div>"
                f'<p class="step-sum">{_esc(ev.get("summary", ""))}</p>'
                f'<div class="step-art">'
                f'<span class="art-path mono" title="{_esc(ev.get("artifact", ""))}">'
                f"{_esc(ev.get('artifact', ''))}</span>"
                f'<span class="art-sha mono" title="SHA-256">{_chain_sha(str(ev.get("sha256", "")))}</span>'
                f"</div></div></li>"
            )
            index += 1

        # -- 终结节点：裁决 ---------------------------------------------------
        reason = hyp.get("verdict_reason", "")
        reason_block = (
            f'<details class="t-reason"><summary data-zh="裁决理由 reason" '
            f'data-en="Verdict reason">裁决理由 reason</summary><p>{_esc(reason)}</p></details>'
            if reason
            else ""
        )
        terminal_cls = "terminal " + (
            "terminal-hit"
            if status == "confirmed"
            else "terminal-killed"
            if status == "killed"
            else ""
        )
        parts.append(
            f'<li class="{terminal_cls}" style="--i:{index}">'
            f'<div class="t-card">'
            f'<span class="t-symbol" aria-hidden="true">{term_symbol}</span>'
            f'<span class="t-label" data-zh="{_esc(term_zh)}" data-en="{_esc(term_en)}">'
            f"{_esc(term_zh)}</span>"
            f"{reason_block}</div></li>"
        )
        parts.append("</ol></section>")
    return "\n".join(parts)


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
  --warn: #8a5f00;          /* 进行中 琥珀（#fbfaf7 上 5.41:1，≥4.5:1） */
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
.badge.paused .dot { background: var(--warn); }
.badge.error { border-color: var(--accent); color: var(--accent); }
.badge.error .dot { background: var(--accent); }
.badge.offline .dot { background: var(--muted); }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .35; } }
#live-toggle {
  font: inherit; cursor: pointer; background: var(--surface); color: var(--ink);
  border: 1px solid var(--line-strong); border-radius: 999px; padding: 8px 14px;
  min-height: 44px; font-family: var(--font-mono); font-size: 11.5px;
  transition: background var(--dur-fast) ease-out, transform var(--dur-fast) ease-out;
}
#live-toggle:hover { background: var(--accent-soft); }
#live-toggle:active { transform: translateY(1px); }
#live-toggle:disabled { opacity: .55; cursor: not-allowed; }
#live-toggle:focus-visible, input:focus-visible, .lang:focus-visible,
.navbtn:focus-visible {
  outline: 2px solid var(--accent); outline-offset: 2px;
}
#live-toggle[hidden], .lang[hidden] { display: none; }

/* 导航按钮：两页共用同一语义与样式（最小 44×44 触摸目标） */
.navbtn {
  display: inline-flex; align-items: center; justify-content: center;
  min-height: 44px; padding: 8px 16px; text-decoration: none; white-space: nowrap;
  font: 12px var(--font-mono); color: var(--ink); background: var(--surface);
  border: 1px solid var(--line-strong); border-radius: var(--radius);
  transition: background var(--dur-fast) ease-out;
}
.navbtn:hover { background: var(--accent-soft); }

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
  border: 1px solid var(--line-strong); border-radius: var(--radius);
  padding: 8px 14px; min-height: 44px; display: inline-flex;
  align-items: center; justify-content: center;
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
      <span class="badge offline" id="live-badge"><span class="dot"></span><span id="live-text">离线快照 Offline snapshot</span></span>
      <button id="live-toggle" hidden>暂停实时</button>
      <button class="lang" data-lang-toggle title="切换中英文 Switch language">EN</button>
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
    <input id="filter" type="text" placeholder="过滤 Filter：目标 / 状态 / ID 关键词">
    <a class="navbtn" href="attack-graph.html" title="打开攻击图 Attack graph">攻击图 →</a>
    <a class="navbtn" href="board.md" title="战役黑板 Board">黑板 →</a>
    <a class="navbtn" href="attack-graph.mmd" title="Mermaid 源 Mermaid source">Mermaid →</a>
    <button class="lang" data-lang-toggle title="切换中英文 Switch language">EN</button>
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
    战役黑板 Board：<a href="board.md">board.md</a> ·
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

/*__SAPPER_LIVE_JS__*/

/* ---------- 跨页状态：语言 + 过滤词 ---------- */
SapperLang.bind();
var filterInput = document.getElementById('filter');
function saveFilter() {
  try { sessionStorage.setItem('sapper.filter', filterInput.value); } catch (e) {}
}
function restoreFilter() {
  try { filterInput.value = sessionStorage.getItem('sapper.filter') || ''; } catch (e) {}
}
/* ---------- 过滤（空分区折叠 + 空态提示） ---------- */
function filterTables() {
  var q = filterInput.value.toLowerCase();
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
filterInput.addEventListener('input', function () { saveFilter(); filterTables(); });

/* ---------- 实时挂钩：两页共用同一状态机（serve 模式生效，离线自动退化） ---------- */
SapperLive.start({
  badgeId: 'live-badge',
  textId: 'live-text',
  toggleId: 'live-toggle',
  saveState: saveFilter,
  restoreState: restoreFilter
});
filterTables();
</script>
</body>
</html>
""",
    autoescape=True,  # C2：账本里的 claim/scope/target 一律视为不可信数据
)


def render_dashboard(view: dict, now_iso: str) -> str:
    rendered = _DASHBOARD_TEMPLATE.render(
        now=now_iso,
        counts=view["counts"],
        hypotheses=view["hypotheses"],
        intents=view["intents"],
        runs=view["runs"],
        approvals=view["approvals"],
    )
    return rendered.replace("/*__SAPPER_LIVE_JS__*/", _LIVE_JS)


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
        add_node(
            fact["id"], f"服务 service: {fact.get('title', fact['id'])}", "service"
        )
    for hyp in view["hypotheses"]:
        add_node(
            hyp["id"],
            f"{hyp['id']} {hyp.get('claim', '')[:40]}"
            + (
                "★发现 finding"
                if hyp["is_finding"]
                else f"（{status_label(hyp['status'])}）"
            ),
            "finding" if hyp["is_finding"] else "hypothesis",
        )
    # Intent / Run 属流程机械（面板表格与攻击链分阶段已呈现），不再入攻击面图：
    # 全部节点 = 资产 / 服务 / 假设，边 = 攻击面关系，杜绝"执行 run R1"噪音

    # 大图降噪：只保留与 findings/活动 intent 相关的假设子集之外全部保留
    # （当前规模直接全量；节点 > 500 时按 finding/一跳过滤，见 ADR-0011）
    if len(node_specs) > 500:
        keep = set(view["findings"])
        node_specs = [
            spec for spec in node_specs if spec[2] != "hypothesis" or spec[0] in keep
        ]

    # 视觉层级（攻击面优先）：finding > 服务/资产 > 假设；字体/尺寸随类型分级
    _NODE_SIZE = {"finding": 26, "asset": 17, "service": 17, "hypothesis": 13}
    _NODE_FONT = {"finding": 15, "asset": 13, "service": 13, "hypothesis": 11}
    for node_id, label, type_ in node_specs:
        # C2：pyvis 的 label/title 会进入 vis-network 的 HTML tooltip，
        # 账本内容必须转义；canvas 文本形态下实体按字面显示，同样安全
        safe_label = _esc(label)
        color = _COLOR_BY_TYPE.get(type_, "#cccccc")
        net.add_node(
            node_id,
            label=safe_label,
            color=color,
            title=safe_label,
            size=_NODE_SIZE.get(type_, 15),
            font={"size": _NODE_FONT.get(type_, 12), "color": "#211e19",
                  "face": "Microsoft YaHei UI", "vadjust": 2},
            borderWidth=2 if type_ == "finding" else 1,
            borderWidthSelected=3,
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
                edges.append(
                    (hyp["id"], fact["id"], STATUS_ZH.get(hyp["status"], hyp["status"]))
                )
        for fact in view["assets"]:
            if _family_hosts(str(fact.get("target", ""))) & hosts:
                edges.append(
                    (
                        hyp["id"],
                        asset_ids[_sanitize_node_id(fact["target"])],
                        STATUS_ZH.get(hyp["status"], hyp["status"]),
                    )
                )
    # Intent/Run 的流程边（intent→run、fact→intent）随节点一并移出攻击面图

    for source, target, label in edges:
        safe_edge = _esc(label)
        net.add_edge(
            source,
            target,
            title=safe_edge,
            label=safe_edge if label != "部署 deploy" else "",
            color={"color": "rgba(33,30,25,.4)", "highlight": "#c2451e"},
            font={"size": 11, "color": "#6f695e", "strokeWidth": 3,
                  "strokeColor": "#f7f5f0"},
            arrows={"to": {"enabled": True, "scaleFactor": 0.7}},
        )

    out_html.parent.mkdir(parents=True, exist_ok=True)
    net.write_html(str(out_html), notebook=False)
    _strip_external_refs(out_html)
    _inject_graph_header(out_html, render_kill_chain(view))


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


# attack-graph.html 注入的头部状态条 + 视图切换 + 攻击链（离线自动退化快照）
_GRAPH_HEADER_HTML = """<style>
:root { --ink: #211e19; --muted: #6f695e; --surface: #fbfaf7; --line: rgba(33,30,25,.14);
        --line-strong: rgba(33,30,25,.28); --accent: #c2451e; --accent-soft: rgba(194, 69, 30, .09);
        --ok: #47714f; --warn: #8a5f00; --info: #46627f; --bg: #f2f0ea;
        --font-display: Bahnschrift, "Segoe UI", "Microsoft YaHei UI", sans-serif;
        --font-body: "Microsoft YaHei UI", "PingFang SC", "Segoe UI", sans-serif;
        --font-mono: "Cascadia Mono", Consolas, "Courier New", monospace;
        --ease-out: cubic-bezier(.16,1,.3,1);
        --shadow-1: 0 2px 6px rgba(33,30,25,.07); --shadow-2: 0 8px 28px rgba(33,30,25,.10); }
body { margin: 0; background: var(--bg); font-family: var(--font-body); color: var(--ink);
  font-size: 14px; line-height: 1.7; }
#graph-bar { position: fixed; top: 0; left: 0; right: 0; z-index: 10; min-height: 56px;
  display: flex; align-items: center; flex-wrap: wrap; gap: 12px; padding: 6px 18px;
  background: var(--surface); border-bottom: 2px solid var(--ink); box-shadow: var(--shadow-2); }
#graph-bar .brand { font-family: var(--font-display); font-weight: 700;
  font-size: 17px; letter-spacing: -.01em; color: var(--ink); }
#graph-bar .brand em { font-style: normal; color: var(--accent); }
#graph-bar .sub { color: var(--muted); font-size: 12px; }
.badge { display: inline-flex; align-items: center; gap: 6px; font-family: var(--font-mono);
  font-size: 11.5px; padding: 2px 9px; border: 1px solid var(--line-strong); border-radius: 999px;
  background: var(--surface); color: var(--muted); }
.badge .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--muted); }
.badge.live { color: var(--ok); border-color: var(--ok); }
.badge.live .dot { background: var(--ok); animation: gpulse 2s cubic-bezier(.16,1,.3,1) infinite; }
.badge.paused { color: var(--warn); border-color: var(--warn); }
.badge.paused .dot { background: var(--warn); }
.badge.error { color: var(--accent); border-color: var(--accent); }
.badge.error .dot { background: var(--accent); }
@keyframes gpulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }
#graph-bar .navbtn, #graph-bar .lang {
  display: inline-flex; align-items: center; justify-content: center;
  min-height: 44px; padding: 8px 16px; font-family: var(--font-mono);
  font-size: 11.5px; color: var(--ink); background: var(--surface);
  border: 1px solid var(--line-strong); border-radius: 999px; text-decoration: none;
  white-space: nowrap; cursor: pointer; transition: background 160ms ease-out; }
#graph-bar .navbtn:hover, #graph-bar .lang:hover { background: var(--accent-soft); }
#graph-bar .navbtn:focus-visible, #graph-bar .lang:focus-visible, .seg-btn:focus-visible {
  outline: 2px solid var(--accent); outline-offset: 2px; }
/* pyvis 的 .card 是 body 直接子元素：给固定头部条留出空间。
   旧实现把节点搬进包装容器，但那段脚本早于 pyvis 节点解析，恒不生效，已移除 */
body > .card { padding-top: 68px; }

/* ============ 视图切换（攻击链 / 资产网络） ============ */
.seg { display: inline-flex; border: 1px solid var(--line-strong); border-radius: 999px;
  overflow: hidden; background: var(--surface); }
.seg-btn { appearance: none; border: none; background: transparent; cursor: pointer;
  font-family: var(--font-mono); font-size: 12px; color: var(--muted);
  padding: 9px 18px; min-height: 44px; transition: background 160ms ease-out, color 160ms ease-out; }
.seg-btn + .seg-btn { border-left: 1px solid var(--line-strong); }
.seg-btn:hover { color: var(--ink); }
.seg-btn.active { background: var(--ink); color: #fbfaf7; }
body[data-view="chain"] > .card { display: none; }
body[data-view="net"] > #chain-root { display: none; }

/* ============ 攻击链推演轨 ============ */
#chain-root { max-width: 980px; margin: 0 auto; padding: 84px 20px 90px; }
.chain { margin: 0 0 44px; }
.chain-head { background: var(--surface); border: 1px solid var(--line-strong);
  border-left: 4px solid var(--ink); box-shadow: var(--shadow-1); padding: 16px 20px 13px; }
.chain-head-row { display: flex; align-items: center; flex-wrap: wrap; gap: 10px;
  font-family: var(--font-mono); font-size: 12px; }
.chain-id { font-family: var(--font-display); font-weight: 700; font-size: 19px; }
.chain-head .st { display: inline-block; padding: 1px 9px; border-radius: 2px;
  font-family: var(--font-mono); font-size: 11px; border: 1px solid var(--line-strong);
  color: var(--muted); background: var(--surface); }
.chain-head .st-confirmed { background: var(--accent); border-color: var(--accent); color: #fbfaf7; }
.chain-head .st-killed { color: var(--ok); border-color: var(--ok); }
.chip { display: inline-block; padding: 1px 8px; border-radius: 2px; font-size: 11px;
  font-family: var(--font-mono); border: 1px solid var(--line-strong); color: var(--muted); }
.chip-verifier { color: var(--info); border-color: var(--info); }
.chip-refutes { color: var(--ok); border-color: var(--ok); }
.chip-run { color: var(--info); border-color: var(--info); }
.chain-claim { margin: 8px 0 4px; font-family: var(--font-display); font-weight: 700;
  font-size: 18px; line-height: 1.4; letter-spacing: -.01em; }
.chain-scope { font-size: 12px; color: var(--muted); }
.mono { font-family: var(--font-mono); }

.chain-steps { list-style: none; margin: 18px 0 0; padding: 0 0 0 34px; position: relative; }
/* 左轨：静态底线 + 入场生长线 */
.chain-steps::before { content: ""; position: absolute; left: 15px; top: 6px; bottom: 6px;
  width: 2px; background: var(--line-strong); }
.chain-steps.js-draw::after { content: ""; position: absolute; left: 15px; top: 6px; bottom: 6px;
  width: 2px; background: var(--ink); transform-origin: top; transform: scaleY(0);
  animation: railgrow .9s var(--ease-out) .15s forwards; }
@keyframes railgrow { to { transform: scaleY(1); } }

.chain-steps li { position: relative; margin: 0 0 12px; }
.stage { display: flex; align-items: center; gap: 12px; margin: 22px 0 12px !important; }
.stage-run { font-size: 11.5px; color: var(--info); border: 1px solid var(--info);
  border-radius: 2px; padding: 0 7px; background: var(--surface); }
.stage-name { font-family: var(--font-display); font-weight: 700; font-size: 13px;
  letter-spacing: .08em; color: var(--muted); text-transform: uppercase; }
.stage-name::after { content: ""; display: inline-block; width: 120px; height: 1px;
  background: var(--line-strong); margin-left: 12px; vertical-align: middle; }

.step { display: flex; gap: 14px; align-items: flex-start; }
.step .marker { position: absolute; left: -34px; top: 10px; width: 32px; height: 32px;
  border-radius: 50%; background: var(--rc, var(--muted)); color: #fbfaf7;
  font-family: var(--font-display); font-weight: 700; font-size: 12.5px;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 0 0 3px var(--bg); }
.step-card { flex: 1; background: var(--surface); border: 1px solid var(--line-strong);
  border-left: 3px solid var(--rc, var(--muted)); box-shadow: var(--shadow-1);
  padding: 11px 15px 10px; transition: transform 160ms var(--ease-out), box-shadow 160ms var(--ease-out); }
.step-card:hover { transform: translateX(3px); box-shadow: var(--shadow-2); }
.step-top { display: flex; align-items: center; flex-wrap: wrap; gap: 8px;
  font-family: var(--font-mono); font-size: 11.5px; color: var(--muted); }
.step-top .eid { font-weight: 700; color: var(--ink); font-size: 12.5px; }
.step-top .role { color: var(--rc, var(--muted)); font-weight: 600; }
.step-top time { margin-left: auto; }
.step-sum { margin: 6px 0 7px; line-height: 1.65; }
.step-art { display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
  font-size: 11.5px; color: var(--muted); border-top: 1px dashed var(--line-strong); padding-top: 7px; }
.art-path { max-width: 60%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.terminal .t-card { display: flex; align-items: center; flex-wrap: wrap; gap: 12px;
  border: 2px solid var(--ink); box-shadow: var(--shadow-2); padding: 15px 20px;
  background: var(--surface); font-family: var(--font-display); font-weight: 700; font-size: 16px; }
.terminal-hit .t-card { background: var(--accent); border-color: var(--accent); color: #fbfaf7; }
.terminal-hit .t-card .t-reason, .terminal-hit .t-card summary { color: #fbfaf7; }
.terminal-killed .t-card { border-color: var(--ok); color: var(--ok); }
.t-symbol { font-size: 20px; }
.t-reason { flex-basis: 100%; font-family: var(--font-body); font-weight: 400; font-size: 13px; }
.t-reason summary { cursor: pointer; font-family: var(--font-mono); font-size: 11.5px;
  color: var(--muted); }
.t-reason p { margin: 6px 0 0; }
.chain-empty { background: var(--surface); border: 1px dashed var(--line-strong);
  padding: 18px 20px; color: var(--muted); }

/* 入场序列：步骤按 --i 错峰浮现（含分阶段行与终结卡） */
#chain-root.js .chain-steps li { opacity: 0; transform: translateY(14px);
  animation: stepin 460ms var(--ease-out) forwards; animation-delay: calc(var(--i, 0) * 70ms); }
@keyframes stepin { to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) {
  .badge.live .dot { animation: none; }
  .chain-steps.js-draw::after { animation: none; transform: none; }
  #chain-root.js .chain-steps li { animation: none; opacity: 1; transform: none; }
  .step-card:hover { transform: none; }
}
@media (max-width: 720px) { #chain-root { padding: 78px 12px 70px; } }
</style>
<div id="graph-bar">
  <span class="brand">攻击图 <em>Attack Graph</em></span>
  <div class="seg" role="tablist" aria-label="视图 View">
    <button class="seg-btn active" data-view-btn="chain" role="tab" aria-selected="true"
      data-zh="攻击链 Kill Chain" data-en="Kill Chain">攻击链 Kill Chain</button>
    <button class="seg-btn" data-view-btn="net" role="tab" aria-selected="false"
      data-zh="资产网络 Network" data-en="Network">资产网络 Network</button>
  </div>
  <span class="sub" data-zh="sapper-skill · 由账本回放派生" data-en="sapper-skill · derived from ledger replay">sapper-skill · 由账本回放派生</span>
  <span class="badge" id="graph-live"><span class="dot"></span><span id="graph-live-text">离线快照 Offline snapshot</span></span>
  <button class="lang" data-lang-toggle title="切换中英文 Switch language">EN</button>
  <a class="navbtn" href="dashboard.html" data-zh="战役面板 →" data-en="Dashboard →">战役面板 →</a>
  <a class="navbtn" href="board.md" data-zh="黑板 →" data-en="Board →">黑板 →</a>
  <a class="navbtn" href="attack-graph.mmd" data-zh="Mermaid →" data-en="Mermaid →">Mermaid →</a>
</div>
<div id="chain-root">/*__SAPPER_CHAIN__*/</div>
<script>
(function () {
  /* 整页 reload 会清空 pyvis 视口：存进 sessionStorage，回来恢复（M3） */
  function saveViewport() {
    try {
      var net = window.network;
      if (net && net.getViewPosition) {
        sessionStorage.setItem('sapper.graph.view', JSON.stringify({
          position: net.getViewPosition(), scale: net.getScale()
        }));
      }
    } catch (e) {}
  }
  function restoreViewport() {
    try {
      var raw = sessionStorage.getItem('sapper.graph.view');
      var net = window.network;
      if (raw && net && net.moveTo) {
        var v = JSON.parse(raw);
        net.moveTo({ position: v.position, scale: v.scale, animation: false });
      }
    } catch (e) {}
  }
  window.addEventListener('beforeunload', saveViewport);
  window.addEventListener('load', restoreViewport);

  /* ---------- 视图切换：攻击链（默认）/ 资产网络 ---------- */
  function netReady() {
    var net = window.network;
    if (!net) { return; }
    try { net.redraw(); net.fit(); } catch (e) {}
    restoreViewport();
  }
  function setView(view, animate) {
    document.body.setAttribute('data-view', view);
    var buttons = document.querySelectorAll('.seg-btn');
    for (var i = 0; i < buttons.length; i++) {
      var on = buttons[i].getAttribute('data-view-btn') === view;
      buttons[i].classList.toggle('active', on);
      buttons[i].setAttribute('aria-selected', on ? 'true' : 'false');
    }
    try { sessionStorage.setItem('sapper.graph.tab', view); } catch (e) {}
    if (view === 'net') {
      /* 隐藏容器里初始化的画布尺寸为 0：激活时重绘并复位视口 */
      if (animate) { setTimeout(netReady, 30); } else { netReady(); }
    }
  }
  var savedView = null;
  try { savedView = sessionStorage.getItem('sapper.graph.tab'); } catch (e) {}
  setView(savedView === 'net' ? 'net' : 'chain', false);
  var segButtons = document.querySelectorAll('.seg-btn');
  for (var i = 0; i < segButtons.length; i++) {
    segButtons[i].addEventListener('click', function () {
      setView(this.getAttribute('data-view-btn'), true);
    });
  }
  /* 攻击链入场编排：JS 可用才隐藏待入场（无 JS 环境直接完整显示） */
  var chainRoot = document.getElementById('chain-root');
  if (chainRoot && 'querySelector' in chainRoot) {
    chainRoot.className = 'js';
    var steps = document.querySelector('.chain-steps');
    if (steps) { steps.className += ' js-draw'; }
  }
/*__SAPPER_LIVE_JS__*/
  SapperLang.bind();
  SapperLive.start({
    badgeId: 'graph-live',
    textId: 'graph-live-text',
    toggleId: null,
    saveState: saveViewport,
    restoreState: function () {}
  });
})();
</script>
"""


def _inject_graph_header(html_path: Path, chain_html: str) -> None:
    """注入头部状态条 + 视图切换 + 攻击链推演轨（serve 模式生效，离线自动退化）。"""
    html = html_path.read_text(encoding="utf-8")
    if "graph-bar" in html:
        return
    header = _GRAPH_HEADER_HTML.replace("/*__SAPPER_LIVE_JS__*/", _LIVE_JS)
    header = header.replace("/*__SAPPER_CHAIN__*/", chain_html)
    html = html.replace("<body>", "<body>" + header, 1)
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
        _atomic_write_text(target_dir / name, content)
    # pyvis 的 check_html 要求文件名以 .html 结尾，临时名必须保留该后缀
    graph_tmp = target_dir / f"attack-graph.{os.getpid()}.tmp.html"
    try:
        render_attack_graph(view, graph_tmp)
        os.replace(graph_tmp, target_dir / "attack-graph.html")
    finally:
        graph_tmp.unlink(missing_ok=True)
    return {
        "out_dir": str(target_dir),
        "files": list(outputs) + ["attack-graph.html"],
        "now": now_iso,
    }
