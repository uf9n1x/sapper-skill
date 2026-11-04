"""P3 可视化测试（T-041）。

锁定三条验收：
1. 离线打开——dashboard.html 与 attack-graph.html 静态资源全部内联
   （无任何 http(s) 外链 script/href），单文件可直接打开
2. 图与账本一致——节点/边/finding 由账本回放派生：confirmed 假设
   投影为 finding，intent→run 关系如实呈现
3. 删除派生物后可重建——board.md / attack-graph.mmd 确定性
   （同 --now 逐字节一致）；删除输出目录后 render 完整重建

设计红线（升级方案 §9）：
- 静态 HTML 是"状态变化时更新、打开或刷新查看"，不伪称实时推送
- board.md：NOW、Active Runs、Ready/Blocked Intents、Findings、Cleanup
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from conftest import run_prism
from prism import state

NOW = "2026-01-01T00:00:00Z"
NOW_DATE = "2026-01-01T08:30:00Z"


def seed_render_case(tmp_path: Path) -> Path:
    """覆盖 asset/service、confirmed finding、killed 假设、intent→run。"""
    case = tmp_path / "case"
    (case / "artifacts").mkdir(parents=True)
    (case / "results").mkdir(parents=True)
    (case / "ledger.jsonl").touch()
    records = [
        {
            "v": 2,
            "type": "fact",
            "id": "F1",
            "at": NOW,
            "kind": "asset",
            "target": "192.0.2.10",
            "title": "主机 192.0.2.10",
            "summary": "存活主机",
        },
        {
            "v": 2,
            "type": "fact",
            "id": "F2",
            "at": NOW,
            "kind": "service",
            "target": "192.0.2.10:80/tcp",
            "title": "example-httpd 2.4",
            "summary": "80 端口 HTTP",
        },
        {
            "v": 2,
            "type": "hypothesis",
            "id": "H1",
            "at": NOW,
            "claim": "192.0.2.10 管理后台存在未授权访问",
            "scope": "192.0.2.10 web",
            "disprove_if": ["控制请求返回 401"],
        },
        {
            "v": 2,
            "type": "verdict",
            "id": "V1",
            "at": NOW,
            "hypothesis": "H1",
            "status": "confirmed",
            "evidence": ["E1"],
            "reason": "三角色闭环",
        },
        {
            "v": 2,
            "type": "hypothesis",
            "id": "H2",
            "at": NOW,
            "claim": "target.example.test 存在子域接管",
            "scope": "DNS",
            "disprove_if": ["CNAME 指向活跃服务"],
        },
        {
            "v": 2,
            "type": "verdict",
            "id": "V2",
            "at": NOW,
            "hypothesis": "H2",
            "status": "killed",
            "evidence": ["E1"],
            "reason": "反证成立",
        },
        {
            "v": 2,
            "type": "intent",
            "id": "I1",
            "at": NOW,
            "event": "created",
            "title": "横向探测内网",
            "objective": "扩展访问面",
            "angle": "credential reuse",
            "target": "192.0.2.0/24",
            "linked_facts": ["F1"],
        },
        {
            "v": 2,
            "type": "run",
            "id": "R1",
            "at": NOW,
            "event": "created",
            "intent": "I1",
            "actor": "worker",
        },
        {
            "v": 2,
            "type": "run",
            "id": "R1",
            "at": NOW,
            "event": "completed",
            "result_ref": "results/R1.json",
        },
    ]
    with open(case / "ledger.jsonl", "a", encoding="utf-8", newline="\n") as fh:
        fh.writelines(
            json.dumps(record, ensure_ascii=False) + "\n" for record in records
        )
    return case


def render(case: Path, out_dir: Path | None = None):
    args = ["render", str(case), "--now", NOW_DATE]
    if out_dir is not None:
        args += ["--out-dir", str(out_dir)]
    return run_prism(*args)


_EXTERNAL_REF_RE = re.compile(r'(?:src|href)="https?://', re.IGNORECASE)


# ---------------------------------------------------------------------------
# 验收 1：离线打开
# ---------------------------------------------------------------------------


class TestOffline:
    def test_all_four_outputs_generated(self, tmp_path: Path):
        case = seed_render_case(tmp_path)
        result = render(case)
        assert result.returncode == 0, result.stderr
        report = json.loads(result.stdout)
        out = Path(report["out_dir"])
        for name in (
            "board.md",
            "dashboard.html",
            "attack-graph.html",
            "attack-graph.mmd",
        ):
            assert (out / name).is_file(), f"缺少 {name}"

    def test_no_external_references_in_html(self, tmp_path: Path):
        case = seed_render_case(tmp_path)
        render(case)
        out = case / "dashboard"
        for name in ("dashboard.html", "attack-graph.html"):
            html = (out / name).read_text(encoding="utf-8")
            matches = _EXTERNAL_REF_RE.findall(html)
            assert not matches, f"{name} 存在外链: {matches[:3]}"

    def test_dashboard_contains_sections_and_filter(self, tmp_path: Path):
        case = seed_render_case(tmp_path)
        render(case)
        html = (case / "dashboard" / "dashboard.html").read_text(encoding="utf-8")
        for marker in ("NOW", "Findings", "Intents", "Approvals"):
            assert marker in html
        # 状态过滤：内联脚本，无外部依赖
        assert "<script>" in html

    def test_board_has_required_sections(self, tmp_path: Path):
        case = seed_render_case(tmp_path)
        render(case)
        board = (case / "dashboard" / "board.md").read_text(encoding="utf-8")
        for section in ("NOW", "Active Runs", "Intents", "Findings", "Cleanup"):
            assert section in board


# ---------------------------------------------------------------------------
# 验收 2：图与账本一致
# ---------------------------------------------------------------------------


class TestConsistencyWithLedger:
    def test_mermaid_contains_ledger_entities(self, tmp_path: Path):
        case = seed_render_case(tmp_path)
        render(case)
        mmd = (case / "dashboard" / "attack-graph.mmd").read_text(encoding="utf-8")
        # 资产 / 服务 / finding / intent→run 全部由账本派生
        assert "192.0.2.10" in mmd
        assert "example-httpd 2.4" in mmd
        assert "H1" in mmd and "H2" in mmd
        assert "I1" in mmd and "R1" in mmd

    def test_findings_projection_matches_replay(self, tmp_path: Path):
        case = seed_render_case(tmp_path)
        derived = state.replay(case)
        render(case)
        board = (case / "dashboard" / "board.md").read_text(encoding="utf-8")
        for finding in derived.findings:
            assert finding in board  # confirmed 投影逐条呈现
        board_html = (case / "dashboard" / "dashboard.html").read_text(encoding="utf-8")
        for finding in derived.findings:
            assert finding in board_html
        # killed 假设不是 finding
        assert derived.findings == ["H1"]

    def test_intent_run_chain_present(self, tmp_path: Path):
        case = seed_render_case(tmp_path)
        derived = state.replay(case)
        assert derived.runs["R1"]["status"] == "completed"
        render(case)
        mmd = (case / "dashboard" / "attack-graph.mmd").read_text(encoding="utf-8")
        assert re.search(r"I1\s*-->.*R1", mmd), "intent→run 诊断链必须呈现"

    def test_attack_graph_html_contains_nodes(self, tmp_path: Path):
        case = seed_render_case(tmp_path)
        render(case)
        html = (case / "dashboard" / "attack-graph.html").read_text(encoding="utf-8")
        # PyVis 把节点数据内联为 JSON
        for needle in ("192.0.2.10", "example-httpd 2.4", "H1"):
            assert needle in html


# ---------------------------------------------------------------------------
# 验收 3：删除派生物后可重建
# ---------------------------------------------------------------------------


class TestRebuildable:
    def test_board_and_mmd_deterministic(self, tmp_path: Path):
        case = seed_render_case(tmp_path)
        render(case)
        first_board = (case / "dashboard" / "board.md").read_bytes()
        first_mmd = (case / "dashboard" / "attack-graph.mmd").read_bytes()
        render(case)  # 覆盖重建
        assert (case / "dashboard" / "board.md").read_bytes() == first_board
        assert (case / "dashboard" / "attack-graph.mmd").read_bytes() == first_mmd

    def test_full_rebuild_after_deletion(self, tmp_path: Path):
        case = seed_render_case(tmp_path)
        render(case)
        first_board = (case / "dashboard" / "board.md").read_bytes()
        first_mmd = (case / "dashboard" / "attack-graph.mmd").read_bytes()
        # 删除全部派生物
        for path in (case / "dashboard").iterdir():
            path.unlink()
        assert not any((case / "dashboard").iterdir())
        result = render(case)
        assert result.returncode == 0, result.stderr
        out = case / "dashboard"
        assert (out / "dashboard.html").is_file()
        assert (out / "attack-graph.html").is_file()
        assert (out / "board.md").read_bytes() == first_board
        assert (out / "attack-graph.mmd").read_bytes() == first_mmd
        # JSONL（审计权威）从未被 render 触碰
        derived = state.replay(case)
        assert derived.counts["facts"] == 2

    def test_custom_out_dir(self, tmp_path: Path):
        case = seed_render_case(tmp_path)
        out_dir = tmp_path / "elsewhere"
        result = render(case, out_dir=out_dir)
        assert result.returncode == 0, result.stderr
        assert (out_dir / "board.md").is_file()
        assert not (case / "dashboard").exists()

    def test_render_does_not_touch_ledger(self, tmp_path: Path):
        case = seed_render_case(tmp_path)
        before = (case / "ledger.jsonl").read_bytes()
        render(case)
        assert (case / "ledger.jsonl").read_bytes() == before
