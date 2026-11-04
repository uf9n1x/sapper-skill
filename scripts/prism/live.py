"""实时面板服务（P4 增量，ADR-0013）。

职责（与离线 render 的分工，不伪称推送）：
- `prism.py serve` 启动本地 HTTP 服务：静态托管 dashboard/ 产物 +
  /api/state、/api/version、/api/live 三个只读/开关端点
- 监听线程轮询 ledger.jsonl（mtime+size 指纹），变化时自动重新
  render_all —— 页面由前端轮询 version 并平滑 reload
- live 开关随时切换（POST /api/live）；交互式启动时询问是否开启
  实时可视化，非交互默认开启
- 硬约束不变：JSONL 只读；默认绑定 127.0.0.1；文件服务限制在
  dashboard 目录内（防路径逃逸）
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from prism import render as render_module
from prism import state as state_store

_MIME = {
    ".html": "text/html; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".mmd": "text/plain; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}


def _now_iso() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def ledger_sha256(case_path: Path) -> str:
    return hashlib.sha256((case_path / "ledger.jsonl").read_bytes()).hexdigest()


class LivePanelServer:
    """dashboard 静态托管 + 账本监听自动重渲染。"""

    def __init__(
        self,
        case_path: Path,
        host: str = "127.0.0.1",
        port: int = 8765,
        interval: float = 2.0,
        live_enabled: bool = True,
    ) -> None:
        self.case_path = case_path.resolve()
        self.dashboard_dir = self.case_path / "dashboard"
        self.host = host
        self.port = port
        self.interval = max(0.2, float(interval))
        self.live_enabled = live_enabled
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.rendered_sha: str | None = None
        self.rendered_at: str | None = None
        self._httpd: ThreadingHTTPServer | None = None
        self._poller: threading.Thread | None = None

    # -- 生命周期 -----------------------------------------------------------

    def start(self) -> None:
        """启动 HTTP accept 循环线程 + 账本监听线程（均可安全 stop）。"""
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # 静默默认访问日志
                pass

            def do_GET(self) -> None:
                server._handle_get(self)

            def do_POST(self) -> None:
                server._handle_post(self)

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self.port = self._httpd.server_address[1]
        self._http_thread = threading.Thread(
            target=self._httpd.serve_forever, daemon=True
        )
        self._http_thread.start()
        self._poller = threading.Thread(target=self._poll_loop, daemon=True)
        self._poller.start()

    def serve_forever(self) -> None:
        """阻塞当前线程直到 stop()（供 CLI 主线程驻留）。"""
        try:
            while not self._stop.wait(0.5):
                pass
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self) -> None:
        self._stop.set()
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    # -- 渲染与监听 ----------------------------------------------------------

    def render_if_stale(self, force: bool = False) -> bool:
        """账本指纹变化时重渲染；返回是否实际渲染。"""
        sha = ledger_sha256(self.case_path)
        with self._lock:
            if not force and sha == self.rendered_sha:
                return False
        render_module.render_all(self.case_path, None, _now_iso())
        with self._lock:
            self.rendered_sha = sha
            self.rendered_at = _now_iso()
        return True

    def _poll_loop(self) -> None:
        # 账本半行写入/回放失败属瞬时状态：下个周期重试（不吞 KeyboardInterrupt）
        transient = (state_store.ReplayError, render_module.RenderError, OSError)
        try:
            self.render_if_stale(force=True)
        except transient:
            pass
        while not self._stop.wait(self.interval):
            if not self.live_enabled:
                continue
            try:
                self.render_if_stale()
            except transient:
                continue

    def set_live(self, enabled: bool) -> None:
        self.live_enabled = bool(enabled)

    # -- HTTP ----------------------------------------------------------------

    def _state_payload(self) -> dict:
        derived = state_store.replay(self.case_path)
        return {
            "case": self.case_path.name,
            "now": _now_iso(),
            "ledger_sha256": ledger_sha256(self.case_path),
            "rendered_at": self.rendered_at,
            "live_enabled": self.live_enabled,
            "counts": derived.counts,
            "findings": list(derived.findings),
            "intents": [
                {"id": iid, **derived.intents[iid]} for iid in sorted(derived.intents)
            ],
            "runs": [{"id": rid, **derived.runs[rid]} for rid in sorted(derived.runs)],
        }

    def _send_json(
        self, handler: BaseHTTPRequestHandler, payload: dict, code: int = 200
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        handler.send_response(code)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    def _handle_get(self, handler: BaseHTTPRequestHandler) -> None:
        path = handler.path.split("?", 1)[0]
        # 页面托管在 /dashboard/ 下，前端相对路径 api/* 会打到
        # /dashboard/api/*——等价路由，避免 404 导致前端轮询永久停止
        if path.startswith("/dashboard/api/"):
            path = path[len("/dashboard") :]
        if path in ("/api/state", "/api/version"):
            try:
                payload = self._state_payload()
            except (state_store.ReplayError, OSError) as exc:
                self._send_json(handler, {"error": str(exc)}, 500)
                return
            if path == "/api/version":
                payload = {
                    "ledger_sha256": payload["ledger_sha256"],
                    "rendered_at": payload["rendered_at"],
                    "live_enabled": payload["live_enabled"],
                    "now": payload["now"],
                }
            self._send_json(handler, payload)
            return
        if path == "/" or path == "/index.html":
            handler.send_response(302)
            handler.send_header("Location", "/dashboard/dashboard.html")
            handler.end_headers()
            return
        if path.startswith("/dashboard/"):
            self._serve_file(handler, path[len("/dashboard/") :])
            return
        handler.send_error(404)

    def _serve_file(self, handler: BaseHTTPRequestHandler, rel: str) -> None:
        rel = rel.replace("\\", "/")
        if ".." in rel.split("/"):
            handler.send_error(403)
            return
        target = (self.dashboard_dir / rel).resolve()
        base = self.dashboard_dir.resolve()
        if base not in target.parents and target != base:
            handler.send_error(403)
            return
        if not target.is_file():
            handler.send_error(404)
            return
        body = target.read_bytes()
        handler.send_response(200)
        handler.send_header(
            "Content-Type", _MIME.get(target.suffix, "application/octet-stream")
        )
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    def _handle_post(self, handler: BaseHTTPRequestHandler) -> None:
        path = handler.path.split("?", 1)[0]
        if path.startswith("/dashboard/api/"):
            path = path[len("/dashboard") :]
        if path != "/api/live":
            handler.send_error(404)
            return
        length = int(handler.headers.get("Content-Length", "0") or 0)
        try:
            payload = json.loads(handler.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send_json(handler, {"error": "invalid json"}, 400)
            return
        if "enabled" not in payload:
            self._send_json(handler, {"error": "missing 'enabled'"}, 400)
            return
        self.set_live(bool(payload["enabled"]))
        self._send_json(handler, {"live_enabled": self.live_enabled, "now": _now_iso()})


def prompt_live_enabled(explicit: bool | None) -> bool:
    """启动时选择是否开启实时可视化；显式参数跳过询问。"""
    if explicit is not None:
        return explicit
    try:
        import sys

        if not sys.stdin.isatty():
            return True  # 非交互（脚本/子 Agent 驱动）：默认开启
        answer = (
            input("是否开启实时可视化（账本变化自动重渲染）？[Y/n] ").strip().lower()
        )
    except (EOFError, OSError):
        return True
    return answer not in ("n", "no", "否")
