"""零依赖最小回归集（开源仓形态）。

只用 Python 标准库 + 注入桩模块：不安装 jinja2 / pyvis / pydantic，
也能真实执行 live.py 的 HTTP 路由，并对 render.py 模板做结构守卫。
CI 另用 Node 真实执行共享实时控制器（tests/js/live_contract.js）。

覆盖审计报告：C1（重复 id）、C2（HTML 转义）、H1/H2/H3（实时状态机）、
H4（Python 口径）、H5（测试与依赖可复现）、M1–M7、L2/L3/L4，
以及 serve 默认后台守护（无控制台窗口）。
"""

from __future__ import annotations

import importlib.util
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# 用桩模块加载 live.py（不依赖第三方包），真实调用 _handle_get / _handle_post
# ---------------------------------------------------------------------------

_LIVE_CACHE: dict = {}


def load_live():
    if _LIVE_CACHE:
        return _LIVE_CACHE["module"]

    prism = types.ModuleType("prism")
    prism.__path__ = []  # 标记为包
    render_stub = types.ModuleType("prism.render")

    class RenderError(ValueError):
        pass

    render_stub.RenderError = RenderError
    render_stub.render_all = lambda case, out, now: None

    state_stub = types.ModuleType("prism.state")

    class ReplayError(Exception):
        pass

    state_stub.ReplayError = ReplayError
    state_stub.replay = lambda case: types.SimpleNamespace(
        counts={}, findings=[], intents={}, runs={}
    )
    prism.render = render_stub
    prism.state = state_stub
    sys.modules["prism"] = prism
    sys.modules["prism.render"] = render_stub
    sys.modules["prism.state"] = state_stub

    spec = importlib.util.spec_from_file_location(
        "prism_live_under_test", ROOT / "scripts" / "prism" / "live.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _LIVE_CACHE.update(
        module=module, state=state_stub, render=render_stub,
        prism=prism, replay=state_stub.replay,
    )
    return module


class FakeHandler:
    """BaseHTTPRequestHandler 的最小替身（只实现 live.py 用到的接口）。"""

    def __init__(self, path: str, headers: dict | None = None, body: bytes = b""):
        self.path = path
        self.headers = dict(headers or {})
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.status = None
        self.sent: dict[str, list[str]] = {}
        self.error_code = None

    def send_response(self, code: int) -> None:
        self.status = code

    def send_header(self, key: str, value: str) -> None:
        self.sent.setdefault(key, []).append(value)

    def end_headers(self) -> None:
        pass

    def send_error(self, code: int) -> None:
        self.status = code
        self.error_code = code

    def payload(self) -> tuple[int | None, dict]:
        raw = self.wfile.getvalue().decode("utf-8")
        return self.status, json.loads(raw) if raw else {}


def request(server, path: str, *, method: str = "GET",
            body: dict | None = None, headers: dict | None = None) -> FakeHandler:
    raw = json.dumps(body).encode() if body is not None else b""
    hdrs = dict(headers or {})
    if body is not None:
        hdrs.setdefault("Content-Type", "application/json")
        hdrs["Content-Length"] = str(len(raw))
    handler = FakeHandler(path, hdrs, raw)
    if method == "POST":
        server._handle_post(handler)
    else:
        server._handle_get(handler)
    return handler


class TestLiveRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = load_live()
        self.state_stub = _LIVE_CACHE["state"]
        self.tmp = tempfile.TemporaryDirectory()
        self.case = Path(self.tmp.name) / "case"
        self.case.mkdir()
        (self.case / "ledger.jsonl").write_bytes(b'{"v":2}\n')

    def tearDown(self) -> None:
        self.state_stub.replay = _LIVE_CACHE["replay"]
        self.tmp.cleanup()

    def server(self, **kwargs):
        server = self.mod.LivePanelServer(self.case, port=0, **kwargs)
        server.rendered_sha = "RENDERED"
        server.rendered_at = "2026-01-01T00:00:00Z"
        return server

    def test_version_is_lightweight_and_exposes_rendered_sha(self):
        def boom(*_a, **_k):
            raise AssertionError("/api/version 不应做 full replay")

        self.state_stub.replay = boom  # L2：只读账本字节算 hash
        server = self.server(live_enabled=False)
        status, body = request(server, "/api/version").payload()
        self.assertEqual(status, 200)
        self.assertEqual(body["rendered_sha256"], "RENDERED")
        self.assertEqual(body["live_enabled"], False)
        self.assertTrue(body["ledger_sha256"])

    def test_state_error_is_structured_not_a_version_response(self):
        def broken(*_a, **_k):
            raise self.state_stub.ReplayError("half-written ledger line")

        self.state_stub.replay = broken
        handler = request(self.server(), "/api/state")
        status, body = handler.payload()
        self.assertEqual(status, 500)
        self.assertIn("error", body)
        self.assertNotIn("ledger_sha256", body)  # H3：错误体不能伪装成版本

    def test_compat_route_still_works(self):
        status, body = request(
            self.server(), "/dashboard/api/version"
        ).payload()
        self.assertEqual(status, 200)
        self.assertEqual(body["rendered_sha256"], "RENDERED")

    def test_path_traversal_blocked(self):
        handler = request(self.server(), "/dashboard/../ledger.jsonl")
        self.assertIn(handler.status, (403, 404))

    def test_post_live_toggle(self):
        handler = request(
            self.server(), "/api/live", method="POST", body={"enabled": False}
        )
        status, body = handler.payload()
        self.assertEqual(status, 200)
        self.assertEqual(body["live_enabled"], False)

    def test_state_file_lives_outside_static_root(self):
        self.assertEqual(self.mod.serve_state_path(self.case).parent, self.case)

    def test_token_gates_every_route_and_sets_cookie(self):
        server = self.server(token="tok")
        self.assertEqual(request(server, "/api/version").status, 401)
        self.assertEqual(request(server, "/api/state").status, 401)
        self.assertEqual(request(server, "/").status, 401)
        self.assertEqual(
            request(server, "/api/live", method="POST",
                    body={"enabled": False}).status, 401
        )
        first = request(server, "/api/version?token=tok")
        self.assertEqual(first.status, 200)
        self.assertTrue(
            any("prism_token=tok" in v for v in first.sent.get("Set-Cookie", []))
        )
        cookie = {"Cookie": "prism_token=tok"}
        self.assertEqual(
            request(server, "/api/version", headers=cookie).status, 200
        )
        self.assertEqual(
            request(server, "/api/live", method="POST",
                    body={"enabled": False}, headers=cookie).status, 200
        )
        self.assertEqual(
            request(server, "/api/version", headers={"X-Prism-Token": "bad"}).status,
            401,
        )


# ---------------------------------------------------------------------------
# 源码 / 文档结构守卫
# ---------------------------------------------------------------------------


class TestSourceGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.render = (ROOT / "scripts" / "prism" / "render.py").read_text(
            encoding="utf-8"
        )
        cls.live = (ROOT / "scripts" / "prism" / "live.py").read_text(
            encoding="utf-8"
        )
        cls.cli = (ROOT / "scripts" / "prism" / "cli.py").read_text(
            encoding="utf-8"
        )
        cls.skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        cls.pyproject = (ROOT / "scripts" / "pyproject.toml").read_text(
            encoding="utf-8"
        )

    def test_dashboard_autoescape_and_pyvis_escaping(self):
        self.assertIn("autoescape=True", self.render)  # C2
        self.assertIn("safe_label = _esc(label)", self.render)

    def test_no_duplicate_language_button_id(self):
        self.assertNotIn('id="lang-toggle"', self.render)  # C1
        self.assertIn("data-lang-toggle", self.render)

    def test_shared_live_state_machine_contract(self):
        for marker in (
            "SAPPER_LIVE_START", "SapperLive.start(", "../api/version",
            "rendered_sha256", "r.ok", "disconnected", "error",
            "SapperLang", "sapper.lang", "sapper.filter",
            "sapper.graph.view", "getViewPosition", "moveTo",
        ):
            self.assertIn(marker, self.render, marker)
        for stale in (
            "known !== v.ledger_sha256", "LIVE.on = !LIVE.on",
            ".catch(function () {})",
        ):
            self.assertNotIn(stale, self.render, stale)

    def test_accessibility_and_navigation(self):
        for marker in ("#8a5f00", "44px", ":focus-visible", "var(--accent-soft)",
                       'href="board.md"', 'href="attack-graph.mmd"',
                       "产物导航 Outputs"):
            self.assertIn(marker, self.render, marker)
        self.assertNotIn("#a4740f", self.render)
        self.assertNotIn("rgba(194,69,30,.09)", self.render)
        self.assertNotIn("P4 落地", self.render)

    def test_daemon_flags_and_token_requirement(self):
        for marker in ("DETACHED_PROCESS", "CREATE_NO_WINDOW", "start_new_session",
                       "--detach/--foreground", '"serve-stop"', "--token",
                       "PYTHONHOME", "_base_executable", "STARTF_USESHOWWINDOW"):
            self.assertIn(marker, self.cli, marker)

    def test_live_docstring_distinguishes_write_endpoint(self):
        docstring = self.live.split('"""')[1]
        for marker in ("/api/state", "/api/version", "/api/live", "POST"):
            self.assertIn(marker, docstring, marker)

    def test_python_version_and_dependency_source(self):
        self.assertIn('requires-python = ">=3.12"', self.pyproject)
        self.assertIn("Python **3.12+**", self.readme)
        self.assertIn("scripts/pyproject.toml", self.readme)

    def test_skill_command_surface_and_description(self):
        self.assertIn("prism.py render <case>", self.skill)
        self.assertIn("serve-stop", self.skill)
        self.assertIn("后台", self.skill)
        match = re.search(r'^description:\s*"([^"]*)"', self.skill, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertNotRegex(match.group(1), r"P0|P3|P4|评测期|已交付|开发中")

    def test_shared_js_behavior_with_node(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node 未安装")
        script = ROOT / "tests" / "js" / "live_contract.js"
        result = subprocess.run(
            [node, str(script)], input=self.render, text=True,
            encoding="utf-8", capture_output=True, check=False,
        )
        self.assertEqual(result.returncode == 0, True, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
