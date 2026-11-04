"""P3 Recall / KB 测试（T-040）。

锁定三条验收：
1. 召回可解释——每条命中返回 score breakdown 与命中原因
2. 失败路径可召回——已证伪假设 / 受阻 Intent 可被检索并标注
   path=failure，避免不同 Worker 重复走死路
3. KB 带来源与信任级别——frontmatter 记录 source / trust /
   applies_to / last_verified，过期知识必须展示警告

设计红线（升级方案 §8）：
- 只有经过验证（latest verdict = confirmed）且去目标化的经验才能
  晋升为通用 KB；原始目标信息泄漏直接拒绝
- 图扩展严格限制深度（1 跳）与节点数
"""

from __future__ import annotations

import json
from pathlib import Path

from conftest import run_prism

NOW = "2026-01-01T00:00:00Z"


def seed_recall_case(tmp_path: Path) -> Path:
    """含成功路径、失败路径、受阻路径的案件。"""
    case = tmp_path / "case"
    (case / "artifacts").mkdir(parents=True)
    (case / "results").mkdir(parents=True)
    (case / "ledger.jsonl").touch()
    records = [
        # 成功路径：管理后台未授权访问（confirmed）
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
            "type": "fact",
            "id": "F1",
            "at": NOW,
            "kind": "service",
            "target": "192.0.2.10:80/tcp",
            "title": "example-httpd 2.4",
            "summary": "80 端口 HTTP 服务，example-httpd 2.4",
        },
        {
            "v": 2,
            "type": "fact",
            "id": "F2",
            "at": NOW,
            "kind": "vulnerability_lead",
            "target": "192.0.2.10",
            "title": "管理后台未认证可访问",
            "summary": "/admin 无需认证返回 200",
            "doc_path": "artifacts/admin-note.md",
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
        # 失败路径：子域接管已被证伪
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
            "reason": "CNAME 指向活跃服务，无悬挂记录",
        },
        # 受阻路径：内网横向 Intent blocked
        {
            "v": 2,
            "type": "intent",
            "id": "I1",
            "at": NOW,
            "event": "created",
            "title": "从 192.0.2.10 横向到内网网段",
            "objective": "扩展访问面",
            "angle": "credential reuse",
            "target": "192.0.2.0/24",
        },
        {
            "v": 2,
            "type": "intent",
            "id": "I1",
            "at": NOW,
            "event": "blocked",
            "reason": "缺少内网可达性，路由不可达",
        },
        # 无关假设（open）
        {
            "v": 2,
            "type": "hypothesis",
            "id": "H3",
            "at": NOW,
            "claim": "192.0.2.10 TLS 证书泄露内网主机名",
            "scope": "192.0.2.10:443",
            "disprove_if": ["SAN 不含内网名"],
        },
    ]
    with open(case / "ledger.jsonl", "a", encoding="utf-8", newline="\n") as fh:
        fh.writelines(
            json.dumps(record, ensure_ascii=False) + "\n" for record in records
        )
    (case / "artifacts" / "admin-note.md").write_text(
        "# 管理后台笔记\n\n/admin 无认证可达（演练数据）。\n",
        encoding="utf-8",
    )
    return case


def recall(case: Path, query: str, top: int = 5):
    return run_prism("recall", str(case), "--query", query, "--top", str(top))


# ---------------------------------------------------------------------------
# 验收 1：召回可解释
# ---------------------------------------------------------------------------


class TestExplainableRecall:
    def test_hits_carry_score_breakdown_and_reasons(self, tmp_path: Path):
        case = seed_recall_case(tmp_path)
        result = recall(case, "管理后台 未授权")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        hits = payload["hits"]
        assert hits, "至少命中一条"
        top = hits[0]
        assert top["id"] == "H1"  # 最相关：confirmed 的管理后台假设
        assert top["breakdown"], "必须有 score breakdown"
        assert abs(sum(top["breakdown"].values()) - top["score"]) < 0.05
        assert top["reasons"], "必须有命中原因"

    def test_chinese_query_tokenized(self, tmp_path: Path):
        case = seed_recall_case(tmp_path)
        result = recall(case, "横向 内网")
        assert result.returncode == 0, result.stderr
        hits = json.loads(result.stdout)["hits"]
        assert any(h["id"] == "I1" for h in hits)

    def test_top_n_short_summary_not_full_doc(self, tmp_path: Path):
        case = seed_recall_case(tmp_path)
        result = recall(case, "管理后台")
        hits = json.loads(result.stdout)["hits"]
        for hit in hits:
            assert len(hit["snippet"]) <= 160

    def test_empty_query_rejected(self, tmp_path: Path):
        case = seed_recall_case(tmp_path)
        result = recall(case, "   ")
        assert result.returncode == 1

    def test_recall_is_deterministic(self, tmp_path: Path):
        case = seed_recall_case(tmp_path)
        r1 = recall(case, "管理后台", top=3).stdout
        r2 = recall(case, "管理后台", top=3).stdout
        assert r1 == r2


# ---------------------------------------------------------------------------
# 验收 2：失败路径可召回
# ---------------------------------------------------------------------------


class TestFailurePathRecall:
    def test_killed_hypothesis_recallable_and_marked(self, tmp_path: Path):
        case = seed_recall_case(tmp_path)
        result = recall(case, "子域接管")
        assert result.returncode == 0, result.stderr
        hits = json.loads(result.stdout)["hits"]
        killed = [h for h in hits if h["id"] == "H2"]
        assert killed, "已证伪假设必须可召回"
        assert killed[0]["path"] == "failure"
        assert killed[0]["status"] == "killed"

    def test_blocked_intent_recallable_and_marked(self, tmp_path: Path):
        case = seed_recall_case(tmp_path)
        result = recall(case, "横向")
        hits = json.loads(result.stdout)["hits"]
        blocked = [h for h in hits if h["id"] == "I1"]
        assert blocked, "受阻 Intent 必须可召回"
        assert blocked[0]["path"] == "failure"

    def test_confirmed_path_marked_success(self, tmp_path: Path):
        case = seed_recall_case(tmp_path)
        result = recall(case, "管理后台")
        hits = json.loads(result.stdout)["hits"]
        h1 = next(h for h in hits if h["id"] == "H1")
        assert h1["path"] == "success"
        assert h1["status"] == "confirmed"


# ---------------------------------------------------------------------------
# 图扩展与 doc 按需读详情
# ---------------------------------------------------------------------------


class TestGraphExpansionAndDoc:
    def test_graph_expansion_brings_same_asset_neighbors(self, tmp_path: Path):
        case = seed_recall_case(tmp_path)
        result = recall(case, "管理后台", top=1)
        hits = json.loads(result.stdout)["hits"]
        # H1（192.0.2.10 管理后台）命中后，图扩展应带出同资产族的 F1/F2
        graph_hits = [h for h in hits if "graph" in h["breakdown"]]
        assert graph_hits, "图扩展应带出同资产邻居"
        assert len(graph_hits) <= 5, "图扩展必须限量"
        # 同资产族 = 192.0.2.10 的邻居集合：H1 / F1 / F2 / H3 都引用该资产
        assert all(h["id"] in ("F1", "F2", "H1", "H3") for h in graph_hits)
        assert any(h["id"] in ("F1", "F2") for h in graph_hits)

    def test_doc_returns_artifact_content(self, tmp_path: Path):
        case = seed_recall_case(tmp_path)
        result = run_prism("doc", str(case), "--id", "F2")
        assert result.returncode == 0, result.stderr
        assert "管理后台笔记" in result.stdout

    def test_doc_without_artifact_returns_record_detail(self, tmp_path: Path):
        case = seed_recall_case(tmp_path)
        result = run_prism("doc", str(case), "--id", "H1")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["id"] == "H1"
        assert payload["type"] == "hypothesis"

    def test_doc_unknown_id_rejected(self, tmp_path: Path):
        case = seed_recall_case(tmp_path)
        result = run_prism("doc", str(case), "--id", "X99")
        assert result.returncode == 1


# ---------------------------------------------------------------------------
# 验收 3：KB 来源与信任级别 + 晋升门禁
# ---------------------------------------------------------------------------


class TestKnowledgeBase:
    def _confirmed_case(self, tmp_path: Path) -> Path:
        case = tmp_path / "eng"
        (case / "artifacts").mkdir(parents=True)
        (case / "ledger.jsonl").touch()
        records = [
            {
                "v": 2,
                "type": "fact",
                "id": "F1",
                "at": NOW,
                "kind": "service",
                "target": "192.0.2.10:80/tcp",
                "title": "example-httpd 2.4",
                "summary": "HTTP 服务",
            },
            {
                "v": 2,
                "type": "hypothesis",
                "id": "H1",
                "at": NOW,
                "claim": "example-httpd 2.4 管理后台默认无认证",
                "scope": "web",
                "disprove_if": ["要求登录"],
            },
            {
                "v": 2,
                "type": "verdict",
                "id": "V1",
                "at": NOW,
                "hypothesis": "H1",
                "status": "confirmed",
                "evidence": ["E1"],
                "reason": "已验证",
            },
        ]
        with open(case / "ledger.jsonl", "a", encoding="utf-8", newline="\n") as fh:
            fh.writelines(
                json.dumps(record, ensure_ascii=False) + "\n" for record in records
            )
        return case

    def test_promote_confirmed_and_detargeted_experience(self, tmp_path: Path):
        case = self._confirmed_case(tmp_path)
        kb = tmp_path / "kb"
        kb.mkdir()
        text_file = tmp_path / "sanitized.md"
        text_file.write_text(
            "# example-httpd 2.4 管理后台默认无认证\n\n"
            "已验证：该产品组合的示例管理后台默认无认证即可访问，"
            "建议优先检查管理路径认证配置。\n",
            encoding="utf-8",
        )
        result = run_prism(
            "kb-promote",
            str(case),
            "--hypothesis",
            "H1",
            "--file",
            str(text_file),
            "--dir",
            str(kb),
            "--source-note",
            "授权演练 finding，已去目标化",
        )
        assert result.returncode == 0, result.stderr
        entry_path = Path(json.loads(result.stdout)["path"])
        raw = entry_path.read_text(encoding="utf-8")
        assert "trust: unverified" in raw
        assert "applies_to: example-httpd 2.4" in raw
        assert "source:" in raw
        assert "last_verified:" in raw
        assert "192.0.2.10" not in raw  # 去目标化硬校验

    def test_promote_rejects_unconfirmed_hypothesis(self, tmp_path: Path):
        case = tmp_path / "eng"
        (case / "artifacts").mkdir(parents=True)
        (case / "ledger.jsonl").touch()
        with open(case / "ledger.jsonl", "a", encoding="utf-8", newline="\n") as fh:
            fh.write(
                json.dumps(
                    {
                        "v": 2,
                        "type": "hypothesis",
                        "id": "H9",
                        "at": NOW,
                        "claim": "某服务存在漏洞",
                        "scope": "web",
                        "disprove_if": ["x"],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        kb = tmp_path / "kb"
        kb.mkdir()
        text_file = tmp_path / "s.md"
        text_file.write_text("经验文本", encoding="utf-8")
        result = run_prism(
            "kb-promote",
            str(case),
            "--hypothesis",
            "H9",
            "--file",
            str(text_file),
            "--dir",
            str(kb),
        )
        assert result.returncode == 1
        assert "confirmed" in result.stderr

    def test_promote_rejects_target_leakage(self, tmp_path: Path):
        case = self._confirmed_case(tmp_path)
        kb = tmp_path / "kb"
        kb.mkdir()
        text_file = tmp_path / "leaky.md"
        text_file.write_text(
            "经验：192.0.2.10 的管理后台无认证。",  # 原始目标泄漏
            encoding="utf-8",
        )
        result = run_prism(
            "kb-promote",
            str(case),
            "--hypothesis",
            "H1",
            "--file",
            str(text_file),
            "--dir",
            str(kb),
        )
        assert result.returncode == 1
        assert "192.0.2.10" in result.stderr  # 指出泄漏的原始目标串

    def test_kb_list_shows_source_trust_and_expired_warning(self, tmp_path: Path):
        kb = tmp_path / "kb"
        kb.mkdir()
        (kb / "kb-old-entry.md").write_text(
            "---\n"
            "title: 旧经验\n"
            "source: 官方公告\n"
            "trust: official\n"
            "applies_to: legacy-httpd 1.0\n"
            "last_verified: 2020-01-01\n"
            "---\n\n内容已过时。\n",
            encoding="utf-8",
        )
        (kb / "kb-fresh-entry.md").write_text(
            "---\n"
            "title: 新经验\n"
            "source: 官方公告\n"
            "trust: official\n"
            "applies_to: example-httpd 2.4\n"
            "last_verified: 2026-06-01\n"
            "---\n\n仍然有效。\n",
            encoding="utf-8",
        )
        result = run_prism("kb-list", "--dir", str(kb), "--today", "2026-11-04")
        assert result.returncode == 0, result.stderr
        assert "kb-old-entry" in result.stdout
        assert "EXPIRED" in result.stdout  # 过期必须警告
        assert "official" in result.stdout
        assert "legacy-httpd 1.0" in result.stdout
        # 过期警告不污染未过期条目所在行
        fresh_line = next(
            line for line in result.stdout.splitlines() if "kb-fresh-entry" in line
        )
        assert "EXPIRED" not in fresh_line

    def test_kb_read_shows_warnings_for_unverified_and_expired(self, tmp_path: Path):
        kb = tmp_path / "kb"
        kb.mkdir()
        (kb / "kb-shaky.md").write_text(
            "---\n"
            "title: 存疑经验\n"
            "source: 论坛帖子\n"
            "trust: unverified\n"
            "applies_to: some-product 9.9\n"
            "last_verified: 2020-06-01\n"
            "---\n\n未验证内容。\n",
            encoding="utf-8",
        )
        result = run_prism(
            "kb-read", "kb-shaky", "--dir", str(kb), "--today", "2026-11-04"
        )
        assert result.returncode == 0, result.stderr
        assert "EXPIRED" in result.stdout
        assert "unverified" in result.stdout
        assert "论坛帖子" in result.stdout

    def test_kb_invalid_trust_rejected(self, tmp_path: Path):
        kb = tmp_path / "kb"
        kb.mkdir()
        (kb / "kb-bad.md").write_text(
            "---\n"
            "title: 坏条目\n"
            "source: x\n"
            "trust: definitely-true\n"
            "applies_to: p 1\n"
            "last_verified: 2026-01-01\n"
            "---\n\n内容\n",
            encoding="utf-8",
        )
        result = run_prism("kb-list", "--dir", str(kb))
        assert result.returncode == 1
        assert "trust" in result.stderr

    def test_empty_kb_list_ok(self, tmp_path: Path):
        kb = tmp_path / "kb"
        kb.mkdir()
        result = run_prism("kb-list", "--dir", str(kb))
        assert result.returncode == 0, result.stderr
