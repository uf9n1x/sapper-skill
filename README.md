# sapper-skill — 假设驱动的授权渗透测试 Skill

> ⚠️ **仅限获得明确授权的安全测试、红队评估、CTF 与漏洞赏金。**
> 使用者须自行确认对目标拥有授权；未授权目标与黑灰产不在适用范围，作者不对未授权使用承担责任。

面向任意 Agent 宿主（DSH / omp / WorkBuddy 等）的渗透测试 Skill：**指挥官只决策、工兵只执行、复核者只验证**，三者围绕一个**可证伪的假设账本**协同推进。Python 确定性控制面负责状态、证据与门禁——Agent 层只产出叙事，账本是唯一真相源。纯本机执行，不依赖 Docker / 常驻服务；面板产物离线单文件打开，也可一键启动实时服务。

## 特性

- **授权 Gate**：一次声明覆盖整个战役，动作组申报与审批入账（`approval` 记录）；越界动作默认不执行，扫描器告警强制 `requires_verification`，不得直接成为确认。
- **角色结构性隔离**：`pack` / `verify-pack` 渐进披露——工兵包不含无关目标，复核包刻意排除工兵叙事；confirmed 裁决必须由独立 Verifier 结果驱动。
- **v2 事件账本**：`ledger.jsonl` 唯一真相源，追加式事件（fact / intent / run / approval / hypothesis / evidence / verdict），确定性回放，v1 旧账本 `migrate` 一键升级。
- **崩溃可恢复**：claim / lease 租约 + 幂等 ingest（同键重放账本逐字节不变）+ 半行尾修复（`repair`）+ 过期租约恢复（`recover`）。
- **工具输出消化**：nmap / masscan / httpx / nuclei / 通用 JSON 五类 parser，秘密脱敏，多来源资产 identity 归一化合并（模糊相似进人工审查队列，不静默合并）。
- **可解释召回与经验沉淀**：BM25 + 模糊 + 结构化 + 一跳图扩展的混合召回，逐项权重可解释；KB 条目带信任级别与过期警告，晋升有 confirmed + 去目标化硬门禁。
- **离线可视化面板**：dashboard / attack-graph / board / mermaid 四产物单文件离线打开（无 CDN），`serve` 一键升级为实时面板（默认后台守护、无命令行黑窗口；账本变化自动重渲染，可随时暂停/恢复），中英双语切换、跨页保持语言/过滤词/图视口。攻击图默认呈现**攻击链推演视图**——假设的每一步证据按实际推演顺序展开（Worker 执行阶段 → Verifier 独立验证阶段 → 终结裁决卡），confirmed 以 ★FINDING 封印卡收束；资产网络视图只保留攻击面（资产/服务/假设），流程噪音不进图。
- **报告门禁**：`prism.py verify` 强制 confirmed 三角色闭环（observation / reproduction / impact）且带 `verifier_run` 溯源，不通过不出报告。

## 安装

```bash
git clone https://github.com/uf9n1x/sapper-skill.git
cd sapper-skill
python -m venv .venv
.venv/Scripts/pip install -r scripts/requirements.lock   # Windows
# Linux/macOS: .venv/bin/pip install -r scripts/requirements.lock
```

把仓库目录注册为你宿主的 Skill（按宿主的 Skill/扩展装载方式），或在任意会话中直接引用 `SKILL.md` 作为角色指令。

**验证**：

```bash
python -X utf8 scripts/prism.py hosts        # 列出可用宿主 adapter
python -X utf8 scripts/prism.py schema --format markdown
```

**依赖**：Python **3.12+**（`scripts/requirements.lock` 由 `scripts/pyproject.toml` 用 uv 编译；其中 `numpy==2.5.4` 要求 3.12，代码亦使用 3.11+ 的 `datetime.UTC`）。锁文件禁止手改，升级依赖请重新编译：

```bash
uv pip compile scripts/pyproject.toml -o scripts/requirements.lock
```

## 快速上手

1. **声明授权**：对 Agent 说明目标与范围（一次声明，战役常驻）；
2. **立假设、派工兵**：指挥官把目标拆成可证伪假设（`hypothesis`），`pack` 生成最小上下文包派发给工兵；
3. **入库与复核**：工兵写结果 JSON（SHA-256 锚定工件），`ingest` 幂等入库；`verify-pack` 派发独立复核，confirmed 必须由复核结果驱动；
4. **出报告**：`python -X utf8 scripts/prism.py verify <case>` 门禁通过后按 `playbooks/report.md` 输出；
5. **看面板**：`python -X utf8 scripts/prism.py render <case>` 离线四产物，或 `serve <case>` 启动实时面板（默认 `http://127.0.0.1:8765`）。

入口协议、角色边界与全部命令见 [SKILL.md](SKILL.md)。

## 实时面板：不会弹出黑窗口

```bash
python -X utf8 scripts/prism.py serve <case>          # 后台守护，立即返回 URL/PID
python -X utf8 scripts/prism.py serve-stop <case>     # 停止（幂等）
python -X utf8 scripts/prism.py serve <case> --foreground   # 需要前台调试时
```

- `serve` 默认在后台启动独立进程：Windows 直接调用 `sys.base_prefix` 下的真实
  `pythonw.exe`（GUI 子系统，配合 `DETACHED_PROCESS | CREATE_NO_WINDOW` 与
  `SW_HIDE`），并用 `PYTHONHOME`/`PYTHONPATH` 挂回虚拟环境依赖；POSIX 用
  `start_new_session`。**关键点**：venv 里的 `python.exe`/`pythonw.exe` 只是
  redirector，会再拉起一个带控制台的孙进程（黑窗口来源），因此必须绕开它。
  服务进程不创建控制台窗口；关闭启动它的终端/会话、结束 Agent 会话都不会中断面板。
- 重复执行 `serve` 会复用已有服务（返回 `reused: true`），不会重复开进程。运行态写在案件根目录的 `serve.json`（PID/端口/URL）和 `serve.log`（日志），都是派生物，可删除；静态服务只托管 `dashboard/`，不会外泄这些文件。
- 面板只在「**已渲染版本**」变化时刷新；暂停态不刷新，HTTP 错误 / 脏响应 / 连接断开会分别显示为「服务异常」「连接断开」而不是触发刷新风暴。双击 `file://` 打开则始终是离线快照，不发起轮询。
- **安全**：默认只绑 `127.0.0.1`。`--host 0.0.0.0` 会把账本投影、全部产物与可写的 `/api/live` 暴露到局域网，因此**强制要求 `--token`**；返回的 URL 带 `?token=...`，首次访问下发 HttpOnly Cookie，后续相对链接与 API 请求自动携带。即便本机运行，账本内容（工具输出、目标响应）也一律经 HTML 转义，不当作可执行内容。

## 测试与 CI

`tests/` 是零依赖（Python 标准库 + 桩模块）的最小回归集，覆盖实时路由、版本契约、token 鉴权、模板转义、重复 id、导航与共享状态机；`tests/js/live_contract.js` 用 Node 真实执行面板的轮询控制器。GitHub Actions 在每次 push / PR 上跑编译检查与回归测试：

```bash
python -X utf8 -m unittest discover -s tests -v
```

## 架构速览

```
Agent 宿主（Commander / Worker / Verifier 角色）
        │  读写
        ▼
case/  ledger.jsonl（唯一真相源）+ artifacts/（SHA-256 锚定）+ results/（结果包）
        │
        ▼
scripts/prism/  确定性控制面
```

| 模块 | 职责 |
|---|---|
| `models.py` | 冻结协议：WorkerResult 契约 + 七类账本记录（pydantic 校验） |
| `state.py` | 确定性回放：引用完整性、Intent/Run 状态派生、findings 投影 |
| `migration.py` | v1 → v2 迁移 + 回放等价性校验 |
| `ingest.py` | 幂等入库：结果包校验 → 记录追加 → run 完成 |
| `packets.py` | `pack` / `verify-pack` 角色上下包装配（最小上下文） |
| `parsers.py` + `identity.py` | 工具输出消化、秘密脱敏、资产 identity 归一化 |
| `recall.py` + `knowledge.py` | 混合召回与 KB 晋升门禁 |
| `render.py` + `live.py` | 离线四产物渲染与实时面板服务 |
| `cli.py` | `prism.py` 命令面（完整清单见 [SKILL.md](SKILL.md) §4） |

宿主差异（子 Agent 生成语法、权限映射、降级路径）见 `references/hosts/`——按宿主选择恰好一个 adapter，无匹配时退回 `generic.md` 顺序模式。

## 文档

| 文档 | 内容 |
|---|---|
| [SKILL.md](SKILL.md) | Skill 入口：授权 Gate、角色协议、证据纪律、全部命令 |
| [playbooks/](playbooks/) | 五阶段角色手册：reason / explore / verify / report / focused |
| [references/hosts/](references/hosts/) | 宿主适配契约（DSH / omp / WorkBuddy / generic） |
| [references/result-schema.md](references/result-schema.md) | Worker 结果包 JSON 契约（字段级文档） |
| [kb/README.md](kb/README.md) | 经验知识库格式与晋升门禁 |
| [tests/](tests/) | 零依赖最小回归测试 + 面板状态机 JS 行为验证 |
| [scripts/pyproject.toml](scripts/pyproject.toml) | 依赖声明（`requirements.lock` 的编译源） |

## 参考项目

- [nvwabase · 女娲基座](https://github.com/N1nEmAn/nvwabase) —— 事实—意图图机制的灵感来源。
- [sapper-v2](https://github.com/N1nEmAn/sapper-v2) —— 多 Agent 渗透协作的编排思路参照。
- [dsh-pentest](https://github.com/howmp/dsh-pentest) —— 同类 DSH bundle 的包结构参照。
- [dsh-prism](https://github.com/uf9n1x/dsh-prism) —— 同一编排思想在 DSH 插件形态的落地。

## License

[MIT](LICENSE)
