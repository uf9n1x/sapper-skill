# DSH Desktop Adapter（dsh-prism 插件）

> 宿主：DSH Desktop（DeepSeek 桌面 Agent 宿主）。
> 参考实现：`dsh-prism`（TS 插件，位于 `D:\mytools\CodeEditor\MyProject\dsh-prism`，
> 历史快照 `reference/projects/dsh-prism-docs`）。
> **状态：文档就绪；实测试按升级方案 §14-P4 排期（"完成 Codex、DSH adapter 的实测文档"）。**

## 子 Agent 生成

dsh-prism 以**双 Agent 预设**承载 Prism 角色（cordis patch 挂载）：

- **commander 预设（`prism`）**：决策 Agent，刻意不挂 shell / 文件写 / web /
  MCP / 委派工具；只通过控制工具行动：
  - `prism_board`：读事实—意图图（黑板）
  - `prism_reason`：把当前事实转成下一批具体子意图
  - `prism_spawn`：派发 Worker（一个 assignment 做一件聚焦的事）
- **worker 预设（`prism-worker`）**：可替换执行体，挂宿主 shell / fs 工具与
  `prism_evidence_add`（证据落盘并取得引用 ID）；刻意不挂 ask-user、
  goal/todo、subagent（首版不再委派）与任何控制工具。
- 结构性隔离：commander 侧 `scope guard` 在执行期拒绝任何执行类工具
  （即使会话中途动态挂载了新 MCP 能力）。

## pack → result 传递

- 首版 DSH 路线用图与事件承载状态，不走文件 packet；与 Skill 路线对接时：
  - Commander 预设改为读 `packets/worker-<H>.md` 生成 assignment brief；
  - Worker 结果仍写 `results/` JSON，经 `prism.py schema` 契约校验后由
    主 Agent 入库（保持"唯一入库者"不变）。

## 权限映射

- 授权 Gate 映射到 commander 的 persona 纪律 + scope guard 双层：
  persona 约定"指挥官永不亲自执行"，guard 在工具层拒绝执行类调用。
- 高影响动作组由 commander 在 assignment brief 中显式列出并限定目标；
  worker 侧对 brief 外的动作默认拒绝。

## 能力降级

| 场景 | 降级方式 |
|---|---|
| dsh-prism 插件不可用 | 退回 `references/hosts/generic.md` 顺序模式 |
| worker 预设不可选 | commander 以无头单进程承担执行（等同于 generic，标注 `sequential`） |
| MCP 能力缺失 | worker 按 `blocked` 上报，不虚报证据 |

## 会话与恢复

- 图状态由宿主持久化（dsh-prism RuntimeFactory 管理）；案件目录的
  ledger / artifacts 仍是可交接的权威副本。
- 接班：重放黑板（ledger）→ 与宿主图状态核对 → 继续未闭环 Intent。

## 实测记录

- **2026-11-04（T-051b，自动验证部分）**：
  - dsh-prism 0.1.0 已安装到 `~/.dsh/profiles/desktop/` 与
    `~/.dsh/profiles/prismui2/` 的 node_modules（与源码仓库版本一致）；
    commander/worker/tools/runtime 与 scope guard 结构完整。
  - **preset 未挂载**：两个 profile 的 `cordis.patch.yml` 均无 prism 引用，
    交互实测前置条件未满足；协议与判定标准见
    验收协议（挂载准备、步骤 D1–D9 与判定标准，待执行后回填）。
  - 宿主 MCP 生态实测：DSH Desktop 持有 DudeSuite MCP 单实例互斥锁
    （stdio），omp 侧拉起即退出——**dudesuite MCP 不能同时挂 dsh 与 omp**；
    yakit MCP 无此限制（omp 侧 connected，55 工具）。
  - 补测（2026-11-04）：dsh 侧断开 dudesuite 后，omp 侧立即挂载成功
    （DudeSuite 1.2.3，13 工具，`query_ip_location` 真实调用成功）——
    互斥约束闭环验证通过；dsh 重新启用后 omp 侧将回到降级告警状态。
- **交互实测**：未执行（GUI 宿主，待用户按 T-051-dsh-acceptance.md §3 协议
  执行并回填）。文档依据：dsh-prism 源码 `lib/host/`
  （commander.js / worker.js / tools.js）与 `presets/prism.patch.yml`、
  `presets/prism-worker.patch.yml`（2026-11-03 读取，2026-11-04 安装副本复核）。
