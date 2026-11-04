"""实时面板服务（P4 增量，ADR-0013）。

职责（与离线 render 的分工，不伪称推送）：
- `prism.py serve` 启动本地 HTTP 服务：静态托管 dashboard/ 产物 +
  `/api/state`、`/api/version` 两个**只读**端点 + `/api/live` 一个
  **可写**（POST）开关端点；`/dashboard/api/*` 为旧页面缓存的兼容入口
  （前端已统一请求 `/api/*`）
- 监听线程轮询 ledger.jsonl（内容 SHA-256 指纹），变化时自动重新
  render；`/api/version` 同时返回 `ledger_sha256` 与 `rendered_sha256`，
  前端只在「已渲染版本」变化时才 reload，避免刷新到过期面板
- live 开关随时切换（POST /api/live）；暂停期间不重渲染、前端不刷新
- 可选 token 鉴权（非本机绑定时强制）：query/header 首次校验后下发
  HttpOnly Cookie，相对链接与 fetch 自动携带
- 硬约束不变：JSONL 只读；默认绑定 127.0.0.1；文件服务限制在
  dashboard 目录内（防路径逃逸）；运行态文件写在案件根目录，不被静态托管
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from prism import render as render_module
from prism import state as state_store

_MIME = {
    ".html": "text/html; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".mmd": "text/plain; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}
SERVE_STATE_NAME = "serve.json"


def _now_iso() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def ledger_sha256(case_path: Path) -> str:
    return hashlib.sha256((case_path / "ledger.jsonl").read_bytes()).hexdigest()


# -- 运行态文件（案件根目录；静态托管只读 dashboard/，不会外泄） -------------


def serve_state_path(case_path: Path) -> Path:
    return case_path / SERVE_STATE_NAME


def write_serve_state(case_path: Path, payload: dict) -> Path:
    """原子写，避免父进程读到半截 JSON；临时名带 pid，避免并发互踩。"""
    path = serve_state_path(case_path)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="\n",
        )
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def read_serve_state(case_path: Path) -> dict | None:
    try:
        return json.loads(serve_state_path(case_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def remove_serve_state(case_path: Path) -> None:
    serve_state_path(case_path).unlink(missing_ok=True)


def _cookie_token(cookie_header: str) -> str | None:
    for part in cookie_header.split(";"):
        key, _, value = part.strip().partition("=")
        if key == "prism_token":
            # 下发时做过 URL 编码，回传值需还原后再比较
            return unquote(value)
    return None


def _tokens_equal(provided: str, expected: str) -> bool:
    """按字节常量时间比较：str 版 compare_digest 遇非 ASCII 会抛 TypeError。"""
    return secrets.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


class LivePanelServer:
    """dashboard 静态托管 + 账本监听自动重渲染。"""

    def __init__(
        self,
        case_path: Path,
        host: str = "127.0.0.1",
        port: int = 8765,
        interval: float = 2.0,
        live_enabled: bool = True,
        token: str | None = None,
    ) -> None:
        self.case_path = case_path.resolve()
        self.dashboard_dir = self.case_path / "dashboard"
        self.host = host
        self.port = port
        self.interval = max(0.2, float(interval))
        self.live_enabled = live_enabled
        self.token = token or None
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
        # 先完成基线渲染再开始监听：/api/version 首帧就有 rendered_sha256，
        # 前端不会短暂误判为错误态
        try:
            self.render_if_stale(force=True)
        except (state_store.ReplayError, render_module.RenderError, OSError):
            pass
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
        while not self._stop.wait(self.interval):
            if not self.live_enabled:
                continue
            try:
                self.render_if_stale()
            except transient:
                continue

    def set_live(self, enabled: bool) -> None:
        self.live_enabled = bool(enabled)

    # -- 版本与状态 ----------------------------------------------------------

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

    def _version_payload(self) -> dict:
        """轻量版本端点：只读账本字节算 hash，不做 full replay（L2/H3）。"""
        with self._lock:
            rendered_sha = self.rendered_sha or ""
            rendered_at = self.rendered_at
        return {
            "ledger_sha256": ledger_sha256(self.case_path),
            "rendered_sha256": rendered_sha,
            "rendered_at": rendered_at,
            "live_enabled": bool(self.live_enabled),
            "now": _now_iso(),
        }

    # -- 鉴权 ---------------------------------------------------------------

    def _authorized(self, handler: BaseHTTPRequestHandler) -> bool:
        handler.prism_set_cookie = False  # type: ignore[attr-defined]
        if not self.token:
            return True
        query_token = parse_qs(urlsplit(handler.path).query).get("token", [None])[0]
        # 按「query（首次访问）→ header → cookie」顺序取第一个校验通过的来源；
        # 只有 query token 校验通过才下发 Cookie（避免错误 query + 正确 header
        # 时把真实 token 写进浏览器）。
        candidates = (
            ("query", query_token),
            ("header", handler.headers.get("X-Prism-Token")),
            ("cookie", _cookie_token(handler.headers.get("Cookie", "") or "")),
        )
        for source, provided in candidates:
            if provided and _tokens_equal(str(provided), self.token):
                if source == "query":
                    handler.prism_set_cookie = True  # type: ignore[attr-defined]
                return True
        self._send_json(handler, {"error": "unauthorized"}, 401)
        return False

    def _maybe_cookie(self, handler: BaseHTTPRequestHandler) -> None:
        if getattr(handler, "prism_set_cookie", False) and self.token:
            handler.send_header(
                "Set-Cookie",
                f"prism_token={quote(self.token, safe='')}; "
                "Path=/; SameSite=Strict; HttpOnly",
            )

    # -- HTTP ----------------------------------------------------------------

    def _send_json(
        self, handler: BaseHTTPRequestHandler, payload: dict, code: int = 200
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        handler.send_response(code)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        self._maybe_cookie(handler)
        handler.end_headers()
        handler.wfile.write(body)

    def _handle_get(self, handler: BaseHTTPRequestHandler) -> None:
        if not self._authorized(handler):
            return
        path = handler.path.split("?", 1)[0]
        # M1：前端统一请求 /api/*；/dashboard/api/* 仅作旧页面缓存的兼容入口
        if path.startswith("/dashboard/api/"):
            path = path[len("/dashboard") :]
        if path == "/api/version":
            try:
                payload = self._version_payload()
            except OSError as exc:
                self._send_json(handler, {"error": str(exc)}, 500)
                return
            self._send_json(handler, payload)
            return
        if path == "/api/state":
            try:
                payload = self._state_payload()
            except (state_store.ReplayError, OSError) as exc:
                self._send_json(handler, {"error": str(exc)}, 500)
                return
            self._send_json(handler, payload)
            return
        if path in ("/", "/index.html"):
            handler.send_response(302)
            handler.send_header("Location", "/dashboard/dashboard.html")
            self._maybe_cookie(handler)
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
        self._maybe_cookie(handler)
        handler.end_headers()
        handler.wfile.write(body)

    def _handle_post(self, handler: BaseHTTPRequestHandler) -> None:
        if not self._authorized(handler):
            return
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
