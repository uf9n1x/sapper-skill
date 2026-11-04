"""P4 实时面板与双语界面测试（ADR-0013）。

锁定验收：
1. serve 托管 dashboard 产物 + /api/state、/api/version 只读端点
2. 实时监听：账本变化 → 自动重渲染 → /api/version 指纹变化 →
   dashboard 文件包含新记录（前端 reload 即见最新）
3. 实时开关：POST /api/live 随时暂停/恢复；暂停期间不重渲染
4. 双语界面：dashboard 默认中文 + data-zh/data-en 切换 + 离线退化
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from pathlib import Path

import pytest
from conftest import run_prism

NOW = "2026-01-01T00:00:00Z"


def seed_case(tmp_path: Path) -> Path:
    case = tmp_path / "case"
    (case / "artifacts").mkdir(parents=True)
    (case / "results").mkdir(parents=True)
    records = [
        {"v": 2, "type": "fact", "id": "F1", "at": NOW, "kind": "asset",
         "target": "192.0.2.10", "title": "主机", "summary": "存活主机"},
        {"v": 2, "type": "hypothesis", "id": "H1", "at": NOW,
         "claim": "192.0.2.10 未授权访问", "scope": "192.0.2.10 web",
         "disprove_if": ["401"]},
        {"v": 2, "type": "verdict", "id": "V1", "at": NOW, "hypothesis": "H1",
         "status": "confirmed", "evidence": ["E1"], "reason": "闭环"},
        {"v": 2, "type": "hypothesis", "id": "H2", "at": NOW,
         "claim": "192.0.2.10 子域接管", "scope": "DNS",
         "disprove_if": ["CNAME 指向活跃服务"]},
        {"v": 2, "type": "verdict", "id": "V2", "at": NOW, "hypothesis": "H2",
         "status": "killed", "evidence": ["E1"], "reason": "反证成立"},
    ]
    (case / "ledger.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
        encoding="utf-8", newline="\n",
    )
    return case


def start_server(case: Path, interval: float = 0.3):
    """在子线程启动 LivePanelServer（port=0 随机），返回 (server, base_url)。"""
    from prism import live as live_module

    server = live_module.LivePanelServer(
        case, port=0, interval=interval, live_enabled=True
    )
    server.start()
    base = f"http://127.0.0.1:{server.port}"
    return server, base


def http_get(url: str):
    with urllib.request.urlopen(url, timeout=5) as resp:
        return resp.status, resp.read().decode("utf-8")


class TestServeApi:
    def test_api_version_matches_ledger(self, tmp_path: Path):
        case = seed_case(tmp_path)
        server, base = start_server(case)
        try:
            deadline = time.time() + 8
            payload = {}
            while time.time() < deadline:
                try:
                    _, body = http_get(f"{base}/api/version")
                    payload = json.loads(body)
                    if payload.get("rendered_at"):
                        break
                except OSError:
                    time.sleep(0.1)
                time.sleep(0.1)
            expected = hashlib.sha256(
                (case / "ledger.jsonl").read_bytes()
            ).hexdigest()
            assert payload["ledger_sha256"] == expected
            assert payload["live_enabled"] is True
            assert payload["rendered_at"]
        finally:
            server.stop()

    def test_api_state_counts_and_findings(self, tmp_path: Path):
        case = seed_case(tmp_path)
        server, base = start_server(case)
        try:
            time.sleep(1.0)  # 等基线渲染
            _, body = http_get(f"{base}/api/state")
            payload = json.loads(body)
            assert payload["counts"]["facts"] == 1
            assert payload["counts"]["hypotheses"] == 2
            assert payload["findings"] == ["H1"]
            assert payload["intents"] == []
        finally:
            server.stop()

    def test_root_redirects_to_dashboard(self, tmp_path: Path):
        case = seed_case(tmp_path)
        server, base = start_server(case)
        try:
            time.sleep(0.8)
            status, _ = http_get(f"{base}/")
            assert status == 200  # urllib 自动跟随 302
            _, body = http_get(f"{base}/dashboard/dashboard.html")
            assert "战役面板" in body
        finally:
            server.stop()

    def test_dashboard_file_traversal_blocked(self, tmp_path: Path):
        case = seed_case(tmp_path)
        server, base = start_server(case)
        try:
            time.sleep(0.5)
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                http_get(f"{base}/dashboard/../ledger.jsonl")
            assert exc_info.value.code in (403, 404)
        finally:
            server.stop()


class TestLiveWatch:
    def test_ledger_change_triggers_rerender(self, tmp_path: Path):
        case = seed_case(tmp_path)
        server, base = start_server(case, interval=0.3)
        try:
            # 等基线渲染完成
            deadline = time.time() + 8
            while time.time() < deadline:
                _, body = http_get(f"{base}/api/version")
                if json.loads(body).get("rendered_at"):
                    break
                time.sleep(0.1)
            # 账本追加新假设 + confirmed 裁决
            new_records = [
                {"v": 2, "type": "hypothesis", "id": "H9", "at": NOW,
                 "claim": "新增假设", "scope": "192.0.2.10", "disprove_if": ["x"]},
                {"v": 2, "type": "verdict", "id": "V9", "at": NOW,
                 "hypothesis": "H9", "status": "confirmed", "evidence": ["E1"],
                 "reason": "闭环"},
            ]
            with open(case / "ledger.jsonl", "a", encoding="utf-8", newline="\n") as fh:
                fh.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in new_records)
            new_sha = hashlib.sha256(
                (case / "ledger.jsonl").read_bytes()
            ).hexdigest()
            # 轮询直到服务端指纹追上新账本（= 已重渲染）
            deadline = time.time() + 8
            while time.time() < deadline:
                _, body = http_get(f"{base}/api/version")
                if json.loads(body)["ledger_sha256"] == new_sha:
                    break
                time.sleep(0.2)
            assert json.loads(body)["ledger_sha256"] == new_sha, (
                "实时监听未在期限内重渲染"
            )
            # dashboard 文件已包含新发现（render 序列含 4 个产物，轮询就绪）
            deadline = time.time() + 8
            html = ""
            while time.time() < deadline:
                html = (case / "dashboard" / "dashboard.html").read_text(
                    encoding="utf-8"
                )
                if "H9" in html:
                    break
                time.sleep(0.2)
            assert "H9" in html, "重渲染后 dashboard 应包含新发现"
        finally:
            server.stop()

    def test_live_toggle_pauses_and_resumes(self, tmp_path: Path):
        case = seed_case(tmp_path)
        server, base = start_server(case, interval=0.3)
        try:
            deadline = time.time() + 8
            while time.time() < deadline:
                _, body = http_get(f"{base}/api/version")
                if json.loads(body).get("rendered_at"):
                    break
                time.sleep(0.1)
            before = hashlib.sha256(
                (case / "dashboard" / "board.md").read_bytes()
            ).hexdigest()
            # 暂停
            req = urllib.request.Request(
                f"{base}/api/live",
                data=json.dumps({"enabled": False}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                assert json.loads(resp.read())["live_enabled"] is False
            # 追加记录：暂停期间不渲染
            with open(case / "ledger.jsonl", "a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(
                    {"v": 2, "type": "fact", "id": "F9", "at": NOW,
                     "kind": "asset", "target": "192.0.2.99", "title": "新资产",
                     "summary": "s"}, ensure_ascii=False) + "\n")
            time.sleep(1.2)
            paused = hashlib.sha256(
                (case / "dashboard" / "board.md").read_bytes()
            ).hexdigest()
            assert paused == before, "暂停期间不应重渲染"
            # 恢复：下个周期重渲染
            req = urllib.request.Request(
                f"{base}/api/live",
                data=json.dumps({"enabled": True}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                assert json.loads(resp.read())["live_enabled"] is True
            deadline = time.time() + 8
            state_payload = {}
            while time.time() < deadline:
                _, body = http_get(f"{base}/api/state")
                state_payload = json.loads(body)
                if state_payload["counts"]["facts"] == 2:
                    break
                time.sleep(0.2)
            assert state_payload["counts"]["facts"] == 2, "恢复实时后应重渲染"
            _, body = http_get(f"{base}/api/state")
            assert state_payload["ledger_sha256"] == hashlib.sha256(
                (case / "ledger.jsonl").read_bytes()
            ).hexdigest()
        finally:
            server.stop()


class TestBilingualAndRedesign:
    def test_dashboard_bilingual_markers(self, tmp_path: Path):
        case = seed_case(tmp_path)
        result = run_prism("render", str(case), "--now", NOW)
        assert result.returncode == 0, result.stderr
        html = (case / "dashboard" / "dashboard.html").read_text(encoding="utf-8")
        # 默认中文 + 英文并存（双语切换的原始文案都在 HTML 里）
        for marker in ("战役面板", "已确认发现", "意图与执行", "审批", "离线快照"):
            assert marker in html
        for en_marker in ("Findings", "Hypotheses", "Intents / Runs", "Approvals",
                          "Campaign Dashboard", "Offline snapshot"):
            assert en_marker in html
        # 语言切换机制存在
        assert 'data-zh' in html and 'data-en' in html
        assert "lang-toggle" in html

    def test_dashboard_no_english_only_labels(self, tmp_path: Path):
        """旧版英文裸标签（作为唯一可见文案）不允许再出现。"""
        case = seed_case(tmp_path)
        run_prism("render", str(case), "--now", NOW)
        html = (case / "dashboard" / "dashboard.html").read_text(encoding="utf-8")
        # 旧版标题不再出现
        assert "<h1>prism dashboard</h1>" not in html
        # 新版状态徽标为中文优先双语
        assert "已确认" in html and "已证伪" in html

    def test_attack_graph_has_status_bar_and_chinese(self, tmp_path: Path):
        case = seed_case(tmp_path)
        run_prism("render", str(case), "--now", NOW)
        html = (case / "dashboard" / "attack-graph.html").read_text(encoding="utf-8")
        assert "graph-bar" in html
        assert "攻击图" in html and "Attack Graph" in html
        # 实时挂钩存在但离线退化（相对路径，非外链）
        assert "api/version" in html
        # 旧英文裸标签不再作为节点标签起始出现（新标签为"资产 asset: ..."；
        # pyvis JSON 对中文做 \uXXXX 转义，正反断言都用转义形态匹配）
        assert '"asset: ' not in html
        assert "\\u8d44\\u4ea7 asset: 192.0.2.10" in html

    def test_board_and_mmd_bilingual(self, tmp_path: Path):
        case = seed_case(tmp_path)
        run_prism("render", str(case), "--now", NOW)
        board = (case / "dashboard" / "board.md").read_text(encoding="utf-8")
        assert "## Active Runs（活动 Run）" in board
        assert "## Findings（已确认发现）" in board
        assert "## Cleanup（清理）" in board
        mmd = (case / "dashboard" / "attack-graph.mmd").read_text(encoding="utf-8")
        assert "攻击链 Attack Chain" in mmd
        assert "资产 asset: 192.0.2.10" in mmd
        assert "已确认 confirmed" in mmd

    def test_serve_command_registered(self):
        result = run_prism("--help")
        assert result.returncode == 0
        assert "serve" in result.stdout
