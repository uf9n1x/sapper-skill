# 最小回归测试

零第三方依赖：Python 标准库 + 注入桩模块（`sys.modules`），因此干净克隆也能直接跑。

```bash
python -X utf8 -m unittest discover -s tests -v
```

- `test_regressions.py`
  - 真实执行 `scripts/prism/live.py` 的 `_handle_get` / `_handle_post`（`FakeHandler` 替身）：版本端点轻量路径、`rendered_sha256`、结构化 500、兼容路由、路径逃逸、token 鉴权与 Cookie、`serve.json` 不落在静态目录。
  - 源码/文档结构守卫：Jinja2 `autoescape`、pyvis 标签转义、无重复 id、共享实时控制器契约、导航闭环、可访问性令牌、守护进程 flag、Python 3.12 口径、SKILL.md 命令面。
  - 调用 Node 真实执行共享控制器（见下）。
- `js/live_contract.js`：从 `render.py` 抽出 `SAPPER_LIVE_START`–`SAPPER_LIVE_END` 之间的 JS，在 Node `vm` 里注入桩 DOM/fetch/location/storage，验证 9 个场景（暂停不刷新、只认已渲染版本、渲染竞态、HTTP 500、脏响应、连接断开、postLive 失败回滚、file 协议不轮询、跨页语言保持）。

CI 见 `.github/workflows/ci.yml`；完整开发测试套件保留在本地开发仓，不在本仓分发。
