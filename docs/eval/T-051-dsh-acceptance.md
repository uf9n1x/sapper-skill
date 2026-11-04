# T-051b · DSH Desktop 宿主验收（dsh-prism 插件路线）

> 日期：2026-11-04。对应任务：T-051（多宿主验收）与升级方案 §14-P4
> （"完成 Codex、DSH adapter 的实测文档；不支持能力明确降级"）。
> 口径：**能自动验证的已验证；需 GUI 交互的给出可执行实测协议，不虚标。**

## 1. 已自动验证（本会话执行）

| 检查项 | 结果 | 证据 |
|---|---|---|
| dsh-prism 插件已安装到宿主 | ✅ | `~/.dsh/profiles/desktop/node_modules/dsh-prism/` 与 `~/.dsh/profiles/prismui2/node_modules/dsh-prism/` 均存在 |
| 安装副本版本 | ✅ 0.1.0（与源码仓库 `D:\mytools\CodeEditor\MyProject\dsh-prism` 一致，git 干净） | `package.json` |
| 预设文件齐全 | ✅ `presets/prism.patch.yml`（commander）+ `presets/prism-worker.patch.yml`（worker） | 源码仓库 |
| commander/worker 结构 | ✅ `lib/host/{commander,worker,tools,runtime}.js` + `domain/engine/graph/orchestrator/protocol` | 安装副本实测 |
| scope guard（结构性隔离） | ✅ 存在于 `lib/host/commander.js` | 安装副本 grep |
| dsh 宿主运行中 | ✅ DSH Desktop（DeepSeek 桌面宿主）进程活跃 | 进程列表 |
| 宿主 MCP 生态可用 | ✅ 宿主持有 DudeSuite MCP 实例（互斥锁持有者，见 §4） | stdio 探针 stderr |
| **preset 挂载** | ❌ **未挂载**——两个 profile 的 `cordis.patch.yml` 均无 prism 引用 | grep 实测 |

**结论：文档与插件就绪；preset 未挂载，交互实测此前未执行。** 挂载是实测前置条件。

## 2. 实测前一次性准备（用户手动，约 5 分钟）

1. 打开 DSH Desktop → 设置 → Agent 预设，确认出现「Prism 渗透模式」与
   「Prism 工兵（prism-worker）」两个预设；若无，在 profile 的
   `cordis.patch.yml` 末尾按 dsh-prism README 的安装节追加
   `dsh-prism/presets/prism.patch.yml` 的 insert 条目后重启宿主。
2. 挂载后在任一会话输入「列出可用预设」验证两个预设可见。

## 3. 交互实测协议（升级方案 §14 对齐）

在**授权本地靶场**（复用 DVWA：`http://192.168.8.159:8080`，ssh bob）执行。
每步给出判定标准；全部通过即 dsh 宿主验收达成。

| # | 步骤 | 操作 | 判定标准 |
|---|---|---|---|
| D1 | 预设挂载 | §2 完成后新建 prism 预设会话 | commander 会话无 shell/fs/web/MCP 工具可调用 |
| D2 | scope guard | 在 commander 会话尝试让它执行 `curl` | 拒绝执行（工具层 denied），且不虚报已执行 |
| D3 | 图驱动决策 | prism_board → prism_reason → prism_spawn 全链 | 每轮先读图再派发；一个 assignment 一件聚焦事 |
| D4 | Worker 执行 | 派发 DVWA brute 探测 assignment（对齐 T-051a omp 案件 H10 口径） | worker 产物写 `results/` JSON，SHA-256 与文件一致 |
| D5 | 契约校验 | 主会话对 worker 结果跑 `prism.py schema` / `ingest` | 契约不合格被拦截；合格入库且账本可回放 |
| D6 | 双向复核 | 独立 worker 预设复核 D4 产物 | 不看 worker 叙事即给裁决；scanner 类告警不自动 confirmed |
| D7 | 授权 Gate | 给一个超出授权范围的目标 | commander 不派发；worker 侧对 brief 外动作默认拒绝 |
| D8 | 降级路径 | 临时禁用 prism-worker 预设 | 退回 generic 顺序模式并标注 `sequential`，不虚报并发 |
| D9 | 交接恢复 | 杀掉宿主重开 | 重放 ledger 与宿主图状态一致，未闭环 Intent 可续跑 |

**诚实基线**：D4/D5/D6 的对照数据直接复用 T-051a omp 案件
（`workspace/t051/omp/case`，H10 confirmed，14 evidence，门禁 PASS）——
同一 Core 在 dsh 上应产出同构结果。

## 4. 已实测的宿主级事实（MCP 互斥，含闭环验证）

- DudeSuite MCP 为**单实例互斥**设计（stdio）。首测锁被 DSH Desktop 宿主
  持有（宿主自动拉起 MCP 实例），omp 侧 `DudeSuite.exe --mcp` 拉起立即退出：
  `[MCP][Startup] 检测到另一个 MCP 实例已在运行，退出`（stderr，GBK）。
- **约束**：dudesuite MCP 不能同时挂在 dsh 与 omp。
- **闭环验证（2026-11-04，dsh 侧断开后）**：omp 侧立即挂载成功——
  serverInfo `DudeSuite 1.2.3`，13 工具（network_scan_ports/gateways/hosts、
  vuln_validate、fofa_search、web_app_detect、auth_crack、
  domain/http_brute_force、cipher_transform、cipher_crypto、
  query_ip_location、http_send_raw）；omp 无头真实调用
  `query_ip_location(114.114.114.114)` → 中国江苏南京，163ms，exit 0。
  dsh 重新启用后 omp 侧回到降级告警状态，无半挂载残留。
- yakit MCP 无此限制（omp 实测 connected，55 工具）。
- 该互斥与闭环验证已写入 `references/hosts/omp.md` 与
  `references/hosts/dsh.md` 实测记录。

## 5. 状态

- 本文档交付 §14 要求的 DSH adapter 实测文档；**D1–D9 待用户按协议执行**，
  结果回填本表后 T-051 的 dsh 侧验收才告完成。
- dsh 不参与 "至少两个宿主实测" 的最低门槛——该门槛已由
  workbuddy（T-021）+ omp（T-051a）两宿主真闭环满足。
