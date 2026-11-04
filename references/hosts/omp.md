# omp Adapter（omp CLI Agent）

> 宿主：omp（pi 系 CLI Agent，实测版本 v18.15.0，`C:\Users\yang\.bun\bin\omp.exe`）。
> omp 提供无头单进程模式与原生子 Agent（`task` 工具），均可承载 Worker / Verifier。

## 子 Agent 生成

两种方式，按阶段选用：

1. **无头进程模式**（推荐用于 Verifier，物理隔离最强）：
   ```powershell
   # PowerShell（Windows 实测可用；Git Bash 沙箱会 SIGTERM 杀掉进程，勿用）
   omp -p --no-context-files --auto-approve --max-time 600 `
       --cwd <案件目录> `
       --system-prompt "<角色指令，指向 verifier-<H>.md 与 result-schema.md>"
   ```
2. **原生 `task` 子 Agent**（Commander 会话内派发 Worker）：
   Commander 会话中用 omp 内置 `task` 工具启动子 Agent，任务说明只给
   worker-<H>.md 路径 + result 输出路径；子 Agent 不继承 Commander 叙事。

## pack → result 传递

- Worker：读 `packets/worker-<H>.md`，写 `results/worker-<R>.json`。
- Verifier：读 `packets/verifier-<H>.md`，写 `results/verifier-<R>.json`。
- 文件路径在派发 prompt 中显式给出；子 Agent 完成后 Commander 校验 JSON
  契约（`prism.py schema`）再入库。

## 权限映射

- `--auto-approve` 仅在**授权战役已声明**的会话中使用；它跳过工具审批，
  因此 Scope 与动作组审批必须在 Commander 的授权声明中先行完成。
- 费用护栏：`--max-cost` 建议随无头模式启用（超限退出码 3）。
- 首次交互授权（`ask` 工具）在 `-p` 模式不可用——派发前确认所需工具
  均可自动批准，否则改用交互会话。

## 能力降级

- MCP 服务器连接失败属常态（实测出现 `dudesuite` 连接失败告警）：
  缺失能力按 workers 的 `blocked` 状态上报，不重试不虚报。
- 无 `task` 工具的环境（旧版本 / 受限配置）：退回 `references/hosts/generic.md`
  顺序模式。

## 会话与恢复

- 会话文件：`~/.omp/agent/sessions/<path>/session.jsonl`。
- 崩溃接班：`omp --restore <session.jsonl>` 可恢复中断轮次**与在跑的子 Agent**；
  案件权威状态仍在案件目录，恢复后先重放黑板再继续。

## 实测记录

- 2026-11-03（omp v18.15.0，Windows）：
  - `omp -p --no-context-files --max-time 90 "Reply with exactly one word: PONG"`
    → 输出 `PONG`，exit 0（PowerShell 下）。
  - 已确认：`-p` 无头模式、`--mode json`、`task` 子 Agent 工具、`--auto-approve`、
    `--restore`（含子 Agent）、`--max-cost` 均存在且可用。
- 2026-11-04（T-051，真实施役闭环，案件 `workspace/t051/omp/case`）：
  - **全流程无头闭环通过**：`pack --hypothesis H10` → claim R1 →
    `omp -p --auto-approve --cwd <case>` 派发 Worker（brute 模块弱口令探测，
    25 请求 45 artifacts，`results/worker-R1.json`）→ ingest（1 fact + 6 evidence）→
    `verify-pack` → claim R2 → 无头派发独立 Verifier（SHA-256 逐条比对 + 独立
    重放，8 evidence + confirmed 建议）→ ingest → 主 Agent 裁决 V10
    （confirmed + verifier_run 溯源）→ render 四件套。同一 Core 零宿主专用修改。
  - Worker 纪律实测：发现 brute 模块实际为 GET（任务写的是 POST）→ 在
    `deviations` 如实记录并同 URL 补测，未扩大范围。
  - Verifier 独立性实测：发现派发参数中的凭据失效 → 不迁就，改用字典内候选
    独立复现（工件与 Worker 产物哈希一致），矛盾如实写入 summary。
  - 契约修正点（主 Agent 职责）：omp 产物需主 Agent 补 `schema_version`/顶层
    `summary`，并裁剪超 300 字符的 evidence summary——契约校验由 ingest 执行，
    缺陷在入库前被拦截（符合预期）。
  - **MCP 能力降级实测**：`yakit`（stdio）connected，55 工具，只读调用成功；
    `dudesuite`（stdio）连接失败——DudeSuite 单实例锁被 DSH Desktop 宿主持有
    （`[MCP][Startup] 检测到另一个 MCP 实例已在运行`），omp 侧如实告警并继续
    任务，无重试无虚报。**约束：DudeSuite MCP 为单实例互斥，dsh 与 omp 不可
    同时挂载**；需要在 omp 使用时先在 dsh 中断开该 MCP。
  - 已知噪音：每次无头运行出现 `dudesuite` MCP 连接失败告警（stderr），
    不影响任务执行与退出码。
- 2026-11-04（T-051 补测，dsh 侧断开 dudesuite 后）：
  - `dudesuite`（stdio）**connected**：serverInfo `DudeSuite 1.2.3`，
    启动认证 `[MCP][Startup] 独立认证通过`；13 工具
    （network_scan_ports/gateways/hosts、vuln_validate、fofa_search、
    web_app_detect、auth_crack、domain/http_brute_force、cipher_transform、
    cipher_crypto、query_ip_location、http_send_raw）。
  - omp 无头真实调用 `query_ip_location(114.114.114.114)` →
    中国江苏南京 32.04°N/118.78°E，163ms，exit 0。
  - 互斥约束闭环验证：dsh 断开后 omp 立即可挂载；dsh 重新启用后 omp 侧
    回到降级告警状态，无半挂载残留。
