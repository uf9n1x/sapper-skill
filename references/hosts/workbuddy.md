# WorkBuddy Adapter（WorkBuddy 桌面宿主）

> 宿主：WorkBuddy 桌面应用。原生子 Agent 机制为 **Agent 工具**
> （general-purpose 等子代理类型），主 Agent 在会话内直接派发。

## 子 Agent 生成

- Commander 通过 Agent 工具派发子 Agent；prompt 结构固定：
  1. 角色声明（Worker / Verifier）+ 授权范围提醒（保留地址 / 演练边界）
  2. pack 文件绝对路径（`packets/worker-<H>.md` 或 `verifier-<H>.md`）
  3. result-schema.md 路径 + 结果 JSON 输出绝对路径
  4. 纪律：不写 ledger、不执行未授权动作、越界进 `blockers`
- Verifier 必须用**独立子 Agent**（不与 Worker 复用同一实例），
  prompt 中明确"不了解也不应猜测之前角色的推理过程"。

## pack → result 传递

- 与通用规则一致：文件进、文件出。
  实测路径样例见下方实测记录。
- 主 Agent 收到 result 后：Pydantic 契约校验 → ledger 入库（唯一入库者）。

## 权限映射

- 子 Agent 默认继承会话沙箱；个人目录（Desktop/Downloads/Documents）的
  删除类操作受宿主保护规则约束——证据固定用**新建文件**，不做删除清理。
- 高影响动作组（写入、提权类）在派发 prompt 中默认不含；需要时由 Commander
  按授权 Gate 单独声明并缩小到具体目标。

## 能力降级

| 场景 | 降级方式 |
|---|---|
| 子 Agent 配额 / 频率限制 | 退回 `references/hosts/generic.md` 顺序模式（标注 `sequential`） |
| 子 Agent 无网络工具 | 观察 / 复现类动作转 `blocked`，改派具备工具的宿主侧机制 |
| 子 Agent 失败 / 超时 | 主 Agent 记 `failed` Run，重派或改顺序模式；不重复入库 |

## 会话与恢复

- 权威状态在案件目录；WorkBuddy 会话历史仅是辅助。
- 新会话接班：读案件目录 → 重放黑板 → 未闭环 Intent 继续；
  子 Agent 是无状态的（packet 进、result 出），无需恢复。

## 可视化面板的常驻方式（serve 后台守护）

- `prism.py serve <case>` **默认后台守护**：命令立即返回 URL/PID，子进程以
  `DETACHED_PROCESS | CREATE_NO_WINDOW`（Windows）或 `start_new_session`
  （POSIX）启动，不会弹出命令行黑窗口，也不要求会话/终端保持打开。
- 宿主侧只需执行一次 `serve` 并把返回的 URL 交给用户；Agent 会话结束、
  用户关闭启动它的终端/窗口，面板依旧可访问。
- 重复执行 `serve` 会复用既有服务（返回 `reused: true`），不会重复开进程；
  需要停止时执行 `prism.py serve-stop <case>`（幂等）。
- 运行态文件在案件根目录：`<case>/serve.json`（PID/端口/URL，静态服务不托管）
  与 `<case>/serve.log`（后台日志）；两者都是派生物，可随时删除。
- 需要前台调试时用 `--foreground`（阻塞，Ctrl-C 退出）；绑定到非本机地址
  必须额外给 `--token`。

## 实测记录

- 2026-11-03（T-021 协议闭环实测，全部通过）：
  - Worker：原生子 Agent 读 `workspace/e2e-host/case/packets/worker-H1.md`，
    落盘复现 artifact + `results/worker-H1.json`；WorkerResult 通过
    `prism.models.WorkerResult` 契约校验。
  - Verifier：独立子 Agent 读 `verifier-H1.md`，PowerShell `Get-FileHash`
    独立比对两个 artifact SHA-256（均一致），正确识别缺失 impact 角色与
    控制对照，给出 provisional 而非迁就 confirmed——独立性纪律生效。
  - 报告门禁双向：provisional 未闭环时 `verify --report` 拒绝（exit 1）；
    补齐三角色 confirmed 后 PASS（6 records）。
